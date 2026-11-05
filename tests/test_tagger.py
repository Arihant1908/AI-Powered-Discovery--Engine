import json
import pytest
from app.schema import (
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
    TaggedRecord,
)
from app.services.pii import remove_pii, mask_pii
from app.services.llm import LLMService, generate_json
from app.services.tagger import tag_items, tag_batch, get_system_prompt
from app.config import settings

def test_pii_removal():
    raw_text = (
        "Hi, contact me at investor.raj+sip@domain.co.in or call +91 9876543210 / 9123456789. "
        "Also follow @fin_guru_99 on Twitter. "
        "I started an SIP of 5000 in 2024 and got 15% return."
    )
    cleaned = remove_pii(raw_text)

    # Emails, phones, handles removed
    assert "investor.raj+sip@domain.co.in" not in cleaned
    assert "9876543210" not in cleaned
    assert "9123456789" not in cleaned
    assert "@fin_guru_99" not in cleaned

    # Financial and temporal context preserved
    assert "5000" in cleaned
    assert "2024" in cleaned
    assert "15%" in cleaned

def test_pii_masking():
    raw_text = "Email test@example.com or DM @expert regarding phone 9876543210."
    masked = mask_pii(raw_text)
    assert "[EMAIL]" in masked
    assert "[HANDLE]" in masked
    assert "[PHONE]" in masked
    assert "test@example.com" not in masked
    assert "@expert" not in masked
    assert "9876543210" not in masked

def test_mock_llm_deterministic_fallback():
    service = LLMService()
    # Explicitly force mock mode
    settings.MOCK_LLM = True

    prompt = json.dumps([
        {"id": "BATCH-001", "text": "Returns look low after 3 months"},
        {"id": "BATCH-002", "text": "Autopay failed twice"}
    ])

    raw_output = service.generate_json(prompt)
    parsed = json.loads(raw_output)

    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "BATCH-001"
    assert parsed[1]["id"] == "BATCH-002"

    for item in parsed:
        assert item["stage"] == "Unclear"
        assert item["main_driver"] == "Other"
        assert item["outcome"] == "Unknown"
        assert item["income_stability"] == "Unclear"
        assert item["age_band"] == "Unclear"
        assert item["influence"] == "Unclear"

def test_tagger_batch_order_and_id_preservation():
    # Generate 45 items (will span across 3 batches: 20, 20, 5)
    sample_items = [
        {
            "id": f"ITEM-{i:03d}",
            "source": "playstore",
            "date": "2026-10-01",
            "text": f"User review text number {i} with some SIP feedback."
        }
        for i in range(1, 46)
    ]

    tagged_results = tag_items(sample_items, batch_size=20)

    assert len(tagged_results) == 45

    # Check exact order and id preservation
    for idx, tagged in enumerate(tagged_results):
        expected_id = f"ITEM-{idx+1:03d}"
        assert tagged.id == expected_id
        assert tagged.source == "playstore"
        assert tagged.stage in ALLOWED_STAGES
        assert tagged.main_driver in ALLOWED_MAIN_DRIVERS
        assert tagged.outcome in ALLOWED_OUTCOMES
        assert tagged.income_stability in ALLOWED_INCOME_STABILITIES
        assert tagged.age_band in ALLOWED_AGE_BANDS
        assert tagged.influence in ALLOWED_INFLUENCES

def test_tagger_invalid_value_fallback(monkeypatch):
    """
    When LLM returns a response where one item has invalid values and one is valid,
    the invalid item should fall back to Other/Unknown/Unclear and be marked 'fallback'
    without crashing the batch.
    """
    items = [
        {"id": "GOOD-01", "text": "SIP paused due to job loss"},
        {"id": "BAD-02", "text": "Some ambiguous feedback text"}
    ]

    # Mock LLM to return one valid and one invalid item
    def mock_llm_response(prompt, system_instruction=None):
        return json.dumps([
            {
                "id": "GOOD-01",
                "stage": "Month 4-6",
                "main_driver": "Cash crunch",
                "outcome": "Paused",
                "unmet_need": "Flexible pause",
                "income_stability": "Fixed salary",
                "age_band": "28-35",
                "influence": "Own research"
            },
            {
                "id": "BAD-02",
                "stage": "Invalid Month 999",  # Invalid
                "main_driver": "Invalid Driver XYZ",  # Invalid
                "outcome": "Unknown",
                "unmet_need": "none",
                "income_stability": "Unclear",
                "age_band": "Unclear",
                "influence": "Unclear"
            }
        ])

    from app.services.tagger import llm_service
    monkeypatch.setattr(llm_service, "generate_json", mock_llm_response)

    results = tag_items(items)

    assert len(results) == 2
    # Good item kept valid tags
    good_item = results[0]
    assert good_item.id == "GOOD-01"
    assert good_item.stage == "Month 4-6"
    assert good_item.main_driver == "Cash crunch"
    assert good_item.outcome == "Paused"
    assert good_item.label_origin == "ai_drafted"

    # Bad item fell back cleanly
    bad_item = results[1]
    assert bad_item.id == "BAD-02"
    assert bad_item.stage == "Unclear"
    assert bad_item.main_driver == "Other"
    assert bad_item.outcome == "Unknown"
    assert bad_item.label_origin == "fallback"

def test_tagger_invalid_json_fallback(monkeypatch):
    """
    When LLM returns completely broken non-JSON text, tagger retries once and
    falls back cleanly for all items in the batch.
    """
    items = [
        {"id": "FAIL-01", "text": "App crashed"},
        {"id": "FAIL-02", "text": "Returns low"}
    ]

    call_count = 0

    def mock_broken_json(prompt, system_instruction=None):
        nonlocal call_count
        call_count += 1
        return "Internal Model Error: Not JSON"

    from app.services.tagger import llm_service
    monkeypatch.setattr(llm_service, "generate_json", mock_broken_json)

    results = tag_items(items)

    # Verified it retried once (2 calls total)
    assert call_count >= 2
    assert len(results) == 2
    for r in results:
        assert r.stage == "Unclear"
        assert r.main_driver == "Other"
        assert r.outcome == "Unknown"
        assert r.label_origin == "fallback"

def test_tagger_pii_removed_before_model(monkeypatch):
    """
    Verifies that text sent to the LLM has all PII stripped.
    """
    items = [
        {"id": "PII-01", "text": "Contact me at alert@bank.com or 9999888877 or @my_handle regarding SIP"}
    ]

    captured_prompt = None

    def mock_capture_prompt(prompt, system_instruction=None):
        nonlocal captured_prompt
        captured_prompt = prompt
        return json.dumps([{
            "id": "PII-01",
            "stage": "Unclear",
            "main_driver": "Other",
            "outcome": "Unknown",
            "unmet_need": "none",
            "income_stability": "Unclear",
            "age_band": "Unclear",
            "influence": "Unclear"
        }])

    from app.services.tagger import llm_service
    monkeypatch.setattr(llm_service, "generate_json", mock_capture_prompt)

    tag_items(items)

    assert captured_prompt is not None
    assert "alert@bank.com" not in captured_prompt
    assert "9999888877" not in captured_prompt
    assert "@my_handle" not in captured_prompt
    assert "PII-01" in captured_prompt

