import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_mock_llm():
    """Default to mock LLM mode for testing, restoring state afterwards."""
    orig_mock = settings.MOCK_LLM
    orig_key = settings.GEMINI_API_KEY
    settings.MOCK_LLM = True
    yield
    settings.MOCK_LLM = orig_mock
    settings.GEMINI_API_KEY = orig_key

def test_get_insights_preloaded_computed_stats():
    """Verify backend computes driver counts, outcome counts, and unmet needs in code."""
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()

    assert data["dataset"] == "preloaded"
    assert data["total_records"] == 54

    stats = data["computed_stats"]
    assert stats["total_records"] == 54

    # Expected driver counts on preloaded data
    drivers = stats["main_driver_counts"]
    assert drivers["Advice or question (no SIP experience)"] == 13
    assert drivers["Cash crunch"] == 12
    assert drivers["Low early returns"] == 7
    assert drivers["Other"] == 6
    assert drivers["Working well / no issue"] == 5
    assert drivers["Payment or mandate failure"] == 4
    assert drivers["Confusion about the app"] == 3
    assert drivers["Outside influence"] == 3
    assert drivers["Expectation gap"] == 1

    # Expected outcome counts on preloaded data
    outcomes = stats["outcome_counts"]
    assert outcomes["Unknown"] == 25
    assert outcomes["Continuing"] == 19
    assert outcomes["Stopped"] == 4
    assert outcomes["Reduced"] == 3
    assert outcomes["Paused"] == 3

    # Supporting IDs per driver
    supporting = stats["supporting_ids_by_driver"]
    assert len(supporting["Cash crunch"]) == 12
    assert "SV-00001" in supporting["Cash crunch"]
    assert len(supporting["Low early returns"]) == 7

    # Top unmet needs (excluding none)
    unmet = stats["top_unmet_needs"]
    assert len(unmet) <= 5
    for item in unmet:
        assert item["theme"].lower() != "none"
        assert item["count"] >= 1

def test_segment_shares_and_n_correct_on_preloaded_data():
    """
    Verify computed share of Paused, Stopped or Reduced per income_stability group,
    with exact n and percentages on the preloaded data.
    """
    response = client.get("/api/insights?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    segment_view = data["segment_view"]

    # Verify all 4 allowed income stability groups are present
    group_map = {item["income_stability"]: item for item in segment_view}
    assert len(group_map) == 4

    # 1. Fixed salary: 12 total, 2 negative (Paused/Stopped/Reduced), 16.7%
    fixed = group_map["Fixed salary"]
    assert fixed["n"] == 12
    assert fixed["negative_count"] == 2
    assert pytest.approx(fixed["negative_share"], 0.001) == 2 / 12
    assert fixed["percentage"] == 16.7

    # 2. Variable income: 7 total, 4 negative, 57.1%
    variable = group_map["Variable income (freelance/business)"]
    assert variable["n"] == 7
    assert variable["negative_count"] == 4
    assert pytest.approx(variable["negative_share"], 0.001) == 4 / 7
    assert variable["percentage"] == 57.1

    # 3. Student or dependent: 5 total, 2 negative, 40.0%
    student = group_map["Student or dependent"]
    assert student["n"] == 5
    assert student["negative_count"] == 2
    assert pytest.approx(student["negative_share"], 0.001) == 2 / 5
    assert student["percentage"] == 40.0

    # 4. Unclear: 30 total, 2 negative, 6.7%
    unclear = group_map["Unclear"]
    assert unclear["n"] == 30
    assert unclear["negative_count"] == 2
    assert pytest.approx(unclear["negative_share"], 0.001) == 2 / 30
    assert unclear["percentage"] == 6.7

    # Sum of n across groups must equal total dataset size (54)
    total_n = sum(item["n"] for item in segment_view)
    assert total_n == 54

    # Sum of negative counts must equal total Paused (3) + Stopped (4) + Reduced (3) = 10
    total_neg = sum(item["negative_count"] for item in segment_view)
    assert total_neg == 10

def test_insight_cards_id_validation_and_invalid_id_dropped():
    """
    Verify AI returns exactly 4 insight cards, every cited ID is validated against
    the dataset, and any hallucinated or non-existent ID (like NONEXISTENT-ID-9999) is dropped.
    """
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()

    cards = data["cards"]
    assert len(cards) == 4

    # Fetch valid IDs from dataset
    stats_resp = client.get("/api/dashboard/evidence?page_size=100")
    valid_ids = {item["id"] for item in stats_resp.json()["items"]}

    for card in cards:
        assert card["headline"]
        assert card["explanation"]
        assert card["proposed_pm_action"]
        assert isinstance(card["supporting_evidence_ids"], list)

        # Every ID must exist in the dataset
        for cited_id in card["supporting_evidence_ids"]:
            assert cited_id in valid_ids
            assert cited_id != "NONEXISTENT-ID-9999"

        # supporting_count must match length of supporting_evidence_ids
        assert card["supporting_count"] == len(card["supporting_evidence_ids"])

def test_strength_rule_and_no_confidence_percentages():
    """
    Verify strength tag rule:
    - Strong = 6 or more supporting records
    - Medium = 3 to 5 supporting records
    - Weak signal = 1 to 2 supporting records
    Count shown with label 'records', NO confidence percentages anywhere.
    """
    from app.services.insights import calculate_strength
    assert calculate_strength(7) == ("Strong", "Strong signal, 7 records")
    assert calculate_strength(4) == ("Medium", "Medium signal, 4 records")
    assert calculate_strength(2) == ("Weak signal", "Weak signal, 2 records")
    assert calculate_strength(1) == ("Weak signal", "Weak signal, 1 record")

    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]

    for card in cards:
        count = card["supporting_count"]
        strength = card["strength"]
        strength_label = card["strength_label"]

        expected_strength, expected_label = calculate_strength(count)
        assert strength == expected_strength
        assert strength_label == expected_label

        if count >= 6:
            assert strength == "Strong"
            assert "Strong signal" in strength_label
            assert str(count) in strength_label
        elif 3 <= count <= 5:
            assert strength == "Medium"
            assert "Medium signal" in strength_label
            assert str(count) in strength_label
        else:
            assert strength == "Weak signal"
            assert "Weak signal" in strength_label
            assert str(count) in strength_label

        # Ensure label says 'records' (or 'record' for 1)
        assert "record" in strength_label

        # Ensure no confidence percentages anywhere in cards or strength
        assert "%" not in card["strength"]
        assert "%" not in card["strength_label"]
        assert "confidence" not in card

def test_insight_cards_filtered_evidence_and_variable_income_ids():
    """
    Verify Fix requirements:
    1. For every insight card, all IDs satisfy that card's filter.
    2. The strength tag matches the number of qualifying records.
    3. The variable income card on the pre-loaded data cites exactly SV-00007, SV-00011, INT-03, INT-07.
    4. When a card talks about a segment, show the segment size and base in the text
       (e.g., '4 of 7 variable-income records paused, stopped or reduced').
    5. Drop-off drivers card is present with 10 records and expected driver counts.
    6. Outcome breakdown shown on every card.
    """
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]
    assert len(cards) == 4

    from app.services.data_store import get_all_tagged_records
    records_by_id = {r.id: r for r in get_all_tagged_records()}

    for card in cards:
        card_filter = card.get("filter")
        assert card_filter, "Card must define its filter"
        cited_ids = card["supporting_evidence_ids"]
        assert len(cited_ids) == card["supporting_count"]

        # Outcome breakdown is shown on every card
        assert "outcome breakdown" in card["explanation"].lower()

        # Strength tag matches the number of qualifying records
        count = card["supporting_count"]
        if count >= 6:
            assert card["strength"] == "Strong"
        elif 3 <= count <= 5:
            assert card["strength"] == "Medium"
        else:
            assert card["strength"] == "Weak signal"

        # All IDs on each card satisfy that card's filter
        if "Variable income" in card_filter:
            for cid in cited_ids:
                r = records_by_id[cid]
                assert r.income_stability == "Variable income (freelance/business)"
                assert r.outcome in {"Paused", "Stopped", "Reduced"}
        elif card_filter == "outcome in ('Paused', 'Stopped', 'Reduced')":
            for cid in cited_ids:
                r = records_by_id[cid]
                assert r.outcome in {"Paused", "Stopped", "Reduced"}
        elif "Payment or mandate failure" in card_filter:
            for cid in cited_ids:
                r = records_by_id[cid]
                assert r.main_driver == "Payment or mandate failure"
        elif "Low early returns" in card_filter:
            for cid in cited_ids:
                r = records_by_id[cid]
                assert r.main_driver == "Low early returns"

    # Specific check for the variable income card:
    var_card = next((c for c in cards if "variable" in c["headline"].lower() or "variable" in str(c.get("filter")).lower()), None)
    assert var_card is not None, "Variable income card must be present"
    assert set(var_card["supporting_evidence_ids"]) == {"SV-00007", "SV-00011", "INT-03", "INT-07"}
    assert var_card["supporting_count"] == 4
    assert var_card["strength"] == "Medium"
    assert var_card["strength_label"] == "Medium signal, 4 records"
    assert "4 of 7 variable-income records paused, stopped or reduced" in var_card["explanation"]

    # Specific check for the Drop-off drivers card:
    drop_card = next((c for c in cards if c.get("filter") == "outcome in ('Paused', 'Stopped', 'Reduced')"), None)
    assert drop_card is not None, "Drop-off drivers card must be present"
    assert drop_card["supporting_count"] == 10
    assert drop_card["strength"] == "Strong"
    assert drop_card["strength_label"] == "Strong signal, 10 records"
    assert "Cash crunch" in drop_card["explanation"]
    assert "Low early returns" in drop_card["explanation"]

def test_suggested_questions():
    """Verify 3 suggested next questions are generated based on data gaps."""
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()

    questions = data["suggested_questions"]
    assert len(questions) == 3
    for q in questions:
        assert isinstance(q, str)
        assert len(q.strip()) > 10

def test_runtime_caching_and_regeneration():
    """Verify results are cached in runtime/ keyed by dataset, and regeneration overwrites cache."""
    cache_path = settings.RUNTIME_DIR / "insights" / "preloaded.json"

    # Call regenerate to ensure fresh cache
    regen_resp = client.post("/api/insights/regenerate?dataset=preloaded")
    assert regen_resp.status_code == 200
    assert regen_resp.json()["cached"] is False
    assert cache_path.exists()

    # Subsequent GET should return cached result
    get_resp = client.get("/api/insights?dataset=preloaded")
    assert get_resp.status_code == 200
    assert get_resp.json()["cached"] is True

def test_unknown_dataset_returns_404():
    """Verify querying an unknown dataset job_id returns standard 404 envelope."""
    response = client.get("/api/insights?dataset=UNKNOWN-JOB-ID-999")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
    assert "Job 'UNKNOWN-JOB-ID-999' not found" in data["error"]["message"]

def test_graceful_fallback_when_ai_unavailable():
    """
    Verify that when AI is unavailable, the endpoint returns the computed stats
    and segment view with a clear 'AI summary unavailable' state and no fake text.
    """
    # Simulate AI unavailable (no API key and mock disabled)
    settings.MOCK_LLM = False
    settings.GEMINI_API_KEY = None

    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()

    # AI summary unavailable
    assert data["ai_summary_available"] is False
    assert data["message"] == "AI summary unavailable"
    assert data["cards"] == []
    assert data["suggested_questions"] == []

    # But computed stats and segment view MUST be returned in full!
    assert data["total_records"] == 54
    assert len(data["segment_view"]) == 4
    assert data["computed_stats"]["total_records"] == 54
    assert data["computed_stats"]["main_driver_counts"]["Cash crunch"] == 12

    # Segment view percentages must remain accurate
    group_map = {item["income_stability"]: item for item in data["segment_view"]}
    assert group_map["Fixed salary"]["n"] == 12
    assert group_map["Fixed salary"]["negative_count"] == 2
    assert group_map["Variable income (freelance/business)"]["percentage"] == 57.1
