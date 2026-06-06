# Phase 2 — Claude Code Execution Guide
## PANW GCS North Star · Step-by-Step Build Instructions
**Use with:** Claude Code CLI (`claude` in terminal) or Cursor AI  
**Pre-requisite:** BigQuery tables live in `gcs_north_star` (Phase 1 complete)

---

## How to use this guide

For each step:
1. Open terminal in your project root (`panw-gcs-northstar/`)
2. Start Claude Code: `claude` (or open Cursor)
3. Paste the **Claude Code Prompt** exactly as written
4. Run the **Verify** command to confirm the step worked
5. Move to the next step only after verification passes

---

## Pre-flight checklist

Run these before starting. All must pass.

```bash
# 1. Confirm BigQuery tables exist
bq ls gcs_north_star
# Expected: csm_rep  accounts  contracts  daily_usage_logs  account_health

# 2. Confirm Python environment
python --version   # must be 3.11+
which python       # must point to your venv

# 3. Confirm gcloud auth
gcloud auth application-default print-access-token | head -c 20
# Expected: ya29... (token prefix)

# 4. Confirm project is set
echo $BIGQUERY_PROJECT_ID
# Expected: your-gcp-project-id
```

---

# PART 1 — DATA PIPELINE

---

## Step 1 — Setup project structure, requirements, environment

**What you're building:** Folder structure, dependencies, and environment config.

### Claude Code Prompt:
```
Set up the project structure for the PANW GCS North Star pipeline.

Create the following directory structure:
  sql/
  pipeline/
    __init__.py
  tests/
    __init__.py
  .env.example

Create requirements.txt with these pinned dependencies:
  google-cloud-bigquery==3.17.2
  google-cloud-bigquery-storage==2.24.0
  pyarrow==15.0.2
  db-dtypes==1.2.0
  pandas==2.2.1
  streamlit==1.32.0
  plotly==5.19.0
  pytest==8.1.0
  python-dotenv==1.0.1

Create .env.example with:
  BIGQUERY_PROJECT_ID=your-gcp-project-id
  BIGQUERY_DATASET_ID=gcs_north_star

Create pipeline/config.py that:
  - Loads .env file using python-dotenv
  - Reads BIGQUERY_PROJECT_ID (raise ValueError if not set)
  - Reads BIGQUERY_DATASET_ID (default: 'gcs_north_star')
  - Exposes PROJECT_ID and DATASET_ID as module-level constants
```

### Verify:
```bash
pip install -r requirements.txt
python -c "from pipeline.config import PROJECT_ID; print('Config OK:', PROJECT_ID)"
```

---

## Step 2 — Create output tables DDL

**What you're building:** `sql/00_setup_tables.sql` — creates all 4 output tables in BigQuery.

### Claude Code Prompt:
```
Create sql/00_setup_tables.sql with BigQuery DDL for these four output tables.
Use CREATE TABLE IF NOT EXISTS for all. Use the project/dataset from pipeline/config.py.

TABLE 1: gcs_north_star.realized_arr_monthly
  account_id               STRING NOT NULL
  month                    DATE NOT NULL           -- first of month e.g. 2024-01-01
  contracted_arr           INT64 NOT NULL
  deployment_score         NUMERIC NOT NULL        -- 0.0000 to 1.0000
  sustained_usage_score    NUMERIC NOT NULL
  technical_health_score   NUMERIC NOT NULL
  expansion_momentum       NUMERIC NOT NULL
  prs                      NUMERIC NOT NULL        -- 0.0000 to 1.0000
  realized_arr             NUMERIC NOT NULL        -- 0.00 to contracted_arr
  prs_band                 STRING NOT NULL         -- Green | Yellow | Orange | Red
  shelfware_override       BOOL NOT NULL
  flag_overage             BOOL NOT NULL
  months_in_window         INT64 NOT NULL
  rep_id                   STRING NOT NULL
  rep_name                 STRING NOT NULL
  region                   STRING NOT NULL
  segment                  STRING NOT NULL
  industry                 STRING
PARTITION BY month
CLUSTER BY region, segment, prs_band

TABLE 2: gcs_north_star.csm_monthly_summary  [NEW — not in sys_arch.md]
  month                    DATE NOT NULL
  csm_id                   STRING NOT NULL
  rep_name                 STRING NOT NULL
  region                   STRING NOT NULL
  segment                  STRING NOT NULL
  account_count            INT64
  total_contracted_arr     INT64
  total_realized_arr       NUMERIC
  portfolio_prs            NUMERIC              -- ARR-weighted: SUM(prs*arr)/SUM(arr)
  realization_rate_pct     NUMERIC              -- 0.00 to 100.00
  green_accounts           INT64
  yellow_accounts          INT64
  orange_accounts          INT64
  red_accounts             INT64
  shelfware_accounts       INT64
  overage_accounts         INT64
  at_risk_arr              NUMERIC              -- ARR where prs_band IN ('Red','Orange')
PARTITION BY month
CLUSTER BY region, segment

TABLE 3: gcs_north_star.portfolio_summary
  month                    DATE NOT NULL
  total_contracted_arr     INT64 NOT NULL
  total_realized_arr       NUMERIC NOT NULL
  unrealized_gap           NUMERIC NOT NULL
  portfolio_prs            NUMERIC NOT NULL     -- ARR-weighted
  realization_rate_pct     NUMERIC NOT NULL
  green_accounts           INT64
  green_arr                NUMERIC
  yellow_accounts          INT64
  yellow_arr               NUMERIC
  orange_accounts          INT64
  orange_arr               NUMERIC
  red_accounts             INT64
  red_arr                  NUMERIC
  shelfware_accounts       INT64
  shelfware_arr            NUMERIC
  overage_accounts         INT64
  overage_arr              NUMERIC
  dq_001_orphaned_count    INT64
  dq_002_rogue_count       INT64
PARTITION BY month

TABLE 4: gcs_north_star.dq_report
  run_timestamp            TIMESTAMP NOT NULL
  log_id                   STRING
  account_id               STRING
  date                     DATE
  compute_credits_consumed INT64
  dq_rule                  STRING NOT NULL      -- DQ-001 | DQ-002 | DQ-005
  exclusion_reason         STRING

Also create pipeline/setup_tables.py that:
  - Reads sql/00_setup_tables.sql
  - Executes it against BigQuery using the client from pipeline/config.py
  - Prints "Created table: <table_name>" for each table
  - Is idempotent (safe to run multiple times)
```

### Verify:
```bash
python pipeline/setup_tables.py
bq ls gcs_north_star
# Expected: 9 tables including realized_arr_monthly, csm_monthly_summary,
#           portfolio_summary, dq_report (plus the 5 source tables)
```

---

## Step 3 — DQ preprocessing view + dq_report insert

**What you're building:** `sql/01_dq_preprocessing.sql` — the DQ gate that all downstream SQL uses.

### Claude Code Prompt:
```
Create sql/01_dq_preprocessing.sql using BigQuery SQL dialect.
Reference: specs/sys_arch.md Section 3.

The file must contain TWO statements separated by a semicolon:

STATEMENT 1 — CREATE OR REPLACE VIEW gcs_north_star.clean_usage_logs AS:
  SELECT log_id, account_id, date, compute_credits_consumed
  FROM gcs_north_star.daily_usage_logs
  WHERE
    account_id IN (SELECT account_id FROM gcs_north_star.accounts)   -- DQ-001: exclude orphaned
    AND date >= DATE('2024-01-01')                                    -- DQ-002: exclude pre-2024
    AND compute_credits_consumed >= 0;                                -- DQ-005: exclude negative

STATEMENT 2 — INSERT INTO gcs_north_star.dq_report:
  Capture all rows from gcs_north_star.daily_usage_logs that fail any DQ rule.
  For each failing row include:
    CURRENT_TIMESTAMP() AS run_timestamp
    log_id, account_id, date, compute_credits_consumed
    dq_rule (DQ-001, DQ-002, or DQ-005)
    exclusion_reason (human-readable description)
  
  DQ-001: account_id NOT IN (SELECT account_id FROM gcs_north_star.accounts)
  DQ-002: date < DATE('2024-01-01')
  DQ-005: compute_credits_consumed < 0

  Use a CASE statement to assign dq_rule to each failing row.
  A row can only have one dq_rule — evaluate in order: DQ-001 first, DQ-002 second, DQ-005 third.

Also create pipeline/dq.py with:
  - run_dq_preprocessing(client, project_id, dataset_id) function
  - Executes both SQL statements in order
  - Returns a dict: {"orphaned": int, "rogue": int, "negative": int}
  - Google-style docstring (LANG-002)
  - Type hints (LANG-001)
```

### Verify:
```bash
python -c "
from google.cloud import bigquery
from pipeline.config import PROJECT_ID, DATASET_ID
from pipeline.dq import run_dq_preprocessing
client = bigquery.Client(project=PROJECT_ID)
counts = run_dq_preprocessing(client, PROJECT_ID, DATASET_ID)
print('DQ counts:', counts)
# Expected: orphaned > 0 (200 injected), rogue > 0 (150 injected)
"
```

---

## Step 4 — Realized ARR monthly SQL (main pipeline, Steps 1–6)

**What you're building:** `sql/02_realized_arr_monthly.sql` — the core metric computation.

### Claude Code Prompt:
```
Create sql/02_realized_arr_monthly.sql using BigQuery SQL dialect.
Reference: specs/sys_arch.md Sections 4–6, specs/prd.md Section 6 (invariants).

This is a single INSERT INTO gcs_north_star.realized_arr_monthly statement
using a WITH clause to compute all 6 steps for a target month.
Use @target_month as a DATE query parameter.

The WITH clause must contain these CTEs in order:

CTE: active_contracts
  - SELECT account_id, MAX(annual_commit_dollars) AS contracted_arr,
           MAX(included_monthly_compute_credits) AS included_monthly_credits,
           MIN(start_date) AS earliest_start
  - FROM gcs_north_star.contracts
  - WHERE start_date <= LAST_DAY(@target_month, MONTH)
    AND end_date >= @target_month
  - GROUP BY account_id
  (INV-006: MAX resolves overlapping contracts)

CTE: monthly_consumption
  - SUM(compute_credits_consumed) AS monthly_consumed per account
  - FROM gcs_north_star.clean_usage_logs
  - WHERE DATE_TRUNC(date, MONTH) = @target_month

CTE: deployment (Step 2)
  - deployment_score = ROUND(LEAST(1.0, COALESCE(consumed,0) / NULLIF(included,0)), 4)
  - flag_overage = COALESCE(consumed, 0) > included
  (INV-001: LEAST(1.0) enforces cap)

CTE: trailing_usage (for sustained score)
  - Monthly aggregation from clean_usage_logs
  - Window: DATE_TRUNC(@target_month - 11 months) to @target_month

CTE: sustained (Step 3)
  - window_size = LEAST(DATE_DIFF(@target_month, earliest_start, MONTH) + 1, 12)
  - healthy_months = COUNTIF(monthly_consumed >= 0.30 * included_monthly_credits)
  - sustained_usage_score = ROUND(SAFE_DIVIDE(healthy_months, window_size), 4)

CTE: health_scores (Step 4)
  - AVG of health_score from gcs_north_star.account_health for the target month
  - health_color mapping: Green=1.00, Yellow=0.60, Red=0.20, NULL/other=0.60
  - If no records for account-month: COALESCE to 0.60

CTE: trailing_6 (for expansion momentum)
  - Monthly aggregation for trailing 6 months

CTE: expansion (Step 5)
  - New account guard: IF months_active < 3 THEN 0.10
  - WHEN COUNTIF(consumed >= 1.20 * included) >= 3 THEN 1.00
  - WHEN COUNTIF(consumed >= 0.70 * included) >= 3 THEN 0.70
  - WHEN COUNTIF(consumed >= 0.30 * included) >= 3 THEN 0.40
  - ELSE 0.10

FINAL SELECT with shelfware override (Step 6, INV-003):
  prs = CASE
    WHEN deployment_score = 0.0 AND sustained_usage_score = 0.0 THEN 0.0
    ELSE ROUND(d*0.40 + s*0.30 + h*0.20 + e*0.10, 4)
  END
  realized_arr = ROUND(contracted_arr * prs, 2)  [INV-002: never > contracted_arr]
  prs_band = CASE WHEN prs >= 0.80 THEN 'Green' WHEN prs >= 0.60 THEN 'Yellow'
                  WHEN prs >= 0.30 THEN 'Orange' ELSE 'Red' END
  shelfware_override = (deployment_score = 0.0 AND sustained_usage_score = 0.0)

JOIN accounts and csm_rep to include rep_id, rep_name, region, segment, industry.
Use WRITE_TRUNCATE style: delete existing rows for @target_month before inserting.
```

### Verify:
```bash
# Quick smoke test — run for one month
bq query --use_legacy_sql=false --parameter="target_month:DATE:2024-12-01" \
  "$(cat sql/02_realized_arr_monthly.sql | sed 's/INSERT INTO.*/SELECT COUNT(*) as rows/')"
# Expected: rows between 800 and 1000
```

---

## Step 5 — CSM-level summary SQL

**What you're building:** `sql/03_csm_monthly_summary.sql` — aggregates account rows to CSM rep level.

### Claude Code Prompt:
```
Create sql/03_csm_monthly_summary.sql using BigQuery SQL dialect.
Use @target_month as a DATE query parameter.

This SQL aggregates gcs_north_star.realized_arr_monthly to the CSM rep level
and inserts into gcs_north_star.csm_monthly_summary.

DELETE existing rows for @target_month before inserting (idempotent).

SELECT:
  @target_month AS month
  rep_id AS csm_id
  MAX(rep_name) AS rep_name
  MAX(region) AS region
  MAX(segment) AS segment
  COUNT(DISTINCT account_id) AS account_count
  SUM(contracted_arr) AS total_contracted_arr
  SUM(realized_arr) AS total_realized_arr
  ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)), 4) AS portfolio_prs
  ROUND(SAFE_DIVIDE(SUM(realized_arr), SUM(contracted_arr)) * 100, 2) AS realization_rate_pct
  COUNTIF(prs_band = 'Green') AS green_accounts
  COUNTIF(prs_band = 'Yellow') AS yellow_accounts
  COUNTIF(prs_band = 'Orange') AS orange_accounts
  COUNTIF(prs_band = 'Red') AS red_accounts
  COUNTIF(shelfware_override = TRUE) AS shelfware_accounts
  COUNTIF(flag_overage = TRUE) AS overage_accounts
  SUM(CASE WHEN prs_band IN ('Red','Orange') THEN contracted_arr ELSE 0 END) AS at_risk_arr

FROM gcs_north_star.realized_arr_monthly
WHERE month = @target_month
GROUP BY rep_id

Note: portfolio_prs uses ARR-weighted average to satisfy prd.md INV-010.
```

### Verify:
```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) as csm_rows FROM gcs_north_star.csm_monthly_summary WHERE month = '2024-12-01'"
# Expected: rows = number of unique reps (up to 50)
```

---

## Step 6 — Portfolio summary SQL

**What you're building:** `sql/04_portfolio_summary.sql` — single-row monthly portfolio rollup.

### Claude Code Prompt:
```
Create sql/04_portfolio_summary.sql using BigQuery SQL dialect.
Use @target_month as a DATE query parameter.

DELETE existing rows for @target_month before inserting (idempotent).

SELECT from gcs_north_star.realized_arr_monthly WHERE month = @target_month:
  @target_month AS month
  SUM(contracted_arr) AS total_contracted_arr
  SUM(realized_arr) AS total_realized_arr
  SUM(contracted_arr) - SUM(realized_arr) AS unrealized_gap
  ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)), 4) AS portfolio_prs
  ROUND(SAFE_DIVIDE(SUM(realized_arr), SUM(contracted_arr)) * 100, 2) AS realization_rate_pct
  COUNTIF(prs_band = 'Green') AS green_accounts
  SUM(CASE WHEN prs_band = 'Green' THEN contracted_arr ELSE 0 END) AS green_arr
  COUNTIF(prs_band = 'Yellow') AS yellow_accounts
  SUM(CASE WHEN prs_band = 'Yellow' THEN contracted_arr ELSE 0 END) AS yellow_arr
  COUNTIF(prs_band = 'Orange') AS orange_accounts
  SUM(CASE WHEN prs_band = 'Orange' THEN contracted_arr ELSE 0 END) AS orange_arr
  COUNTIF(prs_band = 'Red') AS red_accounts
  SUM(CASE WHEN prs_band = 'Red' THEN contracted_arr ELSE 0 END) AS red_arr
  COUNTIF(shelfware_override = TRUE) AS shelfware_accounts
  SUM(CASE WHEN shelfware_override THEN contracted_arr ELSE 0 END) AS shelfware_arr
  COUNTIF(flag_overage = TRUE) AS overage_accounts
  SUM(CASE WHEN flag_overage THEN contracted_arr ELSE 0 END) AS overage_arr

JOIN dq counts from gcs_north_star.dq_report for the same run date:
  COUNTIF(dq_rule = 'DQ-001') AS dq_001_orphaned_count
  COUNTIF(dq_rule = 'DQ-002') AS dq_002_rogue_count
```

### Verify:
```bash
bq query --use_legacy_sql=false \
  "SELECT total_contracted_arr, total_realized_arr, portfolio_prs
   FROM gcs_north_star.portfolio_summary WHERE month = '2024-12-01'"
# Expected: total_contracted_arr ~90M, portfolio_prs ~0.70-0.80
```

---

## Step 7 — Python pipeline runner

**What you're building:** `pipeline/run_pipeline.py` — the entry point that executes all SQL for all 12 months.

### Claude Code Prompt:
```
Create pipeline/run_pipeline.py that orchestrates the full pipeline.
Reference: specs/sys_arch.md Section 7 engineering conventions (LANG-001 to LANG-010).

The script must:

1. Accept CLI argument: --month YYYY-MM-DD (single month) or default to all 12 months of 2024

2. Initialize BigQuery client using pipeline/config.py

3. For each target_month in the range [2024-01-01 ... 2024-12-01]:
   a. Log: "Processing month: {target_month}"
   b. Run sql/01_dq_preprocessing.sql (Step 0) — only once, not per month
   c. Run sql/02_realized_arr_monthly.sql with @target_month parameter
   d. Run sql/03_csm_monthly_summary.sql with @target_month parameter
   e. Run sql/04_portfolio_summary.sql with @target_month parameter
   f. Log row counts: "Month {month}: {n} account rows, {n} CSM rows"

4. Run sql/01_dq_preprocessing.sql ONCE at the start (not inside the month loop)

5. Log total execution time at the end

6. Return exit code 0 on success, 1 on any error

Requirements:
- Use google.cloud.bigquery.Client for all BigQuery operations (LANG-004)
- Use logging.getLogger(__name__) for all log output (LANG-008)
- Parameterize SQL using google.cloud.bigquery.QueryJobConfig with query_parameters
- All SQL is WRITE_TRUNCATE style (idempotent per LANG-005)
- Type hints on all functions (LANG-001)
- Google-style docstrings (LANG-002)

Helper function needed:
  def execute_sql_file(client, sql_path, params=None) -> int:
    Reads the SQL file, substitutes dataset references using config values,
    runs the query with params, returns row count.
```

### Run the full pipeline:
```bash
# Set env
export BIGQUERY_PROJECT_ID=your-project-id

# Run all 12 months
python pipeline/run_pipeline.py

# Or run a single month for testing
python pipeline/run_pipeline.py --month 2024-12-01
```

### Verify:
```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(DISTINCT month) as months, COUNT(*) as total_rows
   FROM gcs_north_star.realized_arr_monthly"
# Expected: months=12, total_rows between 7000 and 15000

bq query --use_legacy_sql=false \
  "SELECT COUNT(DISTINCT month) as months FROM gcs_north_star.csm_monthly_summary"
# Expected: months=12
```

---

# PART 2 — AUTOMATED DQ TESTS

---

## Step 8 — Test infrastructure (conftest.py)

**What you're building:** `tests/conftest.py` — shared fixtures and the `run_query()` helper used by all tests.

### Claude Code Prompt:
```
Create tests/conftest.py with shared test infrastructure.
Reference: specs/test_spec.md Section 1.

The file must contain:

1. Constants:
   PROJECT_ID  = os.environ["BIGQUERY_PROJECT_ID"]
   DATASET_ID  = os.environ.get("BIGQUERY_DATASET_ID", "gcs_north_star")
   TARGET_MONTH = datetime.date(2024, 12, 1)

2. A pytest fixture:
   @pytest.fixture(scope="session")
   def bq_client():
       from google.cloud import bigquery
       return bigquery.Client(project=PROJECT_ID)

3. A helper function (not a fixture):
   def run_query(sql: str, params: list = None) -> pd.DataFrame:
     Executes a BigQuery SQL string and returns the result as a pandas DataFrame.
     - Uses the bq_client from a module-level client instance
     - Replaces {PROJECT_ID} and {DATASET_ID} placeholders in the SQL string
     - Accepts optional query_parameters list for parameterized queries
     - Raises AssertionError with the query if BigQuery returns an error
     - Returns pd.DataFrame with column names matching the SELECT aliases

4. A module-level client:
   _client = bigquery.Client(project=PROJECT_ID)

5. pytest.ini settings (in pytest.ini or pyproject.toml):
   addopts = -v --tb=short
   testpaths = tests
```

### Verify:
```bash
python -c "
import tests.conftest as tc
df = tc.run_query('SELECT 1 AS test_col')
print('conftest OK:', df['test_col'][0] == 1)
"
```

---

## Step 9 — DQ tests and invariant tests

**What you're building:** `tests/test_dq.py` and `tests/test_invariants.py`

### Claude Code Prompt:
```
Create two test files using pytest. Both files import run_query and TARGET_MONTH
from tests/conftest.py.

FILE 1: tests/test_dq.py
Reference: specs/test_spec.md Section 2 (DQ Test Suite)

Include all 5 tests exactly as specified:
- test_dq_t01_no_orphaned_logs(): count of orphaned in clean_usage_logs must be 0
- test_dq_t02_no_rogue_dates(): count of pre-2024 in clean_usage_logs must be 0
- test_dq_t03_orphaned_flagged_in_report(): DQ-001 count in dq_report must be > 0
- test_dq_t04_rogue_flagged_in_report(): DQ-002 count in dq_report must be > 0
- test_dq_t05_no_negative_consumption(): negative consumption count must be 0

FILE 2: tests/test_invariants.py
Reference: specs/test_spec.md Section 3 (Invariant Tests)

Include all 5 invariant tests:
- test_inv_t01_deployment_capped(): deployment_score > 1.0 count must be 0
- test_inv_t02_realized_le_contracted(): realized_arr > contracted_arr count must be 0
- test_inv_t03_shelfware_override(): D=0 AND S=0 must have prs=0.0 and override=TRUE
- test_inv_t04_shelfware_accounts_zero_prs(): accounts with no usage must have realized_arr=0
- test_inv_t05_portfolio_prs_weighted(): portfolio_summary.portfolio_prs must match
  SUM(prs * contracted_arr) / SUM(contracted_arr) within 0.0001 tolerance

All tests:
- Use run_query() from conftest.py
- Have clear assert messages showing the actual value that failed
- Filter to WHERE month = TARGET_MONTH for realized_arr_monthly queries
- Are idempotent (safe to run multiple times)
```

### Verify:
```bash
pytest tests/test_dq.py tests/test_invariants.py -v
# Expected: 10 passed
```

---

## Step 10 — Edge case and integration tests

**What you're building:** `tests/test_edge_cases.py` and `tests/test_integration.py`

### Claude Code Prompt:
```
Create two test files.

FILE 1: tests/test_edge_cases.py
Reference: specs/test_spec.md Section 4 (Edge Case Scenarios)

These tests validate the 5 injected anomalies from generate_dataset.py.
Do NOT create test data — query the existing gcs_north_star tables.

test_s1_shelfware_accounts_have_zero_prs():
  Find accounts in gcs_north_star.accounts that have ZERO entries in 
  gcs_north_star.clean_usage_logs. Assert that ALL of them have 
  realized_arr = 0.0 in realized_arr_monthly for TARGET_MONTH.

test_s2_spike_drop_low_sustained():
  Find accounts where December deployment_score > 0 but sustained_usage_score < 0.15.
  Assert that at least 30 such accounts exist (spike-and-drop pattern).
  Assert their prs_band is 'Orange' or 'Red'.

test_s3_overager_deployment_capped():
  Find accounts where flag_overage = TRUE in TARGET_MONTH.
  Assert deployment_score = 1.0 for all (overages are capped).
  Assert expansion_momentum >= 0.70 for accounts with flag_overage = TRUE for 3+ months.

test_s4_expansion_no_double_count():
  Find account_ids that appear more than once in gcs_north_star.contracts.
  Assert that their contracted_arr in realized_arr_monthly equals
  MAX(annual_commit_dollars) from contracts, NOT the SUM.

test_s5_dq_exclusions_logged():
  Assert dq_report has at least 200 DQ-001 rows (orphaned logs).
  Assert dq_report has at least 100 DQ-002 rows (rogue usage).
  Assert none of those excluded account_ids appear in realized_arr_monthly.

FILE 2: tests/test_integration.py
Reference: specs/test_spec.md Section 6 (Integration Tests)

test_int_t01_output_table_schema(): realized_arr_monthly has all required columns
test_int_t02_row_count(): total rows between 7000 and 15000
test_int_t03_all_bands_present(): all 4 prs_bands appear in December
test_int_t04_idempotent(): running the December pipeline twice produces same row count
  (call python pipeline/run_pipeline.py --month 2024-12-01 twice)
test_int_t05_csm_level_complete(): csm_monthly_summary has rows for all 12 months
  and all unique rep_ids from accounts table appear at least once

test_dash_t01_portfolio_12_months(): portfolio_summary has 12 rows (one per month)
test_dash_t02_all_regions(): all 4 regions appear in December realized_arr_monthly
```

### Verify:
```bash
pytest tests/test_edge_cases.py tests/test_integration.py -v
# Expected: all pass
```

---

## Step 11 — Run the full test suite

### Command:
```bash
pytest tests/ -v --tb=short
```

### Expected output:
```
tests/test_dq.py::test_dq_t01_no_orphaned_logs PASSED
tests/test_dq.py::test_dq_t02_no_rogue_dates PASSED
tests/test_dq.py::test_dq_t03_orphaned_flagged_in_report PASSED
tests/test_dq.py::test_dq_t04_rogue_flagged_in_report PASSED
tests/test_dq.py::test_dq_t05_no_negative_consumption PASSED
tests/test_invariants.py::test_inv_t01_deployment_capped PASSED
tests/test_invariants.py::test_inv_t02_realized_le_contracted PASSED
tests/test_invariants.py::test_inv_t03_shelfware_override PASSED
tests/test_invariants.py::test_inv_t04_shelfware_accounts_zero_prs PASSED
tests/test_invariants.py::test_inv_t05_portfolio_prs_weighted PASSED
tests/test_edge_cases.py::test_s1_shelfware_accounts_have_zero_prs PASSED
... (all 20 tests pass)
========================= 20 passed in Xs =========================
```

### If tests fail:
```
# RULE: Fix the spec first, then regenerate. Never just patch the code.
# 1. Identify which spec section has the ambiguity
# 2. Update the relevant spec file (prd.md or sys_arch.md)
# 3. Re-run the Claude Code prompt for that step
# 4. Re-run pytest
```

---

# PART 3 — VISUALIZATION PROTOTYPE

---

## Step 12 — Streamlit dashboard

**What you're building:** `dashboard.py` — executive dashboard with Portfolio, Region, and Rep views.

### Claude Code Prompt:
```
Create dashboard.py as a multi-page Streamlit application.
Reference: specs/prd.md Section 5 (User Workflows).

SETUP:
  - Load credentials from .env using python-dotenv
  - Use @st.cache_data(ttl=600) on ALL BigQuery query functions
  - Use plotly.express for all charts
  - Add a sidebar with these filters:
      Month selector: selectbox of all 12 months (default: December 2024)
      Region filter: multiselect ['All', 'North America', 'EMEA', 'APAC', 'LATAM']
      Segment filter: radio ['All', 'Enterprise', 'Mid-Market']

PAGE 1 — Portfolio Executive Summary (default page):
  Section A: 4 metric cards in a row:
    - Total Contracted ARR (from portfolio_summary)
    - Total Realized ARR (green card)
    - Unrealized Gap (red/orange card)
    - Portfolio PRS % (formatted as percentage)

  Section B: PRS tier distribution — stacked horizontal bar chart:
    - X axis: ARR ($M), color-coded Green/Yellow/Orange/Red
    - Show account counts as text labels on bars
    - Title: "ARR by health band — {selected_month}"

  Section C: Monthly trend line chart:
    - X axis: months Jan–Dec 2024
    - Two lines: Contracted ARR and Realized ARR
    - Y axis: $M
    - Title: "Realized ARR trend"

PAGE 2 — By Region:
  Section A: Side-by-side bar charts:
    - Left: Total Realized ARR by region
    - Right: Portfolio PRS % by region (with a dashed line at portfolio average)

  Section B: Region summary table:
    Columns: Region | Accounts | Contracted ARR | Realized ARR | PRS% | At-Risk ARR
    Sort by PRS% ascending (worst first)

PAGE 3 — By Sales Rep:
  Section A: Rep performance table (from csm_monthly_summary):
    Columns: Rep Name | Region | Segment | Accounts | Contracted ARR | Realized ARR | PRS% | At-Risk
    Sortable by any column
    Row color: red row if PRS% < 30%, orange if < 60%

  Section B: Rep drill-down:
    Select a rep from a selectbox
    Show their individual accounts sorted by PRS ascending
    Columns: Company | Industry | PRS | Deployment | Sustained | Health | Momentum | Realized ARR | Band

NAVIGATION:
  Use st.sidebar.radio for page navigation: ['Portfolio', 'By Region', 'By Rep']

DATA FUNCTIONS (all cached with @st.cache_data(ttl=600)):
  load_portfolio_summary(month) -> pd.DataFrame  [from portfolio_summary]
  load_portfolio_trend() -> pd.DataFrame          [all 12 months from portfolio_summary]
  load_region_summary(month) -> pd.DataFrame      [from realized_arr_monthly, grouped by region]
  load_rep_summary(month) -> pd.DataFrame         [from csm_monthly_summary]
  load_account_detail(month, rep_id) -> pd.DataFrame  [from realized_arr_monthly]

COLORS (consistent throughout):
  Green:  #1D9E75
  Yellow: #BA7517
  Orange: #D85A30
  Red:    #A32D2D

BOTTOM OF EACH PAGE:
  st.caption("Data source: BigQuery gcs_north_star · Refreshes every 10 minutes")
```

### Verify:
```bash
streamlit run dashboard.py
# Opens at http://localhost:8501
# Verify:
# - Portfolio page loads with 4 metric cards
# - Region page shows all 4 regions
# - Rep page shows all CSM reps with sortable table
# - Month selector changes all charts
```

---

## Step 13 — Final run and VP-ready screenshots

### Commands:
```bash
# 1. Confirm all tests pass before showing to VP
pytest tests/ -v
# Expected: all 20 pass

# 2. Start dashboard
streamlit run dashboard.py

# 3. Take screenshots for Phase 3 exec presentation:
#    - Portfolio page (December 2024) — shows the $XXM realized vs contracted gap
#    - Region page — shows which regions are underperforming
#    - Rep page — shows CSM rankings by PRS%

# 4. Export data for slides
bq extract \
  --destination_format=CSV \
  gcs_north_star.portfolio_summary \
  gs://your-bucket/portfolio_summary.csv
```

### Final verification checklist:
```
[ ] pytest tests/ → all 20 pass
[ ] realized_arr_monthly has 12 months of data
[ ] csm_monthly_summary has data for all 50 reps
[ ] dashboard loads Portfolio, Region, Rep pages without errors
[ ] month selector changes dashboard data
[ ] region filter works
[ ] rep drill-down shows account-level PRS components
[ ] all 5 edge cases appear in data (shelfware, spike-drop, overagers, expansions, DQ flags)
```

---

## Project structure after all 13 steps

```
panw-gcs-northstar/
├── specs/
│   ├── prd.md
│   ├── sys_arch.md
│   └── test_spec.md
├── sql/
│   ├── 00_setup_tables.sql
│   ├── 01_dq_preprocessing.sql
│   ├── 02_realized_arr_monthly.sql
│   ├── 03_csm_monthly_summary.sql
│   └── 04_portfolio_summary.sql
├── pipeline/
│   ├── __init__.py
│   ├── config.py
│   ├── dq.py
│   ├── setup_tables.py
│   └── run_pipeline.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_dq.py
│   ├── test_invariants.py
│   ├── test_edge_cases.py
│   └── test_integration.py
├── dashboard.py
├── generate_dataset.py
├── requirements.txt
├── .env.example
└── Realized_ARR_Spec_v2.md
```
