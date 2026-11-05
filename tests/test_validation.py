import pytest
from pydantic import ValidationError
from app.schema import FeedbackTaggingItem, StageEnum, MainDriverEnum, OutcomeEnum
from app.config import Settings

def test_feedback_tagging_item_valid():
    item = FeedbackTaggingItem(
        id="test-1",
        stage=StageEnum.MONTH_2_3,
        main_driver=MainDriverEnum.LOW_EARLY_RETURNS,
        outcome=OutcomeEnum.PAUSED,
        unmet_need="Reassurance that the SIP is working",
        income_stability="Fixed salary",
        age_band="23-27",
        influence="Friends"
    )
    assert item.stage == "Month 2-3"
    assert item.main_driver == "Low early returns"
    assert item.outcome == "Paused"

def test_feedback_tagging_item_invalid_stage():
    with pytest.raises(ValidationError):
        FeedbackTaggingItem(
            id="test-2",
            stage="Month 99",  # Invalid stage
            main_driver="Low early returns",
            outcome="Paused",
            unmet_need="none",
            income_stability="Unclear",
            age_band="Unclear",
            influence="Unclear"
        )

def test_settings_ai_availability_without_key():
    settings = Settings()
    # Explicitly verify without API key
    settings.GEMINI_API_KEY = None
    settings.MOCK_LLM = False
    assert not settings.is_ai_available

