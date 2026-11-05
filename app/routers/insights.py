from typing import Optional
from fastapi import APIRouter, Query, Body, HTTPException

from app.schema import InsightsResponse, RegenerateInsightsRequest
from app.services.insights import insights_service

router = APIRouter(prefix="/api/insights", tags=["insights"])

@router.get("", response_model=InsightsResponse)
def get_insights(
    dataset: str = Query("preloaded", description="Dataset identifier: 'preloaded' or an upload <job_id>"),
):
    """
    Returns computed analytics (driver & outcome counts, segment shares, unmet needs)
    and AI-generated or cached insight cards and suggested questions.
    """
    return insights_service.get_insights(dataset=dataset, force_regenerate=False)

@router.post("/regenerate", response_model=InsightsResponse)
def regenerate_insights(
    dataset: Optional[str] = Query(None, description="Dataset identifier: 'preloaded' or an upload <job_id>"),
    req: Optional[RegenerateInsightsRequest] = Body(None),
):
    """
    Forces regeneration of AI insights, bypassing and updating the runtime cache.
    """
    target_dataset = "preloaded"
    if req and req.dataset:
        target_dataset = req.dataset
    elif dataset:
        target_dataset = dataset

    return insights_service.get_insights(dataset=target_dataset, force_regenerate=True)

