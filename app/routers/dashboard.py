from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException, Response

from app.schema import (
    DashboardSummaryResponse,
    ChartsResponse,
    UnmetNeedsResponse,
    PaginatedEvidenceResponse,
    EvidenceItem,
)
from app.services.stats import (
    get_dashboard_summary,
    get_dashboard_charts,
    get_dashboard_unmet_needs,
    get_paginated_evidence,
    get_evidence_by_id,
    export_evidence_csv,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    source: Optional[List[str]] = Query(None),
    income_stability: Optional[List[str]] = Query(None),
    age_band: Optional[List[str]] = Query(None),
    influence: Optional[List[str]] = Query(None),
):
    return get_dashboard_summary(
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

@router.get("/charts", response_model=ChartsResponse)
def dashboard_charts(
    source: Optional[List[str]] = Query(None),
    income_stability: Optional[List[str]] = Query(None),
    age_band: Optional[List[str]] = Query(None),
    influence: Optional[List[str]] = Query(None),
):
    return get_dashboard_charts(
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

@router.get("/unmet-needs", response_model=UnmetNeedsResponse)
def dashboard_unmet_needs(
    source: Optional[List[str]] = Query(None),
    income_stability: Optional[List[str]] = Query(None),
    age_band: Optional[List[str]] = Query(None),
    influence: Optional[List[str]] = Query(None),
):
    return get_dashboard_unmet_needs(
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

@router.get("/evidence", response_model=PaginatedEvidenceResponse)
def dashboard_evidence(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    source: Optional[List[str]] = Query(None),
    income_stability: Optional[List[str]] = Query(None),
    age_band: Optional[List[str]] = Query(None),
    influence: Optional[List[str]] = Query(None),
):
    return get_paginated_evidence(
        page=page,
        page_size=page_size,
        search=search,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

@router.get("/export.csv")
def dashboard_export_csv(
    search: Optional[str] = Query(None),
    source: Optional[List[str]] = Query(None),
    income_stability: Optional[List[str]] = Query(None),
    age_band: Optional[List[str]] = Query(None),
    influence: Optional[List[str]] = Query(None),
):
    csv_text = export_evidence_csv(
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
        search=search,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evidence_export.csv"},
    )

@router.get("/evidence/{item_id}", response_model=EvidenceItem)
def dashboard_evidence_detail(
    item_id: str,
    dataset: Optional[str] = Query(None)
):
    record = get_evidence_by_id(item_id, dataset=dataset)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence item with id '{item_id}' not found",
        )
    return record

