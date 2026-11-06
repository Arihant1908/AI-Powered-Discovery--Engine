import json
import re
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

    # 1. Fixed salary: 12 total, 11 known, 2 negative (Paused/Stopped/Reduced), 18.2%
    fixed = group_map["Fixed salary"]
    assert fixed["n"] == 12
    assert fixed["known_outcome_count"] == 11
    assert fixed["negative_count"] == 2
    assert pytest.approx(fixed["negative_share"], 0.001) == 2 / 11
    assert fixed["percentage"] == 18.2
    assert fixed["display_text"] == "2 of 11 (n=12)"

    # 2. Variable income: 7 total, 6 known, 4 negative, 66.7%
    variable = group_map["Variable income (freelance/business)"]
    assert variable["n"] == 7
    assert variable["known_outcome_count"] == 6
    assert variable["negative_count"] == 4
    assert pytest.approx(variable["negative_share"], 0.001) == 4 / 6
    assert variable["percentage"] == 66.7
    assert variable["display_text"] == "4 of 6 (n=7)"

    # 3. Student or dependent: 5 total, 3 known, 2 negative, 66.7%
    student = group_map["Student or dependent"]
    assert student["n"] == 5
    assert student["known_outcome_count"] == 3
    assert student["negative_count"] == 2
    assert pytest.approx(student["negative_share"], 0.001) == 2 / 3
    assert student["percentage"] == 66.7
    assert student["display_text"] == "2 of 3 (n=5)"

    # 4. Unclear: 30 total, 9 known, 2 negative, 22.2%
    unclear = group_map["Unclear"]
    assert unclear["n"] == 30
    assert unclear["known_outcome_count"] == 9
    assert unclear["negative_count"] == 2
    assert pytest.approx(unclear["negative_share"], 0.001) == 2 / 9
    assert unclear["percentage"] == 22.2
    assert unclear["display_text"] == "2 of 9 (n=30)"

    # Sum of n across groups must equal total dataset size (54)
    total_n = sum(item["n"] for item in segment_view)
    assert total_n == 54

    # Sum of negative counts must equal total Paused (3) + Stopped (4) + Reduced (3) = 10
    total_neg = sum(item["negative_count"] for item in segment_view)
    assert total_neg == 10

    # Footnote must match requirement
    assert data["segment_footnote"] == "Share is among records that state an outcome. Most public reviews do not."

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
    assert var_card["source_mix"] == "2 survey, 2 interviews"
    assert var_card["headline"] == "4 of 6 variable-income records with a known outcome paused, stopped or reduced"
    assert not re.search(r'\d', var_card["explanation"].split("Outcome breakdown:")[0]), "Explanation before breakdown must contain zero digits"
    assert "Outcome breakdown:" in var_card["explanation"]

    # Specific check for the Drop-off drivers card:
    drop_card = next((c for c in cards if c.get("filter") == "outcome in ('Paused', 'Stopped', 'Reduced')"), None)
    assert drop_card is not None, "Drop-off drivers card must be present"
    assert drop_card["supporting_count"] == 10
    assert drop_card["strength"] == "Strong"
    assert drop_card["strength_label"] == "Strong signal, 10 records"
    assert drop_card["headline"] == "10 records report paused, stopped or reduced outcomes"
    assert "Cash crunch 5" in drop_card["explanation"]
    assert "Low early returns 2" in drop_card["explanation"]
    assert not re.search(r'\d', drop_card["explanation"].split("Outcome breakdown:")[0])

def test_no_card_contains_two_breakdowns_and_counts_equal_computed():
    """
    Verify:
    1. The model text must NOT contain any digits in headline or explanation.
    2. The backend appends exactly one 'Outcome breakdown: ...' line.
    3. The breakdown numbers equal the computed outcome counts for qualifying records.
    4. Each card includes the computed source mix.
    5. Feature claims ('struggle to find', 'cannot find') only appear if at least half of cited records mention it.
    """
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]
    assert len(cards) == 4

    import pandas as pd
    from scripts.audit_check import evaluate_card_filter
    engine_df = pd.read_csv("data/engine_dataset.csv")

    for card in cards:
        hl = card["headline"]
        expl = card["explanation"]
        card_filter = card.get("filter")

        # 1. Headline is built by code and contains template structure
        assert re.search(r"(\d+ records cite |\d+ of \d+ .+ records with a known outcome |\d+ records report )", hl)

        # 2. Exactly one Outcome breakdown line
        assert expl.lower().count("outcome breakdown:") == 1, f"Expected 1 breakdown line in: '{expl}'"

        # 3. Text preceding Outcome breakdown must contain NO digits
        parts = expl.split("Outcome breakdown:")
        preceding = parts[0]
        assert not re.search(r'\d', preceding), f"Preceding explanation contains digits: '{preceding}'"

        # 4. Source mix is present and non-empty
        assert card.get("source_mix"), f"Card {hl} missing source_mix"
        assert re.search(r"\d+\s+[a-z]+", card["source_mix"]), f"Invalid source_mix format: {card['source_mix']}"

        # 5. Feature find claim requires at least half of cited records to mention it
        if re.search(r"\b(struggle to find|cannot find|can't find)\b", expl, re.I):
            cited = engine_df[engine_df["id"].isin(card["supporting_evidence_ids"])]
            find_mentions = cited["text"].str.contains(r"\b(find|locate|button|where|hidden)\b", case=False, regex=True).sum()
            assert find_mentions >= (len(cited) / 2.0)

        # 6. Breakdown counts must equal computed outcome counts from qualifying records
        # Separate outcome breakdown from any subsequent Driver/Stage/Unmet needs breakdown lines
        outcome_part = parts[1].split("Driver breakdown:")[0].split("Stage breakdown:")[0].split("Unmet needs cited:")[0].strip().rstrip(".")
        breakdown_counts = {}
        for item in outcome_part.split(","):
            item = item.strip()
            if item:
                m = re.match(r"(\d+)\s+(.+)", item)
                assert m, f"Could not parse breakdown item: '{item}'"
                cnt = int(m.group(1))
                out_name = m.group(2).strip()
                breakdown_counts[out_name] = cnt

        qualifying_df = evaluate_card_filter(engine_df, card_filter)
        expected_counts = qualifying_df["outcome"].value_counts().to_dict()
        assert breakdown_counts == expected_counts, f"Breakdown {breakdown_counts} does not match expected {expected_counts} for filter '{card_filter}'"

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
    assert group_map["Variable income (freelance/business)"]["percentage"] == 66.7
    assert group_map["Variable income (freelance/business)"]["display_text"] == "4 of 6 (n=7)"

def test_preloaded_insights_never_shows_rating_notice():
    """Verify rating-column notice is never shown for the pre-loaded dataset."""
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    warnings = data.get("data_warnings", [])
    assert not any("rating" in w.lower() for w in warnings)

def test_digit_validator_rejects_and_falls_back_to_template(monkeypatch):
    """
    Verify that if the LLM produces digits or numbers in the headline or explanation,
    the validator rejects it and falls back to a template sentence,
    with no digits in the narrative and exactly one outcome breakdown line.
    """
    from app.services.llm import llm_service
    # Mock LLM returning text with digits in headline and explanation
    bad_cards_json = json.dumps({
        "insight_cards": [
            {
                "headline": "4 of 7 investors face issues",
                "explanation": "10 users reported 5 issues during testing. Outcome breakdown: 3 Paused.",
                "proposed_pm_action": "Fix it.",
                "supporting_evidence_ids": ["SV-00007", "SV-00011", "INT-03", "INT-07"]
            }
        ],
        "suggested_questions": ["Q1?", "Q2?", "Q3?"]
    })
    monkeypatch.setattr(llm_service, "generate_json", lambda prompt, system_instruction=None: bad_cards_json)

    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]
    assert len(cards) == 4

    for card in cards:
        # Every card headline is generated by code using the template structure
        assert re.search(r"(\d+ records cite |\d+ of \d+ .+ records with a known outcome |\d+ records report )", card["headline"])
        # Explanation preceding breakdown must have zero digits
        preceding = card["explanation"].split("Outcome breakdown:")[0]
        assert not re.search(r'\d', preceding)
        # Exactly one outcome breakdown line
        assert card["explanation"].count("Outcome breakdown:") == 1

def test_feature_claim_validator_enforces_evidence_threshold(monkeypatch):
    """
    Verify that if the LLM produces a claim that users 'struggle to find' or 'cannot find'
    a feature, but fewer than half of cited records mention it, the validator rejects it
    and falls back to describing only the cash-flow pattern.
    """
    from app.services.llm import llm_service
    # Mock LLM returning "struggle to find" for Card 1 (where only 1 of 4 records mentions a button/finding)
    bad_cards_json = json.dumps({
        "insight_cards": [
            {
                "headline": "Variable income investors struggle to find pause controls",
                "explanation": "Users experiencing cash flow shifts struggle to find pause controls during critical billing windows.",
                "proposed_pm_action": "Add pause button.",
                "supporting_evidence_ids": ["SV-00007", "SV-00011", "INT-03", "INT-07"]
            }
        ],
        "suggested_questions": ["Q1?", "Q2?", "Q3?"]
    })
    monkeypatch.setattr(llm_service, "generate_json", lambda prompt, system_instruction=None: bad_cards_json)

    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]
    var_card = next(c for c in cards if "variable" in c["headline"].lower() or "variable" in str(c.get("filter")).lower())

    # Must NOT contain "struggle to find" because < half mention it
    assert "struggle to find" not in var_card["explanation"].lower()
    # Must describe only cash-flow pattern
    assert "cash-flow" in var_card["explanation"].lower() or "cash flow" in var_card["explanation"].lower()

def test_no_card_contains_unevidenced_mechanism_word():
    """
    Verify Fix requirement 4 & 5:
    No card explanation contains unevidenced mechanism words:
    (timeout, server, delay, latency, bank, initial, early, structural, dissatisfaction, billing window)
    unless that word appears in the card's cited unmet_need phrases or driver label.
    """
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]
    assert len(cards) == 4

    from app.services.insights import find_forbidden_mechanism_words, get_unmet_needs_str
    from app.services.data_store import get_all_tagged_records
    records_by_id = {r.id: r for r in get_all_tagged_records()}

    for card in cards:
        expl = card["explanation"]
        preceding = expl.split("Outcome breakdown:")[0].strip()
        cited_recs = [records_by_id[cid] for cid in card["supporting_evidence_ids"] if cid in records_by_id]
        unmet_ctx = get_unmet_needs_str(cited_recs, max_items=10)
        allowed_context = f"{card.get('filter', '')} {unmet_ctx} {card.get('headline', '')}"

        forbidden = find_forbidden_mechanism_words(preceding, allowed_context)
        assert not forbidden, f"Card '{card['headline']}' contains unevidenced mechanism words: {forbidden} in '{preceding}'"

def test_drop_off_card_driver_breakdown_and_card_lines():
    """
    Verify Fix requirement 2 & 5:
    1. Drop-off card shows driver breakdown:
       Cash crunch 5, Low early returns 2, Payment or mandate failure 1, Other 1, Confusion about the app 1
    2. Multi-driver cards have 'Driver breakdown:' line.
    3. Single-driver cards do not have 'Driver breakdown:' line.
    4. Cards with cited unmet needs have 'Unmet needs cited:' line.
    5. Cards mentioning timing have 'Stage breakdown:' line.
    """
    response = client.post("/api/insights/regenerate?dataset=preloaded")
    assert response.status_code == 200
    data = response.json()
    cards = data["cards"]

    drop_card = next((c for c in cards if c.get("filter") == "outcome in ('Paused', 'Stopped', 'Reduced')"), None)
    assert drop_card is not None
    assert drop_card["headline"] == "10 records report paused, stopped or reduced outcomes"
    assert "Driver breakdown: Cash crunch 5, Low early returns 2, Payment or mandate failure 1, Other 1, Confusion about the app 1." in drop_card["explanation"]
    assert "Outcome breakdown:" in drop_card["explanation"]
    assert "Unmet needs cited:" in drop_card["explanation"]

    # Variable income card (multi-driver: Cash crunch 3, Low early returns 1)
    var_card = next((c for c in cards if "variable" in str(c.get("filter")).lower()), None)
    assert var_card is not None
    assert var_card["headline"] == "4 of 6 variable-income records with a known outcome paused, stopped or reduced"
    assert "Driver breakdown: Cash crunch 3, Low early returns 1." in var_card["explanation"]
    assert "Unmet needs cited: Skip SIP button on the home page, Pause that is easy to find, with no long notice period." in var_card["explanation"]

    # Driver cards (Payment or mandate failure, Low early returns)
    pay_card = next((c for c in cards if "Payment or mandate failure" in str(c.get("filter"))), None)
    assert pay_card is not None
    assert pay_card["headline"] == "4 records cite Payment or mandate failure"
    assert "Driver breakdown:" not in pay_card["explanation"], "Single-driver card must not have Driver breakdown"
    assert "Unmet needs cited:" in pay_card["explanation"]

    low_card = next((c for c in cards if "Low early returns" in str(c.get("filter"))), None)
    assert low_card is not None
    assert low_card["headline"] == "7 records cite Low early returns"
    assert "Driver breakdown:" not in low_card["explanation"], "Single-driver card must not have Driver breakdown"
    assert "Unmet needs cited:" in low_card["explanation"]

def test_unmet_theme_members_file_exists_and_valid():
    """
    Verify Fix requirement 6:
    audit/raw/unmet_theme_members.json exists and lists each theme with member phrases and record IDs.
    """
    path = settings.BASE_DIR / "audit" / "raw" / "unmet_theme_members.json"
    assert path.exists(), f"Missing {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 5

    total_records = 0
    for theme_obj in data:
        assert "theme" in theme_obj
        assert "count" in theme_obj
        assert "member_phrases" in theme_obj
        assert "record_ids" in theme_obj
        assert len(theme_obj["record_ids"]) == theme_obj["count"]
        assert len(theme_obj["member_phrases"]) > 0
        total_records += theme_obj["count"]

    assert total_records == 42
