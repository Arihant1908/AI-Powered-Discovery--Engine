import math
import json
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
import pandas as pd
import numpy as np

from app.config import settings
from app.schema import (
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    DashboardSummaryResponse,
    ChartsResponse,
    ChartItem,
    UnmetNeedsResponse,
    UnmetNeedTheme,
    EvidenceItem,
    PaginatedEvidenceResponse,
)

logger = logging.getLogger(__name__)

from app.services.data_store import (
    get_corpus_df,
    get_tagged_df as get_engine_df,
    get_tagged_record_by_id,
)

def normalize_filter_values(values: Optional[List[str]]) -> Optional[List[str]]:
    if not values:
        return None
    res = []
    for val in values:
        if val is None:
            continue
        for part in str(val).split(","):
            cleaned = part.strip()
            if cleaned:
                res.append(cleaned)
    return res if res else None

def filter_engine_data(
    df: pd.DataFrame,
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
    search: Optional[str] = None,
) -> pd.DataFrame:
    filtered = df.copy()

    sources = normalize_filter_values(source)
    if sources:
        sources_lower = [s.lower() for s in sources]
        filtered = filtered[filtered["source"].astype(str).str.lower().isin(sources_lower)]

    income_stabs = normalize_filter_values(income_stability)
    if income_stabs:
        income_lower = [s.lower() for s in income_stabs]
        filtered = filtered[filtered["income_stability"].astype(str).str.lower().isin(income_lower)]

    age_bands = normalize_filter_values(age_band)
    if age_bands:
        age_lower = [s.lower() for s in age_bands]
        filtered = filtered[filtered["age_band"].astype(str).str.lower().isin(age_lower)]

    influences = normalize_filter_values(influence)
    if influences:
        inf_lower = [s.lower() for s in influences]
        filtered = filtered[filtered["influence"].astype(str).str.lower().isin(inf_lower)]

    if search and search.strip():
        search_term = search.strip()
        filtered = filtered[filtered["text"].astype(str).str.contains(search_term, case=False, na=False)]

    return filtered

def get_dashboard_summary(
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
) -> DashboardSummaryResponse:
    corpus_df = get_corpus_df()
    engine_df = get_engine_df()

    filtered_engine = filter_engine_data(
        engine_df,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

    has_filters = bool(source or income_stability or age_band or influence)
    sources = normalize_filter_values(source)

    if sources:
        sources_lower = [s.lower() for s in sources]
        filtered_corpus = corpus_df[corpus_df["source"].astype(str).str.lower().isin(sources_lower)]
    else:
        filtered_corpus = corpus_df

    labelled_count = len(filtered_engine)
    deep_interviews = int((filtered_engine["source"].astype(str).str.lower() == "interviews").sum())

    # Empty filter results return zeros and not errors
    if labelled_count == 0 and has_filters:
        return DashboardSummaryResponse(
            total_items_collected=0,
            distinct_sources=0,
            labelled_evidence_items=0,
            deep_interviews=0,
        )

    # Total items collected
    if sources:
        total_collected = len(filtered_corpus)
    else:
        total_collected = len(corpus_df)

    # Number of distinct sources
    if has_filters:
        sources_in_engine = set(filtered_engine["source"].dropna().unique())
        distinct_sources = len(sources_in_engine)
    else:
        all_sources = set(corpus_df["source"].dropna().unique()) | set(engine_df["source"].dropna().unique())
        distinct_sources = len(all_sources)

    return DashboardSummaryResponse(
        total_items_collected=total_collected,
        distinct_sources=distinct_sources,
        labelled_evidence_items=labelled_count,
        deep_interviews=deep_interviews,
    )

def get_dashboard_charts(
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
) -> ChartsResponse:
    engine_df = get_engine_df()
    filtered = filter_engine_data(
        engine_df,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

    total_records = len(filtered)
    driver_counts_series = filtered["main_driver"].value_counts()
    outcome_counts_series = filtered["outcome"].value_counts()

    main_driver_items: List[ChartItem] = []
    main_driver_counts: Dict[str, int] = {}
    main_driver_percentages: Dict[str, float] = {}

    for driver in ALLOWED_MAIN_DRIVERS:
        cnt = int(driver_counts_series.get(driver, 0))
        pct = round((cnt / total_records * 100), 2) if total_records > 0 else 0.0
        main_driver_items.append(ChartItem(label=driver, count=cnt, percentage=pct))
        main_driver_counts[driver] = cnt
        main_driver_percentages[driver] = pct

    outcome_items: List[ChartItem] = []
    outcome_counts: Dict[str, int] = {}
    outcome_percentages: Dict[str, float] = {}

    for outcome in ALLOWED_OUTCOMES:
        cnt = int(outcome_counts_series.get(outcome, 0))
        pct = round((cnt / total_records * 100), 2) if total_records > 0 else 0.0
        outcome_items.append(ChartItem(label=outcome, count=cnt, percentage=pct))
        outcome_counts[outcome] = cnt
        outcome_percentages[outcome] = pct

    return ChartsResponse(
        main_driver=main_driver_items,
        outcome=outcome_items,
        total_records=total_records,
        counts={
            "main_driver": main_driver_counts,
            "outcome": outcome_counts,
        },
        percentages={
            "main_driver": main_driver_percentages,
            "outcome": outcome_percentages,
        },
    )

def get_dashboard_unmet_needs(
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
) -> UnmetNeedsResponse:
    engine_df = get_engine_df()
    filtered = filter_engine_data(
        engine_df,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
    )

    if len(filtered) == 0:
        return UnmetNeedsResponse(themes=[], ai_available=settings.is_ai_available, ai_grouped=False)

    # Exclude "none", empty, NaN
    needs_series = filtered["unmet_need"].dropna().astype(str).str.strip()
    valid_needs = needs_series[(needs_series.str.lower() != "none") & (needs_series != "")]

    if len(valid_needs) == 0:
        return UnmetNeedsResponse(themes=[], ai_available=settings.is_ai_available, ai_grouped=False)

    # If AI is available and API key is set, attempt AI grouping
    if settings.is_ai_available and settings.GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            phrases_list = valid_needs.tolist()
            prompt = (
                "You are a research analyst. Group the following user unmet needs into at most 5 concise themes. "
                "For each theme, count the number of matching items. "
                "Return ONLY a JSON array of objects with keys 'theme' (string) and 'count' (integer), sorted by count descending.\n"
                f"Needs:\n{json.dumps(phrases_list)}"
            )
            ai_response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            parsed = json.loads(ai_response.text)
            if isinstance(parsed, list) and len(parsed) > 0:
                ai_themes = [
                    UnmetNeedTheme(theme=str(item.get("theme", "Other")), count=int(item.get("count", 1)))
                    for item in parsed[:5]
                ]
                return UnmetNeedsResponse(
                    themes=ai_themes,
                    ai_available=True,
                    ai_grouped=True,
                )
        except Exception as e:
            logger.warning(f"AI grouping failed, falling back to normalised phrase grouping: {e}")

    # Fallback: group by exact normalised phrase
    phrase_counts = valid_needs.value_counts()
    top_5 = phrase_counts.head(5)

    themes = [
        UnmetNeedTheme(theme=theme, count=int(count))
        for theme, count in top_5.items()
    ]

    return UnmetNeedsResponse(
        themes=themes,
        ai_available=settings.is_ai_available,
        ai_grouped=False,
    )

def get_paginated_evidence(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
) -> PaginatedEvidenceResponse:
    engine_df = get_engine_df()
    filtered = filter_engine_data(
        engine_df,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
        search=search,
    )

    total = len(filtered)
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    start = (page - 1) * page_size
    end = start + page_size

    sliced = filtered.iloc[start:end]
    records = sliced.replace({np.nan: None}).to_dict(orient="records")
    items = [EvidenceItem(**rec) for rec in records]

    return PaginatedEvidenceResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

def get_evidence_by_id(item_id: str, dataset: Optional[str] = None) -> Optional[EvidenceItem]:
    target_id = item_id.strip().lower()
    if dataset and dataset != "preloaded":
        from app.services.job_manager import job_manager
        job = job_manager.get_job(dataset)
        if job:
            for r in job.get("rows", []):
                if str(r.get("id", "")).strip().lower() == target_id:
                    return EvidenceItem(**r)

    # Check preloaded
    rec = get_tagged_record_by_id(item_id)
    if rec:
        return rec

    # Check jobs as fallback
    try:
        from app.services.job_manager import job_manager
        for job_id, job in job_manager._jobs.items():
            for r in job.get("rows", []):
                if str(r.get("id", "")).strip().lower() == target_id:
                    return EvidenceItem(**r)
    except Exception:
        pass

    return None

def export_evidence_csv(
    source: Optional[List[str]] = None,
    income_stability: Optional[List[str]] = None,
    age_band: Optional[List[str]] = None,
    influence: Optional[List[str]] = None,
    search: Optional[str] = None,
) -> str:
    engine_df = get_engine_df()
    filtered = filter_engine_data(
        engine_df,
        source=source,
        income_stability=income_stability,
        age_band=age_band,
        influence=influence,
        search=search,
    )
    return filtered.to_csv(index=False)

