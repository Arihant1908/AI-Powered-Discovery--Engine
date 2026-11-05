import re
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.schema import (
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)

client = TestClient(app)

def parse_allowed_values_from_prompt():
    prompt_path = Path(__file__).resolve().parent.parent / "data" / "tagging_prompt.txt"
    content = prompt_path.read_text(encoding="utf-8")
    
    extracted = {}
    keys = ["stage", "main_driver", "outcome", "income_stability", "age_band", "influence"]
    for key in keys:
        # Pattern matches e.g. stage: "Month 0-1", "Month 2-3", ...
        pattern = rf'^{key}:\s*(.+)$'
        match = re.search(pattern, content, re.MULTILINE)
        assert match, f"Could not find key '{key}' in tagging_prompt.txt"
        raw_items = match.group(1)
        items = re.findall(r'"([^"]+)"', raw_items)
        extracted[key] = items
        
    return extracted

def test_schema_matches_tagging_prompt():
    prompt_values = parse_allowed_values_from_prompt()
    
    assert ALLOWED_STAGES == prompt_values["stage"], "Stage values mismatch"
    assert ALLOWED_MAIN_DRIVERS == prompt_values["main_driver"], "Main driver values mismatch"
    assert ALLOWED_OUTCOMES == prompt_values["outcome"], "Outcome values mismatch"
    assert ALLOWED_INCOME_STABILITIES == prompt_values["income_stability"], "Income stability values mismatch"
    assert ALLOWED_AGE_BANDS == prompt_values["age_band"], "Age band values mismatch"
    assert ALLOWED_INFLUENCES == prompt_values["influence"], "Influence values mismatch"

def test_allowed_values_api_endpoint():
    response = client.get("/api/schema/allowed-values")
    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == ALLOWED_STAGES
    assert data["main_driver"] == ALLOWED_MAIN_DRIVERS
    assert data["outcome"] == ALLOWED_OUTCOMES
    assert data["income_stability"] == ALLOWED_INCOME_STABILITIES
    assert data["age_band"] == ALLOWED_AGE_BANDS
    assert data["influence"] == ALLOWED_INFLUENCES

def test_error_envelope_format_404():
    response = client.get("/non-existent-endpoint-xyz")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]

