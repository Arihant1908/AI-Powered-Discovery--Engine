# PROJECT BRIEF: SIP Discovery Engine

## Core Rules

1. **Visual Reference Only**: The Stitch files in `frontend/design_reference/` are VISUAL REFERENCE ONLY. Every number, row, ID, quote, persona and name inside them is a placeholder. Never copy any of it into code, data, tests or the UI. Copy only layout, styling and static labels.
2. **Zero Hardcoded Data**: Nothing is hardcoded. Every number, chart value, table row and insight comes from the data files or from the AI at runtime.
3. **Single Source of Truth**: `app/schema.py` is the single source of truth for allowed values (`stage`, `main_driver`, `outcome`, `income_stability`, `age_band`, `influence`). Read them from `data/tagging_prompt.txt` and verify they match. The frontend gets them from an API endpoint, never from its own copy.
4. **Read-Only Reference Directories**: Never edit anything in `data/` or `frontend/design_reference/`.
5. **Secrets & Graceful Degradation**: Secrets only in `.env` (`GEMINI_API_KEY`, `GEMINI_MODEL`, `MOCK_LLM`). Never in code or logs. The app must start and work without a key (AI features show a clear "AI unavailable" message).
6. **Consistent Error Envelope**: Every API error returns JSON: `{"error": {"code": "...", "message": "..."}}`.
7. **Strict Grounding / Fallbacks**: Never invent data, labels or IDs. If unsure, use the fallback values `Other` / `Unknown` / `Unclear`.
8. **Iterative Step Verification**: Do one step at a time. At the end of each step run the tests, then report: files created or changed, commands run, test results, anything not done. Then stop and wait.

