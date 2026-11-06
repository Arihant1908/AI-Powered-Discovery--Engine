import re
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Load allowed values directly from data/tagging_prompt.txt
def _load_allowed_values() -> Dict[str, List[str]]:
    base_dir = Path(__file__).resolve().parent.parent
    prompt_file = base_dir / "data" / "tagging_prompt.txt"
    if not prompt_file.exists():
        prompt_file = Path("data/tagging_prompt.txt")
        
    content = prompt_file.read_text(encoding="utf-8")
    keys = ["stage", "main_driver", "outcome", "income_stability", "age_band", "influence"]
    allowed: Dict[str, List[str]] = {}
    
    for key in keys:
        pattern = rf'^{key}:\s*(.+)$'
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            raw_items = match.group(1)
            items = re.findall(r'"([^"]+)"', raw_items)
            allowed[key] = items
        else:
            allowed[key] = []
            
    return allowed

_ALLOWED_DATA = _load_allowed_values()

# Allowed lists directly loaded from prompt file
ALLOWED_STAGES: List[str] = _ALLOWED_DATA.get("stage", [])
ALLOWED_MAIN_DRIVERS: List[str] = _ALLOWED_DATA.get("main_driver", [])
ALLOWED_OUTCOMES: List[str] = _ALLOWED_DATA.get("outcome", [])
ALLOWED_INCOME_STABILITIES: List[str] = _ALLOWED_DATA.get("income_stability", [])
ALLOWED_AGE_BANDS: List[str] = _ALLOWED_DATA.get("age_band", [])
ALLOWED_INFLUENCES: List[str] = _ALLOWED_DATA.get("influence", [])

# Enums matching allowed values
class StageEnum(str, Enum):
    MONTH_0_1 = "Month 0-1"
    MONTH_2_3 = "Month 2-3"
    MONTH_4_6 = "Month 4-6"
    MONTH_7_12 = "Month 7-12"
    MONTH_13_17 = "Month 13-17"
    MONTH_18_24 = "Month 18-24"
    MONTH_24_PLUS = "Month 24+"
    UNCLEAR = "Unclear"

class MainDriverEnum(str, Enum):
    EXPECTATION_GAP = "Expectation gap"
    LOW_EARLY_RETURNS = "Low early returns"
    CONFUSION_ABOUT_THE_APP = "Confusion about the app"
    CASH_CRUNCH = "Cash crunch"
    PAYMENT_OR_MANDATE_FAILURE = "Payment or mandate failure"
    OUTSIDE_INFLUENCE = "Outside influence"
    FORGOT_ABOUT_IT = "Forgot about it"
    WORKING_WELL = "Working well / no issue"
    ADVICE_OR_QUESTION = "Advice or question (no SIP experience)"
    PRAISE_OR_FEEDBACK = "Praise or general feedback"
    OTHER = "Other"

class OutcomeEnum(str, Enum):
    CONTINUING = "Continuing"
    PAUSED = "Paused"
    REDUCED = "Reduced"
    STOPPED = "Stopped"
    UNKNOWN = "Unknown"

class IncomeStabilityEnum(str, Enum):
    FIXED_SALARY = "Fixed salary"
    VARIABLE_INCOME = "Variable income (freelance/business)"
    STUDENT_OR_DEPENDENT = "Student or dependent"
    UNCLEAR = "Unclear"

class AgeBandEnum(str, Enum):
    UNDER_23 = "Under 23"
    AGE_23_27 = "23-27"
    AGE_28_35 = "28-35"
    AGE_36_PLUS = "36+"
    UNCLEAR = "Unclear"

class InfluenceEnum(str, Enum):
    FAMILY = "Family"
    FRIENDS = "Friends"
    YOUTUBE_OR_SOCIAL_MEDIA = "YouTube or social media"
    OWN_RESEARCH = "Own research"
    OTHER = "Other"
    UNCLEAR = "Unclear"

# Models for Tagged Record and Raw Item
class TaggedRecord(BaseModel):
    id: str
    source: str
    date: Optional[str] = None
    rating: Optional[float] = None
    text: str
    stage: str
    main_driver: str
    outcome: str
    unmet_need: str
    income_stability: str
    age_band: str
    influence: str
    label_origin: Optional[str] = None

class RawItem(BaseModel):
    id: str
    source: str
    date: Optional[str] = None
    rating: Optional[float] = None
    text: str

# Legacy EvidenceItem alias for TaggedRecord
EvidenceItem = TaggedRecord

class FeedbackTaggingItem(BaseModel):
    id: str
    stage: StageEnum = StageEnum.UNCLEAR
    main_driver: MainDriverEnum = MainDriverEnum.OTHER
    outcome: OutcomeEnum = OutcomeEnum.UNKNOWN
    unmet_need: str = "none"
    income_stability: IncomeStabilityEnum = IncomeStabilityEnum.UNCLEAR
    age_band: AgeBandEnum = AgeBandEnum.UNCLEAR
    influence: InfluenceEnum = InfluenceEnum.UNCLEAR

class AllowedValuesResponse(BaseModel):
    stage: List[str]
    main_driver: List[str]
    outcome: List[str]
    income_stability: List[str]
    age_band: List[str]
    influence: List[str]

class MetaResponse(BaseModel):
    allowed_values: Dict[str, List[str]]
    sources: List[str]
    stage: Optional[List[str]] = None
    main_driver: Optional[List[str]] = None
    outcome: Optional[List[str]] = None
    income_stability: Optional[List[str]] = None
    age_band: Optional[List[str]] = None
    influence: Optional[List[str]] = None
    ai_available: Optional[bool] = None

class APIErrorDetail(BaseModel):
    code: str
    message: str

class APIErrorEnvelope(BaseModel):
    error: APIErrorDetail

class HealthResponse(BaseModel):
    status: str

# Dashboard Responses
class DashboardSummaryResponse(BaseModel):
    total_items_collected: int
    distinct_sources: int
    labelled_evidence_items: int
    deep_interviews: int

class ChartItem(BaseModel):
    label: str
    count: int
    percentage: float

class ChartsResponse(BaseModel):
    main_driver: List[ChartItem]
    outcome: List[ChartItem]
    total_records: int
    counts: Dict[str, Dict[str, int]]
    percentages: Dict[str, Dict[str, float]]

class UnmetNeedTheme(BaseModel):
    theme: str
    count: int

class UnmetNeedsResponse(BaseModel):
    themes: List[UnmetNeedTheme]
    ai_available: bool
    ai_grouped: bool

class PaginatedEvidenceResponse(BaseModel):
    items: List[EvidenceItem]
    total: int
    page: int
    page_size: int
    total_pages: int

# Upload / Job Models
class UploadJobInitResponse(BaseModel):
    job_id: str
    state: str
    total: int
    data_warnings: List[str] = []
    missing_columns: List[str] = []

class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    rows_tagged: int
    total: int
    fallback_count: int
    error_message: Optional[str] = None
    data_warnings: List[str] = []
    missing_columns: List[str] = []

class PaginatedJobRowsResponse(BaseModel):
    items: List[TaggedRecord]
    total: int
    page: int
    page_size: int
    total_pages: int
    job_state: str = "done"
    is_complete: bool = True
    warning: Optional[str] = None

class UpdateRowLabelRequest(BaseModel):
    stage: Optional[str] = None
    main_driver: Optional[str] = None
    outcome: Optional[str] = None
    income_stability: Optional[str] = None
    age_band: Optional[str] = None
    influence: Optional[str] = None
    unmet_need: Optional[str] = None

# Insights Models
class SegmentItem(BaseModel):
    income_stability: str
    n: int
    negative_count: int
    negative_share: float
    percentage: float

class InsightCard(BaseModel):
    headline: str
    explanation: str
    proposed_pm_action: str
    supporting_evidence_ids: List[str]
    supporting_count: int
    strength: str
    strength_label: str
    filter: Optional[str] = None

class InsightsComputedStats(BaseModel):
    total_records: int
    main_driver_counts: Dict[str, int]
    outcome_counts: Dict[str, int]
    segment_view: List[SegmentItem]
    top_unmet_needs: List[UnmetNeedTheme]
    supporting_ids_by_driver: Dict[str, List[str]]

class InsightsResponse(BaseModel):
    dataset: str
    total_records: int
    computed_stats: InsightsComputedStats
    segment_view: List[SegmentItem]
    ai_summary_available: bool
    message: Optional[str] = None
    cards: List[InsightCard] = []
    suggested_questions: List[str] = []
    generated_at: Optional[str] = None
    cached: bool = False
    data_warnings: List[str] = []

class RegenerateInsightsRequest(BaseModel):
    dataset: Optional[str] = "preloaded"
