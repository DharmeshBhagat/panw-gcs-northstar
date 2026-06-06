# Claude Code Prompts — PANW GCS North Star
## Phase 2: AI-Assisted Implementation (Spec to Code)

Use these prompts in Claude Code (terminal) or Cursor once Phase 1 BigQuery tables are live.

---

## Prompt 1 — BigQuery SQL Pipeline (Realized ARR)

Paste this into Claude Code:

```
I have 5 tables in BigQuery project [YOUR_PROJECT_ID], dataset gcs_north_star:
  - csm_rep (csm_id, name, region, segment)
  - accounts (account_id, company_name, industry, rep_id)
  - contracts (contract_id, account_id, start_date, end_date, annual_commit_dollars, included_monthly_compute_credits)
  - account_health (health_color, account_id, date, compute_credits_consumed)
  - daily_usage_logs (log_id, account_id, date, compute_credits_consumed)

Using the metric spec in specs/Realized_ARR_Spec_v2.md, write a BigQuery SQL file
(realized_arr_pipeline.sql) that produces a table:
  gcs_north_star.realized_arr_monthly

With one row per account_id × month containing:
  account_id, month, contracted_arr, deployment_score, sustained_usage_score,
  technical_health_score, expansion_momentum, prs, realized_arr, prs_band,
  shelfware_override, flag_overage, rep_id, region, segment, industry

Rules:
  - Exclude orphaned logs (account_id NOT IN accounts)
  - Exclude rogue usage (date before 2024-01-01)
  - Use MAX(annual_commit_dollars) per account-month for overlapping contracts
  - Apply the shelfware override: if deployment=0 AND sustained=0, set prs=0
  - Sustained usage window: MIN(months_since_contract_start, 12)
  - Missing health_color maps to 0.60
  - Expansion momentum: accounts < 3 months active → 0.10 default
  - Expansion momentum window: trailing 6 months
```

---

## Prompt 2 — Automated DQ Tests

```
Write a Python file (dq_tests.py) with automated data quality assertions
that run against the BigQuery tables in [YOUR_PROJECT_ID].gcs_north_star.

Tests to include:
  1. No orphaned usage logs (account_id in daily_usage_logs must exist in accounts)
  2. No rogue usage (daily_usage_logs.date must be >= contract start_date)
  3. No negative compute credits consumed
  4. No contracts with zero included_monthly_compute_credits
  5. Shelfware override fired correctly (accounts with 0 usage have realized_arr = 0)
  6. PRS weights sum to 1.0 for all non-shelfware accounts
  7. realized_arr <= contracted_arr for all accounts
  8. No duplicate log_ids in daily_usage_logs
  9. All accounts have at least one active contract in the dataset period
  10. Overlapping contracts are handled (MAX logic applied, no double-counting)

Use google-cloud-bigquery Python client. Print PASS / FAIL for each test.
Exit with code 1 if any test fails.
```

---

## Prompt 3 — Streamlit Dashboard

```
Write a Streamlit app (dashboard.py) that connects to BigQuery
[YOUR_PROJECT_ID].gcs_north_star.realized_arr_monthly
and shows an executive view of Realized ARR.

Screens / views:
  1. Portfolio summary: Total Contracted ARR, Total Realized ARR, Gap, Portfolio PRS%
  2. Tier distribution: Green/Yellow/Orange/Red accounts and ARR by band (bar chart)
  3. By Region: Realized ARR and avg PRS per region (bar chart)
  4. By Sales Rep (CSM): Realized ARR, Contracted ARR, realization %, top 10 (table)
  5. Account drilldown: searchable table of accounts with all PRS components

Filters:
  - Month selector (Jan–Dec 2024)
  - Region filter
  - Segment filter (Enterprise / Mid-Market)

Use google-cloud-bigquery for data fetching.
Use st.cache_data with ttl=600 for query caching.
Use Plotly Express for charts.

Run with: streamlit run dashboard.py
```

---

## Prompt 4 — dbt-style SQL models (optional, if using dbt)

```
Create a dbt project structure for the PANW GCS North Star metric.

Models:
  - staging/stg_contracts.sql     — active contracts, MAX for overlaps
  - staging/stg_usage_logs.sql    — clean logs (exclude orphaned + rogue)
  - staging/stg_account_health.sql — latest monthly health score
  - marts/realized_arr_monthly.sql — full PRS + Realized ARR calculation
  - marts/portfolio_summary.sql   — aggregated monthly portfolio view

Include:
  - schema.yml with column descriptions and tests (not_null, unique, accepted_values)
  - sources.yml pointing to gcs_north_star dataset in BigQuery
  - A dbt_project.yml configured for BigQuery
```

---

## Project folder structure (Phase 2 complete)

```
panw-gcs-northstar/
├── generate_dataset.py          Phase 1: data generation
├── requirements.txt
├── specs/
│   └── Realized_ARR_Spec_v2.md  metric definition (hand to Claude Code)
├── sql/
│   └── realized_arr_pipeline.sql   BigQuery SQL (output of Prompt 1)
├── dq_tests.py                  automated DQ assertions (Prompt 2)
├── dashboard.py                 Streamlit exec dashboard (Prompt 3)
├── data/                        local CSV backups
│   ├── csm_rep.csv
│   ├── accounts.csv
│   ├── contracts.csv
│   ├── daily_usage_logs.csv
│   └── account_health.csv
└── .gitignore
```

---

## Quick verification queries (run in BigQuery after Phase 1)

```sql
-- 1. Row counts across all 5 tables
SELECT table_id, row_count
FROM `YOUR_PROJECT.gcs_north_star.__TABLES__`
ORDER BY table_id;

-- 2. Confirm edge cases are present
SELECT
  COUNT(*) as total_logs,
  COUNTIF(account_id NOT IN (SELECT account_id FROM `YOUR_PROJECT.gcs_north_star.accounts`)) as orphaned,
  COUNTIF(date < '2024-01-01') as rogue_predates_2024
FROM `YOUR_PROJECT.gcs_north_star.daily_usage_logs`;

-- 3. Shelfware check
SELECT COUNT(*) as shelfware_accounts
FROM `YOUR_PROJECT.gcs_north_star.accounts` a
WHERE NOT EXISTS (
  SELECT 1 FROM `YOUR_PROJECT.gcs_north_star.daily_usage_logs` l
  WHERE l.account_id = a.account_id
);

-- 4. Overlapping contracts check
SELECT account_id, COUNT(*) as contract_count
FROM `YOUR_PROJECT.gcs_north_star.contracts`
WHERE CURRENT_DATE BETWEEN start_date AND end_date
GROUP BY account_id
HAVING contract_count > 1
LIMIT 10;
```
