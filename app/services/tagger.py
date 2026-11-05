import json
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from app.config import settings
from app.schema import (
    TaggedRecord,
    RawItem,
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)
from app.services.llm import llm_service
from app.services.pii import remove_pii

logger = logging.getLogger(__name__)

FALLBACK_VALUES = {
    "stage": "Unclear",
    "main_driver": "Other",
    "outcome": "Unknown",
    "unmet_need": "none",
    "income_stability": "Unclear",
    "age_band": "Unclear",
    "influence": "Unclear",
    "label_origin": "fallback",
}

def get_system_prompt() -> str:
    prompt_file = settings.DATA_DIR / "tagging_prompt.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    return ""

def is_valid_tag_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if "id" not in item:
        return False
    if str(item.get("stage")).strip() not in ALLOWED_STAGES:
        return False
    if str(item.get("main_driver")).strip() not in ALLOWED_MAIN_DRIVERS:
        return False
    if str(item.get("outcome")).strip() not in ALLOWED_OUTCOMES:
        return False
    if str(item.get("income_stability")).strip() not in ALLOWED_INCOME_STABILITIES:
        return False
    if str(item.get("age_band")).strip() not in ALLOWED_AGE_BANDS:
        return False
    if str(item.get("influence")).strip() not in ALLOWED_INFLUENCES:
        return False
    return True

def _parse_llm_json(raw_text: str) -> Optional[List[Dict[str, Any]]]:
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
        return None
    except Exception:
        return None

def tag_batch(batch: List[Dict[str, Any]], system_prompt: str) -> List[TaggedRecord]:
    """
    Tags a single batch of up to 20 items.
    Validates every item against allowed lists. Retries once if JSON is invalid
    or values are not allowed, then falls back to Other / Unknown / Unclear
    for any failing item and marks it as 'fallback'. Never crashes the whole batch.
    """
    if not batch:
        return []

    # Clean PII before sending to model
    cleaned_payload = [
        {
            "id": str(item["id"]).strip(),
            "text": remove_pii(str(item.get("text", "")))
        }
        for item in batch
    ]

    # Attempt 1: Call LLM
    raw_response = llm_service.generate_json(
        prompt=json.dumps(cleaned_payload),
        system_instruction=system_prompt,
    )
    parsed = _parse_llm_json(raw_response)

    # If first attempt returned invalid JSON, retry once
    if parsed is None:
        logger.warning("Batch JSON parsing failed on attempt 1. Retrying once...")
        raw_response = llm_service.generate_json(
            prompt=json.dumps(cleaned_payload),
            system_instruction=system_prompt,
        )
        parsed = _parse_llm_json(raw_response)

    # Index parsed results by ID
    parsed_by_id: Dict[str, Dict[str, Any]] = {}
    if parsed is not None:
        for idx, obj in enumerate(parsed):
            if isinstance(obj, dict):
                obj_id = str(obj.get("id", "")).strip().lower()
                if obj_id:
                    parsed_by_id[obj_id] = obj
                elif idx < len(batch):
                    # Positional fallback if ID was omitted in model response
                    expected_id = str(batch[idx]["id"]).strip().lower()
                    parsed_by_id[expected_id] = obj

    # Identify any invalid items that need a single retry
    invalid_indices = []
    validated_results: Dict[str, Dict[str, Any]] = {}

    for idx, item in enumerate(batch):
        item_id = str(item["id"]).strip().lower()
        candidate = parsed_by_id.get(item_id)
        if candidate and is_valid_tag_item(candidate):
            validated_results[item_id] = {
                "stage": str(candidate["stage"]).strip(),
                "main_driver": str(candidate["main_driver"]).strip(),
                "outcome": str(candidate["outcome"]).strip(),
                "unmet_need": str(candidate.get("unmet_need", "none")).strip() or "none",
                "income_stability": str(candidate["income_stability"]).strip(),
                "age_band": str(candidate["age_band"]).strip(),
                "influence": str(candidate["influence"]).strip(),
                "label_origin": "ai_drafted",
            }
        else:
            invalid_indices.append(idx)

    # If some items failed validation, retry those specific items once
    if invalid_indices:
        retry_payload = [
            cleaned_payload[idx]
            for idx in invalid_indices
        ]
        retry_raw = llm_service.generate_json(
            prompt=json.dumps(retry_payload),
            system_instruction=system_prompt,
        )
        retry_parsed = _parse_llm_json(retry_raw)
        if retry_parsed:
            for idx, obj in enumerate(retry_parsed):
                if isinstance(obj, dict):
                    obj_id = str(obj.get("id", "")).strip().lower()
                    if not obj_id and idx < len(retry_payload):
                        obj_id = retry_payload[idx]["id"].lower()
                    if obj_id and is_valid_tag_item(obj):
                        validated_results[obj_id] = {
                            "stage": str(obj["stage"]).strip(),
                            "main_driver": str(obj["main_driver"]).strip(),
                            "outcome": str(obj["outcome"]).strip(),
                            "unmet_need": str(obj.get("unmet_need", "none")).strip() or "none",
                            "income_stability": str(obj["income_stability"]).strip(),
                            "age_band": str(obj["age_band"]).strip(),
                            "influence": str(obj["influence"]).strip(),
                            "label_origin": "ai_drafted",
                        }

    # Construct final TaggedRecord instances in exact original order and with original IDs
    results: List[TaggedRecord] = []
    for item in batch:
        orig_id = str(item["id"]).strip()
        lookup_id = orig_id.lower()

        item_tags = validated_results.get(lookup_id)
        if item_tags is None:
            # Fallback for that specific item
            item_tags = FALLBACK_VALUES.copy()

        tagged_rec = TaggedRecord(
            id=orig_id,
            source=str(item.get("source", "unknown")),
            date=str(item["date"]) if item.get("date") is not None else None,
            text=str(item.get("text", "")),
            stage=item_tags["stage"],
            main_driver=item_tags["main_driver"],
            outcome=item_tags["outcome"],
            unmet_need=item_tags["unmet_need"],
            income_stability=item_tags["income_stability"],
            age_band=item_tags["age_band"],
            influence=item_tags["influence"],
            label_origin=item_tags["label_origin"],
        )
        results.append(tagged_rec)

    return results

def tag_items(
    items: List[Union[Dict[str, Any], RawItem]],
    batch_size: int = 20
) -> List[TaggedRecord]:
    """
    Tags items in batches of 20 using tagging_prompt.txt as system prompt.
    Returns results in the exact same order and with the exact same IDs as the input.
    """
    if not items:
        return []

    system_prompt = get_system_prompt()
    dict_items: List[Dict[str, Any]] = [
        item.model_dump() if isinstance(item, RawItem) else dict(item)
        for item in items
    ]

    all_tagged: List[TaggedRecord] = []
    for i in range(0, len(dict_items), batch_size):
        chunk = dict_items[i:i + batch_size]
        tagged_chunk = tag_batch(chunk, system_prompt)
        all_tagged.extend(tagged_chunk)

    return all_tagged

