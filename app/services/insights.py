import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Callable

import pandas as pd
from fastapi import HTTPException

from app.config import settings
from app.schema import (
    TaggedRecord,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    SegmentItem,
    InsightCard,
    InsightsComputedStats,
    InsightsResponse,
    UnmetNeedTheme,
)
from app.services.data_store import get_all_tagged_records
from app.services.job_manager import job_manager
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

NEGATIVE_OUTCOMES = {"Paused", "Stopped", "Reduced"}

def sanitize_dataset_key(dataset: str) -> str:
    cleaned = "".join(c for c in dataset.strip() if c.isalnum() or c in ("-", "_"))
    return cleaned if cleaned else "preloaded"

def get_dataset_records(dataset: str = "preloaded") -> List[TaggedRecord]:
    key = sanitize_dataset_key(dataset)
    if key == "preloaded":
        records = get_all_tagged_records()
        if not records:
            raise HTTPException(status_code=404, detail="Preloaded dataset is empty or not loaded.")
        return records

    # Query from job_manager
    job = job_manager.get_job(key)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{key}' not found. The upload session has expired or the server restarted. Please upload your dataset again."
        )

    rows = job.get("rows", [])
    if not rows:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset for job '{key}' contains 0 tagged rows or is still running."
        )

    return [TaggedRecord(**r) for r in rows]

def compute_dataset_stats(records: List[TaggedRecord]) -> InsightsComputedStats:
    total_records = len(records)

    # 1. Counts of main_driver (including all allowed drivers, default 0)
    main_driver_counts: Dict[str, int] = {d: 0 for d in ALLOWED_MAIN_DRIVERS}
    for r in records:
        if r.main_driver in main_driver_counts:
            main_driver_counts[r.main_driver] += 1
        else:
            main_driver_counts[r.main_driver] = 1

    # 2. Counts of outcome (including all allowed outcomes, default 0)
    outcome_counts: Dict[str, int] = {o: 0 for o in ALLOWED_OUTCOMES}
    for r in records:
        if r.outcome in outcome_counts:
            outcome_counts[r.outcome] += 1
        else:
            outcome_counts[r.outcome] = 1

    # 3. Share of Paused, Stopped or Reduced per income_stability group, with n for each group
    segment_view: List[SegmentItem] = []
    for group in ALLOWED_INCOME_STABILITIES:
        group_recs = [r for r in records if r.income_stability == group]
        n = len(group_recs)
        neg_count = sum(1 for r in group_recs if r.outcome in NEGATIVE_OUTCOMES)
        neg_share = (neg_count / n) if n > 0 else 0.0
        pct = round(neg_share * 100, 1)

        segment_view.append(
            SegmentItem(
                income_stability=group,
                n=n,
                negative_count=neg_count,
                negative_share=neg_share,
                percentage=pct,
            )
        )

    # 4. Top unmet-need themes (excluding 'none' and empty)
    valid_needs = [
        r.unmet_need.strip()
        for r in records
        if r.unmet_need and r.unmet_need.strip().lower() != "none"
    ]
    need_counts = pd.Series(valid_needs).value_counts() if valid_needs else pd.Series(dtype=int)
    top_5_needs = [
        UnmetNeedTheme(theme=theme, count=int(cnt))
        for theme, cnt in need_counts.head(5).items()
    ]

    # 5. Supporting item ids per driver
    supporting_ids_by_driver: Dict[str, List[str]] = {}
    for d in ALLOWED_MAIN_DRIVERS:
        matching_ids = [r.id for r in records if r.main_driver == d]
        if matching_ids:
            supporting_ids_by_driver[d] = matching_ids

    return InsightsComputedStats(
        total_records=total_records,
        main_driver_counts=main_driver_counts,
        outcome_counts=outcome_counts,
        segment_view=segment_view,
        top_unmet_needs=top_5_needs,
        supporting_ids_by_driver=supporting_ids_by_driver,
    )

def calculate_strength(count: int) -> Tuple[str, str]:
    """
    Strength tag by rule:
    - Strong = 6 or more supporting items
    - Medium = 3 to 5 supporting items
    - Weak signal = 1 to 2 supporting items
    With the count shown. No confidence percentages anywhere.
    """
    if count >= 6:
        strength = "Strong"
        label = f"Strong signal ({count} items)" if count != 1 else f"Strong signal ({count} item)"
    elif 3 <= count <= 5:
        strength = "Medium"
        label = f"Medium signal ({count} items)"
    else:
        strength = "Weak signal"
        label = f"Weak signal ({count} items)" if count != 1 else f"Weak signal ({count} item)"
    return strength, label

class InsightFilterDefinition:
    def __init__(
        self,
        description: str,
        match_fn: Callable[[TaggedRecord], bool],
        is_segment: bool = False,
        segment_name: Optional[str] = None,
        segment_base: Optional[int] = None,
        segment_count: Optional[int] = None,
        segment_text: Optional[str] = None,
        qualifying_ids: Optional[List[str]] = None,
    ):
        self.description = description
        self.match_fn = match_fn
        self.is_segment = is_segment
        self.segment_name = segment_name
        self.segment_base = segment_base
        self.segment_count = segment_count
        self.segment_text = segment_text
        self.qualifying_ids = qualifying_ids or []
        self.qualifying_ids_set = set(self.qualifying_ids)

def get_card_filters(
    records: List[TaggedRecord],
    computed_stats: InsightsComputedStats,
) -> List[InsightFilterDefinition]:
    """
    Defines the exact filter for each of the 3 insight cards.
    Supporting IDs and strength count come ONLY from records satisfying each filter.
    """
    filters: List[InsightFilterDefinition] = []

    # 1. Segment Claim (if a non-unclear segment has negative outcomes)
    valid_segments = [
        s for s in computed_stats.segment_view
        if s.income_stability != "Unclear" and s.negative_count > 0
    ]
    # Sort by negative_share descending, then negative_count descending
    valid_segments.sort(key=lambda s: (s.negative_share, s.negative_count), reverse=True)

    if valid_segments:
        top_seg = valid_segments[0]
        seg_inc = top_seg.income_stability

        if seg_inc == "Variable income (freelance/business)":
            short_label = "variable-income"
        elif seg_inc == "Fixed salary":
            short_label = "fixed-salary"
        elif seg_inc == "Student or dependent":
            short_label = "student or dependent"
        else:
            short_label = seg_inc.lower()

        seg_text = f"{top_seg.negative_count} of {top_seg.n} {short_label} records paused, stopped or reduced"
        desc = f"income_stability = '{seg_inc}' AND outcome in ('Paused', 'Stopped', 'Reduced')"

        def match_seg(r: TaggedRecord, target_inc=seg_inc) -> bool:
            return r.income_stability == target_inc and r.outcome in NEGATIVE_OUTCOMES

        matching_ids = [r.id for r in records if match_seg(r)]
        filters.append(
            InsightFilterDefinition(
                description=desc,
                match_fn=match_seg,
                is_segment=True,
                segment_name=seg_inc,
                segment_base=top_seg.n,
                segment_count=top_seg.negative_count,
                segment_text=seg_text,
                qualifying_ids=matching_ids,
            )
        )

    # 2. Driver Claims to complete exactly 3 cards
    preferred_drivers = [
        "Payment or mandate failure",
        "Low early returns",
        "Cash crunch",
        "Confusion about the app",
        "Expectation gap",
        "Outside influence",
        "Forgot about it",
        "Advice or question (no SIP experience)",
        "Praise or general feedback",
        "Working well / no issue",
        "Other",
    ]

    for d in preferred_drivers:
        if len(filters) >= 3:
            break
        cnt = computed_stats.main_driver_counts.get(d, 0)
        if cnt <= 0:
            continue

        desc = f"main_driver = '{d}'"
        def match_driver(r: TaggedRecord, target_driver=d) -> bool:
            return r.main_driver == target_driver

        matching_ids = [r.id for r in records if match_driver(r)]
        if not matching_ids:
            continue

        filters.append(
            InsightFilterDefinition(
                description=desc,
                match_fn=match_driver,
                is_segment=False,
                qualifying_ids=matching_ids,
            )
        )

    # Fallback if fewer than 3 filters found
    if len(filters) < 3:
        all_ids = [r.id for r in records]
        while len(filters) < 3:
            filters.append(
                InsightFilterDefinition(
                    description="General feedback records",
                    match_fn=lambda r: True,
                    is_segment=False,
                    qualifying_ids=all_ids,
                )
            )

    return filters[:3]

def generate_ai_insights(
    computed_stats: InsightsComputedStats,
    records: List[TaggedRecord],
) -> Tuple[bool, Optional[str], List[InsightCard], List[str]]:
    """
    Calls Gemini (or deterministic mock if enabled) with strict grounding:
    - Defines exact filter for each of the 3 insight cards.
    - Supporting IDs and strength count come ONLY from records satisfying each filter.
    - When a card talks about a segment, shows segment size and base in the text.
    - If a card cites records outside its filter, drops those IDs.
    - Returns (ai_available, message, cards, suggested_questions).
    """
    if not settings.is_ai_available:
        return False, "AI summary unavailable", [], []

    card_filters = get_card_filters(records, computed_stats)

    # Build prompt grounded strictly in stats, card filters, and quotes
    stats_summary = {
        "total_records": computed_stats.total_records,
        "main_driver_counts": {k: v for k, v in computed_stats.main_driver_counts.items() if v > 0},
        "outcome_counts": {k: v for k, v in computed_stats.outcome_counts.items() if v > 0},
        "segment_view": [
            {"income_stability": s.income_stability, "n": s.n, "negative_percentage": f"{s.percentage}%"}
            for s in computed_stats.segment_view
        ],
        "top_unmet_needs": [
            {"theme": t.theme, "count": t.count} for t in computed_stats.top_unmet_needs
        ],
    }

    prompt = (
        "You are an executive product research analyst for mutual funds SIP management.\n"
        "Generate strategic product insights based strictly on the provided evidence dataset.\n\n"
        "=== COMPUTED DATASET STATISTICS ===\n"
        f"{json.dumps(stats_summary, indent=2)}\n\n"
        "=== 3 MANDATORY INSIGHT CARDS (STRICTLY DEFINED BY DATA FILTERS) ===\n"
    )
    for idx, f in enumerate(card_filters, start=1):
        prompt += f"\n--- Card {idx} Filter: {f.description} ---\n"
        if f.is_segment and f.segment_text:
            prompt += f"Mandatory segment baseline fact to include in explanation: \"{f.segment_text}\"\n"
        prompt += f"Valid evidence IDs for Card {idx}: {json.dumps(f.qualifying_ids)}\n"
        sample_quotes = [
            {"id": r.id, "text": r.text[:140]}
            for r in records if r.id in f.qualifying_ids[:8]
        ]
        prompt += f"Sample quotes for Card {idx}:\n{json.dumps(sample_quotes, indent=2)}\n"

    prompt += (
        "\nINSTRUCTIONS:\n"
        "1. Produce exactly 3 insight cards corresponding to Card 1, Card 2, and Card 3 above.\n"
        "2. For each card:\n"
        "   - 'headline': One concise executive takeaway line.\n"
        "   - 'explanation': Exactly two sentences explaining the investor behavior and underlying friction, referencing the quotes. For segment cards, you MUST include the segment baseline fact.\n"
        "   - 'proposed_pm_action': Concrete, actionable product or UX solution.\n"
        "   - 'supporting_evidence_ids': Array of cited IDs. Cite ONLY from that card's valid evidence IDs list above!\n"
        "3. Produce exactly 3 'suggested_questions' highlighting critical qualitative or quantitative gaps in the data.\n"
        "4. Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "insight_cards": [\n'
        '    {"headline": "...", "explanation": "Sentence 1. Sentence 2.", "proposed_pm_action": "...", "supporting_evidence_ids": ["..."]}\n'
        "  ],\n"
        '  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]\n'
        "}\n"
    )

    system_instruction = (
        "You are an executive insights analyst. "
        "Ground every claim strictly in the provided dataset and specified card filters. "
        "Never cite IDs outside each card's valid evidence list. Return JSON only."
    )

    try:
        raw_response = llm_service.generate_json(prompt, system_instruction=system_instruction)
        parsed = json.loads(raw_response)

        raw_cards = parsed.get("insight_cards", [])
        if not isinstance(raw_cards, list) or len(raw_cards) == 0:
            logger.warning("AI response did not return a valid 'insight_cards' array.")
            return False, "AI summary unavailable", [], []

        validated_cards: List[InsightCard] = []
        for i in range(min(3, len(card_filters))):
            filter_def = card_filters[i]
            card = raw_cards[i] if i < len(raw_cards) else {}

            headline = str(card.get("headline", "")).strip() or f"Insight on {filter_def.description}"
            explanation = str(card.get("explanation", "")).strip()
            action = str(card.get("proposed_pm_action", "")).strip() or "Review and optimize user flows."

            raw_ids = card.get("supporting_evidence_ids", [])
            # Rule 3: If a card cites records outside its filter, drop those ids.
            valid_cited_ids = [
                str(cid).strip()
                for cid in raw_ids
                if str(cid).strip() in filter_def.qualifying_ids_set
            ]

            # Rule 1: Supporting ids and the strength count come ONLY from records that satisfy that filter.
            # The model may choose the wording but not the evidence set.
            # Combine validated model citations with qualifying records to ensure complete, grounded evidence
            supporting_ids = list(dict.fromkeys(valid_cited_ids + filter_def.qualifying_ids))

            # Rule 2: When a card talks about a segment, show the segment size and base in the text,
            # for example "4 of 7 variable-income records paused, stopped or reduced".
            if filter_def.is_segment and filter_def.segment_text:
                if filter_def.segment_text.lower() not in explanation.lower():
                    explanation = f"{filter_def.segment_text}. {explanation}"

            count = len(supporting_ids)
            strength, strength_label = calculate_strength(count)

            validated_cards.append(
                InsightCard(
                    headline=headline,
                    explanation=explanation,
                    proposed_pm_action=action,
                    supporting_evidence_ids=supporting_ids,
                    supporting_count=count,
                    strength=strength,
                    strength_label=strength_label,
                    filter=filter_def.description,
                )
            )

        raw_questions = parsed.get("suggested_questions", [])
        suggested_questions = [
            str(q).strip() for q in raw_questions if str(q).strip()
        ][:3]

        return True, None, validated_cards, suggested_questions

    except Exception as exc:
        logger.error(f"Error generating AI insights: {exc}")
        return False, "AI summary unavailable", [], []

class InsightsService:
    def __init__(self):
        self._cache_dir = settings.RUNTIME_DIR / "insights"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_insights(
        self,
        dataset: str = "preloaded",
        force_regenerate: bool = False,
    ) -> InsightsResponse:
        key = sanitize_dataset_key(dataset)
        cache_file = self._cache_dir / f"{key}.json"

        # Check runtime cache if regeneration is not requested
        if not force_regenerate and cache_file.exists():
            try:
                cached_dict = json.loads(cache_file.read_text(encoding="utf-8"))
                resp = InsightsResponse(**cached_dict)
                resp.cached = True
                return resp
            except Exception as e:
                logger.warning(f"Failed to read insights cache for {key}: {e}")

        # Compute fresh insights
        records = get_dataset_records(key)
        stats = compute_dataset_stats(records)
        ai_available, message, cards, questions = generate_ai_insights(stats, records)

        # Detect and assemble data quality notices
        warnings: List[str] = []
        if key != "preloaded":
            job = job_manager.get_job(key)
            if job:
                warnings.extend(job.get("data_warnings", []))

        has_ratings = any(r.rating is not None for r in records)
        if not has_ratings and not any("rating" in w.lower() for w in warnings):
            warnings.append("Rating column not provided. Numerical satisfaction scores are not available.")

        has_dates = any(r.date is not None for r in records)
        if not has_dates and not any("date" in w.lower() for w in warnings):
            warnings.append("Date column not provided. Timeline tracking is not available.")

        response = InsightsResponse(
            dataset=key,
            total_records=stats.total_records,
            computed_stats=stats,
            segment_view=stats.segment_view,
            ai_summary_available=ai_available,
            message=message,
            cards=cards,
            suggested_questions=questions,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cached=False,
            data_warnings=warnings,
        )

        # Cache results in runtime/
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(response.model_dump(), indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to write insights cache for {key}: {e}")

        return response

insights_service = InsightsService()

