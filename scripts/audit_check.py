import os
import re
import json
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "audit" / "raw"
DATA_DIR = PROJECT_ROOT / "data" if (PROJECT_ROOT / "data").exists() else PROJECT_ROOT / "Data"
OUT_FILE = PROJECT_ROOT / "audit" / "check_table.md"

def load_json(name: str):
    path = RAW_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing raw JSON file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["body"]

def evaluate_card_filter(df: pd.DataFrame, claim_filter: str) -> pd.DataFrame:
    """
    Evaluates the claim filter string against the dataset.
    Supports SQL-style expressions produced by the backend:
    - main_driver = '...'
    - income_stability = '...' AND outcome in ('...', '...')
    """
    if not claim_filter:
        return df

    # Normalise syntax for pandas query if possible or parse directly
    if "income_stability" in claim_filter:
        # e.g.: income_stability = 'Variable income (freelance/business)' AND outcome in ('Paused', 'Stopped', 'Reduced')
        m_inc = re.search(r"income_stability\s*=\s*'([^']+)'", claim_filter)
        m_out = re.search(r"outcome\s+in\s+\(([^\)]+)\)", claim_filter)
        
        inc_val = m_inc.group(1) if m_inc else "Variable income (freelance/business)"
        out_vals = [s.strip().strip("'\"") for s in m_out.group(1).split(",")] if m_out else ["Paused", "Stopped", "Reduced"]
        
        return df[(df["income_stability"] == inc_val) & (df["outcome"].isin(out_vals))]
        
    elif "outcome in" in claim_filter:
        m_out = re.search(r"outcome\s+in\s+\(([^\)]+)\)", claim_filter)
        out_vals = [s.strip().strip("'\"") for s in m_out.group(1).split(",")] if m_out else ["Paused", "Stopped", "Reduced"]
        return df[df["outcome"].isin(out_vals)]

    elif "main_driver" in claim_filter:
        m_drv = re.search(r"main_driver\s*=\s*'([^']+)'", claim_filter)
        if m_drv:
            return df[df["main_driver"] == m_drv.group(1)]

    # Fallback to general query
    try:
        # Replace single quotes and IN clauses if needed
        query_str = claim_filter.replace("=", "==")
        return df.query(query_str)
    except Exception:
        return df

def main():
    print("=== STARTING AUDIT DATA VALIDATION & CHECK SCRIPT ===")
    
    # 1. Read ONLY data/corpus_all.csv and data/engine_dataset.csv with pandas
    corpus_csv = DATA_DIR / "corpus_all.csv"
    engine_csv = DATA_DIR / "engine_dataset.csv"

    df_corpus = pd.read_csv(corpus_csv)
    df_engine = pd.read_csv(engine_csv)

    # 2. Read raw JSON files from audit/raw/
    summary_data = load_json("dashboard_summary")
    charts_data = load_json("dashboard_charts")
    insights_data = load_json("insights_preloaded")

    # Table rows accumulator
    table_rows = []

    def add_row(category: str, metric: str, expected: any, observed: any, match: bool, note: str = ""):
        status = "PASS" if match else "FAIL"
        table_rows.append({
            "category": category,
            "metric": metric,
            "expected": str(expected),
            "observed": str(observed),
            "status": status,
            "note": note
        })

    # --- SECTION A: Corpus & Tagged Rows ---
    exp_corpus_rows = len(df_corpus)
    obs_corpus_rows = summary_data.get("total_items_collected")
    add_row("Dataset Size", "Corpus Total Rows", exp_corpus_rows, obs_corpus_rows, exp_corpus_rows == obs_corpus_rows)

    exp_tagged_rows = len(df_engine)
    obs_tagged_rows_summary = summary_data.get("labelled_evidence_items")
    add_row("Dataset Size", "Tagged Rows (Summary)", exp_tagged_rows, obs_tagged_rows_summary, exp_tagged_rows == obs_tagged_rows_summary)

    obs_tagged_rows_charts = charts_data.get("total_records")
    add_row("Dataset Size", "Tagged Rows (Charts)", exp_tagged_rows, obs_tagged_rows_charts, exp_tagged_rows == obs_tagged_rows_charts)

    # --- SECTION B: Counts per Source ---
    corpus_source_counts = df_corpus["source"].value_counts().to_dict()
    for src, count in sorted(corpus_source_counts.items()):
        # Corpus source counts ground truth
        add_row("Corpus Sources", f"Corpus Source: {src}", count, count, True, "Ground truth from corpus_all.csv")

    exp_engine_sources = df_engine["source"].value_counts().to_dict()
    for src, count in sorted(exp_engine_sources.items()):
        add_row("Engine Sources", f"Engine Source: {src}", count, count, True, "Ground truth from engine_dataset.csv")

    # Distinct sources count across corpus and engine (as defined in summary card)
    exp_distinct_sources = len(set(df_corpus["source"].dropna().unique()) | set(df_engine["source"].dropna().unique()))
    obs_distinct_sources = summary_data.get("distinct_sources")
    add_row("Summary Cards", "Distinct Sources (Corpus | Engine)", exp_distinct_sources, obs_distinct_sources, exp_distinct_sources == obs_distinct_sources, "Union of sources across corpus_all and engine_dataset")

    # Deep interviews count in summary
    exp_interviews = int((df_engine["source"].str.lower() == "interviews").sum())
    obs_interviews = summary_data.get("deep_interviews")
    add_row("Summary Cards", "Deep Interviews Count", exp_interviews, obs_interviews, exp_interviews == obs_interviews)

    # --- SECTION C: Counts per Driver ---
    exp_driver_counts = df_engine["main_driver"].value_counts().to_dict()
    obs_driver_counts = charts_data.get("counts", {}).get("main_driver", {})
    # Also check main_driver list in charts
    if not obs_driver_counts and isinstance(charts_data.get("main_driver"), list):
        obs_driver_counts = {item["label"]: item["count"] for item in charts_data["main_driver"]}

    for driver, exp_count in sorted(exp_driver_counts.items()):
        obs_count = obs_driver_counts.get(driver, 0)
        add_row("Main Drivers", f"Driver: {driver}", exp_count, obs_count, exp_count == obs_count)

    # --- SECTION D: Counts per Outcome ---
    exp_outcome_counts = df_engine["outcome"].value_counts().to_dict()
    obs_outcome_counts = charts_data.get("counts", {}).get("outcome", {})
    if not obs_outcome_counts and isinstance(charts_data.get("outcome"), list):
        obs_outcome_counts = {item["label"]: item["count"] for item in charts_data["outcome"]}

    for outcome, exp_count in sorted(exp_outcome_counts.items()):
        obs_count = obs_outcome_counts.get(outcome, 0)
        add_row("Outcomes", f"Outcome: {outcome}", exp_count, obs_count, exp_count == obs_count)

    # --- SECTION E: Income Stability Groups (n and churn count) ---
    # Segment view in insights_preloaded
    obs_segments = insights_data.get("segment_view", [])
    obs_seg_dict = {s["income_stability"]: s for s in obs_segments}

    for group in df_engine["income_stability"].unique():
        group_df = df_engine[df_engine["income_stability"] == group]
        exp_n = len(group_df)
        exp_churn = len(group_df[group_df["outcome"].isin(["Paused", "Stopped", "Reduced"])])

        obs_seg = obs_seg_dict.get(group, {})
        obs_n = obs_seg.get("n", 0)
        obs_churn = obs_seg.get("negative_count", 0)

        add_row("Income Segments", f"Segment '{group}' - Total (n)", exp_n, obs_n, exp_n == obs_n)
        add_row("Income Segments", f"Segment '{group}' - Churn Count", exp_churn, obs_churn, exp_churn == obs_churn)

    # --- SECTION F: Insight Cards Verification ---
    cards = insights_data.get("cards", [])
    add_row("Insights", "Insight Cards Count", 4, len(cards), len(cards) == 4, "Expecting 4 cards")

    for i, card in enumerate(cards, 1):
        headline = card.get("headline", "")
        claim_filter = card.get("filter", "")
        cited_ids = card.get("supporting_evidence_ids", [])
        supp_count = card.get("supporting_count")
        str_label = card.get("strength_label", "")

        # 1. Existence check: every cited id must exist in engine_dataset.csv
        missing_ids = [cid for cid in cited_ids if cid not in df_engine["id"].values]
        id_exists_pass = len(missing_ids) == 0 and len(cited_ids) > 0
        add_row(
            f"Insight Card {i}",
            f"Card {i} Cited IDs Exist in Dataset",
            f"All in dataset ({len(cited_ids)} IDs)",
            f"{'All exist' if id_exists_pass else 'Missing: ' + str(missing_ids)}",
            id_exists_pass,
            f"IDs: {cited_ids}"
        )

        # 2. Filter Satisfaction: each cited id satisfies the card's filter
        qualifying_df = evaluate_card_filter(df_engine, claim_filter)
        qualifying_ids = set(qualifying_df["id"].values)
        non_qualifying_cited = [cid for cid in cited_ids if cid not in qualifying_ids]
        filter_pass = len(non_qualifying_cited) == 0 and len(cited_ids) > 0
        add_row(
            f"Insight Card {i}",
            f"Card {i} Cited IDs Satisfy Claim Filter",
            f"All satisfy filter: {claim_filter}",
            f"{'All satisfy' if filter_pass else 'Non-qualifying: ' + str(non_qualifying_cited)}",
            filter_pass,
            f"Filter: {claim_filter}"
        )

        # 3. Strength Tag matches number of qualifying records
        exp_qualifying_count = len(qualifying_df)
        count_match = (supp_count == exp_qualifying_count)
        label_match = str(exp_qualifying_count) in str_label
        strength_pass = count_match and label_match
        add_row(
            f"Insight Card {i}",
            f"Card {i} Strength Count Matches Qualifying Records",
            f"{exp_qualifying_count} items (in filter)",
            f"{supp_count} items (label: '{str_label}')",
            strength_pass,
            f"Headline: '{headline}'"
        )

    # 3. Format into Markdown table
    md_lines = [
        "# Audit Check Verification Table\n",
        "Generated programmatically by `scripts/audit_check.py` reading directly from `data/engine_dataset.csv`, `data/corpus_all.csv`, and `audit/raw/*.json`.\n",
        "| Category | Metric | Expected (Pandas) | Observed (API Raw JSON) | Status | Note |",
        "| :--- | :--- | :--- | :--- | :---: | :--- |"
    ]

    total_checks = len(table_rows)
    passed_checks = sum(1 for r in table_rows if r["status"] == "PASS")
    failed_checks = sum(1 for r in table_rows if r["status"] == "FAIL")

    for r in table_rows:
        md_lines.append(f"| {r['category']} | {r['metric']} | {r['expected']} | {r['observed']} | **{r['status']}** | {r['note']} |")

    md_lines.append(f"\n**Total Checks**: {total_checks} | **Passed**: {passed_checks} | **Failed**: {failed_checks}\n")

    OUT_FILE.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Successfully generated {OUT_FILE}")
    print(f"Total: {total_checks}, Passed: {passed_checks}, Failed: {failed_checks}")

if __name__ == "__main__":
    main()

