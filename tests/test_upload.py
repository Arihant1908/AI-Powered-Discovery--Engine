import io
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.data_store import get_corpus_row_count, get_all_tagged_records
from app.services.job_manager import job_manager

client = TestClient(app)

def test_download_template_csv():
    response = client.get("/api/template.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    assert len(lines) == 2
    assert lines[0] == "id,source,date,rating,text"
    assert "SAMPLE-0001" in lines[1]
    assert "Invented sample text for upload template" in lines[1]

def test_valid_csv_upload_and_progress_reaching_done():
    csv_content = (
        "id,source,date,rating,text\n"
        "UP-001,playstore,2026-10-01,5,Love the app and automated SIP payments\n"
        "UP-002,playstore,2026-10-02,1,Returns look low after first month thinking of stopping\n"
        "UP-003,survey,2026-10-03,,Needed to pause SIP due to sudden emergency expenses\n"
    )

    file_obj = io.BytesIO(csv_content.encode("utf-8"))
    response = client.post(
        "/api/upload",
        files={"file": ("test_upload.csv", file_obj, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["total"] == 3
    job_id = data["job_id"]

    # Verify status progresses to done
    status_resp = client.get(f"/api/upload/{job_id}/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["job_id"] == job_id
    assert status["total"] == 3
    assert status["state"] in ["running", "done"]

    # In TestClient, background tasks execute synchronously before response returns
    assert status["state"] == "done"
    assert status["rows_tagged"] == 3

    # Check rows pagination
    rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=2")
    assert rows_resp.status_code == 200
    rows_data = rows_resp.json()
    assert rows_data["total"] == 3
    assert len(rows_data["items"]) == 2
    assert rows_data["total_pages"] == 2
    assert rows_data["items"][0]["id"] == "UP-001"
    assert rows_data["items"][1]["id"] == "UP-002"

def test_valid_xlsx_upload():
    import pandas as pd
    df = pd.DataFrame([
        {"id": "XLSX-01", "source": "playstore", "date": "2026-10-01", "rating": 5, "text": "Excel test item 1"},
        {"id": "XLSX-02", "source": "survey", "date": "2026-10-02", "rating": 4, "text": "Excel test item 2"},
    ])
    xlsx_io = io.BytesIO()
    df.to_excel(xlsx_io, index=False, engine="openpyxl")
    xlsx_io.seek(0)

    response = client.post(
        "/api/upload",
        files={"file": ("test.xlsx", xlsx_io, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["total"] == 2

    # Check status reaches done
    status_resp = client.get(f"/api/upload/{data['job_id']}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["state"] == "done"
    assert status_resp.json()["rows_tagged"] == 2

def test_validation_error_wrong_file_type():
    file_obj = io.BytesIO(b"some text content")
    response = client.post(
        "/api/upload",
        files={"file": ("invalid.txt", file_obj, "text/plain")}
    )
    assert response.status_code == 400
    error_data = response.json()
    assert "error" in error_data
    assert "Only .csv and .xlsx files are supported" in error_data["error"]["message"]

def test_validation_error_missing_columns():
    csv_missing = (
        "id,source,date\n"
        "UP-101,playstore,2026-10-01\n"
    )
    file_obj = io.BytesIO(csv_missing.encode("utf-8"))
    response = client.post(
        "/api/upload",
        files={"file": ("missing.csv", file_obj, "text/csv")}
    )
    assert response.status_code == 400
    error_data = response.json()
    assert "error" in error_data
    assert "Missing required columns" in error_data["error"]["message"]

def test_validation_error_too_many_rows():
    # 501 rows exceeds limit
    rows = ["id,source,date,rating,text"]
    for i in range(501):
        rows.append(f"ROW-{i},playstore,2026-10-01,5,Valid text comment {i}")
    big_csv = "\n".join(rows)

    file_obj = io.BytesIO(big_csv.encode("utf-8"))
    response = client.post(
        "/api/upload",
        files={"file": ("too_many.csv", file_obj, "text/csv")}
    )
    assert response.status_code == 400
    error_data = response.json()
    assert "error" in error_data
    assert "exceeds maximum row limit of 500 rows" in error_data["error"]["message"]

def test_validation_error_duplicate_ids():
    csv_dup = (
        "id,source,date,rating,text\n"
        "DUP-01,playstore,2026-10-01,5,Comment 1\n"
        "DUP-01,playstore,2026-10-02,4,Comment 2\n"
    )
    file_obj = io.BytesIO(csv_dup.encode("utf-8"))
    response = client.post(
        "/api/upload",
        files={"file": ("dup.csv", file_obj, "text/csv")}
    )
    assert response.status_code == 400
    error_data = response.json()
    assert "error" in error_data
    assert "Duplicate ID 'DUP-01'" in error_data["error"]["message"]

def test_validation_error_empty_text():
    csv_empty_text = (
        "id,source,date,rating,text\n"
        "EMP-01,playstore,2026-10-01,5,   \n"
    )
    file_obj = io.BytesIO(csv_empty_text.encode("utf-8"))
    response = client.post(
        "/api/upload",
        files={"file": ("empty.csv", file_obj, "text/csv")}
    )
    assert response.status_code == 400
    error_data = response.json()
    assert "error" in error_data
    assert "Empty text found in row with ID 'EMP-01'" in error_data["error"]["message"]

def test_upload_sample_dataset():
    response = client.post("/api/upload/sample")
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["total"] == 36
    job_id = data["job_id"]

    status_resp = client.get(f"/api/upload/{job_id}/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["state"] == "done"
    assert status["rows_tagged"] == 36
    assert status["total"] == 36

def test_label_correction_and_bad_label_rejected():
    # 1. Start with sample job
    sample_resp = client.post("/api/upload/sample")
    job_id = sample_resp.json()["job_id"]

    # 2. Get first row id
    rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=1")
    row = rows_resp.json()["items"][0]
    row_id = row["id"]

    # 3. Bad label rejected
    bad_patch = client.patch(
        f"/api/upload/{job_id}/rows/{row_id}",
        json={"main_driver": "Completely Invalid Driver"}
    )
    assert bad_patch.status_code == 400
    err = bad_patch.json()
    assert "error" in err
    assert "Invalid value" in err["error"]["message"]

    # 4. Valid label correction
    good_patch = client.patch(
        f"/api/upload/{job_id}/rows/{row_id}",
        json={
            "main_driver": "Cash crunch",
            "outcome": "Paused",
            "stage": "Month 4-6"
        }
    )
    assert good_patch.status_code == 200
    updated = good_patch.json()
    assert updated["id"] == row_id
    assert updated["main_driver"] == "Cash crunch"
    assert updated["outcome"] == "Paused"
    assert updated["stage"] == "Month 4-6"
    assert updated["label_origin"] == "user_corrected"

    # Verify persistence in row fetch
    verify_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=1")
    refetched = verify_resp.json()["items"][0]
    assert refetched["main_driver"] == "Cash crunch"
    assert refetched["label_origin"] == "user_corrected"

def test_persistence_under_runtime_survives_memory_clear():
    # Create sample upload
    sample_resp = client.post("/api/upload/sample")
    job_id = sample_resp.json()["job_id"]

    # Confirm json file exists on disk under runtime/jobs
    job_file = settings.RUNTIME_DIR / "jobs" / f"{job_id}.json"
    assert job_file.exists()

    # Clear in-memory dictionary to simulate server restart
    with job_manager._lock:
        job_manager._jobs.clear()

    # Fetch status: should reload from runtime/jobs/{job_id}.json
    status_resp = client.get(f"/api/upload/{job_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["job_id"] == job_id
    assert status_resp.json()["state"] == "done"

def test_uploaded_data_never_mixes_with_preloaded_data():
    # Preloaded datasets counts
    tagged_records_before = len(get_all_tagged_records())
    corpus_count_before = get_corpus_row_count()

    # Perform multiple uploads
    client.post("/api/upload/sample")
    csv_content = (
        "id,source,date,rating,text\n"
        "TEST-999,appstore,2026-10-01,1,Some isolated test text\n"
    )
    client.post(
        "/api/upload",
        files={"file": ("isolated.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    )

    # Preloaded datasets counts MUST remain completely unchanged
    assert len(get_all_tagged_records()) == tagged_records_before == 54
    assert get_corpus_row_count() == corpus_count_before == 1094

def test_expired_or_missing_job_returns_clear_friendly_error():
    """Verify that querying an expired/non-existent job returns a clear message rather than a generic error."""
    resp = client.get("/api/upload/EXPIRED-JOB-999/status")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert "expired or the server restarted" in data["error"]["message"].lower()

def test_upload_rate_limiter_exceeded():
    """Verify rate limiter blocks abuse (>10 uploads per hour per IP) with a friendly 429 error."""
    headers = {"x-test-rate-limit": "1"}
    from app.routers.upload import upload_rate_limiter
    # Clear rate limiter memory for isolation
    upload_rate_limiter._requests.clear()

    # Perform 10 permitted uploads
    for i in range(10):
        resp = client.post("/api/upload/sample", headers=headers)
        assert resp.status_code == 200

    # 11th request must trigger rate limit
    resp_limited = client.post("/api/upload/sample", headers=headers)
    assert resp_limited.status_code == 429
    data = resp_limited.json()
    assert "error" in data
    assert "rate limit exceeded" in data["error"]["message"].lower()
    assert "10 uploads per hour" in data["error"]["message"].lower()

    # Clean up rate limiter state
    upload_rate_limiter._requests.clear()
