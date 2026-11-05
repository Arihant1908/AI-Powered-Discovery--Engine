import json
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import math

from app.config import settings
from app.schema import (
    TaggedRecord,
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)
from app.services.tagger import tag_items

class JobManager:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._jobs_dir = settings.RUNTIME_DIR / "jobs"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._load_persisted_jobs()

    def _load_persisted_jobs(self) -> None:
        if not self._jobs_dir.exists():
            return
        for file in self._jobs_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                job_id = data.get("job_id")
                if job_id:
                    self._jobs[job_id] = data
            except Exception:
                pass

    def create_job(
        self,
        total_rows: int,
        data_warnings: Optional[List[str]] = None,
        missing_columns: Optional[List[str]] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = {
            "job_id": job_id,
            "state": "running",
            "rows_tagged": 0,
            "total": total_rows,
            "fallback_count": 0,
            "error_message": None,
            "data_warnings": list(data_warnings or []),
            "missing_columns": list(missing_columns or []),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rows": []
        }
        with self._lock:
            self._jobs[job_id] = job
            self._persist_job_locked(job_id)
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        # Attempt loading from disk (e.g. after server restart)
        job_file = self._jobs_dir / f"{job_id}.json"
        if job_file.exists():
            try:
                job = json.loads(job_file.read_text(encoding="utf-8"))
                with self._lock:
                    self._jobs[job_id] = job
                return job
            except Exception:
                pass
        return None

    def _persist_job_locked(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        job_file = self._jobs_dir / f"{job_id}.json"
        job_file.write_text(json.dumps(job, indent=2), encoding="utf-8")

    def process_tagging_job(self, job_id: str, raw_items: List[Dict[str, Any]]) -> None:
        try:
            from app.services.tagger import tag_batch, get_system_prompt
            system_prompt = get_system_prompt()
            all_rows = []
            fallback_count = 0
            batch_size = 20
            for i in range(0, len(raw_items), batch_size):
                chunk = raw_items[i:i + batch_size]
                tagged_chunk = tag_batch(chunk, system_prompt)
                for r in tagged_chunk:
                    rd = r.model_dump()
                    all_rows.append(rd)
                    if rd.get("label_origin") == "fallback":
                        fallback_count += 1
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job:
                        job["rows"] = all_rows
                        job["rows_tagged"] = len(all_rows)
                        job["fallback_count"] = fallback_count
                        self._persist_job_locked(job_id)
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job["state"] = "done"
                    self._persist_job_locked(job_id)
        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job["state"] = "failed"
                    job["error_message"] = str(exc)
                    self._persist_job_locked(job_id)

    def update_row_label(
        self,
        job_id: str,
        row_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self.get_job(job_id)
            if not job:
                return None
            target_row = None
            for row in job.get("rows", []):
                if str(row.get("id")).strip().lower() == row_id.strip().lower():
                    target_row = row
                    break
            if not target_row:
                return None

            for key, val in updates.items():
                if val is not None:
                    target_row[key] = str(val).strip()

            target_row["label_origin"] = "user_corrected"
            self._persist_job_locked(job_id)
            return target_row

job_manager = JobManager()
