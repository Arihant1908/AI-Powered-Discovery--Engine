"""
Live upload verification script.
Run this script while the server is active on http://127.0.0.1:8000:
    python scripts/verify_live_upload.py
"""
import time
import httpx

def main():
    client = httpx.Client(base_url="http://127.0.0.1:8000")

    # 1. Test GET /upload HTML
    r_upload = client.get("/upload")
    assert r_upload.status_code == 200
    assert "Upload Investor Feedback" in r_upload.text
    assert 'id="dropZone"' in r_upload.text
    assert 'id="btnSampleData"' in r_upload.text
    assert "ID-00101" not in r_upload.text  # Rule 1
    print("[PASS] GET /upload serves clean template adhering to Rule 1")

    # 2. Test GET /static/upload.js
    r_js = client.get("/static/upload.js")
    assert r_js.status_code == 200
    print("[PASS] GET /static/upload.js serves correctly")

    # 3. Test Sample Data Upload
    r_sample = client.post("/api/upload/sample")
    assert r_sample.status_code == 200
    job_id = r_sample.json()["job_id"]
    total = r_sample.json()["total"]
    print(f"[PASS] POST /api/upload/sample started job: {job_id} with {total} items")

    # 4. Poll status until done
    for _ in range(20):
        r_stat = client.get(f"/api/upload/{job_id}/status")
        assert r_stat.status_code == 200
        st = r_stat.json()
        if st["state"] == "done":
            print(f"[PASS] Status reached done: {st['rows_tagged']}/{st['total']} tagged (fallbacks: {st['fallback_count']})")
            break
        time.sleep(0.3)
    else:
        raise AssertionError("Job did not complete in time")

    # 5. Fetch rows
    r_rows = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
    assert r_rows.status_code == 200
    rows = r_rows.json()["items"]
    assert len(rows) == 5
    print(f"[PASS] GET /api/upload/{job_id}/rows returned {len(rows)} rows (first ID: {rows[0]['id']})")

    # 6. Test PATCH editing a row
    test_row_id = rows[0]["id"]
    r_patch = client.patch(f"/api/upload/{job_id}/rows/{test_row_id}", json={"main_driver": "Cash crunch"})
    assert r_patch.status_code == 200
    assert r_patch.json()["main_driver"] == "Cash crunch"
    print(f"[PASS] PATCH label update successfully saved for row {test_row_id}")

    # 7. Test deliberately broken CSV (missing required column 'text')
    broken_csv = "id,source,date,rating\nBRK-01,playstore,2026-10-01,5\n"
    r_broken1 = client.post("/api/upload", files={"file": ("broken.csv", broken_csv.encode(), "text/csv")})
    assert r_broken1.status_code == 400
    assert "Missing required columns" in r_broken1.json()["error"]["message"]
    print(f"[PASS] Missing column rejected: {r_broken1.json()['error']['message']}")

    # 8. Test deliberately broken CSV (duplicate ID)
    broken_csv_dup = "id,source,date,rating,text\nID-DUP,playstore,2026-10-01,5,text1\nID-DUP,playstore,2026-10-02,4,text2\n"
    r_broken2 = client.post("/api/upload", files={"file": ("dup.csv", broken_csv_dup.encode(), "text/csv")})
    assert r_broken2.status_code == 400
    assert "Duplicate ID" in r_broken2.json()["error"]["message"]
    print(f"[PASS] Duplicate ID rejected: {r_broken2.json()['error']['message']}")

    # 9. Test deliberately broken CSV (empty text)
    broken_csv_empty = "id,source,date,rating,text\nID-EMPTY,playstore,2026-10-01,5,   \n"
    r_broken3 = client.post("/api/upload", files={"file": ("empty.csv", broken_csv_empty.encode(), "text/csv")})
    assert r_broken3.status_code == 400
    assert "Empty text" in r_broken3.json()["error"]["message"]
    print(f"[PASS] Empty text rejected: {r_broken3.json()['error']['message']}")

    # 10. Test download template
    r_tpl = client.get("/api/template.csv")
    assert r_tpl.status_code == 200
    assert "SAMPLE-0001" in r_tpl.text
    print("[PASS] GET /api/template.csv returned valid CSV template")

    print("\n--- ALL LIVE VERIFICATIONS PASSED ---")

if __name__ == "__main__":
    main()

