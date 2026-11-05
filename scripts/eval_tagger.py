import os
import sys
import time
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure live Gemini mode (MOCK_LLM=0)
os.environ["MOCK_LLM"] = "0"

from app.config import settings
from app.services.tagger import tag_items, TaggedRecord

def find_golden_csv() -> Path:
    candidates = [
        PROJECT_ROOT / "data" / "golden" / "golden_set_20_-_golden_set.csv",
        PROJECT_ROOT / "data" / "golden" / "golden_set_20_-_golden_set - golden_set.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    # Fallback to any csv in data/golden
    golden_dir = PROJECT_ROOT / "data" / "golden"
    csv_files = list(golden_dir.glob("*.csv"))
    if csv_files:
        return csv_files[0]
    raise FileNotFoundError("Golden set CSV not found in data/golden/")

def load_golden_set(csv_path: Path) -> List[Dict[str, str]]:
    rows = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "id": str(r.get("id", "")).strip(),
                "text": str(r.get("text", "")).strip(),
                "stage": str(r.get("Stage", "")).strip(),
                "main_driver": str(r.get("Main driver", "")).strip(),
                "outcome": str(r.get("Outcome", "")).strip(),
            })
    return rows

def evaluate_run(
    golden_rows: List[Dict[str, str]],
    tagged_records: List[TaggedRecord]
) -> Dict[str, Any]:
    tagged_by_id = {r.id: r for r in tagged_records}
    total = len(golden_rows)

    stage_matches = 0
    driver_matches = 0
    outcome_matches = 0
    all_3_matches = 0

    row_evaluations = []
    mismatches = []

    for item in golden_rows:
        row_id = item["id"]
        human_stage = item["stage"]
        human_driver = item["main_driver"]
        human_outcome = item["outcome"]
        text_preview = item["text"].replace("\n", " ")[:70]

        ai_rec = tagged_by_id.get(row_id)
        if not ai_rec:
            ai_stage = "MISSING"
            ai_driver = "MISSING"
            ai_outcome = "MISSING"
        else:
            ai_stage = ai_rec.stage.strip()
            ai_driver = ai_rec.main_driver.strip()
            ai_outcome = ai_rec.outcome.strip()

        stage_match = (human_stage.lower() == ai_stage.lower())
        driver_match = (human_driver.lower() == ai_driver.lower())
        outcome_match = (human_outcome.lower() == ai_outcome.lower())
        all_3 = stage_match and driver_match and outcome_match

        if stage_match:
            stage_matches += 1
        else:
            mismatches.append({
                "id": row_id,
                "text_preview": text_preview,
                "field": "Stage",
                "human_label": human_stage,
                "ai_label": ai_stage,
            })

        if driver_match:
            driver_matches += 1
        else:
            mismatches.append({
                "id": row_id,
                "text_preview": text_preview,
                "field": "Main driver",
                "human_label": human_driver,
                "ai_label": ai_driver,
            })

        if outcome_match:
            outcome_matches += 1
        else:
            mismatches.append({
                "id": row_id,
                "text_preview": text_preview,
                "field": "Outcome",
                "human_label": human_outcome,
                "ai_label": ai_outcome,
            })

        if all_3:
            all_3_matches += 1

        row_evaluations.append({
            "id": row_id,
            "text_preview": text_preview,
            "human_stage": human_stage,
            "ai_stage": ai_stage,
            "stage_match": stage_match,
            "human_main_driver": human_driver,
            "ai_main_driver": ai_driver,
            "driver_match": driver_match,
            "human_outcome": human_outcome,
            "ai_outcome": ai_outcome,
            "outcome_match": outcome_match,
            "all_3_match": all_3,
        })

    total_field_checks = total * 3
    total_field_matches = stage_matches + driver_matches + outcome_matches

    return {
        "total_rows": total,
        "stage_matches": stage_matches,
        "stage_agreement_pct": (stage_matches / total * 100) if total else 0.0,
        "driver_matches": driver_matches,
        "driver_agreement_pct": (driver_matches / total * 100) if total else 0.0,
        "outcome_matches": outcome_matches,
        "outcome_agreement_pct": (outcome_matches / total * 100) if total else 0.0,
        "total_field_checks": total_field_checks,
        "total_field_matches": total_field_matches,
        "overall_field_agreement_pct": (total_field_matches / total_field_checks * 100) if total_field_checks else 0.0,
        "all_3_matches": all_3_matches,
        "exact_row_match_pct": (all_3_matches / total * 100) if total else 0.0,
        "mismatches": mismatches,
        "row_evaluations": row_evaluations,
    }

def main():
    print("==========================================================")
    print("       AI TAGGER EVALUATION ON GOLDEN SET (20 ROWS)       ")
    print("==========================================================")
    print(f"Model: {settings.GEMINI_MODEL}")
    print(f"MOCK_LLM: {settings.MOCK_LLM}")
    print(f"API Key Configured: {bool(settings.GEMINI_API_KEY)}")
    assert not settings.MOCK_LLM, "MOCK_LLM must be False for evaluation"
    assert settings.GEMINI_API_KEY, "GEMINI_API_KEY must be configured"

    golden_csv = find_golden_csv()
    print(f"Loaded Golden Set: {golden_csv.name}")

    golden_rows = load_golden_set(golden_csv)
    print(f"Total Golden Rows: {len(golden_rows)}")

    # Prepare input payload for tagger (ONLY id and text, no labels)
    raw_inputs = [{"id": r["id"], "text": r["text"]} for r in golden_rows]

    # Run 1
    print("\n--- Running AI Tagger: Run 1 ---")
    t0_run1 = time.time()
    tagged_run1 = tag_items(raw_inputs, batch_size=20)
    t1_run1 = time.time()
    time_run1 = t1_run1 - t0_run1
    print(f"Run 1 completed in {time_run1:.2f}s ({len(tagged_run1)} items tagged).")

    # Run 2 (repeatability check)
    print("\n--- Running AI Tagger: Run 2 ---")
    t0_run2 = time.time()
    tagged_run2 = tag_items(raw_inputs, batch_size=20)
    t1_run2 = time.time()
    time_run2 = t1_run2 - t0_run2
    print(f"Run 2 completed in {time_run2:.2f}s ({len(tagged_run2)} items tagged).")

    # Evaluate Run 1
    eval1 = evaluate_run(golden_rows, tagged_run1)
    eval2 = evaluate_run(golden_rows, tagged_run2)

    # Compare Run 1 vs Run 2 repeatability
    run1_by_id = {r.id: r for r in tagged_run1}
    run2_by_id = {r.id: r for r in tagged_run2}

    identical_3_fields_count = 0
    identical_all_fields_count = 0
    row_comparison_records = []

    for item in golden_rows:
        rid = item["id"]
        r1 = run1_by_id.get(rid)
        r2 = run2_by_id.get(rid)

        is_3_identical = (
            r1 and r2 and
            r1.stage == r2.stage and
            r1.main_driver == r2.main_driver and
            r1.outcome == r2.outcome
        )
        is_all_identical = (
            is_3_identical and
            r1.unmet_need == r2.unmet_need and
            r1.income_stability == r2.income_stability and
            r1.age_band == r2.age_band and
            r1.influence == r2.influence
        )

        if is_3_identical:
            identical_3_fields_count += 1
        if is_all_identical:
            identical_all_fields_count += 1

        row_comparison_records.append({
            "id": rid,
            "text_preview": item["text"].replace("\n", " ")[:65],
            "human_stage": item["stage"],
            "ai_stage_run1": r1.stage if r1 else "",
            "ai_stage_run2": r2.stage if r2 else "",
            "stage_match_run1": (r1.stage.lower() == item["stage"].lower()) if r1 else False,
            "human_main_driver": item["main_driver"],
            "ai_main_driver_run1": r1.main_driver if r1 else "",
            "ai_main_driver_run2": r2.main_driver if r2 else "",
            "driver_match_run1": (r1.main_driver.lower() == item["main_driver"].lower()) if r1 else False,
            "human_outcome": item["outcome"],
            "ai_outcome_run1": r1.outcome if r1 else "",
            "ai_outcome_run2": r2.outcome if r2 else "",
            "outcome_match_run1": (r1.outcome.lower() == item["outcome"].lower()) if r1 else False,
            "all_3_match_run1": (
                r1 and
                r1.stage.lower() == item["stage"].lower() and
                r1.main_driver.lower() == item["main_driver"].lower() and
                r1.outcome.lower() == item["outcome"].lower()
            ),
            "run1_run2_identical": is_3_identical,
        })

    # Print summary to console
    print("\n==========================================================")
    print("                    EVALUATION RESULTS                    ")
    print("==========================================================")
    print(f"Stage Agreement:       {eval1['stage_matches']}/20 ({eval1['stage_agreement_pct']:.1f}%)")
    print(f"Main Driver Agreement: {eval1['driver_matches']}/20 ({eval1['driver_agreement_pct']:.1f}%)")
    print(f"Outcome Agreement:     {eval1['outcome_matches']}/20 ({eval1['outcome_agreement_pct']:.1f}%)")
    print("----------------------------------------------------------")
    print(f"Overall Field Agreement: {eval1['total_field_matches']}/60 ({eval1['overall_field_agreement_pct']:.1f}%)")
    print(f"Exact Row Match (all 3): {eval1['all_3_matches']}/20 ({eval1['exact_row_match_pct']:.1f}%)")
    print("----------------------------------------------------------")
    print(f"Run-to-Run Consistency:  {identical_3_fields_count}/20 rows ({identical_3_fields_count / 20 * 100:.1f}%) identical across both runs")
    print("==========================================================")

    print(f"\nTotal Mismatches on Run 1: {len(eval1['mismatches'])}")
    print(f"{'ID':<10} | {'Field':<15} | {'Human Label':<35} | {'AI Label':<35}")
    print("-" * 105)
    for m in eval1["mismatches"]:
        print(f"{m['id']:<10} | {m['field']:<15} | {m['human_label']:<35} | {m['ai_label']:<35}")
        print(f"   Text: \"{m['text_preview']}\"")
        print("-" * 105)

    # Save runtime/eval_report.csv
    runtime_dir = PROJECT_ROOT / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    csv_out_path = runtime_dir / "eval_report.csv"
    with open(csv_out_path, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "id",
            "text_preview",
            "human_stage",
            "ai_stage_run1",
            "ai_stage_run2",
            "stage_match_run1",
            "human_main_driver",
            "ai_main_driver_run1",
            "ai_main_driver_run2",
            "driver_match_run1",
            "human_outcome",
            "ai_outcome_run1",
            "ai_outcome_run2",
            "outcome_match_run1",
            "all_3_match_run1",
            "run1_run2_identical",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in row_comparison_records:
            writer.writerow(rec)

    print(f"\nSaved CSV Report to: {csv_out_path}")

    # Save runtime/eval_report.md
    md_out_path = runtime_dir / "eval_report.md"
    md_content = f"""# AI Tagger Evaluation Report

- **Date / Time**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
- **Golden Set Path**: `{golden_csv.relative_to(PROJECT_ROOT)}`
- **Total Rows Evaluated**: {len(golden_rows)}
- **Model Used**: `{settings.GEMINI_MODEL}` (temperature: 0.0)
- **Execution Time**: Run 1 = {time_run1:.2f}s, Run 2 = {time_run2:.2f}s

---

## 1. Agreement Summary (Run 1 vs Human Golden Labels)

| Field | Matches | Total | Agreement % |
|---|---|---|---|
| **Stage** | {eval1['stage_matches']} | 20 | **{eval1['stage_agreement_pct']:.1f}%** |
| **Main Driver** | {eval1['driver_matches']} | 20 | **{eval1['driver_agreement_pct']:.1f}%** |
| **Outcome** | {eval1['outcome_matches']} | 20 | **{eval1['outcome_agreement_pct']:.1f}%** |
| **Overall (Field-level)** | {eval1['total_field_matches']} | 60 | **{eval1['overall_field_agreement_pct']:.1f}%** |
| **Exact Row Matches (All 3 Fields)** | {eval1['all_3_matches']} | 20 | **{eval1['exact_row_match_pct']:.1f}%** |

---

## 2. Repeatability Across Runs (Run 1 vs Run 2)

- **Rows with identical predictions for all 3 fields (Stage, Main Driver, Outcome)**: **{identical_3_fields_count} / 20 ({identical_3_fields_count / 20 * 100:.1f}%)**
- **Rows with identical predictions across all 8 schema fields**: **{identical_all_fields_count} / 20 ({identical_all_fields_count / 20 * 100:.1f}%)**

---

## 3. Detailed Mismatch List (Run 1)

Total field mismatches: **{len(eval1['mismatches'])}**

| ID | Field | Human Label | AI Label (Run 1) | Text Preview |
|---|---|---|---|---|
"""
    for m in eval1["mismatches"]:
        escaped_preview = m["text_preview"].replace("|", "\\|")
        md_content += f"| `{m['id']}` | **{m['field']}** | {m['human_label']} | {m['ai_label']} | {escaped_preview} |\n"

    md_content += """
---

## 4. Full Per-Row Comparison Table

| ID | Stage (H / AI) | Driver (H / AI) | Outcome (H / AI) | Match (All 3) | Run 1=Run 2 |
|---|---|---|---|---|---|
"""
    for r in row_comparison_records:
        stage_status = f"{r['human_stage']} / {r['ai_stage_run1']}"
        driver_status = f"{r['human_main_driver']} / {r['ai_main_driver_run1']}"
        outcome_status = f"{r['human_outcome']} / {r['ai_outcome_run1']}"
        all_3_str = "Yes" if r["all_3_match_run1"] else "No"
        r1_r2_str = "Yes" if r["run1_run2_identical"] else "No"
        md_content += f"| `{r['id']}` | {stage_status} | {driver_status} | {outcome_status} | {all_3_str} | {r1_r2_str} |\n"

    with open(md_out_path, mode="w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Saved Markdown Report to: {md_out_path}")
    print("\n=== EVALUATION FINISHED ===")

if __name__ == "__main__":
    main()
