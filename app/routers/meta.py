from fastapi import APIRouter
from app.config import settings
from app.schema import (
    AllowedValuesResponse,
    MetaResponse,
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)
from app.services.data_store import get_sources

router = APIRouter(prefix="/api", tags=["meta"])

@router.get("/meta", response_model=MetaResponse)
def get_meta():
    sources = get_sources()
    allowed_dict = {
        "stage": ALLOWED_STAGES,
        "main_driver": ALLOWED_MAIN_DRIVERS,
        "outcome": ALLOWED_OUTCOMES,
        "income_stability": ALLOWED_INCOME_STABILITIES,
        "age_band": ALLOWED_AGE_BANDS,
        "influence": ALLOWED_INFLUENCES,
    }
    return MetaResponse(
        allowed_values=allowed_dict,
        sources=sources,
        stage=ALLOWED_STAGES,
        main_driver=ALLOWED_MAIN_DRIVERS,
        outcome=ALLOWED_OUTCOMES,
        income_stability=ALLOWED_INCOME_STABILITIES,
        age_band=ALLOWED_AGE_BANDS,
        influence=ALLOWED_INFLUENCES,
        ai_available=bool(settings.GEMINI_API_KEY and not settings.MOCK_LLM),
    )

@router.get("/schema/allowed-values", response_model=AllowedValuesResponse)
def get_allowed_values():
    return AllowedValuesResponse(
        stage=ALLOWED_STAGES,
        main_driver=ALLOWED_MAIN_DRIVERS,
        outcome=ALLOWED_OUTCOMES,
        income_stability=ALLOWED_INCOME_STABILITIES,
        age_band=ALLOWED_AGE_BANDS,
        influence=ALLOWED_INFLUENCES,
    )
