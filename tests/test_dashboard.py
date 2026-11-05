import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.schema import ALLOWED_MAIN_DRIVERS, ALLOWED_OUTCOMES

client = TestClient(app)

def test_unfiltered_dashboard_charts_counts():
    response = client.get("/api/dashboard/charts")
    assert response.status_code == 200
    data = response.json()

    # Verify every allowed main_driver is present
    main_driver_counts = {item["label"]: item["count"] for item in data["main_driver"]}
    assert len(main_driver_counts) == len(ALLOWED_MAIN_DRIVERS)
    
    # Exact expected counts from prompt
    assert main_driver_counts["Advice or question (no SIP experience)"] == 13
    assert main_driver_counts["Cash crunch"] == 12
    assert main_driver_counts["Low early returns"] == 7
    assert main_driver_counts["Other"] == 6
    assert main_driver_counts["Working well / no issue"] == 5
    assert main_driver_counts["Payment or mandate failure"] == 4
    assert main_driver_counts["Confusion about the app"] == 3
    assert main_driver_counts["Outside influence"] == 3
    assert main_driver_counts["Expectation gap"] == 1
    assert main_driver_counts["Forgot about it"] == 0
    assert main_driver_counts["Praise or general feedback"] == 0

    # Verify every allowed outcome is present
    outcome_counts = {item["label"]: item["count"] for item in data["outcome"]}
    assert len(outcome_counts) == len(ALLOWED_OUTCOMES)

    # Exact expected counts from prompt
    assert outcome_counts["Unknown"] == 25
    assert outcome_counts["Continuing"] == 19
    assert outcome_counts["Stopped"] == 4
    assert outcome_counts["Reduced"] == 3
    assert outcome_counts["Paused"] == 3

    assert data["total_records"] == 54

    # Check percentage calculation
    advice_item = next(item for item in data["main_driver"] if item["label"] == "Advice or question (no SIP experience)")
    assert round(advice_item["percentage"], 1) == round((13 / 54) * 100, 1)

def test_unfiltered_dashboard_summary():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()

    assert data["total_items_collected"] == 1094
    assert data["distinct_sources"] == 6
    assert data["labelled_evidence_items"] == 54
    assert data["deep_interviews"] == 8

def test_dashboard_filters_change_counts():
    # Filter by source=youtube
    response_yt = client.get("/api/dashboard/charts?source=youtube")
    assert response_yt.status_code == 200
    data_yt = response_yt.json()
    assert data_yt["total_records"] == 22
    yt_counts = {item["label"]: item["count"] for item in data_yt["main_driver"]}
    assert yt_counts["Advice or question (no SIP experience)"] == 13
    assert yt_counts["Cash crunch"] == 4
    assert yt_counts["Low early returns"] == 1

    # Filter summary by source=interviews
    response_int = client.get("/api/dashboard/summary?source=interviews")
    assert response_int.status_code == 200
    data_int = response_int.json()
    assert data_int["labelled_evidence_items"] == 8
    assert data_int["deep_interviews"] == 8
    assert data_int["distinct_sources"] == 1

    # Multi-value list filter: source=youtube and source=survey
    response_multi = client.get("/api/dashboard/charts?source=youtube&source=survey")
    assert response_multi.status_code == 200
    data_multi = response_multi.json()
    assert data_multi["total_records"] == 34  # 22 (youtube) + 12 (survey)

    # Complex multi-attribute filter: income_stability + age_band + influence
    response_attr = client.get("/api/dashboard/charts?income_stability=Fixed%20salary&age_band=28-35&influence=Own%20research")
    assert response_attr.status_code == 200
    assert response_attr.json()["total_records"] > 0

def test_empty_filter_results_return_zeros_and_not_errors():
    # Non-existent source
    response = client.get("/api/dashboard/charts?source=nonexistent_channel")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 0
    for item in data["main_driver"]:
        assert item["count"] == 0
        assert item["percentage"] == 0.0
    for item in data["outcome"]:
        assert item["count"] == 0
        assert item["percentage"] == 0.0

    # Summary with empty filter
    summary_resp = client.get("/api/dashboard/summary?source=nonexistent_channel")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_items_collected"] == 0
    assert summary_data["distinct_sources"] == 0
    assert summary_data["labelled_evidence_items"] == 0
    assert summary_data["deep_interviews"] == 0

    # Unmet needs with empty filter
    unmet_resp = client.get("/api/dashboard/unmet-needs?source=nonexistent_channel")
    assert unmet_resp.status_code == 200
    assert unmet_resp.json()["themes"] == []

    # Evidence pagination with empty filter
    evidence_resp = client.get("/api/dashboard/evidence?source=nonexistent_channel")
    assert evidence_resp.status_code == 200
    assert evidence_resp.json()["items"] == []
    assert evidence_resp.json()["total"] == 0

def test_unmet_needs_top_5_excludes_none(monkeypatch):
    # Test fallback path when AI is unavailable (groups by exact normalised phrase)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "MOCK_LLM", False)
    response = client.get("/api/dashboard/unmet-needs")
    assert response.status_code == 200
    data = response.json()
    themes = data["themes"]
    assert len(themes) <= 5
    for theme_item in themes:
        assert theme_item["theme"].strip().lower() != "none"
        assert theme_item["count"] >= 1
    assert not data["ai_available"]
    assert not data["ai_grouped"]

def test_evidence_pagination_and_search():
    # Page 1, size 5
    resp_page1 = client.get("/api/dashboard/evidence?page=1&page_size=5")
    assert resp_page1.status_code == 200
    data1 = resp_page1.json()
    assert len(data1["items"]) == 5
    assert data1["total"] == 54
    assert data1["page"] == 1
    assert data1["total_pages"] == 11

    # Search over text
    resp_search = client.get("/api/dashboard/evidence?search=autopay")
    assert resp_search.status_code == 200
    search_data = resp_search.json()
    assert search_data["total"] > 0
    for item in search_data["items"]:
        assert "autopay" in item["text"].lower()

def test_evidence_by_id_found():
    response = client.get("/api/dashboard/evidence/SV-00001")
    assert response.status_code == 200
    item = response.json()
    assert item["id"] == "SV-00001"
    assert item["source"] == "survey"
    assert item["main_driver"] == "Cash crunch"
    assert item["outcome"] == "Continuing"

def test_evidence_by_id_unknown_returns_standard_404_error():
    response = client.get("/api/dashboard/evidence/UNKNOWN-99999")
    assert response.status_code == 404
    error_envelope = response.json()
    assert "error" in error_envelope
    assert error_envelope["error"]["code"] == "HTTP_404"
    assert "Evidence item with id 'UNKNOWN-99999' not found" in error_envelope["error"]["message"]

def test_dashboard_export_csv():
    response = client.get("/api/dashboard/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    # Header + 54 rows
    assert len(lines) == 55
    assert "id,source,date,text" in lines[0]

    # Filtered export
    resp_filtered = client.get("/api/dashboard/export.csv?source=interviews")
    assert resp_filtered.status_code == 200
    lines_int = resp_filtered.text.strip().split("\n")
    # Header + 8 interview rows
    assert len(lines_int) == 9
