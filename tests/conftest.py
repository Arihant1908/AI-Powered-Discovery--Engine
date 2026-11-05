import pytest
from app.config import settings

@pytest.fixture(autouse=True)
def default_mock_llm(monkeypatch):
    """
    Ensure the test suite uses deterministic mock LLM for rapid, hermetic testing,
    unless explicitly overridden in a test.
    """
    monkeypatch.setattr(settings, "MOCK_LLM", True)

