import pandas as pd
import numpy as np
from typing import List, Optional, Dict
from pathlib import Path

from app.config import settings
from app.schema import TaggedRecord, RawItem

class DataStore:
    def __init__(self):
        self._tagged_df: Optional[pd.DataFrame] = None
        self._corpus_df: Optional[pd.DataFrame] = None
        self._tagged_records: List[TaggedRecord] = []
        self._tagged_by_id: Dict[str, TaggedRecord] = {}
        self._sources: List[str] = []
        self._is_loaded: bool = False

    def load(self, force_reload: bool = False) -> None:
        if self._is_loaded and not force_reload:
            return

        tagged_file = settings.DATA_DIR / "engine_dataset.csv"
        corpus_file = settings.DATA_DIR / "corpus_all.csv"

        if tagged_file.exists():
            self._tagged_df = pd.read_csv(tagged_file)
        else:
            self._tagged_df = pd.DataFrame(columns=[
                "id", "source", "date", "text", "stage", "main_driver",
                "outcome", "unmet_need", "income_stability", "age_band",
                "influence", "label_origin"
            ])

        if corpus_file.exists():
            self._corpus_df = pd.read_csv(corpus_file)
        else:
            self._corpus_df = pd.DataFrame(columns=["id", "source", "date", "rating", "text"])

        # Clean NaN values and create TaggedRecord instances
        clean_tagged = self._tagged_df.replace({np.nan: None})
        records_dicts = clean_tagged.to_dict(orient="records")
        self._tagged_records = [TaggedRecord(**rec) for rec in records_dicts]
        self._tagged_by_id = {r.id.strip().lower(): r for r in self._tagged_records}

        # Collect distinct sources across datasets
        sources_set = set()
        if not self._tagged_df.empty and "source" in self._tagged_df.columns:
            sources_set.update(self._tagged_df["source"].dropna().unique())
        if not self._corpus_df.empty and "source" in self._corpus_df.columns:
            sources_set.update(self._corpus_df["source"].dropna().unique())
        self._sources = sorted(list(sources_set))

        self._is_loaded = True

    @property
    def tagged_df(self) -> pd.DataFrame:
        if not self._is_loaded:
            self.load()
        return self._tagged_df

    @property
    def corpus_df(self) -> pd.DataFrame:
        if not self._is_loaded:
            self.load()
        return self._corpus_df

    def get_all_tagged_records(self) -> List[TaggedRecord]:
        if not self._is_loaded:
            self.load()
        return list(self._tagged_records)

    def get_tagged_record_by_id(self, record_id: str) -> Optional[TaggedRecord]:
        if not self._is_loaded:
            self.load()
        return self._tagged_by_id.get(record_id.strip().lower())

    def get_corpus_row_count(self) -> int:
        if not self._is_loaded:
            self.load()
        return len(self._corpus_df)

    def get_sources(self) -> List[str]:
        if not self._is_loaded:
            self.load()
        return list(self._sources)

data_store = DataStore()

# Public API functions matching requirements
def load_data(force_reload: bool = False) -> None:
    data_store.load(force_reload=force_reload)

def get_all_tagged_records() -> List[TaggedRecord]:
    return data_store.get_all_tagged_records()

def get_tagged_record_by_id(record_id: str) -> Optional[TaggedRecord]:
    return data_store.get_tagged_record_by_id(record_id)

def get_corpus_row_count() -> int:
    return data_store.get_corpus_row_count()

def get_sources() -> List[str]:
    return data_store.get_sources()

def get_tagged_df() -> pd.DataFrame:
    return data_store.tagged_df

def get_corpus_df() -> pd.DataFrame:
    return data_store.corpus_df

