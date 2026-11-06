import os
import sys
import json
import time
from pathlib import Path
import httpx

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = PROJECT_ROOT / "audit" / "raw_upload_columns.json"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# 3-row CSV test cases
CASES = {
    "case_1_id_text_only": {
        "filename": "case1_id_text.csv",
        "csv": (
            'id,text\n'
            'C1-01,"Bank mandate rejected due to signature mismatch on auto debit setup"\n'
            'C1-02,"Markets fell 5% this month, pausing my SIP until recovery"\n'
            'C1-03,"Urgent medical expense in family, had to stop the monthly investment"\n'
        ),
        "track_completion": True
    },
    "case_2_id_text_rating": {
        "filename": "case2_id_text_rating.csv",
        "csv": (
            'id,text,rating\n'
            'C2-01,"Bank mandate rejected due to signature mismatch on auto debit setup",2\n'
            'C2-02,"Markets fell 5% this month, pausing my SIP until recovery",3\n'
            'C2-03,"Urgent medical expense in family, had to stop the monthly investment",1\n'
        ),
        "track_completion": True
    },
    "case_3_full_columns": {
        "filename": "case3_full.csv",
        "csv": (
            'id,source,date,rating,text\n'
            'C3-01,playstore,2026-10-15,2,"Bank mandate rejected due to signature mismatch on auto debit setup"\n'
            'C3-02,appstore,2026-10-16,3,"Markets fell 5% this month, pausing my SIP until recovery"\n'
            'C3-03,survey,2026-10-17,1,"Urgent medical expense in family, had to stop the monthly investment"\n'
        ),
        "track_completion": True
    },
    "case_4_missing_id": {
        "filename": "case4_missing_id.csv",
        "csv": (
            'source,date,rating,text\n'
            'playstore,2026-10-15,2,"Bank mandate rejected due to signature mismatch on auto debit setup"\n'
            'appstore,2026-10-16,3,"Markets fell 5% this month, pausing my SIP until recovery"\n'
            'survey,2026-10-17,1,"Urgent medical expense in family, had to stop the monthly investment"\n'
        ),
        "track_completion": False
    },
    "case_5_missing_text": {
        "filename": "case5_missing_text.csv",
        "csv": (
            'id,source,date,rating\n'
            'C5-01,playstore,2026-10-15,2\n'
            'C5-02,appstore,2026-10-16,3\n'
            'C5-03,survey,2026-10-17,1\n'
        ),
        "track_completion": False
    },
    "case_6_extra_foo_column": {
        "filename": "case6_extra_foo.csv",
        "csv": (
            'id,text,foo\n'
            'C6-01,"Bank mandate rejected due to signature mismatch on auto debit setup",extra_value_1\n'
            'C6-02,"Markets fell 5% this month, pausing my SIP until recovery",extra_value_2\n'
            'C6-03,"Urgent medical expense in family, had to stop the monthly investment",extra_value_3\n'
        ),
        "track_completion": True
    },
    "case_7_empty_source_value": {
        "filename": "case7_empty_source.csv",
        "csv": (
            'id,source,date,rating,text\n'
            'C7-01,playstore,2026-10-15,2,"Bank mandate rejected due to signature mismatch on auto debit setup"\n'
            'C7-02,,2026-10-16,3,"Markets fell 5% this month, pausing my SIP until recovery"\n'
            'C7-03,survey,2026-10-17,1,"Urgent medical expense in family, had to stop the monthly investment"\n'
        ),
        "track_completion": True
    }
}

def main():
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)
    results = {}

    for case_key, case_info in CASES.items():
        fname = case_info["filename"]
        csv_bytes = case_info["csv"].encode("utf-8")
        track = case_info["track_completion"]

        # POST /api/upload
        r_upload = client.post(
            "/api/upload",
            files={"file": (fname, csv_bytes, "text/csv")}
        )
        try:
            body = r_upload.json()
        except Exception:
            body = r_upload.text

        case_result = {
            "upload_response": {
                "status_code": r_upload.status_code,
                "body": body
            }
        }

        # If job created and track requested (or if case 4 also created job)
        job_id = body.get("job_id") if isinstance(body, dict) else None

        if track and job_id:
            # Poll status
            polls = []
            while True:
                r_status = client.get(f"/api/upload/{job_id}/status")
                try:
                    s_body = r_status.json()
                except Exception:
                    s_body = r_status.text
                polls.append({
                    "status_code": r_status.status_code,
                    "body": s_body
                })
                state = s_body.get("state") if isinstance(s_body, dict) else None
                if state in ["done", "failed"]:
                    break
                time.sleep(1.5)

            case_result["poll_timeline"] = polls

            # Fetch rows
            r_rows = client.get(f"/api/upload/{job_id}/rows", params={"page": 1, "page_size": 50})
            try:
                rows_body = r_rows.json()
            except Exception:
                rows_body = r_rows.text
            case_result["rows_response"] = {
                "status_code": r_rows.status_code,
                "body": rows_body
            }

            # Extract source, date, rating per row
            extracted_rows = []
            if isinstance(rows_body, dict) and "items" in rows_body:
                for item in rows_body["items"]:
                    extracted_rows.append({
                        "id": item.get("id"),
                        "source": item.get("source"),
                        "date": item.get("date"),
                        "rating": item.get("rating"),
                        "text": item.get("text"),
                        "main_driver": item.get("main_driver"),
                        "outcome": item.get("outcome")
                    })
            case_result["extracted_row_fields"] = extracted_rows

            # Fetch insights
            r_ins = client.get("/api/insights", params={"dataset": job_id})
            try:
                ins_body = r_ins.json()
            except Exception:
                ins_body = r_ins.text
            case_result["insights_response"] = {
                "status_code": r_ins.status_code,
                "body": ins_body
            }

            # Extract data_warnings, missing_columns, main_driver_counts
            if isinstance(ins_body, dict):
                case_result["data_warnings"] = ins_body.get("data_warnings", [])
                computed = ins_body.get("computed_stats", {})
                case_result["main_driver_counts"] = computed.get("main_driver_counts", {})
            else:
                case_result["data_warnings"] = []
                case_result["main_driver_counts"] = {}

            if isinstance(body, dict):
                case_result["missing_columns"] = body.get("missing_columns", [])
                if not case_result["data_warnings"]:
                    case_result["data_warnings"] = body.get("data_warnings", [])

        results[case_key] = case_result

    # Save to audit/raw_upload_columns.json
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Print file contents unchanged
    with open(OUT_FILE, "r", encoding="utf-8") as f:
        print(f.read())

if __name__ == "__main__":
    main()

