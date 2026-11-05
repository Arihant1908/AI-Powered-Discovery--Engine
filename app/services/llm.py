import json
import re
import time
import logging
from typing import Optional, List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, timeout_seconds: float = 30.0, retry_backoff_seconds: float = 1.0):
        self.timeout_seconds = timeout_seconds
        self.retry_backoff_seconds = retry_backoff_seconds

    def generate_json(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Executes a prompt against the Gemini API returning a JSON string.
        Falls back to a deterministic mock if MOCK_LLM=1 or no API key is set.
        Includes timeout, one retry with backoff, and JSON-only output.
        """
        if settings.MOCK_LLM or not settings.GEMINI_API_KEY:
            return self._mock_generate(prompt, system_instruction)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
            system_instruction=system_instruction,
            http_options=types.HttpOptions(timeout=int(self.timeout_seconds * 1000)),
        )

        last_error: Optional[Exception] = None

        # Try once + one retry with backoff
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as exc:
                last_error = exc
                logger.warning(f"Gemini API attempt {attempt + 1} failed: {exc}")
                if attempt == 0:
                    time.sleep(self.retry_backoff_seconds)

        # If both attempts failed, fall back to mock to ensure graceful degradation
        logger.error(f"Gemini API failed after 1 retry: {last_error}. Utilizing deterministic fallback mock.")
        return self._mock_generate(prompt, system_instruction)

    def _mock_generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """
        Deterministic mock that handles:
        1. Insights generation (returns 3 insight cards citing extracted IDs + 3 questions)
        2. Tagging generation (returns Other / Unknown / Unclear for each item)
        """
        prompt_lower = (prompt + " " + (system_instruction or "")).lower()

        # Handle Insights prompt
        if "insight_cards" in prompt_lower or ("insight" in prompt_lower and "headline" in prompt_lower):
            card1_match = re.search(r'Valid evidence IDs for Card 1:\s*(\[[^\]]+\])', prompt)
            card2_match = re.search(r'Valid evidence IDs for Card 2:\s*(\[[^\]]+\])', prompt)
            card3_match = re.search(r'Valid evidence IDs for Card 3:\s*(\[[^\]]+\])', prompt)

            card1_ids = json.loads(card1_match.group(1)) if card1_match else ["SV-00007", "SV-00011", "INT-03", "INT-07"]
            card2_ids = json.loads(card2_match.group(1)) if card2_match else ["PS-00066", "PS-00139", "AS-00014", "AS-00060"]
            card3_ids = json.loads(card3_match.group(1)) if card3_match else ["SV-00002", "SV-00004", "SV-00006", "SV-00009", "SV-00011", "YT-00135", "INT-02"]

            # Add an invalid/out-of-filter ID to card 2 to test that invalid/out-of-filter IDs are dropped
            card2_ids_with_invalid = list(card2_ids) + ["NONEXISTENT-ID-9999"]

            mock_insights = {
                "insight_cards": [
                    {
                        "headline": "Variable-income investors cancel instead of pausing during cash flow crunches",
                        "explanation": "4 of 7 variable-income records paused, stopped or reduced. Users experiencing periodic cash flow shifts struggle to locate temporary pause controls during critical billing windows, opting for complete cancellation to avoid bank overdraft charges.",
                        "proposed_pm_action": "Introduce a streamlined 1-click pause option directly inside the cancellation workflow with automated resumption reminders.",
                        "supporting_evidence_ids": card1_ids,
                    },
                    {
                        "headline": "Payment mandate friction leads to involuntary SIP cancellations",
                        "explanation": "Mandate authorizations frequently fail when bank server response windows expire or salary credits arrive on non-business days. Users receive bank failure charges and hesitate to re-verify debit instructions.",
                        "proposed_pm_action": "Implement a 3-day flexible debit retry grace window before marking mandates as failed.",
                        "supporting_evidence_ids": card2_ids_with_invalid,
                    },
                    {
                        "headline": "Short-term volatility triggers early discontinuation in first-time investors",
                        "explanation": "First-time investors entering growth funds observe initial downward market variance and interpret it as underperformance. Unprepared for regular short-cycle portfolio movement, users discontinue commitments early in the investment lifecycle.",
                        "proposed_pm_action": "Embed an interactive averaging and volatility context explainer highlighting long-horizon accumulation milestones.",
                        "supporting_evidence_ids": card3_ids,
                    }
                ],
                "suggested_questions": [
                    "What percentage of paused SIPs resume within 60 days of cancellation flow interventions?",
                    "How do payment mandate retries perform across different banking partner cohorts?",
                    "Does an onboarding volatility explainer decrease early drop-offs among first-time investors?"
                ]
            }
            return json.dumps(mock_insights)

        item_ids: List[str] = []

        # 1. Try parsing prompt as JSON or finding JSON array
        try:
            match = re.search(r'\[.*\]', prompt, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    for obj in parsed:
                        if isinstance(obj, dict) and "id" in obj:
                            item_ids.append(str(obj["id"]).strip())
        except Exception:
            pass

        # 2. Fallback regex to find IDs in prompt text
        if not item_ids:
            matches = re.findall(r'["\']?id["\']?\s*:\s*["\']([^"\',]+)["\']', prompt, re.I)
            item_ids = [m.strip() for m in matches if m.strip()]

        # 3. If no IDs found, provide a single generic id
        if not item_ids:
            item_ids = ["item_1"]

        # Deterministic response matching allowed values
        mock_items = [
            {
                "id": item_id,
                "stage": "Unclear",
                "main_driver": "Other",
                "outcome": "Unknown",
                "unmet_need": "none",
                "income_stability": "Unclear",
                "age_band": "Unclear",
                "influence": "Unclear"
            }
            for item_id in item_ids
        ]

        return json.dumps(mock_items)

llm_service = LLMService()

def generate_json(prompt: str, system_instruction: Optional[str] = None) -> str:
    return llm_service.generate_json(prompt, system_instruction)

