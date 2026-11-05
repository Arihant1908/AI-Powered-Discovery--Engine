"""
Live Insights verification script:
Tests GET /insights and API endpoints with dataset=preloaded and with a finished upload job.
"""
import time
import httpx

def main():
    client = httpx.Client(base_url="http://127.0.0.1:8000")

    # 1. Test GET /insights HTML (preloaded)
    r_page = client.get("/insights?dataset=preloaded")
    assert r_page.status_code == 200
    assert "AI insight summary" in r_page.text
    assert 'id="btnRegenerate"' in r_page.text
    assert 'id="cardsContainer"' in r_page.text
    assert "Small sample. Treat as patterns, not proof." in r_page.text
    assert "ID-00101" not in r_page.text  # Rule 1
    print("[PASS] GET /insights?dataset=preloaded serves valid HTML adhering to Rule 1")

    # 2. Test GET /static/insights.js
    r_js = client.get("/static/insights.js")
    assert r_js.status_code == 200
    print("[PASS] GET /static/insights.js serves correctly")

    # 3. Test API GET /api/insights?dataset=preloaded
    r_api = client.get("/api/insights?dataset=preloaded")
    assert r_api.status_code == 200
    data_pre = r_api.json()
    assert data_pre["dataset"] == "preloaded"
    assert data_pre["total_records"] == 54
    assert len(data_pre["segment_view"]) == 4
    print(f"[PASS] Preloaded insights loaded: {data_pre['total_records']} records, {len(data_pre['segment_view'])} segment rows")

    # 4. Test Regenerate API
    r_regen = client.post("/api/insights/regenerate?dataset=preloaded")
    assert r_regen.status_code == 200
    data_regen = r_regen.json()
    assert data_regen["cached"] is False
    print("[PASS] POST /api/insights/regenerate refreshed and uncached insights successfully")

    # 5. Test Finished Upload Job Flow
    print("\nStarting upload job test...")
    r_sample = client.post("/api/upload/sample")
    assert r_sample.status_code == 200
    job_id = r_sample.json()["job_id"]
    total = r_sample.json()["total"]
    print(f"[PASS] Sample upload job created: {job_id} ({total} rows)")

    # Poll status until done
    for _ in range(20):
        r_stat = client.get(f"/api/upload/{job_id}/status")
        assert r_stat.status_code == 200
        if r_stat.json()["state"] == "done":
            print(f"[PASS] Job {job_id} reached 'done'")
            break
        time.sleep(0.3)
    else:
        raise AssertionError("Job did not finish in time")

    # Load Insights for finished upload job
    r_job_page = client.get(f"/insights?dataset={job_id}")
    assert r_job_page.status_code == 200
    print(f"[PASS] GET /insights?dataset={job_id} loaded successfully")

    r_job_api = client.post(f"/api/insights/regenerate?dataset={job_id}")
    assert r_job_api.status_code == 200
    job_insights = r_job_api.json()
    assert job_insights["dataset"] == job_id
    assert job_insights["total_records"] == total
    assert len(job_insights["segment_view"]) == 4
    print(f"[PASS] Job insights computed for {job_id}: {total} rows, {len(job_insights['segment_view'])} segment groups")

    # Test evidence chip lookup for this job
    if job_insights["cards"]:
        chip_id = job_insights["cards"][0]["supporting_evidence_ids"][0]
        r_chip = client.get(f"/api/dashboard/evidence/{chip_id}?dataset={job_id}")
        assert r_chip.status_code == 200
        assert r_chip.json()["id"] == chip_id
        print(f"[PASS] Evidence chip {chip_id} lookup verified for upload job")

    print("\n--- ALL LIVE INSIGHTS VERIFICATIONS PASSED ---")

if __name__ == "__main__":
    main()

