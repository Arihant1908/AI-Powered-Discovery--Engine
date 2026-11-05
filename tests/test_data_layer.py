import tempfile
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.data_store import (
    get_all_tagged_records,
    get_tagged_record_by_id,
    get_corpus_row_count,
    get_sources,
    get_tagged_df,
    get_corpus_df,
)
from scripts.validate_data import validate_data

client = TestClient(app)

def test_dataset_counts_and_sources():
    tagged_records = get_all_tagged_records()
    tagged_df = get_tagged_df()
    corpus_df = get_corpus_df()

    # The tagged dataset has 54 rows
    assert len(tagged_records) == 54
    assert len(tagged_df) == 54

    # The corpus has 1,094 rows
    assert get_corpus_row_count() == 1094
    assert len(corpus_df) == 1094

    # Sources are youtube 22, survey 12, playstore 8, interviews 8, appstore 4
    source_counts = tagged_df["source"].value_counts().to_dict()
    assert source_counts["youtube"] == 22
    assert source_counts["survey"] == 12
    assert source_counts["playstore"] == 8
    assert source_counts["interviews"] == 8
    assert source_counts["appstore"] == 4

def test_data_store_record_lookup():
    rec = get_tagged_record_by_id("SV-00001")
    assert rec is not None
    assert rec.id == "SV-00001"
    assert rec.source == "survey"
    assert rec.stage == "Month 24+"
    assert rec.main_driver == "Cash crunch"
    assert rec.outcome == "Continuing"

    # Non-existent
    assert get_tagged_record_by_id("NONEXISTENT-999") is None

def test_validate_data_passes_on_project_data():
    assert validate_data() is True

def test_validate_data_fails_loudly_on_invalid_tag():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        engine_df = get_tagged_df().copy()
        corpus_df = get_corpus_df().copy()

        # Introduce an invalid tag at a specific row ID
        bad_row_id = engine_df.iloc[0]["id"]
        engine_df.at[0, "stage"] = "Invalid Month 999"

        engine_df.to_csv(tmp_path / "engine_dataset.csv", index=False)
        corpus_df.to_csv(tmp_path / "corpus_all.csv", index=False)

        with pytest.raises(ValueError) as excinfo:
            validate_data(data_dir=tmp_path)

        # Must fail loudly with the row id
        assert str(bad_row_id) in str(excinfo.value)
        assert "Invalid stage" in str(excinfo.value)

def test_validate_data_fails_loudly_on_empty_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        engine_df = get_tagged_df().copy()
        corpus_df = get_corpus_df().copy()

        bad_row_id = engine_df.iloc[2]["id"]
        engine_df.at[2, "text"] = "   "

        engine_df.to_csv(tmp_path / "engine_dataset.csv", index=False)
        corpus_df.to_csv(tmp_path / "corpus_all.csv", index=False)

        with pytest.raises(ValueError) as excinfo:
            validate_data(data_dir=tmp_path)

        assert str(bad_row_id) in str(excinfo.value)
        assert "Empty text" in str(excinfo.value)

def test_api_meta_endpoint():
    response = client.get("/api/meta")
    assert response.status_code == 200
    data = response.json()

    assert "allowed_values" in data
    allowed = data["allowed_values"]
    assert "stage" in allowed
    assert "main_driver" in allowed
    assert "outcome" in allowed
    assert "income_stability" in allowed
    assert "age_band" in allowed
    assert "influence" in allowed

    # Verify sources
    assert "sources" in data
    sources = data["sources"]
    for expected_src in ["youtube", "survey", "playstore", "interviews", "appstore"]:
        assert expected_src in sources

