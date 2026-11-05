import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path so app modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schema import (
    ALLOWED_STAGES,
    ALLOWED_MAIN_DRIVERS,
    ALLOWED_OUTCOMES,
    ALLOWED_INCOME_STABILITIES,
    ALLOWED_AGE_BANDS,
    ALLOWED_INFLUENCES,
)

ENGINE_REQUIRED_COLUMNS = [
    "id",
    "source",
    "date",
    "text",
    "stage",
    "main_driver",
    "outcome",
    "unmet_need",
    "income_stability",
    "age_band",
    "influence",
]

CORPUS_REQUIRED_COLUMNS = [
    "id",
    "source",
    "date",
    "rating",
    "text",
]

def validate_data(data_dir: Path | None = None) -> bool:
    if data_dir is None:
        data_dir = PROJECT_ROOT / "data"

    engine_path = data_dir / "engine_dataset.csv"
    corpus_path = data_dir / "corpus_all.csv"

    if not engine_path.exists():
        raise FileNotFoundError(f"Tagged dataset missing: {engine_path}")
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus dataset missing: {corpus_path}")

    # 1. Validate engine_dataset.csv
    engine_df = pd.read_csv(engine_path)
    engine_cols = set(engine_df.columns)
    missing_engine_cols = [c for c in ENGINE_REQUIRED_COLUMNS if c not in engine_cols]
    if missing_engine_cols:
        raise ValueError(f"engine_dataset.csv is missing required columns: {missing_engine_cols}")

    seen_engine_ids = set()
    for _, row in engine_df.iterrows():
        row_id = str(row["id"]).strip()
        if not row_id or row_id in seen_engine_ids:
            raise ValueError(f"Duplicate or empty id '{row['id']}' in engine_dataset.csv")
        seen_engine_ids.add(row_id)

        # Check non-empty text
        text_val = "" if pd.isna(row["text"]) else str(row["text"]).strip()
        if not text_val:
            raise ValueError(f"Empty text in engine_dataset.csv at row id '{row_id}'")

        # Check allowed values
        stage_val = "" if pd.isna(row["stage"]) else str(row["stage"]).strip()
        if stage_val not in ALLOWED_STAGES:
            raise ValueError(f"Invalid stage '{row['stage']}' in engine_dataset.csv at row id '{row_id}'")

        driver_val = "" if pd.isna(row["main_driver"]) else str(row["main_driver"]).strip()
        if driver_val not in ALLOWED_MAIN_DRIVERS:
            raise ValueError(f"Invalid main_driver '{row['main_driver']}' in engine_dataset.csv at row id '{row_id}'")

        outcome_val = "" if pd.isna(row["outcome"]) else str(row["outcome"]).strip()
        if outcome_val not in ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid outcome '{row['outcome']}' in engine_dataset.csv at row id '{row_id}'")

        income_val = "" if pd.isna(row["income_stability"]) else str(row["income_stability"]).strip()
        if income_val not in ALLOWED_INCOME_STABILITIES:
            raise ValueError(f"Invalid income_stability '{row['income_stability']}' in engine_dataset.csv at row id '{row_id}'")

        age_val = "" if pd.isna(row["age_band"]) else str(row["age_band"]).strip()
        if age_val not in ALLOWED_AGE_BANDS:
            raise ValueError(f"Invalid age_band '{row['age_band']}' in engine_dataset.csv at row id '{row_id}'")

        inf_val = "" if pd.isna(row["influence"]) else str(row["influence"]).strip()
        if inf_val not in ALLOWED_INFLUENCES:
            raise ValueError(f"Invalid influence '{row['influence']}' in engine_dataset.csv at row id '{row_id}'")

    # 2. Validate corpus_all.csv
    corpus_df = pd.read_csv(corpus_path)
    corpus_cols = set(corpus_df.columns)
    missing_corpus_cols = [c for c in CORPUS_REQUIRED_COLUMNS if c not in corpus_cols]
    if missing_corpus_cols:
        raise ValueError(f"corpus_all.csv is missing required columns: {missing_corpus_cols}")

    seen_corpus_ids = set()
    for _, row in corpus_df.iterrows():
        row_id = str(row["id"]).strip()
        if not row_id or row_id in seen_corpus_ids:
            raise ValueError(f"Duplicate or empty id '{row['id']}' in corpus_all.csv")
        seen_corpus_ids.add(row_id)

        # Check non-empty text
        text_val = "" if pd.isna(row["text"]) else str(row["text"]).strip()
        if not text_val:
            raise ValueError(f"Empty text in corpus_all.csv at row id '{row_id}'")

    return True

if __name__ == "__main__":
    try:
        validate_data()
        print("Data validation successful: all datasets passed required checks.")
        sys.exit(0)
    except Exception as exc:
        print(f"DATA VALIDATION ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

