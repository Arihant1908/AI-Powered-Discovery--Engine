import io
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_upload_page_html_structure_and_rule1():
    """Verify upload page serves valid HTML without any hardcoded data (Rule 1)."""
    response = client.get("/upload")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text

    # Static elements present
    assert "SIP Discovery Engine" in html
    assert 'id="dropZone"' in html
    assert 'id="fileUploadInput"' in html
    assert 'id="btnSampleData"' in html
    assert 'id="btnDownloadTemplate"' in html
    assert 'href="/api/template.csv"' in html
    assert 'id="btnViewInsights"' in html
    assert 'src="/static/upload.js"' in html

    # Rule 1: No hardcoded sample rows or Stitch placeholder data
    assert "ID-00101" not in html
    assert "ID-00102" not in html
    assert "ID-00103" not in html
    assert "ID-00104" not in html
    assert "ID-00105" not in html
    assert "SIP auto-debit bounced" not in html
    assert "Need option to pause" not in html

def test_full_sample_upload_flow_and_editing():
    """Simulates browser sample upload, status polling, row retrieval, and label correction."""
    # 1. Start sample upload
    init_resp = client.post("/api/upload/sample")
    assert init_resp.status_code == 200
    init_data = init_resp.json()
    assert "job_id" in init_data
    job_id = init_data["job_id"]
    assert init_data["total"] > 0

    # 2. Poll status
    status_resp = client.get(f"/api/upload/{job_id}/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["state"] == "done"
    assert status["rows_tagged"] == status["total"]

    # 3. Retrieve first page of rows
    rows_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
    assert rows_resp.status_code == 200
    rows_data = rows_resp.json()
    assert len(rows_data["items"]) == 5
    assert rows_data["total"] == status["total"]

    first_item = rows_data["items"][0]
    row_id = first_item["id"]

    # 4. Get allowed values from /api/meta
    meta_resp = client.get("/api/meta")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    allowed_drivers = meta["main_driver"]
    allowed_outcomes = meta["outcome"]

    # 5. Patch label with a valid value
    new_driver = [d for d in allowed_drivers if d != first_item["main_driver"]][0]
    new_outcome = [o for o in allowed_outcomes if o != first_item["outcome"]][0]

    patch_resp = client.patch(
        f"/api/upload/{job_id}/rows/{row_id}",
        json={"main_driver": new_driver, "outcome": new_outcome}
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["main_driver"] == new_driver
    assert updated["outcome"] == new_outcome

    # 6. Re-fetch row and confirm persistence
    refetch_resp = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=5")
    refetched_items = refetch_resp.json()["items"]
    matching = [r for r in refetched_items if r["id"] == row_id][0]
    assert matching["main_driver"] == new_driver
    assert matching["outcome"] == new_outcome

def test_deliberately_broken_csv_missing_column():
    """Upload CSV missing the required 'text' column."""
    broken_csv = (
        "id,source,date,rating\n"
        "ERR-01,playstore,2026-10-01,5\n"
    )
    file_obj = io.BytesIO(broken_csv.encode("utf-8"))
    resp = client.post(
        "/api/upload",
        files={"file": ("missing_text.csv", file_obj, "text/csv")}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert "Missing required columns" in err["message"]
    assert "text" in err["message"]

def test_deliberately_broken_csv_empty_text():
    """Upload CSV with empty text in a row."""
    broken_csv = (
        "id,source,date,rating,text\n"
        "ERR-EMPTY,playstore,2026-10-01,5,   \n"
    )
    file_obj = io.BytesIO(broken_csv.encode("utf-8"))
    resp = client.post(
        "/api/upload",
        files={"file": ("empty_text.csv", file_obj, "text/csv")}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert "Empty text" in err["message"]
    assert "ERR-EMPTY" in err["message"]

def test_deliberately_broken_csv_duplicate_ids():
    """Upload CSV with duplicate IDs."""
    broken_csv = (
        "id,source,date,rating,text\n"
        "DUP-01,playstore,2026-10-01,5,First message\n"
        "DUP-01,survey,2026-10-02,4,Second message\n"
    )
    file_obj = io.BytesIO(broken_csv.encode("utf-8"))
    resp = client.post(
        "/api/upload",
        files={"file": ("duplicate_ids.csv", file_obj, "text/csv")}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert "Duplicate ID 'DUP-01'" in err["message"]

def test_deliberately_broken_file_wrong_extension():
    """Upload invalid file extension like .pdf or .txt."""
    broken_file = io.BytesIO(b"Hello world")
    resp = client.post(
        "/api/upload",
        files={"file": ("document.pdf", broken_file, "application/pdf")}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert "Only .csv and .xlsx files are supported" in err["message"]

def test_deliberately_broken_csv_exceeds_row_limit():
    """Upload CSV with 501 rows (>500 limit)."""
    rows = ["id,source,date,rating,text"]
    for i in range(501):
        rows.append(f"ROW-{i:04d},playstore,2026-10-01,5,Feedback text item {i}")
    huge_csv = "\n".join(rows)
    file_obj = io.BytesIO(huge_csv.encode("utf-8"))
    resp = client.post(
        "/api/upload",
        files={"file": ("too_many_rows.csv", file_obj, "text/csv")}
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert "maximum row limit of 500 rows" in err["message"]

