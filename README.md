# SIP Discovery Engine

A voice-of-customer research analysis and automated classification engine for Systematic Investment Plan (SIP) mutual fund investing in India. Built with **FastAPI**, **Pydantic**, **Pandas**, and the **Google Gen AI SDK**.

---

## Prerequisites

- **Python 3.11+**
- Virtual environment (`venv`)
- Cross-platform support for Windows, macOS, and Linux

---

## Setup Instructions

### 1. Clone & Navigate
```bash
git clone <repository-url>
cd "sip engine"
```

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
py -3.11 -m venv .venv
.\.venv\Scripts\activate.bat
```

**macOS / Linux (bash/zsh):**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## Environment Variables Configuration

Copy `.env.example` to `.env`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

### Supported Configuration Keys

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(None / empty)* | Google Gemini API key. If absent, the app starts cleanly and degrades gracefully without crashing. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Hosted model name for tagging and insights. |
| `MOCK_LLM` | `false` | When set to `true` or `1`, uses deterministic local mocks returning validated schema tags, 3 grounded insight cards across strength tiers, and 3 follow-up questions. |

*Note: The application starts and functions completely even without a Gemini API key. Quantitative data, filtering, CSV export, job persistence, and segment analytics remain 100% operational, while generative features clearly state that AI is unavailable.*

---

## Running the Application

Start the server using Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

Once running, access the web platform and APIs:
- **Interactive Dashboard**: [http://localhost:8000/](http://localhost:8000/)
- **Data Ingestion & Upload**: [http://localhost:8000/upload](http://localhost:8000/upload)
- **Qualitative Insights**: [http://localhost:8000/insights](http://localhost:8000/insights)
- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **System Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Running Tests

Run the full automated test suite with `pytest`:
```bash
pytest -v
```

Run specific test modules:
```bash
pytest tests/test_dashboard.py -v       # Dashboard summaries, charts, filters, export
pytest tests/test_upload_flow.py -v     # Upload flows, validations, label editing
pytest tests/test_insights.py -v        # Insights computation, grounding, strength rules
pytest tests/test_tagger.py -v          # PII removal, batch tagging, schema enforcement
```

Run end-to-end integration verification against a running server:
```bash
python scripts/e2e_integration_test.py
python scripts/verify_configurations.py
```

---

## Folder Structure

```text
sip engine/
├── .env                      # Local environment configuration (git-ignored)
├── .env.example              # Template environment variables
├── .gitignore                # Git ignore configuration
├── PROJECT_BRIEF.md          # Canonical rules & constraints
├── README.md                 # Setup, run, and architecture documentation
├── requirements.txt          # Pinned dependency specifications
│
├── app/
│   ├── __init__.py
│   ├── config.py             # Settings, environment parsing & AI availability
│   ├── main.py               # FastAPI application, route mounting, global error handler
│   ├── schema.py             # Single source of truth for allowed enums & Pydantic models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── dashboard.py      # /api/dashboard summary, charts, evidence, export
│   │   ├── insights.py       # /api/insights GET & POST regenerate
│   │   ├── meta.py           # /api/meta allowed values & sources
│   │   └── upload.py         # /api/upload, /api/upload/sample, status, rows, PATCH
│   └── services/
│       ├── __init__.py
│       ├── data_store.py     # In-memory store for preloaded dataset & corpus
│       ├── insights.py       # Segment calculations, strength rules, AI prompt & cache
│       ├── job_manager.py    # In-memory & disk job manager with thread locks
│       ├── llm.py            # Gemini client wrapper with retry & deterministic mock
│       ├── pii.py            # PII removal (emails, phone numbers, social handles)
│       ├── stats.py          # Dashboard aggregation, filtering, & CSV export
│       └── tagger.py         # 20-item batch classification with schema validation
│
├── frontend/
│   ├── design_reference/     # Visual reference HTML only (read-only)
│   ├── pages/
│   │   ├── dashboard.html    # Dynamic quantitative dashboard page
│   │   ├── upload.html       # Dynamic upload, polling, & live editing page
│   │   └── insights.html     # Dynamic qualitative cards, segment view & modal
│   └── static/
│       ├── api.js            # Frontend API client library
│       ├── app.js            # Dashboard UI controller
│       ├── upload.js         # Upload drop-zone, polling, & edit controller
│       └── insights.js       # Insights cards, modal, & regenerate controller
│
├── data/                     # Read-only source datasets (never modified)
│   ├── corpus_all.csv        # 1,094 raw voice-of-customer rows
│   ├── engine_dataset.csv    # 54 preloaded classified records
│   ├── sample_upload.csv     # 36 feedback rows for sample upload testing
│   └── tagging_prompt.txt    # Taxonomy definitions & classification prompt
│
├── runtime/                  # Persistent runtime storage (git-ignored)
│   ├── insights/             # Cached insight responses (*.json)
│   └── jobs/                 # Persisted upload jobs surviving restarts (*.json)
│
├── scripts/
│   ├── validate_data.py      # Startup & CLI validation of taxonomy consistency
│   ├── e2e_integration_test.py # End-to-end integration test runner
│   ├── verify_configurations.py # Configuration verification script
│   ├── verify_live_insights.py # Insights live endpoint verification
│   └── verify_live_upload.py   # Upload live endpoint verification
│
└── tests/                    # 62 unit and integration test cases
    ├── test_dashboard.py
    ├── test_data_layer.py
    ├── test_frontend.py
    ├── test_health.py
    ├── test_insights.py
    ├── test_insights_page.py
    ├── test_schema.py
    ├── test_tagger.py
    ├── test_upload.py
    ├── test_upload_flow.py
    └── test_validation.py
```

---

## Core Rules & Design Principles

1. **Zero Hardcoded Data**: Nothing is hardcoded. Every number, chart, table row, card, and chip is populated at runtime from datasets or APIs.
2. **Visual Reference Only**: The reference files in `frontend/design_reference/` are visual guides only. No placeholder values (`XX`, `ID-00`, `Independent Consultant`) exist in the codebase.
3. **Single Source of Truth**: `app/schema.py` defines all allowed classification categories (`stage`, `main_driver`, `outcome`, `income_stability`, `age_band`, `influence`) validated against `data/tagging_prompt.txt`.
4. **Standard Error Envelope**: Every HTTP error returns JSON: `{"error": {"code": "...", "message": "..."}}`.
5. **Deterministic Testing**: Complete test suite runs without external network dependencies or API keys using the built-in deterministic mock (`MOCK_LLM=1`).
