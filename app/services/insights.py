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

MECHANISM_PATTERNS = {
    "timeout": re.compile(r"\btimeouts?\b", re.IGNORECASE),
    "server": re.compile(r"\bservers?\b", re.IGNORECASE),
    "delay": re.compile(r"\bdelay(s|ed|ing)?\b", re.IGNORECASE),
    "latency": re.compile(r"\blatenc(y|ies)\b", re.IGNORECASE),
    "bank": re.compile(r"\bbank(s|ing)?\b", re.IGNORECASE),
    "initial": re.compile(r"\binitial\b", re.IGNORECASE),
    "early": re.compile(r"\bearly\b", re.IGNORECASE),
    "structural": re.compile(r"\bstructural\b", re.IGNORECASE),
    "dissatisfaction": re.compile(r"\bdissatisfaction\b", re.IGNORECASE),
    "billing window": re.compile(r"\bbilling\s+windows?\b", re.IGNORECASE),
}

TIMING_PATTERN = re.compile(
    r"\b(timing|months?|stage|initial|early|years?|tenure|duration|periods?|timeline|horizon)\b",
    re.IGNORECASE,
)

FEATURE_CLAIM_PATTERN = re.compile(
    r"\b(struggle[s]? to (find|locate)|cannot find|can't find|unable to (find|locate)|difficult to find|hard to find|trouble finding|could not find|couldn't find)\b",
    re.IGNORECASE,
)

RECORD_FEATURE_FIND_PATTERN = re.compile(
    r"\b(find|locate|button|where|hidden|couldn't find|can't find|cannot find|search|dikhe|saamne)\b",
    re.IGNORECASE,
)

def has_feature_find_claim(text: str) -> bool:
    return bool(FEATURE_CLAIM_PATTERN.search(text))

def record_mentions_feature_find(text: str) -> bool:
    return bool(RECORD_FEATURE_FIND_PATTERN.search(text))

def count_words(text: str) -> int:
    return len(text.strip().split())

def find_forbidden_mechanism_words(text: str, allowed_context: str) -> List[str]:
    """
    Checks if text contains any mechanism word (timeout, server, delay, latency, bank,
    initial, early, structural, dissatisfaction, billing window)
    unless that word appears in allowed_context (cited unmet_need phrases or driver label).
    """
    allowed_context_lower = allowed_context.lower()
    forbidden_found = []
    for word_key, pat in MECHANISM_PATTERNS.items():
        if pat.search(text):
            if not pat.search(allowed_context_lower):
                forbidden_found.append(word_key)
    return forbidden_found

def compute_source_mix(records: List[TaggedRecord]) -> str:
    first_seen = {}
    counts = Counter()
    for idx, r in enumerate(records):
        src = r.source or "unknown"
        counts[src] += 1
        if src not in first_seen:
            first_seen[src] = idx
    sorted_items = sorted(counts.items(), key=lambda x: (-x[1], first_seen[x[0]]))
    return ", ".join(f"{cnt} {src}" for src, cnt in sorted_items) if sorted_items else "Unknown"

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
    counts = Counter(r.main_driver for r in records if r.main_driver)
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    parts = [f"{drv} {cnt}" for drv, cnt in sorted_items if cnt > 0]
    return ", ".join(parts) if parts else "Other 0"

def get_stage_breakdown_str(records: List[TaggedRecord]) -> str:
    counts = Counter(r.stage for r in records if r.stage)
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    parts = [f"{stg} {cnt}" for stg, cnt in sorted_items if cnt > 0]
    return ", ".join(parts) if parts else "Unclear 0"

def get_unmet_needs_str(records: List[TaggedRecord], max_items: int = 4) -> str:
    valid_needs = []
    seen = set()
    for r in records:
        if r.unmet_need:
            n = r.unmet_need.strip()
            if n and n.lower() != "none" and n not in seen:
                seen.add(n)
                valid_needs.append(n)
    return ", ".join(valid_needs[:max_items]) if valid_needs else ""

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

    # 3. Share of Paused, Stopped or Reduced per income_stability group,
    # computed among records with a known outcome (outcome != "Unknown") plus total n in brackets
    segment_view: List[SegmentItem] = []
    for group in ALLOWED_INCOME_STABILITIES:
        group_recs = [r for r in records if r.income_stability == group]
        n = len(group_recs)
        known_recs = [r for r in group_recs if r.outcome != "Unknown"]
        known_count = len(known_recs)
        neg_count = sum(1 for r in known_recs if r.outcome in NEGATIVE_OUTCOMES)
        neg_share = (neg_count / known_count) if known_count > 0 else 0.0
        pct = round(neg_share * 100, 1)
        display_str = f"{neg_count} of {known_count} (n={n})"

        segment_view.append(
            SegmentItem(
                income_stability=group,
                n=n,
                negative_count=neg_count,
                negative_share=neg_share,
                percentage=pct,
                known_outcome_count=known_count,
                display_text=display_str,
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
        segment_known_count: Optional[int] = None,
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
        self.segment_known_count = segment_known_count
        self.segment_text = segment_text
        self.qualifying_ids = qualifying_ids or []
        self.qualifying_ids_set = set(self.qualifying_ids)
        self.has_outcome_condition = has_outcome_condition
        self.target_driver = target_driver

def build_headline(
    filter_def: InsightFilterDefinition,
    qualifying_recs: List[TaggedRecord],
) -> str:
    n = len(qualifying_recs)
    if filter_def.is_drop_off:
        return f"{n} records report paused, stopped or reduced outcomes"
    elif filter_def.is_segment:
        label = "variable-income"
        if filter_def.segment_name:
            if "variable" in filter_def.segment_name.lower():
                label = "variable-income"
            elif "fixed" in filter_def.segment_name.lower():
                label = "fixed-salary"
            elif "student" in filter_def.segment_name.lower():
                label = "student or dependent"
            else:
                label = filter_def.segment_name.lower()
        k = filter_def.segment_count if filter_def.segment_count is not None else n
        m = filter_def.segment_known_count if filter_def.segment_known_count is not None else n
        return f"{k} of {m} {label} records with a known outcome paused, stopped or reduced"
    else:
        drv = filter_def.target_driver or "customer feedback"
        return f"{n} records cite {drv}"

def build_template_card(
    filter_def: InsightFilterDefinition,
    qualifying_recs: List[TaggedRecord]
) -> Tuple[str, str, str]:
    hl = build_headline(filter_def, qualifying_recs)
    if filter_def.is_drop_off:
        expl = "Investors pausing or stopping mutual fund commitments most frequently report cash constraints alongside portfolio performance considerations."
        act = "Implement proactive pause options and educational check-ins prior to scheduled SIP debits."
    elif filter_def.is_segment:
        expl = "Variable-income investors report cash flow difficulties and liquidity constraints when maintaining recurring mutual fund investments."
        act = "Introduce targeted flexibility options and automated pause controls."
    else:
        drv = filter_def.target_driver or "customer feedback"
        if drv == "Payment or mandate failure":
            expl = "Investors report recurring issues with autopay authorizations and payment execution when managing their recurring mutual fund investments."
            act = "Implement automated mandate retries and clearer status feedback for pending autopay authorizations."
        elif drv == "Low early returns":
            expl = "Investors report concerns with portfolio gains and market fluctuations across their active mutual fund tenures."
            act = "Provide benchmark comparisons and contextual guidance illustrating historical long-term market volatility."
        else:
            expl = f"Investors cite {drv.lower()} as a notable consideration across their mutual fund experiences."
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

        seg_text = f"{short_label} investors face cash-flow volatility during billing windows"
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
                segment_known_count=top_seg.known_outcome_count,
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
        stage_str = get_stage_breakdown_str(q_recs)
        source_mix_str = compute_source_mix(q_recs)
        unmet_list = [
            r.unmet_need.strip()
            for r in q_recs
            if r.unmet_need and r.unmet_need.strip().lower() != "none" and r.unmet_need.strip() != ""
        ]
        distinct_unmet = list(dict.fromkeys(unmet_list))[:4]

        prompt += f"\n--- Card {idx} Filter: {f.description} ---\n"
        prompt += f"Total qualifying records: {len(q_recs)}\n"
        prompt += f"Outcome breakdown: {outcome_str}\n"
        prompt += f"Driver breakdown: {driver_str}\n"
        prompt += f"Stage breakdown: {stage_str}\n"
        prompt += f"Source mix: {source_mix_str}\n"
        prompt += f"Exact unmet needs cited in records: {json.dumps(distinct_unmet)}\n"
        if f.is_segment and f.segment_text:
            prompt += f"Mandatory segment baseline fact: \"{f.segment_text}\"\n"
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
        "2. Ground every card strictly in the evidence.\n"
        "3. ONE SENTENCE & 25 WORDS LIMIT: For each card, write exactly ONE concise explanation sentence of at most 25 words using only the structured facts provided above.\n"
        "4. NO MECHANISMS OR CAUSES: Do not speculate on mechanisms, causes, timing, or technical reasons unless an exact listed unmet_need phrase states them.\n"
        "5. ZERO DIGITS CONSTRAINT: You MUST NOT output any digits (0-9), numbers, or counts anywhere in 'explanation'. Write purely qualitative descriptions without digits.\n"
        "6. FORBIDDEN CAUSAL WORDS: Unless the card's filter includes an outcome condition, you MUST NOT use any of these causal words: 'leads to', 'triggers', 'causes', 'drives', 'cancel', 'churn', 'drop out', 'discontinue' (or any of their variations).\n"
        "7. FORBIDDEN MECHANISM WORDS: You MUST NOT use any of the following mechanism or technical words unless that exact word appears in that card's cited unmet needs list or driver name: timeout, server, delay, latency, bank, initial, early, structural, dissatisfaction, billing window (or their plural/verb forms).\n"
        "8. CLAIMS MUST MATCH EVIDENCE: If you claim users 'struggle to find', 'cannot find', or similar about a feature, it must only appear if at least half of the card's cited records explicitly mention it; otherwise you MUST describe only the cash-flow pattern.\n"
        "9. DO NOT output any breakdown line ('Outcome breakdown:', 'Driver breakdown:', 'Stage breakdown:', 'Unmet needs cited:') in explanation. The backend strictly appends them in code.\n"
        "10. For each card:\n"
        "   - 'explanation': Exactly ONE qualitative sentence of at most 25 words without digits, mechanism words, or breakdown lines.\n"
        "   - 'proposed_pm_action': Concrete, actionable product or UX solution.\n"
        "   - 'supporting_evidence_ids': Array of cited IDs. Cite ONLY from that card's valid evidence IDs list above!\n"
        "11. Produce exactly 3 'suggested_questions' highlighting critical data gaps.\n"
        "12. Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "insight_cards": [\n'
        '    {"explanation": "One qualitative sentence of at most 25 words.", "proposed_pm_action": "...", "supporting_evidence_ids": ["..."]}\n'
        "  ],\n"
        '  "suggested_questions": ["Question 1?", "Question 2?", "Question 3?"]\n'
        "}\n"
    )

    if correction_feedback:
        prompt += f"\nCRITICAL CORRECTION REQUIRED:\n{correction_feedback}\n"

    system_instruction = (
        "You are an executive insights analyst. Ground every claim strictly in the provided dataset and specified card filters. "
        "Write exactly one sentence of at most 25 words per card. Never make causal claims without outcome filters. "
        "Never use unevidenced mechanism words. Return JSON only."
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
    - Headlines are generated in code from filter and counts.
    - Model must NOT output any digits or breakdown lines in explanation (at most 25 words).
    - Backend appends Outcome, Driver, Stage, and Unmet needs breakdown lines built in code.
    - Validates against digits, forbidden words, unevidenced mechanism words, length <= 25 words, and unverified feature find claims (retries once, then template).
    - Source mix is computed and attached to each card.
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
                expl = str(card.get("explanation", "")).strip()

                # Clean any self-generated breakdown lines before validation
                clean_expl = re.sub(
                    r"\s*(Outcome|Driver|Stage|Unmet\s+needs\s+cited)\s*breakdown:.*$",
                    "",
                    expl,
                    flags=re.IGNORECASE,
                ).strip()
                clean_expl = re.sub(r"\s*Unmet\s+needs\s+cited:.*$", "", clean_expl, flags=re.IGNORECASE).strip()

                q_recs = [records_by_id[cid] for cid in f.qualifying_ids if cid in records_by_id]
                allowed_ctx = " ".join(
                    [
                        f.target_driver or "",
                        f.description or "",
                        get_unmet_needs_str(q_recs, max_items=10),
                    ]
                )

                # 1. Reject digits
                if re.search(r"\d", clean_expl):
                    failed_reasons.append(
                        f"Card {i+1} explanation contains digits. Digits are strictly forbidden in AI narrative."
                    )

                # 2. Reject self-generated Outcome/Driver/Stage breakdown lines
                if any(b in expl.lower() for b in ["outcome breakdown", "driver breakdown", "stage breakdown", "unmet needs cited"]):
                    failed_reasons.append(
                        f"Card {i+1} contains breakdown lines. The backend automatically produces these lines."
                    )

                # 3. Forbidden causal words
                if not f.has_outcome_condition:
                    bad_words_expl = find_forbidden_words(clean_expl)
                    if bad_words_expl:
                        failed_reasons.append(
                            f"Card {i+1} ('{f.description}') contains forbidden words: {bad_words_expl}. "
                            f"Do NOT use 'leads to', 'triggers', 'causes', 'drives', 'cancel', 'churn', 'drop out', 'discontinue'."
                        )

                # 4. Forbidden mechanism words
                bad_mech = find_forbidden_mechanism_words(clean_expl, allowed_ctx)
                if bad_mech:
                    failed_reasons.append(
                        f"Card {i+1} contains unevidenced mechanism words: {bad_mech}. "
                        f"Do NOT use timeout, server, delay, latency, bank, initial, early, structural, dissatisfaction, billing window unless present in cited unmet needs."
                    )

                # 5. Length constraint (at most 25 words)
                if count_words(clean_expl) > 25:
                    failed_reasons.append(
                        f"Card {i+1} explanation has {count_words(clean_expl)} words (max 25 allowed)."
                    )

                # 6. Feature discoverability claim check
                if has_feature_find_claim(clean_expl):
                    find_count = sum(1 for r in q_recs if record_mentions_feature_find(r.text))
                    if find_count < (len(q_recs) / 2.0):
                        failed_reasons.append(
                            f"Card {i+1} claims users struggle to find/cannot find a feature, but only {find_count} of {len(q_recs)} records mention it (at least half required). Describe only the cash-flow pattern."
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
            driver_str = get_driver_breakdown_str(q_recs)
            source_mix = compute_source_mix(q_recs)
            template_hl, template_expl, template_act = build_template_card(filter_def, q_recs)

            # Headline is strictly built in code from filter and counts
            hl = build_headline(filter_def, q_recs)

            card = raw_cards[i] if i < len(raw_cards) else {}
            expl = str(card.get("explanation", "")).strip()
            act = str(card.get("proposed_pm_action", "")).strip()

            # Clean any model-generated breakdown lines if present
            clean_expl = re.sub(
                r"\s*(Outcome|Driver|Stage|Unmet\s+needs\s+cited)\s*breakdown:.*$",
                "",
                expl,
                flags=re.IGNORECASE,
            ).strip()
            clean_expl = re.sub(r"\s*Unmet\s+needs\s+cited:.*$", "", clean_expl, flags=re.IGNORECASE).strip()

            allowed_ctx = " ".join(
                [
                    filter_def.target_driver or "",
                    filter_def.description or "",
                    get_unmet_needs_str(q_recs, max_items=10),
                ]
            )

            # Check digit violations
            has_digits = bool(re.search(r"\d", clean_expl))

            # Check forbidden causal words
            card_has_forbidden = False
            if not filter_def.has_outcome_condition:
                if find_forbidden_words(clean_expl):
                    card_has_forbidden = True

            # Check forbidden mechanism words
            forbidden_mech = bool(find_forbidden_mechanism_words(clean_expl, allowed_ctx))

            # Check word count limit
            word_count_exceeded = count_words(clean_expl) > 25

            # Check feature claim threshold
            feature_claim_invalid = False
            if has_feature_find_claim(clean_expl):
                find_count = sum(1 for r in q_recs if record_mentions_feature_find(r.text))
                if find_count < (len(q_recs) / 2.0):
                    feature_claim_invalid = True

            # If card is invalid, empty, contains digits, forbidden causal/mechanism words,
            # exceeds 25 words, or has unverified feature claims, fall back to template sentence
            if (
                not clean_expl
                or has_digits
                or card_has_forbidden
                or forbidden_mech
                or word_count_exceeded
                or feature_claim_invalid
            ):
                clean_expl = template_expl
                act = act or template_act

            # Build backend-appended breakdown lines
            lines = [clean_expl]

            # 1. Outcome breakdown (always)
            lines.append(f"Outcome breakdown: {outcome_str}.")

            # 2. Driver breakdown (when filter spans several drivers)
            distinct_drivers = {r.main_driver for r in q_recs if r.main_driver}
            if len(distinct_drivers) > 1:
                lines.append(f"Driver breakdown: {driver_str}.")

            # 3. Stage breakdown (when the text mentions timing)
            if TIMING_PATTERN.search(clean_expl):
                stage_str = get_stage_breakdown_str(q_recs)
                lines.append(f"Stage breakdown: {stage_str}.")

            # 4. Unmet needs cited (distinct phrases, up to 4)
            unmet_str = get_unmet_needs_str(q_recs, max_items=4)
            if unmet_str:
                lines.append(f"Unmet needs cited: {unmet_str}.")

            final_expl = " ".join(lines)

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
                    explanation=final_expl,
                    proposed_pm_action=act or template_act,
                    supporting_evidence_ids=supporting_ids,
                    supporting_count=count,
                    strength=strength,
                    strength_label=strength_label,
                    filter=filter_def.description,
                    source_mix=source_mix,
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

        # Detect and assemble data quality notices (rating notice only for uploaded jobs)
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

