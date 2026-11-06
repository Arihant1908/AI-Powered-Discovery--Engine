import os
import sys
import json
import time
import hashlib
import subprocess
from pathlib import Path
import httpx

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "audit" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

def save_json(name: str, status_code: int, body: any):
    out_path = RAW_DIR / f"{name}.json"
    payload = {
        "status_code": status_code,
        "body": body
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved: {out_path.name} (status {status_code})")

def get_body(resp: httpx.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text

def main():
    print("=== STARTING AUDIT DATA COLLECTION ===")
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # 1. /health
    r = client.get("/health")
    save_json("health", r.status_code, get_body(r))

    # 2. /api/meta
    r = client.get("/api/meta")
    meta_body = get_body(r)
    save_json("meta", r.status_code, meta_body)

    # Extract exact Variable income string from meta
    var_income_val = "Variable income (freelance/business)"
    if isinstance(meta_body, dict):
        allowed = meta_body.get("allowed_values", {})
        incomes = allowed.get("income_stability", [])
        for inc in incomes:
            if "variable" in inc.lower():
                var_income_val = inc
                break
    print(f"Variable income value from meta: {var_income_val}")

    # 3. /api/dashboard/summary
    r = client.get("/api/dashboard/summary")
    save_json("dashboard_summary", r.status_code, get_body(r))

    # 4. /api/dashboard/charts
    r = client.get("/api/dashboard/charts")
    save_json("dashboard_charts", r.status_code, get_body(r))

    # 5. /api/dashboard/charts with income_stability set to exact Variable income
    r = client.get("/api/dashboard/charts", params={"income_stability": var_income_val})
    save_json("dashboard_charts_variable_income", r.status_code, get_body(r))

    # 6. Filter that matches nothing
    r = client.get("/api/dashboard/charts", params={"source": "nonexistent_source_xyz"})
    save_json("dashboard_charts_empty_filter", r.status_code, get_body(r))

    # 7. /api/dashboard/unmet-needs
    r = client.get("/api/dashboard/unmet-needs")
    save_json("dashboard_unmet_needs", r.status_code, get_body(r))

    # 8. /api/dashboard/evidence?page=1&page_size=5
    r = client.get("/api/dashboard/evidence", params={"page": 1, "page_size": 5})
    save_json("dashboard_evidence_page1", r.status_code, get_body(r))

    # 9. /api/dashboard/evidence/SV-00001
    r = client.get("/api/dashboard/evidence/SV-00001")
    save_json("dashboard_evidence_sv00001", r.status_code, get_body(r))

    # 10. Unknown evidence id
    r = client.get("/api/dashboard/evidence/UNKNOWN-99999")
    save_json("dashboard_evidence_unknown", r.status_code, get_body(r))

    # 11. First 5 lines of /api/dashboard/export.csv
    r = client.get("/api/dashboard/export.csv")
    lines = r.text.strip().split("\n")
    first_5 = "\n".join(lines[:5])
    save_json("dashboard_export_first5", r.status_code, first_5)

    # 12. /api/insights?dataset=preloaded
    r = client.get("/api/insights", params={"dataset": "preloaded"})
    save_json("insights_preloaded", r.status_code, get_body(r))

    # 13. /api/template.csv
    r = client.get("/api/template.csv")
    save_json("template_csv", r.status_code, get_body(r))

    # 14. POST /api/upload/sample and poll to completion
    print("Initiating sample upload flow...")
    r_upload = client.post("/api/upload/sample")
    upload_init = get_body(r_upload)
    save_json("upload_sample_init", r_upload.status_code, upload_init)

    job_id = None
    if isinstance(upload_init, dict):
        job_id = upload_init.get("job_id")

    if job_id:
        poll_idx = 0
        while True:
            r_poll = client.get(f"/api/upload/{job_id}/status")
            poll_body = get_body(r_poll)
            save_json(f"upload_poll_{poll_idx}", r_poll.status_code, poll_body)
            poll_idx += 1
            state = poll_body.get("state") if isinstance(poll_body, dict) else None
            if state in ["done", "failed"]:
                break
            time.sleep(2.0)

        # Final rows
        r_rows = client.get(f"/api/upload/{job_id}/rows", params={"page": 1, "page_size": 100})
        save_json("upload_job_rows", r_rows.status_code, get_body(r_rows))

        # 16. One valid and one invalid PATCH on first row
        rows_data = get_body(r_rows)
        if isinstance(rows_data, dict) and rows_data.get("items"):
            row_id = rows_data["items"][0]["id"]
            # Valid PATCH
            r_patch_v = client.patch(
                f"/api/upload/{job_id}/rows/{row_id}",
                json={"main_driver": "Payment or mandate failure"}
            )
            save_json("patch_valid", r_patch_v.status_code, get_body(r_patch_v))

            # Invalid PATCH
            r_patch_iv = client.patch(
                f"/api/upload/{job_id}/rows/{row_id}",
                json={"main_driver": "Invalid Nonexistent Driver Name"}
            )
            save_json("patch_invalid", r_patch_iv.status_code, get_body(r_patch_iv))

        # 17. /api/insights for uploaded job
        r_up_ins = client.get("/api/insights", params={"dataset": job_id})
        save_json("insights_uploaded", r_up_ins.status_code, get_body(r_up_ins))

    # 15. Invalid uploads
    # a. Missing text column
    csv_missing_text = "id,source,date,rating\nERR-01,playstore,2026-10-01,5\n"
    r = client.post("/api/upload", files={"file": ("missing_text.csv", csv_missing_text.encode("utf-8"), "text/csv")})
    save_json("invalid_upload_missing_text", r.status_code, get_body(r))

    # b. Empty text value
    csv_empty_text = "id,source,date,rating,text\nEMP-01,playstore,2026-10-01,5,   \n"
    r = client.post("/api/upload", files={"file": ("empty_text.csv", csv_empty_text.encode("utf-8"), "text/csv")})
    save_json("invalid_upload_empty_text", r.status_code, get_body(r))

    # c. Duplicate ids
    csv_dup_ids = "id,source,date,rating,text\nDUP-01,playstore,2026-10-01,5,Text 1\nDUP-01,survey,2026-10-02,4,Text 2\n"
    r = client.post("/api/upload", files={"file": ("dup_ids.csv", csv_dup_ids.encode("utf-8"), "text/csv")})
    save_json("invalid_upload_duplicate_ids", r.status_code, get_body(r))

    # d. A .txt file
    r = client.post("/api/upload", files={"file": ("notes.txt", b"plain text content", "text/plain")})
    save_json("invalid_upload_txt_file", r.status_code, get_body(r))

    # e. CSV with 501 rows
    rows_501 = ["id,source,date,rating,text"] + [f"R-{i},playstore,2026-10-01,5,User comment {i}" for i in range(501)]
    csv_501 = "\n".join(rows_501)
    r = client.post("/api/upload", files={"file": ("rows_501.csv", csv_501.encode("utf-8"), "text/csv")})
    save_json("invalid_upload_501_rows", r.status_code, get_body(r))

    # 18. POST /api/insights/regenerate
    r = client.post("/api/insights/regenerate", params={"dataset": "preloaded"})
    save_json("insights_regenerate", r.status_code, get_body(r))

    # 19. Sizes and SHA-256 of every file in data/
    data_meta = []
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        data_dir = PROJECT_ROOT / "Data"
    for root, _, files in os.walk(data_dir):
        for f in sorted(files):
            p = Path(root) / f
            size = p.stat().st_size
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            data_meta.append({
                "file": rel,
                "size_bytes": size,
                "sha256": sha
            })
    save_json("data_files_metadata", 200, data_meta)

    # 20. Output of pytest -q
    print("Running pytest -q...")
    p = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
    save_json("pytest_output", 200, {
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr
    })

    print("=== AUDIT DATA COLLECTION COMPLETED ===")

if __name__ == "__main__":
    main()

