import io
import math
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Query, Response, Request

from app.config import settings
from app.schema import (
    UploadJobInitResponse,
    JobStatusResponse,
    PaginatedJobRowsResponse,
    UpdateRowLabelRequest,
    TaggedRecord,
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)
from app.services.job_manager import job_manager

router = APIRouter(prefix="/api", tags=["upload"])

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_ROWS = 500
REQUIRED_COLUMNS = ["id", "source", "date", "rating", "text"]

class UploadRateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self.bypass_for_tests: bool = True

    def check(self, request: Request) -> None:
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        # Allow test client bypass unless explicitly testing rate limits
        if self.bypass_for_tests and client_ip in ("testclient", "127.0.0.1", "localhost") and request.headers.get("x-test-rate-limit") != "1":
            return

        now = time.time()
        with self._lock:
            cutoff = now - self.window_seconds
            timestamps = [t for t in self._requests[client_ip] if t > cutoff]
            if len(timestamps) >= self.max_requests:
                oldest = timestamps[0]
                retry_after_min = max(1, int((oldest + self.window_seconds - now) / 60))
                raise HTTPException(
                    status_code=429,
                    detail=f"Upload rate limit exceeded (maximum {self.max_requests} uploads per hour per IP). Please try again in {retry_after_min} minutes."
                )
            timestamps.append(now)
            self._requests[client_ip] = timestamps

upload_rate_limiter = UploadRateLimiter(max_requests=10, window_seconds=3600)

def validate_dataframe(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Check column names (case-insensitive)
    df_cols_lower = [str(c).strip().lower() for c in df.columns]
    col_map = {str(c).strip().lower(): c for c in df.columns}

    missing = [c for c in REQUIRED_COLUMNS if c not in df_cols_lower]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}"
        )

    row_count = len(df)
    if row_count > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum row limit of 500 rows ({row_count} rows found)."
        )

    if row_count == 0:
        raise HTTPException(
            status_code=400,
            detail="File contains 0 data rows."
        )

    seen_ids = set()
    validated_items = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based line number including header

        # Validate ID
        raw_id = row[col_map["id"]]
        id_str = "" if pd.isna(raw_id) else str(raw_id).strip()
        if not id_str:
            raise HTTPException(
                status_code=400,
                detail=f"Missing or empty ID at row {row_num}."
            )
        if id_str.lower() in seen_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate ID '{id_str}' found in row {row_num}."
            )
        seen_ids.add(id_str.lower())

        # Validate Text
        raw_text = row[col_map["text"]]
        text_str = "" if pd.isna(raw_text) else str(raw_text).strip()
        if not text_str:
            raise HTTPException(
                status_code=400,
                detail=f"Empty text found in row with ID '{id_str}'."
            )

        # Optional Date
        raw_date = row[col_map["date"]]
        date_str = None if pd.isna(raw_date) else str(raw_date).strip()

        # Optional Rating
        raw_rating = row[col_map["rating"]]
        try:
            rating_val = float(raw_rating) if not pd.isna(raw_rating) else None
        except (ValueError, TypeError):
            rating_val = None

        # Source
        raw_source = row[col_map["source"]]
        source_str = "unknown" if pd.isna(raw_source) else str(raw_source).strip()

        validated_items.append({
            "id": id_str,
            "source": source_str,
            "date": date_str,
            "rating": rating_val,
            "text": text_str,
        })

    return validated_items

@router.post("/upload", response_model=UploadJobInitResponse)
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    upload_rate_limiter.check(request)
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in [".csv", ".xlsx"]:
        raise HTTPException(
            status_code=400,
            detail="Only .csv and .xlsx files are supported."
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds the 25 MB limit."
        )

    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse {ext} file: {str(exc)}"
        )

    raw_items = validate_dataframe(df)

    job_id = job_manager.create_job(total_rows=len(raw_items))
    background_tasks.add_task(job_manager.process_tagging_job, job_id, raw_items)

    return UploadJobInitResponse(
        job_id=job_id,
        state="running",
        total=len(raw_items),
    )

@router.post("/upload/sample", response_model=UploadJobInitResponse)
def upload_sample(request: Request, background_tasks: BackgroundTasks):
    upload_rate_limiter.check(request)
    sample_file = settings.DATA_DIR / "sample_upload.csv"
    if not sample_file.exists():
        raise HTTPException(status_code=404, detail="sample_upload.csv not found in data directory.")

    df = pd.read_csv(sample_file)
    raw_items = validate_dataframe(df)

    job_id = job_manager.create_job(total_rows=len(raw_items))
    background_tasks.add_task(job_manager.process_tagging_job, job_id, raw_items)

    return UploadJobInitResponse(
        job_id=job_id,
        state="running",
        total=len(raw_items),
    )

@router.get("/upload/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found. The upload session has expired or the server restarted. Please upload your dataset again."
        )

    return JobStatusResponse(
        job_id=job["job_id"],
        state=job["state"],
        rows_tagged=job.get("rows_tagged", 0),
        total=job.get("total", 0),
        fallback_count=job.get("fallback_count", 0),
        error_message=job.get("error_message"),
    )

@router.get("/upload/{job_id}/rows", response_model=PaginatedJobRowsResponse)
def get_job_rows(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found. The upload session has expired or the server restarted. Please upload your dataset again."
        )

    rows = job.get("rows", [])
    total = len(rows)
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    start = (page - 1) * page_size
    end = start + page_size
    sliced = rows[start:end]

    items = [TaggedRecord(**r) for r in sliced]

    return PaginatedJobRowsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

@router.patch("/upload/{job_id}/rows/{row_id}", response_model=TaggedRecord)
def update_row_label(
    job_id: str,
    row_id: str,
    req: UpdateRowLabelRequest,
):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found. The upload session has expired or the server restarted. Please upload your dataset again."
        )

    # Validate allowed lists for any provided label
    if req.stage is not None and req.stage.strip() not in ALLOWED_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.stage}' for stage. Allowed values: {ALLOWED_STAGES}"
        )
    if req.main_driver is not None and req.main_driver.strip() not in ALLOWED_MAIN_DRIVERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.main_driver}' for main_driver. Allowed values: {ALLOWED_MAIN_DRIVERS}"
        )
    if req.outcome is not None and req.outcome.strip() not in ALLOWED_OUTCOMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.outcome}' for outcome. Allowed values: {ALLOWED_OUTCOMES}"
        )
    if req.income_stability is not None and req.income_stability.strip() not in ALLOWED_INCOME_STABILITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.income_stability}' for income_stability. Allowed values: {ALLOWED_INCOME_STABILITIES}"
        )
    if req.age_band is not None and req.age_band.strip() not in ALLOWED_AGE_BANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.age_band}' for age_band. Allowed values: {ALLOWED_AGE_BANDS}"
        )
    if req.influence is not None and req.influence.strip() not in ALLOWED_INFLUENCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid value '{req.influence}' for influence. Allowed values: {ALLOWED_INFLUENCES}"
        )

    updates = req.model_dump(exclude_unset=True)
    updated_row = job_manager.update_row_label(job_id, row_id, updates)

    if not updated_row:
        raise HTTPException(
            status_code=404,
            detail=f"Row '{row_id}' not found in job '{job_id}'."
        )

    return TaggedRecord(**updated_row)

@router.get("/template.csv")
def download_template():
    # Header row plus one clearly invented example row
    content = (
        'id,source,date,rating,text\n'
        'SAMPLE-0001,playstore,2026-01-01,5,"Invented sample text for upload template"\n'
    )
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template.csv"}
    )

