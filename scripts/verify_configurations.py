"""
Verify app behavior in both required configurations:
Configuration A: MOCK_LLM=1 (with no key)
Configuration B: MOCK_LLM=0 with no key (Graceful degradation)
"""
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_configuration_mock_mode():
    print("\n--- Testing Configuration A: MOCK_LLM=1 (No API Key) ---")
    settings.MOCK_LLM = True
    settings.GEMINI_API_KEY = None

    # 1. Health
    r = client.get("/health")
    assert r.status_code == 200

    # 2. Tagging in mock mode
    from app.services.tagger import tag_items
    sample_items = [
        {"id": "TEST-1", "source": "playstore", "text": "App crashes during auto debit setup", "rating": 1, "date": "2026-01-01"},
        {"id": "TEST-2", "source": "survey", "text": "Returns were too low so I stopped", "rating": 2, "date": "2026-01-02"},
    ]
    tagged = tag_items(sample_items)
    assert len(tagged) == 2
    assert tagged[0].id == "TEST-1"
    assert tagged[0].main_driver in ["Other", "Cash crunch", "Low early returns"] or tagged[0].label_origin in ["ai_drafted", "fallback"]
    print(f"[PASS] Tagging works with MOCK_LLM=1 ({len(tagged)} items tagged)")

    # 3. Insights in mock mode
    r_ins = client.post("/api/insights/regenerate?dataset=preloaded")
    assert r_ins.status_code == 200
    ins_data = r_ins.json()
    assert ins_data["ai_summary_available"] is True
    assert len(ins_data["cards"]) == 3
    assert len(ins_data["suggested_questions"]) == 3
    for c in ins_data["cards"]:
        assert c["strength"] in ["Strong", "Medium", "Weak signal"]
        assert c["supporting_count"] == len(c["supporting_evidence_ids"])
    print(f"[PASS] Insights generate 3 cards and 3 questions with MOCK_LLM=1")

def test_configuration_no_key_no_mock():
    print("\n--- Testing Configuration B: No Key & MOCK_LLM=0 (Graceful degradation) ---")
    settings.MOCK_LLM = False
    settings.GEMINI_API_KEY = None

    # 1. App starts and serves health
    r = client.get("/health")
    assert r.status_code == 200
    print("[PASS] App starts without API key and responds with 200 ok")

    # 2. Dashboard works completely
    r_dash = client.get("/api/dashboard/summary")
    assert r_dash.status_code == 200
    assert r_dash.json()["total_items_collected"] == 1094
    print("[PASS] Full quantitative dashboard operational without API key")

    # 3. Insights returns computed stats and clear 'AI summary unavailable' state
    r_ins = client.post("/api/insights/regenerate?dataset=preloaded")
    assert r_ins.status_code == 200
    ins_data = r_ins.json()
    assert ins_data["ai_summary_available"] is False
    assert ins_data["message"] == "AI summary unavailable"
    assert ins_data["cards"] == []
    assert ins_data["suggested_questions"] == []
    assert len(ins_data["segment_view"]) == 4
    assert ins_data["total_records"] == 54
    print("[PASS] Insights returns computed segment view + stats with 'AI summary unavailable' message and zero fake text")

if __name__ == "__main__":
    test_configuration_mock_mode()
    test_configuration_no_key_no_mock()
    print("\n[SUCCESS] Both configurations verified!")

