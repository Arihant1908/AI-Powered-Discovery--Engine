import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from collections import Counter

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

FORBIDDEN_PATTERNS = [
    re.compile(r"\bleads?\s+to\b", re.IGNORECASE),
    re.compile(r"\btriggers?\b|\btrigger(ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bcauses?\b|\bcaus(ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bdrives?\b|\bdriv(en|ing)?\b", re.IGNORECASE),
    re.compile(r"\bcancel(s|ed|led|ing|ling|lation|lations)?\b", re.IGNORECASE),
    re.compile(r"\bchurn(s|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bdrops?\s+out\b|\bdropp(ed|ing)\s+out\b|\bdrop-?outs?\b", re.IGNORECASE),
    re.compile(r"\bdiscontinu(e|es|ed|ing|ation|ations)?\b", re.IGNORECASE),
]

def find_forbidden_words(text: str) -> List[str]:
    found = []
    for pat in FORBIDDEN_PATTERNS:
        m = pat.search(text)
        if m:
            found.append(m.group(0))
    return found

def get_outcome_breakdown_str(records: List[TaggedRecord]) -> str:
    counts = Counter(r.outcome for r in records)
    order = ["Continuing", "Paused", "Stopped", "Reduced", "Unknown"]
    parts = []
    for out in order:
        if counts[out] > 0:
            parts.append(f"{counts[out]} {out}")
    for out, cnt in counts.items():
        if out not in order and cnt > 0:
            parts.append(f"{cnt} {out}")
    return ", ".join(parts) if parts else "0 Unknown"

def get_driver_breakdown_str(records: List[TaggedRecord]) -> str:
    counts = Counter(r.main_driver for r in records)
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    parts = [f"{cnt} {drv}" for drv, cnt in sorted_items if cnt > 0]
    return ", ".join(parts) if parts else "0 Other"

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
    - Strong = 6 or more supporting records
    - Medium = 3 to 5 supporting records
    - Weak signal = 1 to 2 supporting records
    With count shown and label saying 'records' (e.g., 'Medium signal, 4 records').
    No confidence percentages anywhere.
    """
    if count >= 6:
        strength = "Strong"
        label = f"Strong signal, {count} records"
    elif 3 <= count <= 5:
        strength = "Medium"
        label = f"Medium signal, {count} records"
    else:
        strength = "Weak signal"
        label = f"Weak signal, {count} record" if count == 1 else f"Weak signal, {count} records"
    return strength, label

class InsightFilterDefinition:
    def __init__(
        self,
        description: str,
        match_fn: Callable[[TaggedRecord], bool],
        is_segment: bool = False,
        is_drop_off: bool = False,
        segment_name: Optional[str] = None,
        segment_base: Optional[int] = None,
        segment_count: Optional[int] = None,
        segment_text: Optional[str] = None,
        qualifying_ids: Optional[List[str]] = None,
        has_outcome_condition: bool = False,
        target_driver: Optional[str] = None,
    ):
        self.description = description
        self.match_fn = match_fn
        self.is_segment = is_segment
        self.is_drop_off = is_drop_off
        self.segment_name = segment_name
        self.segment_base = segment_base
        self.segment_count = segment_count
        self.segment_text = segment_text
        self.qualifying_ids = qualifying_ids or []
        self.qualifying_ids_set = set(self.qualifying_ids)
        self.has_outcome_condition = has_outcome_condition
        self.target_driver = target_driver

def build_template_card(
    filter_def: InsightFilterDefinition,
    qualifying_recs: List[TaggedRecord]
) -> Tuple[str, str, str]:
    n = len(qualifying_recs)
    outcome_str = get_outcome_breakdown_str(qualifying_recs)
    driver_str = get_driver_breakdown_str(qualifying_recs)

    if filter_def.is_drop_off:
        hl = f"Drop-off drivers: analysis across {n} records"
        expl = (
            f"Among {n} records with outcome in Paused, Stopped, or Reduced, "
            f"the reported main drivers are: {driver_str}. "
            f"Outcome breakdown: {outcome_str}."
        )
        act = "Implement targeted retention interventions for top reported drop-off drivers."
    elif filter_def.is_segment:
        hl = f"{filter_def.segment_name}: {filter_def.segment_text}"
        expl = f"{filter_def.segment_text}. Outcome breakdown: {outcome_str}."
        act = "Introduce targeted flexibility options and automated pause controls."
    else:
        drv = filter_def.target_driver or "customer feedback"
        hl = f"{n} records cite {drv}"
        expl = f"{n} records cite {drv}: {outcome_str}. Feedback reports investor observations and operational friction across these records."
        act = f"Review user workflows and investor guidance regarding {drv}."
    return hl, expl, act

def get_card_filters(
    records: List[TaggedRecord],
    computed_stats: InsightsComputedStats,
) -> List[InsightFilterDefinition]:
    """
    Defines the exact filters for the 4 insight cards:
    1. Segment Claim (Variable income / top non-unclear segment)
    2. Drop-off drivers Card (among records with outcome in Paused, Stopped, Reduced, count by main_driver)
    3. Preferred driver 1 (Payment or mandate failure)
    4. Preferred driver 2 (Low early returns)
    """
    filters: List[InsightFilterDefinition] = []

    # 1. Segment Claim (if a non-unclear segment has negative outcomes)
    valid_segments = [
        s for s in computed_stats.segment_view
        if s.income_stability != "Unclear" and s.negative_count > 0
    ]
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
                has_outcome_condition=True,
            )
        )

    # 2. Drop-off drivers card (among records with outcome in Paused, Stopped, Reduced)
    def match_drop_off(r: TaggedRecord) -> bool:
        return r.outcome in NEGATIVE_OUTCOMES

    drop_off_ids = [r.id for r in records if match_drop_off(r)]
    if drop_off_ids:
        filters.append(
            InsightFilterDefinition(
                description="outcome in ('Paused', 'Stopped', 'Reduced')",
                match_fn=match_drop_off,
                is_drop_off=True,
                qualifying_ids=drop_off_ids,
                has_outcome_condition=True,
            )
        )

    # 3 & 4. Driver Claims to complete 4 cards
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
        if len(filters) >= 4:
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
                has_outcome_condition=False,
                target_driver=d,
            )
        )

    # Fallback if fewer than 4 filters found
    if len(filters) < 4:
        all_ids = [r.id for r in records]
        while len(filters) < 4:
            filters.append(
                InsightFilterDefinition(
                    description="General feedback records",
                    match_fn=lambda r: True,
                    is_segment=False,
                    qualifying_ids=all_ids,
                    has_outcome_condition=False,
                    target_driver="Feedback",
                )
            )

    return filters[:4]

def _build_generation_prompt(
    computed_stats: InsightsComputedStats,
    records: List[TaggedRecord],
    card_filters: List[InsightFilterDefinition],
    correction_feedback: Optional[str] = None,
) -> Tuple[str, str]:
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

    records_by_id = {r.id: r for r in records}

    prompt = (
        "You are an executive product research analyst for mutual funds SIP management.\n"
        "Generate strategic product insights based strictly on the provided evidence dataset.\n\n"
        "=== COMPUTED DATASET STATISTICS ===\n"
        f"{json.dumps(stats_summary, indent=2)}\n\n"
        f"=== {len(card_filters)} MANDATORY INSIGHT CARDS (STRICTLY DEFINED BY DATA FILTERS) ===\n"
    )

    for idx, f in enumerate(card_filters, start=1):
        q_recs = [records_by_id[cid] for cid in f.qualifying_ids if cid in records_by_id]
        outcome_str = get_outcome_breakdown_str(q_recs)
        driver_str = get_driver_breakdown_str(q_recs)

        prompt += f"\n--- Card {idx} Filter: {f.description} ---\n"
        prompt += f"Total qualifying records: {len(q_recs)}\n"
        prompt += f"Outcome breakdown for Card {idx}: {outcome_str}\n"
        prompt += f"Driver breakdown for Card {idx}: {driver_str}\n"
        if f.is_segment and f.segment_text:
            prompt += f"Mandatory segment baseline fact to include in explanation: \"{f.segment_text}\"\n"
        if f.is_drop_off:
            prompt += f"Mandatory drop-off driver fact: Among records with outcome in Paused, Stopped, or Reduced, count by main_driver: {driver_str}\n"

        prompt += f"Valid evidence IDs for Card {idx}: {json.dumps(f.qualifying_ids)}\n"
        sample_quotes = [
            {"id": r.id, "text": r.text[:140]}
            for r in q_recs[:8]
        ]
        prompt += f"Sample quotes for Card {idx}:\n{json.dumps(sample_quotes, indent=2)}\n"

    prompt += (
        f"\nINSTRUCTIONS:\n"
        f"1. Produce exactly {len(card_filters)} insight cards corresponding to the cards above.\n"
        "2. Ground every card strictly in the evidence. Use ONLY words the data supports ('cite', 'mention', 'report') with counts, for example '7 records cite Low early returns: 4 Continuing, 1 Paused, 1 Reduced, 1 Unknown'.\n"
        "3. FORBIDDEN WORDS: Unless the card's filter includes an outcome condition, you MUST NOT use any of these causal words: 'leads to', 'triggers', 'causes', 'drives', 'cancel', 'churn', 'drop out', 'discontinue' (or any of their variations).\n"
        "4. Show the exact outcome breakdown on EVERY card's explanation.\n"
        "5. For each card:\n"
        "   - 'headline': One concise takeaway line (e.g. '7 records cite Low early returns').\n"
        "   - 'explanation': Two sentences explaining the observations, citing counts and quotes, including the exact outcome breakdown.\n"
        "   - 'proposed_pm_action': Concrete, actionable product or UX solution.\n"
        "   - 'supporting_evidence_ids': Array of cited IDs. Cite ONLY from that card's valid evidence IDs list above!\n"
        "6. Produce exactly 3 'suggested_questions' highlighting critical data gaps.\n"
        "7. Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "insight_cards": [\n'
        '    {"headline": "...", "explanation": "Sentence 1. Sentence 2. Outcome breakdown: ...", "proposed_pm_action": "...", "supporting_evidence_ids": ["..."]}\n'
        "  ],\n"
        '  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]\n'
        "}\n"
    )

    if correction_feedback:
        prompt += f"\nCRITICAL CORRECTION REQUIRED:\n{correction_feedback}\n"

    system_instruction = (
        "You are an executive insights analyst. Ground every claim strictly in the provided dataset and specified card filters. "
        "Never make causal claims without outcome filters. Never use forbidden words. Return JSON only."
    )
    return prompt, system_instruction

def generate_ai_insights(
    computed_stats: InsightsComputedStats,
    records: List[TaggedRecord],
) -> Tuple[bool, Optional[str], List[InsightCard], List[str]]:
    """
    Calls Gemini (or deterministic mock if enabled) with strict grounding:
    - Defines exact filter for each insight card.
    - Supporting IDs and strength count come ONLY from records satisfying each filter.
    - Passes outcome and driver breakdown of qualifying records.
    - Enforces supported words ('cite', 'mention', 'report') with counts.
    - Forbids causal words ('leads to', 'triggers', 'causes', 'drives', 'cancel', 'churn', 'drop out', 'discontinue')
      unless filter includes an outcome condition.
    - Retries once if forbidden words or invalid cards found; falls back to template sentence built from counts.
    - Shows outcome breakdown on every card.
    - Strength tag label says 'records'.
    """
    if not settings.is_ai_available:
        return False, "AI summary unavailable", [], []

    card_filters = get_card_filters(records, computed_stats)
    records_by_id = {r.id: r for r in records}

    prompt, system_instruction = _build_generation_prompt(computed_stats, records, card_filters)

    def parse_and_validate_cards(
        raw_json_str: str,
    ) -> Tuple[bool, Optional[str], List[Dict[str, Any]], List[str]]:
        try:
            parsed = json.loads(raw_json_str)
            raw_cards = parsed.get("insight_cards", [])
            raw_questions = parsed.get("suggested_questions", [])
            if not isinstance(raw_cards, list) or len(raw_cards) == 0:
                return False, "Missing insight_cards array in response", [], []

            failed_reasons = []
            for i, f in enumerate(card_filters):
                if i >= len(raw_cards):
                    failed_reasons.append(f"Missing card {i+1}")
                    continue
                card = raw_cards[i]
                hl = str(card.get("headline", "")).strip()
                expl = str(card.get("explanation", "")).strip()

                if not f.has_outcome_condition:
                    bad_words_hl = find_forbidden_words(hl)
                    bad_words_expl = find_forbidden_words(expl)
                    bad_all = bad_words_hl + bad_words_expl
                    if bad_all:
                        failed_reasons.append(
                            f"Card {i+1} ('{f.description}') contains forbidden words: {bad_all}. "
                            f"Do NOT use 'leads to', 'triggers', 'causes', 'drives', 'cancel', 'churn', 'drop out', 'discontinue'."
                        )

            is_valid = len(failed_reasons) == 0
            err_msg = "; ".join(failed_reasons) if failed_reasons else None
            return is_valid, err_msg, raw_cards, raw_questions
        except Exception as e:
            return False, str(e), [], []

    try:
        raw_response = llm_service.generate_json(prompt, system_instruction=system_instruction)
        is_valid, err_msg, raw_cards, raw_questions = parse_and_validate_cards(raw_response)

        # Retry once if validation failed
        if not is_valid:
            logger.warning(f"AI insights validation failed: {err_msg}. Retrying once...")
            retry_prompt, retry_sys = _build_generation_prompt(
                computed_stats, records, card_filters, correction_feedback=err_msg
            )
            retry_raw = llm_service.generate_json(retry_prompt, system_instruction=retry_sys)
            retry_valid, retry_err, retry_cards, retry_questions = parse_and_validate_cards(retry_raw)
            if retry_valid:
                raw_cards = retry_cards
                raw_questions = retry_questions
                is_valid = True
            else:
                logger.warning(f"AI insights retry failed: {retry_err}. Falling back to template sentences for failing cards.")

        validated_cards: List[InsightCard] = []

        for i, filter_def in enumerate(card_filters):
            q_recs = [records_by_id[cid] for cid in filter_def.qualifying_ids if cid in records_by_id]
            outcome_str = get_outcome_breakdown_str(q_recs)
            template_hl, template_expl, template_act = build_template_card(filter_def, q_recs)

            card = raw_cards[i] if i < len(raw_cards) else {}
            hl = str(card.get("headline", "")).strip()
            expl = str(card.get("explanation", "")).strip()
            act = str(card.get("proposed_pm_action", "")).strip()

            # Check if this card violates forbidden words
            card_has_forbidden = False
            if not filter_def.has_outcome_condition:
                if find_forbidden_words(hl) or find_forbidden_words(expl):
                    card_has_forbidden = True

            # If card is invalid, empty, or has forbidden words, fall back to template sentence
            if not hl or not expl or card_has_forbidden:
                hl = template_hl
                expl = template_expl
                act = act or template_act

            # Segment card baseline fact check
            if filter_def.is_segment and filter_def.segment_text:
                if filter_def.segment_text.lower() not in expl.lower():
                    expl = f"{filter_def.segment_text}. {expl}"

            # Ensure outcome breakdown is shown on every card
            if outcome_str.lower() not in expl.lower():
                expl = f"{expl} Outcome breakdown: {outcome_str}."

            # Evidence IDs filtering
            raw_ids = card.get("supporting_evidence_ids", []) if isinstance(card, dict) else []
            valid_cited_ids = [
                str(cid).strip()
                for cid in raw_ids
                if str(cid).strip() in filter_def.qualifying_ids_set
            ]
            supporting_ids = list(dict.fromkeys(valid_cited_ids + filter_def.qualifying_ids))

            count = len(supporting_ids)
            strength, strength_label = calculate_strength(count)

            validated_cards.append(
                InsightCard(
                    headline=hl,
                    explanation=expl,
                    proposed_pm_action=act or template_act,
                    supporting_evidence_ids=supporting_ids,
                    supporting_count=count,
                    strength=strength,
                    strength_label=strength_label,
                    filter=filter_def.description,
                )
            )

        suggested_questions = [
            str(q).strip() for q in raw_questions if str(q).strip()
        ][:3]
        if not suggested_questions:
            suggested_questions = [
                "What percentage of paused SIPs resume within 60 days of cancellation flow interventions?",
                "How do payment mandate retries perform across different banking partner cohorts?",
                "Does an onboarding volatility explainer decrease early drop-offs among first-time investors?"
            ]

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

