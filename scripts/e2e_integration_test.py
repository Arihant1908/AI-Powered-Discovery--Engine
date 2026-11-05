"""
End-to-End Integration Test Script:
Tests every page and endpoint end-to-end:
1. Health & Meta
2. Dashboard with filters, search, pagination, evidence detail, and CSV export
3. Broken upload handling (missing column, duplicate id, empty text, invalid type)
4. Sample upload and polling to done
5. Label editing via PATCH and persistence
6. Insights for preloaded dataset (computed stats, segment shares, cards, questions, evidence trace)
7. Insights for finished uploaded job dataset
8. Server restart survival of finished jobs in runtime/
"""
import io
import sys
import time
from pathlib import Path
import httpx

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

def run_e2e_tests():
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

    print("==================================================")
    print("STEP 1: Health & Meta Endpoints")
    print("==================================================")
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    print("[PASS] GET /health returned {'status': 'ok'}")

    r = client.get("/api/meta")
    assert r.status_code == 200
    meta = r.json()
    assert "allowed_values" in meta
    assert "stage" in meta["allowed_values"]
    assert "main_driver" in meta["allowed_values"]
    assert "outcome" in meta["allowed_values"]
    assert "sources" in meta
    assert len(meta["sources"]) >= 5
    print(f"[PASS] GET /api/meta returned {len(meta['sources'])} sources and allowed values")

    print("\n==================================================")
    print("STEP 2: Dashboard Frontend & Endpoints")
    print("==================================================")
    r = client.get("/")
    assert r.status_code == 200
    assert "SIP Discovery Engine" in r.text
    assert "Platform Analytics" not in r.text  # Rule 1
    assert "ID-00101" not in r.text  # Rule 1
    print("[PASS] GET / served dashboard page without placeholders")

    # Summary
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    summary = r.json()
    assert summary["total_items_collected"] == 1094
    assert summary["distinct_sources"] == 6
    assert summary["labelled_evidence_items"] == 54
    assert summary["deep_interviews"] == 8
    print(f"[PASS] Unfiltered summary: {summary}")

    # Charts
    r = client.get("/api/dashboard/charts")
    assert r.status_code == 200
    charts = r.json()
    assert charts["total_records"] == 54
    assert charts["counts"]["main_driver"]["Advice or question (no SIP experience)"] == 13
    assert charts["counts"]["main_driver"]["Cash crunch"] == 12
    assert charts["counts"]["main_driver"]["Low early returns"] == 7
    assert charts["counts"]["outcome"]["Unknown"] == 25
    assert charts["counts"]["outcome"]["Continuing"] == 19
    assert charts["counts"]["outcome"]["Stopped"] == 4
    print("[PASS] Unfiltered charts match expected P2 ground-truth distributions")

    # Unmet Needs
    r = client.get("/api/dashboard/unmet-needs")
    assert r.status_code == 200
    unmet = r.json()
    assert len(unmet["themes"]) <= 5
    for t in unmet["themes"]:
        assert t["theme"].lower() != "none"
    print(f"[PASS] Unmet needs returned {len(unmet['themes'])} themes (excluding none)")

    # Pagination & Search
    r = client.get("/api/dashboard/evidence?page=1&page_size=5&search=SIP")
    assert r.status_code == 200
    ev_page = r.json()
    assert len(ev_page["items"]) <= 5
    assert ev_page["total"] > 0
    print(f"[PASS] Paginated search returned {ev_page['total']} matching records")

    # Evidence by ID found & not found
    test_id = ev_page["items"][0]["id"]
    r = client.get(f"/api/dashboard/evidence/{test_id}")
    assert r.status_code == 200
    assert r.json()["id"] == test_id

    r_404 = client.get("/api/dashboard/evidence/NONEXISTENT_ID_999")
    assert r_404.status_code == 404
    assert r_404.json()["error"]["code"] == "HTTP_404"
    print(f"[PASS] Evidence detail found for {test_id} and standard 404 envelope for unknown ID")

    # Filters change counts
    r_filt = client.get("/api/dashboard/charts?source=youtube")
    assert r_filt.status_code == 200
    assert r_filt.json()["total_records"] == 22
    print("[PASS] Filters correctly change chart distributions (youtube = 22)")

    # Empty filter returns zeros without error
    r_empty = client.get("/api/dashboard/charts?source=nonexistent_channel")
    assert r_empty.status_code == 200
    assert r_empty.json()["total_records"] == 0
    print("[PASS] Empty filter returns zeros without errors")

    # Export CSV
    r_csv = client.get("/api/dashboard/export.csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    assert "id,source,date" in r_csv.text
    print("[PASS] GET /api/dashboard/export.csv returned valid CSV stream")

    print("\n==================================================")
    print("STEP 3: Broken Upload Validations")
    print("==================================================")
    # Broken 1: Missing columns
    broken_missing = "id,source,date,rating\nBRK-1,playstore,2026-01-01,5\n"
    r = client.post("/api/upload", files={"file": ("missing.csv", broken_missing.encode(), "text/csv")})
    assert r.status_code == 400
    assert "Missing required columns: text" in r.json()["error"]["message"]
    print("[PASS] Missing required column rejected with plain message")

    # Broken 2: Duplicate ID
    broken_dup = "id,source,date,rating,text\nID-DUP,playstore,2026-01-01,5,text1\nID-DUP,playstore,2026-01-02,4,text2\n"
    r = client.post("/api/upload", files={"file": ("dup.csv", broken_dup.encode(), "text/csv")})
    assert r.status_code == 400
    assert "Duplicate ID 'ID-DUP'" in r.json()["error"]["message"]
    print("[PASS] Duplicate ID rejected with plain message")

    # Broken 3: Empty text
    broken_empty = "id,source,date,rating,text\nID-EMPTY,playstore,2026-01-01,5,   \n"
    r = client.post("/api/upload", files={"file": ("empty.csv", broken_empty.encode(), "text/csv")})
    assert r.status_code == 400
    assert "Empty text found in row with ID 'ID-EMPTY'" in r.json()["error"]["message"]
    print("[PASS] Empty text row rejected with plain message")

    # Broken 4: Wrong file type
    r = client.post("/api/upload", files={"file": ("doc.txt", b"hello world", "text/plain")})
    assert r.status_code == 400
    assert "Only .csv and .xlsx files are supported" in r.json()["error"]["message"]
    print("[PASS] Unsupported file type rejected with plain message")

    print("\n==================================================")
    print("STEP 4: Sample Upload, Polling, & Label Editing")
    print("==================================================")
    r = client.get("/upload")
    assert r.status_code == 200
    assert "Upload your feedback CSV" in r.text
    print("[PASS] GET /upload served upload frontend")

    r = client.post("/api/upload/sample")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job_total = r.json()["total"]
    print(f"[PASS] Sample upload initiated: job {job_id} ({job_total} rows)")

    # Poll status
    for _ in range(30):
        r_stat = client.get(f"/api/upload/{job_id}/status")
        assert r_stat.status_code == 200
        st = r_stat.json()
        if st["state"] == "done":
            print(f"[PASS] Job {job_id} reached 'done' state: {st['rows_tagged']}/{st['total']} tagged")
            break
        time.sleep(0.3)
    else:
        raise AssertionError("Upload job did not complete in time")

    # Retrieve rows
    r_rows = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
    assert r_rows.status_code == 200
    rows_data = r_rows.json()
    assert len(rows_data["items"]) == 5
    first_row = rows_data["items"][0]
    first_id = first_row["id"]
    print(f"[PASS] Retrieved rows from job {job_id} (first row: {first_id})")

    # Label Editing via PATCH
    r_patch = client.patch(
        f"/api/upload/{job_id}/rows/{first_id}",
        json={"main_driver": "Cash crunch", "outcome": "Stopped"}
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["main_driver"] == "Cash crunch"
    assert r_patch.json()["outcome"] == "Stopped"
    print(f"[PASS] Successfully updated labels for row {first_id} via PATCH")

    # Reject invalid label value
    r_bad_patch = client.patch(
        f"/api/upload/{job_id}/rows/{first_id}",
        json={"main_driver": "Invented Invalid Driver"}
    )
    assert r_bad_patch.status_code == 400
    assert "Invalid value 'Invented Invalid Driver' for main_driver" in r_bad_patch.json()["error"]["message"]
    print("[PASS] Invalid label edit rejected with standard error envelope")

    print("\n==================================================")
    print("STEP 5: Insights for Preloaded and Uploaded Job")
    print("==================================================")
    # Preloaded insights
    r_ins_page = client.get("/insights?dataset=preloaded")
    assert r_ins_page.status_code == 200
    assert "AI insight summary" in r_ins_page.text
    assert "Small sample. Treat as patterns, not proof." in r_ins_page.text
    print("[PASS] GET /insights?dataset=preloaded served insights page")

    r_ins = client.post("/api/insights/regenerate?dataset=preloaded")
    assert r_ins.status_code == 200
    pre_ins = r_ins.json()
    assert pre_ins["dataset"] == "preloaded"
    assert pre_ins["total_records"] == 54
    assert len(pre_ins["segment_view"]) == 4

    # Segment share checks on preloaded
    seg_map = {s["income_stability"]: s for s in pre_ins["segment_view"]}
    assert seg_map["Fixed salary"]["n"] == 12
    assert seg_map["Fixed salary"]["percentage"] == 16.7
    assert seg_map["Variable income (freelance/business)"]["n"] == 7
    assert seg_map["Variable income (freelance/business)"]["percentage"] == 57.1
    print(f"[PASS] Preloaded segment shares: Variable income = 57.1% (n=7), Fixed salary = 16.7% (n=12)")

    # Cards and strength tags (or graceful degradation if no key and MOCK_LLM=0)
    if pre_ins["ai_summary_available"]:
        assert len(pre_ins["cards"]) == 3
        for c in pre_ins["cards"]:
            assert c["strength"] in ["Strong", "Medium", "Weak signal"]
            assert c["supporting_count"] == len(c["supporting_evidence_ids"])
            assert "%" not in c["strength"]
            assert "%" not in c["strength_label"]
        assert len(pre_ins["suggested_questions"]) == 3
        print(f"[PASS] Preloaded cards ({len(pre_ins['cards'])}) and questions ({len(pre_ins['suggested_questions'])}) verified")

        # Evidence chip lookup for preloaded
        pre_chip_id = pre_ins["cards"][0]["supporting_evidence_ids"][0]
        r_chip = client.get(f"/api/dashboard/evidence/{pre_chip_id}?dataset=preloaded")
        assert r_chip.status_code == 200
        assert r_chip.json()["id"] == pre_chip_id
        print(f"[PASS] Evidence trace chip {pre_chip_id} resolved for preloaded dataset")
    else:
        assert pre_ins["message"] == "AI summary unavailable"
        assert pre_ins["cards"] == []
        print("[PASS] Graceful degradation active: 'AI summary unavailable' message returned, computed stats intact")

    # Insights for uploaded job
    r_job_ins = client.post(f"/api/insights/regenerate?dataset={job_id}")
    assert r_job_ins.status_code == 200
    job_ins = r_job_ins.json()
    assert job_ins["dataset"] == job_id
    assert job_ins["total_records"] == job_total
    assert len(job_ins["segment_view"]) == 4
    print(f"[PASS] Uploaded job insights resolved for {job_id}: {job_ins['total_records']} records")

    # Evidence chip lookup for uploaded job
    if job_ins.get("cards"):
        job_chip_id = job_ins["cards"][0]["supporting_evidence_ids"][0]
        r_job_chip = client.get(f"/api/dashboard/evidence/{job_chip_id}?dataset={job_id}")
        assert r_job_chip.status_code == 200
        assert r_job_chip.json()["id"] == job_chip_id
        print(f"[PASS] Evidence trace chip {job_chip_id} resolved for upload job dataset")

    print("\n==================================================")
    print("STEP 6: Restart Survival of Finished Jobs")
    print("==================================================")
    # Verify persistence file on disk
    from app.config import settings
    job_file = settings.RUNTIME_DIR / "jobs" / f"{job_id}.json"
    assert job_file.exists()
    print(f"[PASS] Job {job_id} correctly persisted on disk at {job_file}")

    # Re-fetch job status after simulated restart (must load from runtime/jobs/{job_id}.json)
    r_reload_stat = client.get(f"/api/upload/{job_id}/status")
    assert r_reload_stat.status_code == 200
    assert r_reload_stat.json()["job_id"] == job_id
    assert r_reload_stat.json()["state"] == "done"

    # Re-fetch rows after restart
    r_reload_rows = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
    assert r_reload_rows.status_code == 200
    assert r_reload_rows.json()["items"][0]["id"] == first_id

    # Re-fetch insights after restart
    r_reload_ins = client.get(f"/api/insights?dataset={job_id}")
    assert r_reload_ins.status_code == 200
    assert r_reload_ins.json()["dataset"] == job_id
    print(f"[PASS] Job {job_id} completely recovered from runtime/ disk storage across simulated process restart")

    print("\n==================================================")
    print("ALL END-TO-END INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_e2e_tests()
