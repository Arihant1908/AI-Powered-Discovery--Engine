import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_mock_llm():
    orig_mock = settings.MOCK_LLM
    orig_key = settings.GEMINI_API_KEY
    settings.MOCK_LLM = True
    yield
    settings.MOCK_LLM = orig_mock
    settings.GEMINI_API_KEY = orig_key

def test_insights_page_with_preloaded_dataset():
    """Verify Insights page and API endpoints with dataset=preloaded."""
    # 1. Page serves 200 with HTML and required layout elements
    page_resp = client.get("/insights?dataset=preloaded")
    assert page_resp.status_code == 200
    assert "text/html" in page_resp.headers["content-type"]
    html = page_resp.text
    assert "SIP Discovery Engine" in html
    assert "AI insight summary" in html
    assert 'id="btnRegenerate"' in html
    assert 'id="cardsContainer"' in html
    assert 'id="nextQuestionsSection"' in html
    assert 'id="segmentViewContainer"' in html
    assert 'id="evidenceModal"' in html
    assert "Small sample. Treat as patterns, not proof." in html

    # Rule 1 verification: no hardcoded Stitch placeholder records or IDs
    assert "ID-00101" not in html
    assert "ID-00201" not in html

    # 2. API returns preloaded insights with 54 records
    api_resp = client.post("/api/insights/regenerate?dataset=preloaded")
    assert api_resp.status_code == 200
    data = api_resp.json()

    assert data["dataset"] == "preloaded"
    assert data["total_records"] == 54
    assert len(data["segment_view"]) == 4
    assert len(data["cards"]) == 3
    assert len(data["suggested_questions"]) == 3

    # 3. Test evidence lookup for a cited chip ID from the preloaded dataset
    first_chip_id = data["cards"][0]["supporting_evidence_ids"][0]
    ev_resp = client.get(f"/api/dashboard/evidence/{first_chip_id}?dataset=preloaded")
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert ev_data["id"] == first_chip_id
    assert "text" in ev_data
    assert "main_driver" in ev_data
    assert "outcome" in ev_data

def test_insights_page_with_finished_upload_job():
    """Verify Insights page and API endpoints with a finished upload job dataset."""
    # 1. Trigger sample upload to create and run an upload job
    upload_resp = client.post("/api/upload/sample")
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    job_id = upload_data["job_id"]
    total = upload_data["total"]
    assert total > 0

    # 2. Check job status is done
    status_resp = client.get(f"/api/upload/{job_id}/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["state"] == "done"

    # 3. Page serves 200 with job_id in query
    page_resp = client.get(f"/insights?dataset={job_id}")
    assert page_resp.status_code == 200
    assert "AI insight summary" in page_resp.text
    assert "Small sample. Treat as patterns, not proof." in page_resp.text

    # 4. API computes insights specifically for this upload job
    insights_resp = client.post(f"/api/insights/regenerate?dataset={job_id}")
    assert insights_resp.status_code == 200
    insights = insights_resp.json()

    assert insights["dataset"] == job_id
    assert insights["total_records"] == total
    assert len(insights["segment_view"]) == 4
    assert len(insights["cards"]) == 3
    assert len(insights["suggested_questions"]) == 3

    # Verify cited evidence IDs belong to this job
    all_job_rows = client.get(f"/api/upload/{job_id}/rows?page=1&page_size=100").json()["items"]
    job_row_ids = {r["id"] for r in all_job_rows}

    for card in insights["cards"]:
        for cited_id in card["supporting_evidence_ids"]:
            assert cited_id in job_row_ids

    # 5. Test evidence detail lookup for a cited chip ID from this upload job
    test_chip_id = insights["cards"][0]["supporting_evidence_ids"][0]
    chip_resp = client.get(f"/api/dashboard/evidence/{test_chip_id}?dataset={job_id}")
    assert chip_resp.status_code == 200
    chip_rec = chip_resp.json()
    assert chip_rec["id"] == test_chip_id
    assert len(chip_rec["text"]) > 0

