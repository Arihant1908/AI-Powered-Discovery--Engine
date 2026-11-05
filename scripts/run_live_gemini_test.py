import os
import sys
import time
import json
from pathlib import Path
from starlette.testclient import TestClient

# Ensure MOCK_LLM is disabled
os.environ["MOCK_LLM"] = "0"

from app.main import app
from app.config import settings
from app.services.job_manager import job_manager
from app.services.insights import insights_service, get_dataset_records, compute_dataset_stats

def main():
    print(f"=== 1. VERIFY CONFIGURATION ===")
    print(f"MOCK_LLM: {settings.MOCK_LLM}")
    print(f"GEMINI_MODEL: {settings.GEMINI_MODEL}")
    print(f"API Key configured: {bool(settings.GEMINI_API_KEY)}")
    assert not settings.MOCK_LLM, "MOCK_LLM must be False for live test"
    assert settings.GEMINI_API_KEY, "GEMINI_API_KEY must be set"

    client = TestClient(app)

    # 1. Upload data/sample_upload.csv through the real upload flow
    csv_path = settings.DATA_DIR / "sample_upload.csv"
    assert csv_path.exists(), f"File {csv_path} does not exist"

    print("\n=== 2. UPLOADING SAMPLE_UPLOAD.CSV ===")
    start_time = time.time()
    with open(csv_path, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("sample_upload.csv", f, "text/csv")}
        )
    assert response.status_code == 200, f"Upload failed: {response.text}"
    job_info = response.json()
    job_id = job_info["job_id"]
    print(f"Upload initiated. Job ID: {job_id}")

    # If background tasks run asynchronously or synchronously, wait if needed
    job = job_manager.get_job(job_id)
    while job and job.get("state") == "running":
        time.sleep(0.5)
        job = job_manager.get_job(job_id)

    total_time = time.time() - start_time
    print(f"Total time taken: {total_time:.2f} seconds")

    # 2. Status & Fallbacks
    status_resp = client.get(f"/api/upload/{job_id}/status")
    status_data = status_resp.json()
    rows_tagged = status_data["rows_tagged"]
    total_rows = status_data["total"]
    fallback_count = status_data["fallback_count"]
    state = status_data["state"]

    fallback_pct = (fallback_count / total_rows * 100) if total_rows > 0 else 0.0

    print("\n=== 3. UPLOAD RESULTS ===")
    print(f"State: {state}")
    print(f"Total rows: {total_rows}")
    print(f"Rows tagged: {rows_tagged}")
    print(f"Fallback count: {fallback_count} ({fallback_pct:.1f}%)")
    print(f"Total time: {total_time:.2f}s")
    if status_data.get("error_message"):
        print(f"Error message: {status_data['error_message']}")

    assert fallback_pct <= 10.0, f"Fallbacks exceeded 10%: {fallback_pct:.1f}% ({fallback_count}/{total_rows})"

    # 3. Show 10 tagged rows (id, text preview, main_driver, outcome)
    print("\n=== 4. 10 TAGGED ROWS PREVIEW ===")
    rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=10")
    rows_data = rows_resp.json().get("items", [])
    for idx, r in enumerate(rows_data[:10], start=1):
        clean_text = r["text"].replace("\n", " ")[:60]
        print(f"[{idx:02d}] ID: {r['id']} | Driver: {r['main_driver']} | Outcome: {r['outcome']} | Text: \"{clean_text}...\"")

    # 4. Generate insights for pre-loaded dataset
    print("\n=== 5. GENERATING INSIGHTS FOR PRELOADED DATASET ===")
    t_ins_pre = time.time()
    preloaded_insights = insights_service.get_insights("preloaded", force_regenerate=True)
    t_ins_pre_elapsed = time.time() - t_ins_pre
    print(f"Preloaded insights generated in {t_ins_pre_elapsed:.2f}s.")
    print(f"AI Summary Available: {preloaded_insights.ai_summary_available}")
    assert preloaded_insights.ai_summary_available, "AI summary should be available"
    assert len(preloaded_insights.cards) == 3, f"Expected 3 cards, got {len(preloaded_insights.cards)}"

    pre_records = get_dataset_records("preloaded")
    pre_ids = {r.id for r in pre_records}
    pre_stats = compute_dataset_stats(pre_records)

    print("\nPreloaded Cards:")
    for i, c in enumerate(preloaded_insights.cards, 1):
        print(f"\n--- Card {i}: {c.headline} ({c.strength_label}) ---")
        print(f"Explanation: {c.explanation}")
        print(f"Action: {c.proposed_pm_action}")
        print(f"Supporting IDs ({c.supporting_count}): {c.supporting_evidence_ids}")
        # Verify IDs exist
        for cid in c.supporting_evidence_ids:
            assert cid in pre_ids, f"Cited ID {cid} not in preloaded dataset!"

    print("\nPreloaded Suggested Questions:")
    for q in preloaded_insights.suggested_questions:
        print(f"- {q}")

    # Generate insights for uploaded job
    print("\n=== 6. GENERATING INSIGHTS FOR UPLOADED DATASET ===")
    t_ins_job = time.time()
    job_insights = insights_service.get_insights(job_id, force_regenerate=True)
    t_ins_job_elapsed = time.time() - t_ins_job
    print(f"Job insights generated in {t_ins_job_elapsed:.2f}s.")
    print(f"Job AI Summary Available: {job_insights.ai_summary_available}")
    assert job_insights.ai_summary_available, "Job AI summary should be available"
    assert len(job_insights.cards) == 3, f"Expected 3 cards, got {len(job_insights.cards)}"

    job_records = get_dataset_records(job_id)
    job_ids = {r.id for r in job_records}
    job_stats = compute_dataset_stats(job_records)

    print("\nJob Cards:")
    for i, c in enumerate(job_insights.cards, 1):
        print(f"\n--- Card {i}: {c.headline} ({c.strength_label}) ---")
        print(f"Explanation: {c.explanation}")
        print(f"Action: {c.proposed_pm_action}")
        print(f"Supporting IDs ({c.supporting_count}): {c.supporting_evidence_ids}")
        # Verify IDs exist
        for cid in c.supporting_evidence_ids:
            assert cid in job_ids, f"Cited ID {cid} not in uploaded dataset!"

    print("\nJob Suggested Questions:")
    for q in job_insights.suggested_questions:
        print(f"- {q}")

    print("\n=== ALL LIVE CHECKS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
