# Audit Check Verification Table

Generated programmatically by `scripts/audit_check.py` reading directly from `data/engine_dataset.csv`, `data/corpus_all.csv`, and `audit/raw/*.json`.

| Category | Metric | Expected (Pandas) | Observed (API Raw JSON) | Status | Note |
| :--- | :--- | :--- | :--- | :---: | :--- |
| Dataset Size | Corpus Total Rows | 1094 | 1094 | **PASS** |  |
| Dataset Size | Tagged Rows (Summary) | 54 | 54 | **PASS** |  |
| Dataset Size | Tagged Rows (Charts) | 54 | 54 | **PASS** |  |
| Corpus Sources | Corpus Source: appstore | 73 | 73 | **PASS** | Ground truth from corpus_all.csv |
| Corpus Sources | Corpus Source: playstore | 355 | 355 | **PASS** | Ground truth from corpus_all.csv |
| Corpus Sources | Corpus Source: reddit | 106 | 106 | **PASS** | Ground truth from corpus_all.csv |
| Corpus Sources | Corpus Source: survey | 12 | 12 | **PASS** | Ground truth from corpus_all.csv |
| Corpus Sources | Corpus Source: youtube | 548 | 548 | **PASS** | Ground truth from corpus_all.csv |
| Engine Sources | Engine Source: appstore | 4 | 4 | **PASS** | Ground truth from engine_dataset.csv |
| Engine Sources | Engine Source: interviews | 8 | 8 | **PASS** | Ground truth from engine_dataset.csv |
| Engine Sources | Engine Source: playstore | 8 | 8 | **PASS** | Ground truth from engine_dataset.csv |
| Engine Sources | Engine Source: survey | 12 | 12 | **PASS** | Ground truth from engine_dataset.csv |
| Engine Sources | Engine Source: youtube | 22 | 22 | **PASS** | Ground truth from engine_dataset.csv |
| Summary Cards | Distinct Sources (Corpus | Engine) | 6 | 6 | **PASS** | Union of sources across corpus_all and engine_dataset |
| Summary Cards | Deep Interviews Count | 8 | 8 | **PASS** |  |
| Main Drivers | Driver: Advice or question (no SIP experience) | 13 | 13 | **PASS** |  |
| Main Drivers | Driver: Cash crunch | 12 | 12 | **PASS** |  |
| Main Drivers | Driver: Confusion about the app | 3 | 3 | **PASS** |  |
| Main Drivers | Driver: Expectation gap | 1 | 1 | **PASS** |  |
| Main Drivers | Driver: Low early returns | 7 | 7 | **PASS** |  |
| Main Drivers | Driver: Other | 6 | 6 | **PASS** |  |
| Main Drivers | Driver: Outside influence | 3 | 3 | **PASS** |  |
| Main Drivers | Driver: Payment or mandate failure | 4 | 4 | **PASS** |  |
| Main Drivers | Driver: Working well / no issue | 5 | 5 | **PASS** |  |
| Outcomes | Outcome: Continuing | 19 | 19 | **PASS** |  |
| Outcomes | Outcome: Paused | 3 | 3 | **PASS** |  |
| Outcomes | Outcome: Reduced | 3 | 3 | **PASS** |  |
| Outcomes | Outcome: Stopped | 4 | 4 | **PASS** |  |
| Outcomes | Outcome: Unknown | 25 | 25 | **PASS** |  |
| Income Segments | Segment 'Fixed salary' - Total (n) | 12 | 12 | **PASS** |  |
| Income Segments | Segment 'Fixed salary' - Churn Count | 2 | 2 | **PASS** |  |
| Income Segments | Segment 'Student or dependent' - Total (n) | 5 | 5 | **PASS** |  |
| Income Segments | Segment 'Student or dependent' - Churn Count | 2 | 2 | **PASS** |  |
| Income Segments | Segment 'Variable income (freelance/business)' - Total (n) | 7 | 7 | **PASS** |  |
| Income Segments | Segment 'Variable income (freelance/business)' - Churn Count | 4 | 4 | **PASS** |  |
| Income Segments | Segment 'Unclear' - Total (n) | 30 | 30 | **PASS** |  |
| Income Segments | Segment 'Unclear' - Churn Count | 2 | 2 | **PASS** |  |
| Insights | Insight Cards Count | 4 | 4 | **PASS** | Expecting 4 cards |
| Insight Card 1 | Card 1 Cited IDs Exist in Dataset | All in dataset (4 IDs) | All exist | **PASS** | IDs: ['SV-00007', 'SV-00011', 'INT-03', 'INT-07'] |
| Insight Card 1 | Card 1 Cited IDs Satisfy Claim Filter | All satisfy filter: income_stability = 'Variable income (freelance/business)' AND outcome in ('Paused', 'Stopped', 'Reduced') | All satisfy | **PASS** | Filter: income_stability = 'Variable income (freelance/business)' AND outcome in ('Paused', 'Stopped', 'Reduced') |
| Insight Card 1 | Card 1 Strength Count Matches Qualifying Records | 4 items (in filter) | 4 items (label: 'Medium signal, 4 records') | **PASS** | Headline: 'Variable-income investors report cash flow crunches during billing windows' |
| Insight Card 2 | Card 2 Cited IDs Exist in Dataset | All in dataset (10 IDs) | All exist | **PASS** | IDs: ['SV-00007', 'SV-00009', 'SV-00011', 'SV-00012', 'PS-00139', 'PS-00087', 'INT-01', 'INT-03', 'INT-06', 'INT-07'] |
| Insight Card 2 | Card 2 Cited IDs Satisfy Claim Filter | All satisfy filter: outcome in ('Paused', 'Stopped', 'Reduced') | All satisfy | **PASS** | Filter: outcome in ('Paused', 'Stopped', 'Reduced') |
| Insight Card 2 | Card 2 Strength Count Matches Qualifying Records | 10 items (in filter) | 10 items (label: 'Strong signal, 10 records') | **PASS** | Headline: 'Drop-off drivers: cash crunch and low early returns dominate churn' |
| Insight Card 3 | Card 3 Cited IDs Exist in Dataset | All in dataset (4 IDs) | All exist | **PASS** | IDs: ['PS-00066', 'PS-00139', 'AS-00014', 'AS-00060'] |
| Insight Card 3 | Card 3 Cited IDs Satisfy Claim Filter | All satisfy filter: main_driver = 'Payment or mandate failure' | All satisfy | **PASS** | Filter: main_driver = 'Payment or mandate failure' |
| Insight Card 3 | Card 3 Strength Count Matches Qualifying Records | 4 items (in filter) | 4 items (label: 'Medium signal, 4 records') | **PASS** | Headline: '4 records cite Payment or mandate failure across bank debits' |
| Insight Card 4 | Card 4 Cited IDs Exist in Dataset | All in dataset (7 IDs) | All exist | **PASS** | IDs: ['SV-00002', 'SV-00004', 'SV-00006', 'SV-00009', 'SV-00011', 'YT-00135', 'INT-02'] |
| Insight Card 4 | Card 4 Cited IDs Satisfy Claim Filter | All satisfy filter: main_driver = 'Low early returns' | All satisfy | **PASS** | Filter: main_driver = 'Low early returns' |
| Insight Card 4 | Card 4 Strength Count Matches Qualifying Records | 7 items (in filter) | 7 items (label: 'Strong signal, 7 records') | **PASS** | Headline: '7 records cite Low early returns during initial investment period' |

**Total Checks**: 50 | **Passed**: 50 | **Failed**: 0
