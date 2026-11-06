import sys
import time
import json
import httpx

BASE_URL = "http://127.0.0.1:8000"

CSV_DATA = (
    'id,text\n'
    'CASE1-01,"Bank mandate rejected due to signature mismatch on auto debit setup"\n'
    'CASE1-02,"Markets fell 5% this month, pausing my SIP until recovery"\n'
    'CASE1-03,"Urgent medical expense in family, had to stop the monthly investment"\n'
)

def run():
    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # 1. Upload CSV with only id, text
    files = {"file": ("case1_only_id_text.csv", CSV_DATA.encode("utf-8"), "text/csv")}
    upload_resp = client.post("/api/upload", files=files)
    if upload_resp.status_code != 200:
        print(f"UPLOAD FAILED: {upload_resp.status_code} - {upload_resp.text}")
        sys.exit(1)

    init_data = upload_resp.json()
    job_id = init_data["job_id"]
    print(f"Job ID: {job_id}")
    print(f"Data Warnings: {json.dumps(init_data.get('data_warnings', []))}")
    print(f"Missing Columns: {json.dumps(init_data.get('missing_columns', []))}")

    # 2. Check rows endpoint BEFORE job completion (flags rows requested before completion)
    early_rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=10")
    if early_rows_resp.status_code == 200:
        early_data = early_rows_resp.json()
        print(f"\n--- Early Rows Request Check ---")
        print(f"job_state: {early_data.get('job_state')}")
        print(f"is_complete: {early_data.get('is_complete')}")
        print(f"warning: {early_data.get('warning')}")

    # 3. Poll until state is done
    max_wait = 60
    start = time.time()
    final_status = None
    while time.time() - start < max_wait:
        st_resp = client.get(f"/api/upload/{job_id}/status")
        if st_resp.status_code == 200:
            st = st_resp.json()
            if st.get("state") in ("done", "failed"):
                final_status = st
                break
        time.sleep(1.0)

    if not final_status or final_status.get("state") != "done":
        print(f"JOB FAILED OR TIMED OUT: {final_status}")
        sys.exit(1)

    # 4. Fetch final rows
    rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=10")
    rows_data = rows_resp.json()

    print(f"\n--- Final Status ---")
    print(f"rows_tagged: {final_status.get('rows_tagged')}")
    print(f"fallback_count: {final_status.get('fallback_count')}")
    print(f"job_state: {rows_data.get('job_state')}")
    print(f"is_complete: {rows_data.get('is_complete')}")
    print(f"warning: {rows_data.get('warning')}")

    print(f"\n--- Tagged Rows ---")
    tagged_rows = rows_data.get("items", [])
    for idx, r in enumerate(tagged_rows, 1):
        print(f"Row {idx}: id={r.get('id')}, driver='{r.get('main_driver')}', outcome='{r.get('outcome')}', origin='{r.get('label_origin')}', text='{r.get('text')}'")

    # Diagnostic check
    fallback_cnt = final_status.get("fallback_count", 0)
    all_other = all(r.get("main_driver") == "Other" for r in tagged_rows)

    if fallback_cnt > 0:
        print(f"\n[DIAGNOSTIC] fallback_count is {fallback_cnt} > 0. Check API connectivity or logs.")
    if all_other:
        print(f"\n[DIAGNOSTIC] Every row was tagged as 'Other'.")

if __name__ == "__main__":
    run()
