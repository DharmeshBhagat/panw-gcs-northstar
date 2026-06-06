# test_spec.md — Verification & Test Specification
## PANW GCS · Realized ARR Pipeline
**Version:** 2.0  
**Owner:** Principal PM, Centralized Data & AI / Analytics  
**Companion files:** `prd.md`, `sys_arch.md`

---

## 1. Test Environment Requirements

```python
# Environment setup for all tests
PROJECT_ID  = os.environ["BIGQUERY_PROJECT_ID"]
DATASET_ID  = os.environ.get("BIGQUERY_DATASET_ID", "gcs_north_star")
TARGET_MONTH = datetime.date(2024, 12, 1)   # December snapshot for assertions

# Test framework: pytest
# Run: pytest tests/ -v --tb=short
# Exit code 0 = all pass; exit code 1 = any fail
```

All assertions must be **deterministic**: given the same input data, they must
produce the same output. Tests must be idempotent (safe to run multiple times).

---

## 2. DQ Test Suite (automated, runs before metric tests)

### DQ-T01 — No orphaned logs in clean_usage_logs

```python
def test_dq_t01_no_orphaned_logs():
    """
    Assert: clean_usage_logs contains ZERO rows where
    account_id is not in the accounts table.
    Expected: count = 0
    """
    query = """
    SELECT COUNT(*) AS orphaned_count
    FROM gcs_north_star.clean_usage_logs l
    WHERE l.account_id NOT IN (
        SELECT account_id FROM gcs_north_star.accounts
    )
    """
    result = run_query(query)
    assert result["orphaned_count"][0] == 0, \
        f"FAIL DQ-T01: {result['orphaned_count'][0]} orphaned rows in clean_usage_logs"
```

### DQ-T02 — No pre-2024 dates in clean_usage_logs

```python
def test_dq_t02_no_rogue_dates():
    """
    Assert: clean_usage_logs contains ZERO rows with date < 2024-01-01.
    Expected: count = 0
    """
    query = """
    SELECT COUNT(*) AS rogue_count
    FROM gcs_north_star.clean_usage_logs
    WHERE date < DATE('2024-01-01')
    """
    result = run_query(query)
    assert result["rogue_count"][0] == 0, \
        f"FAIL DQ-T02: {result['rogue_count'][0]} pre-2024 rows in clean_usage_logs"
```

### DQ-T03 — Orphaned logs appear in dq_report with DQ-001

```python
def test_dq_t03_orphaned_flagged_in_report():
    """
    Assert: The raw daily_usage_logs table contains rows where account_id
    does not exist in accounts. These rows MUST appear in dq_report as DQ-001.
    Expected: dq_report DQ-001 count > 0 (injected anomaly must be detected)
    """
    query = """
    SELECT COUNT(*) AS flagged_count
    FROM gcs_north_star.dq_report
    WHERE dq_rule = 'DQ-001'
    """
    result = run_query(query)
    assert result["flagged_count"][0] > 0, \
        "FAIL DQ-T03: No DQ-001 records in dq_report — orphaned logs not detected"
```

### DQ-T04 — Rogue usage flagged in dq_report with DQ-002

```python
def test_dq_t04_rogue_flagged_in_report():
    """
    Assert: Pre-2024 usage rows from daily_usage_logs appear in dq_report as DQ-002.
    Expected: dq_report DQ-002 count > 0
    """
    query = """
    SELECT COUNT(*) AS flagged_count
    FROM gcs_north_star.dq_report
    WHERE dq_rule = 'DQ-002'
    """
    result = run_query(query)
    assert result["flagged_count"][0] > 0, \
        "FAIL DQ-T04: No DQ-002 records — rogue usage not detected"
```

### DQ-T05 — No negative consumption in clean_usage_logs

```python
def test_dq_t05_no_negative_consumption():
    """
    Assert: All compute_credits_consumed values >= 0.
    Expected: count = 0
    """
    query = """
    SELECT COUNT(*) AS neg_count
    FROM gcs_north_star.clean_usage_logs
    WHERE compute_credits_consumed < 0
    """
    result = run_query(query)
    assert result["neg_count"][0] == 0, \
        f"FAIL DQ-T05: {result['neg_count'][0]} negative consumption rows"
```

---

## 3. Invariant Tests (enforces prd.md INV-001 through INV-010)

### INV-T01 — Deployment Score never exceeds 1.0

```python
def test_inv_t01_deployment_capped():
    """INV-001: deployment_score must never exceed 1.0."""
    query = """
    SELECT COUNT(*) AS violations
    FROM gcs_north_star.realized_arr_monthly
    WHERE deployment_score > 1.0
    """
    result = run_query(query)
    assert result["violations"][0] == 0, \
        "FAIL INV-T01: deployment_score > 1.0 found"
```

### INV-T02 — Realized ARR never exceeds Contracted ARR

```python
def test_inv_t02_realized_le_contracted():
    """INV-002: realized_arr <= contracted_arr for every row."""
    query = """
    SELECT COUNT(*) AS violations
    FROM gcs_north_star.realized_arr_monthly
    WHERE realized_arr > contracted_arr + 0.01   -- 0.01 tolerance for float
    """
    result = run_query(query)
    assert result["violations"][0] == 0, \
        "FAIL INV-T02: realized_arr > contracted_arr found"
```

### INV-T03 — Shelfware override fires when D=0 and S=0

```python
def test_inv_t03_shelfware_override():
    """
    INV-003: All rows where deployment_score=0 AND sustained_usage_score=0
    must have prs=0.0 AND realized_arr=0.0 AND shelfware_override=TRUE.
    """
    query = """
    SELECT COUNT(*) AS violations
    FROM gcs_north_star.realized_arr_monthly
    WHERE deployment_score = 0.0
      AND sustained_usage_score = 0.0
      AND (prs != 0.0 OR realized_arr != 0.0 OR shelfware_override != TRUE)
    """
    result = run_query(query)
    assert result["violations"][0] == 0, \
        "FAIL INV-T03: Shelfware override did not fire correctly"
```

### INV-T04 — PRS is 0.0 for known shelfware accounts

```python
def test_inv_t04_shelfware_accounts_zero_prs():
    """
    Assert: Accounts with zero entries in daily_usage_logs must have
    prs = 0.0 and realized_arr = 0.0 in December 2024.
    Expected: all shelfware accounts have realized_arr = 0
    """
    query = """
    WITH zero_usage AS (
        SELECT account_id
        FROM gcs_north_star.accounts
        WHERE account_id NOT IN (
            SELECT DISTINCT account_id
            FROM gcs_north_star.clean_usage_logs
        )
    )
    SELECT COUNT(*) AS violations
    FROM gcs_north_star.realized_arr_monthly m
    JOIN zero_usage z USING (account_id)
    WHERE m.month = DATE('2024-12-01')
      AND (m.prs > 0.0 OR m.realized_arr > 0.0)
    """
    result = run_query(query)
    assert result["violations"][0] == 0, \
        "FAIL INV-T04: Shelfware accounts have non-zero PRS"
```

### INV-T05 — Portfolio PRS is ARR-weighted (not simple average)

```python
def test_inv_t05_portfolio_prs_weighted():
    """
    INV-010: Verify portfolio_prs in portfolio_summary equals
    SUM(prs * contracted_arr) / SUM(contracted_arr) for December.
    """
    query = """
    WITH computed AS (
        SELECT
            SUM(prs * contracted_arr) / SUM(contracted_arr) AS weighted_prs,
        FROM gcs_north_star.realized_arr_monthly
        WHERE month = DATE('2024-12-01')
    ),
    stored AS (
        SELECT portfolio_prs
        FROM gcs_north_star.portfolio_summary
        WHERE month = DATE('2024-12-01')
    )
    SELECT
        ABS(c.weighted_prs - s.portfolio_prs) AS delta
    FROM computed c, stored s
    """
    result = run_query(query)
    assert result["delta"][0] < 0.0001, \
        f"FAIL INV-T05: Portfolio PRS mismatch. Delta = {result['delta'][0]}"
```

---

## 4. Edge Case Scenarios (exact input → expected output)

### Scenario S1 — Shelfware account

```python
# Input
account  = { "account_id": "ACC_TEST_SHELF",  "annual_commit_dollars": 200000,
             "included_monthly_compute_credits": 16666 }
usage    = []   # ZERO usage log rows
health   = [{ "health_color": "Red", ... }]   # Red health

# Expected output (December 2024)
expected = {
    "deployment_score":      0.0,
    "sustained_usage_score": 0.0,
    "technical_health_score": 0.20,
    "expansion_momentum":    0.10,
    "prs":                   0.0,     # shelfware override fires
    "realized_arr":          0.0,     # NOT 200000 * 0.05 = 10000
    "prs_band":              "Red",
    "shelfware_override":    True,
    "flag_overage":          False,
}

def test_s1_shelfware():
    result = get_account_month_metrics("ACC_TEST_SHELF", date(2024, 12, 1))
    assert result["prs"] == 0.0,         "S1: PRS must be 0 for shelfware"
    assert result["realized_arr"] == 0.0,"S1: Realized ARR must be 0 for shelfware"
    assert result["shelfware_override"], "S1: shelfware_override flag must be True"
```

### Scenario S2 — Spike and Drop account

```python
# Input: 90% of annual credits in Month 1 (January), near-zero after
account  = { "annual_commit_dollars": 120000,
             "included_monthly_compute_credits": 10000 }
# January: consumed 108000 (= 0.9 * 12 * 10000 = 90% of annual)
# Feb-Dec: consumed ~100 per month

# Expected (December 2024, 12-month window)
expected = {
    "deployment_score":      approx(0.01),  # December month itself: 100/10000
    "sustained_usage_score": approx(0.08),  # 1 healthy month (Jan) / 12 = 0.083
    "prs_band":              "Red",          # PRS well below 0.30
    "shelfware_override":    False,          # Jan had usage → D > 0 in some months
}

def test_s2_spike_drop():
    result = get_account_month_metrics("ACC_TEST_SPIKE", date(2024, 12, 1))
    assert result["sustained_usage_score"] < 0.15, \
        f"S2: Sustained score too high for spike-and-drop: {result['sustained_usage_score']}"
    assert result["prs_band"] in ["Orange", "Red"], \
        "S2: Spike-and-drop should be Orange or Red band"
```

### Scenario S3 — Consistent Overager

```python
# Input: consistently consumes 130% of included credits every month
account  = { "annual_commit_dollars": 100000,
             "included_monthly_compute_credits": 8333 }
# All 12 months: consumed 10833 = 130% of 8333

# Expected (December 2024)
expected = {
    "deployment_score":      1.00,    # capped at 1.0 even though consuming 130%
    "sustained_usage_score": 1.00,    # 12/12 healthy months
    "expansion_momentum":    1.00,    # 6+ months at 120%+ in trailing 6
    "flag_overage":          True,    # raw consumption > included
    "prs":                   approx(0.94),  # 1.0*0.40 + 1.0*0.30 + H*0.20 + 1.0*0.10
    "prs_band":              "Green",
}

def test_s3_overager():
    result = get_account_month_metrics("ACC_TEST_OVER", date(2024, 12, 1))
    assert result["deployment_score"] == 1.0, "S3: Deployment must be capped at 1.0"
    assert result["flag_overage"] == True,    "S3: flag_overage must be True"
    assert result["expansion_momentum"] == 1.00, \
        "S3: Expansion momentum must be 1.00 for consistent overager"
    assert result["prs_band"] == "Green", "S3: Overager must be Green band"
    assert result["realized_arr"] <= result["contracted_arr"], \
        "S3: Realized ARR must never exceed Contracted ARR (INV-002)"
```

### Scenario S4 — Mid-Year Expansion (overlapping contracts)

```python
# Input: account with TWO active contracts in December
contract_1 = { "start_date": "2024-01-01", "end_date": "2024-12-31",
               "annual_commit_dollars": 100000,
               "included_monthly_compute_credits": 8333 }
contract_2 = { "start_date": "2024-06-01", "end_date": "2025-05-31",
               "annual_commit_dollars": 250000,        # larger
               "included_monthly_compute_credits": 20833 }

# Expected (December 2024)
expected = {
    "contracted_arr":   250000,   # MAX(), not 100000+250000=350000
    "deployment_score": approx(0.85),  # computed against MAX included credits
}

def test_s4_mid_year_expansion():
    result = get_account_month_metrics("ACC_TEST_EXPAND", date(2024, 12, 1))
    assert result["contracted_arr"] == 250000, \
        f"S4: contracted_arr must be MAX=250000, got {result['contracted_arr']}"
    assert result["contracted_arr"] != 350000, \
        "S4: Must not double-count overlapping contracts"
```

### Scenario S5 — Orphaned and Rogue Logs Excluded

```python
# Input:
# - Account ACC_REAL has 5000 credits consumed in December (valid)
# - ACC_FAKE_9999 has 2000 credits consumed (orphaned — not in accounts)
# - ACC_REAL has 3000 credits consumed on 2023-06-01 (rogue — pre-contract)

# Expected (December 2024 for ACC_REAL)
expected = {
    "deployment_score": approx(5000 / included_monthly),  # only 5000 counted
    # 2000 orphaned NOT added, 3000 rogue NOT added
}

def test_s5_exclusions():
    # DQ-001: orphaned count must be > 0 in dq_report
    # DQ-002: rogue count must be > 0 in dq_report
    # clean_usage_logs must not contain ACC_FAKE_9999 or 2023 dates
    dq_query = """
    SELECT
        COUNTIF(dq_rule = 'DQ-001') AS orphaned,
        COUNTIF(dq_rule = 'DQ-002') AS rogue
    FROM gcs_north_star.dq_report
    """
    dq = run_query(dq_query)
    assert dq["orphaned"][0] > 0, "S5: DQ-001 must detect injected orphaned logs"
    assert dq["rogue"][0] > 0,    "S5: DQ-002 must detect injected rogue logs"
```

---

## 5. Component Unit Tests

### Component D — Deployment Score

```python
@pytest.mark.parametrize("consumed, included, expected_d", [
    (0,      10000, 0.00),   # shelfware
    (5000,   10000, 0.50),   # 50% deployment
    (9000,   10000, 0.90),   # 90% deployment
    (10000,  10000, 1.00),   # 100% deployment
    (12000,  10000, 1.00),   # 120% — capped at 1.0
    (0,      0,     None),   # DQ-004: zero included → D = NULL
])
def test_deployment_score(consumed, included, expected_d):
    d = compute_deployment_score(consumed, included)
    if expected_d is None:
        assert d is None
    else:
        assert abs(d - expected_d) < 0.0001
```

### Component S — Sustained Usage Score

```python
@pytest.mark.parametrize("monthly_data, included, months_active, expected_s", [
    ([0]*12,             10000, 12, 0.00),  # shelfware: no healthy months
    ([9000]+[100]*11,    10000, 12, 0.083), # spike-drop: 1/12 healthy
    ([7000]*10+[0]*2,    10000, 12, 0.833), # 10/12 healthy
    ([10000]*12,         10000, 12, 1.00),  # all months healthy
    ([10000]*3,          10000, 3,  1.00),  # new account, 3 healthy months
    ([0]*3,              10000, 3,  0.00),  # new account, no usage
])
def test_sustained_usage_score(monthly_data, included, months_active, expected_s):
    s = compute_sustained_usage_score(monthly_data, included, months_active)
    assert abs(s - expected_s) < 0.005
```

### Component H — Technical Health Score

```python
@pytest.mark.parametrize("health_records, expected_h", [
    (["Green"]*4,                    1.00),
    (["Yellow"]*4,                   0.60),
    (["Red"]*4,                      0.20),
    (["Green", "Green", "Red"],      round((1.0+1.0+0.2)/3, 4)),  # 0.7333
    ([],                             0.60),  # no records → neutral default
    ([None, None],                   0.60),  # missing → neutral default
    (["Green", None, "Red"],         round((1.0+0.6+0.2)/3, 4)),  # 0.6000
])
def test_technical_health_score(health_records, expected_h):
    h = compute_technical_health_score(health_records)
    assert abs(h - expected_h) < 0.001
```

### Component E — Expansion Momentum

```python
@pytest.mark.parametrize("t6_monthly, included, months_active, expected_e", [
    ([0]*6,                10000, 12, 0.10),   # no usage
    ([8000]*6,             10000,  1, 0.10),   # new account guard (< 3 months)
    ([3500]*6,             10000, 12, 0.40),   # 6 months at 35% (≥30%)
    ([8000]*6,             10000, 12, 0.70),   # 6 months at 80% (≥70%)
    ([12500]*6,            10000, 12, 1.00),   # 6 months at 125% (≥120%)
    ([12500]*2+[0]*4,      10000, 12, 0.10),   # only 2 months at 120%+ → 0.10
    ([8000]*3+[0]*3,       10000, 12, 0.70),   # exactly 3 months at 80%
])
def test_expansion_momentum(t6_monthly, included, months_active, expected_e):
    e = compute_expansion_momentum(t6_monthly, included, months_active)
    assert e == expected_e, f"Expected {expected_e}, got {e}"
```

### PRS Assembly — Shelfware Override

```python
@pytest.mark.parametrize("d, s, h, e, expected_prs, expect_override", [
    # Shelfware: D=0, S=0 → override fires → PRS=0
    (0.0,  0.0,  0.20, 0.10, 0.0,    True),
    # D=0 but S>0 → override does NOT fire
    (0.0,  0.10, 0.60, 0.10, 0.191,  False),
    # Normal healthy account
    (0.80, 0.75, 1.00, 0.70, 0.815,  False),
    # Perfect score
    (1.0,  1.0,  1.0,  1.0,  1.0,    False),
])
def test_prs_assembly(d, s, h, e, expected_prs, expect_override):
    prs, override = compute_prs(d, s, h, e)
    assert abs(prs - expected_prs) < 0.001, \
        f"PRS mismatch: expected {expected_prs}, got {prs}"
    assert override == expect_override, \
        f"Override flag mismatch: expected {expect_override}"
```

---

## 6. Integration Tests (end-to-end pipeline)

### INT-T01 — Output table exists and has correct schema

```python
def test_int_t01_output_table_exists():
    """realized_arr_monthly must exist and have the correct column names."""
    expected_cols = {
        "account_id", "month", "contracted_arr", "deployment_score",
        "sustained_usage_score", "technical_health_score", "expansion_momentum",
        "prs", "realized_arr", "prs_band", "shelfware_override", "flag_overage",
        "months_in_window", "rep_id", "rep_name", "region", "segment"
    }
    query = """
    SELECT column_name
    FROM gcs_north_star.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = 'realized_arr_monthly'
    """
    result = run_query(query)
    actual_cols = set(result["column_name"].tolist())
    missing = expected_cols - actual_cols
    assert not missing, f"INT-T01: Missing columns: {missing}"
```

### INT-T02 — Row count in expected range

```python
def test_int_t02_row_count():
    """
    12-month pipeline for 1,000 accounts produces between 7,000 and 15,000 rows
    (accounts × active months — not all accounts are active all 12 months).
    """
    query = "SELECT COUNT(*) AS row_count FROM gcs_north_star.realized_arr_monthly"
    result = run_query(query)
    rc = result["row_count"][0]
    assert 7000 <= rc <= 15000, \
        f"INT-T02: Unexpected row count {rc}. Expected 7000–15000."
```

### INT-T03 — All PRS bands present in output

```python
def test_int_t03_all_bands_present():
    """All four health bands must appear in December output."""
    query = """
    SELECT DISTINCT prs_band
    FROM gcs_north_star.realized_arr_monthly
    WHERE month = DATE('2024-12-01')
    """
    result = run_query(query)
    bands = set(result["prs_band"].tolist())
    expected = {"Green", "Yellow", "Orange", "Red"}
    assert expected == bands, \
        f"INT-T03: Missing bands: {expected - bands}"
```

### INT-T04 — Pipeline is idempotent

```python
def test_int_t04_idempotent():
    """
    Running the pipeline twice produces identical row counts and PRS sums.
    Uses WRITE_TRUNCATE — second run must not duplicate rows.
    """
    query = """
    SELECT COUNT(*) AS rows, ROUND(SUM(prs), 2) AS total_prs
    FROM gcs_north_star.realized_arr_monthly
    WHERE month = DATE('2024-12-01')
    """
    run_1 = run_query(query)
    run_pipeline(target_month=date(2024, 12, 1))  # run again
    run_2 = run_query(query)
    assert run_1["rows"][0] == run_2["rows"][0], \
        "INT-T04: Row count changed after second pipeline run"
    assert run_1["total_prs"][0] == run_2["total_prs"][0], \
        "INT-T04: PRS sum changed after second pipeline run"
```

---

## 7. Dashboard Smoke Tests

```python
def test_dash_t01_portfolio_summary_loads():
    """Portfolio summary table returns one row per month for all 12 months."""
    query = """
    SELECT COUNT(DISTINCT month) AS months
    FROM gcs_north_star.portfolio_summary
    """
    result = run_query(query)
    assert result["months"][0] == 12, \
        f"DASH-T01: Expected 12 months in portfolio_summary, got {result['months'][0]}"

def test_dash_t02_all_regions_present():
    """All 4 regions appear in December realized_arr_monthly."""
    query = """
    SELECT COUNT(DISTINCT region) AS region_count
    FROM gcs_north_star.realized_arr_monthly
    WHERE month = DATE('2024-12-01')
    """
    result = run_query(query)
    assert result["region_count"][0] == 4, \
        "DASH-T02: Not all 4 regions present in output"

def test_dash_t03_all_reps_have_data():
    """Every csm_rep.csm_id must appear in December output (via accounts)."""
    query = """
    SELECT COUNT(*) AS reps_without_data
    FROM gcs_north_star.csm_rep r
    WHERE r.csm_id NOT IN (
        SELECT rep_id FROM gcs_north_star.realized_arr_monthly
        WHERE month = DATE('2024-12-01')
    )
    """
    result = run_query(query)
    # Some reps may have no accounts — allow up to 20% gaps
    assert result["reps_without_data"][0] < 10, \
        f"DASH-T03: {result['reps_without_data'][0]} reps have no data"
```

---

## 8. Success Criteria (overall pass conditions)

The prototype is **PASSING** when all of the following are true:

| # | Criterion | Measured by |
|---|-----------|-------------|
| 1 | All 5 DQ tests pass | `tests/test_dq.py` |
| 2 | All 5 invariant tests pass | `tests/test_invariants.py` |
| 3 | All 5 edge case scenarios pass | `tests/test_edge_cases.py` |
| 4 | All component unit tests pass (D, S, H, E, PRS) | `tests/test_components.py` |
| 5 | All 4 integration tests pass | `tests/test_integration.py` |
| 6 | Dashboard smoke tests pass | `tests/test_dashboard.py` |
| 7 | Full 12-month run completes in < 60s | Logged by `run_pipeline.py` |
| 8 | `realized_arr_monthly` contains 7,000–15,000 rows | INT-T02 |
| 9 | No row has `realized_arr > contracted_arr` | INV-T02 |
| 10 | All shelfware accounts have `realized_arr = 0` | INV-T04 |

**Run all tests:**
```bash
pytest tests/ -v --tb=short --exit-first
# exit code 0 = all pass
# exit code 1 = any fail → fix spec first, then regenerate code
```

---

## 9. Claude Code Handoff Prompt

When handing these specs to Claude Code, use this exact prompt:

```
You are building a data pipeline for Palo Alto Networks GCS.

Read the three spec files in the specs/ directory:
  - specs/prd.md       → business rules and invariants
  - specs/sys_arch.md  → exact schema, SQL logic, and file structure
  - specs/test_spec.md → verification tests and success criteria

Your task:
1. Create the BigQuery views and tables defined in sys_arch.md (sql/ directory)
2. Write the Python pipeline in pipeline/ following LANG-001 through LANG-010
3. Write all tests in tests/ matching test_spec.md exactly
4. The pipeline must pass all 10 success criteria in test_spec.md Section 8

Constraints:
- Never hardcode project_id. Read from BIGQUERY_PROJECT_ID env variable.
- All functions must be stateless and idempotent (LANG-003, LANG-005).
- Write Google-style docstrings on every function (LANG-002).
- Use NUMERIC (not FLOAT64) for all monetary and score values (LANG-009).
- Exit code 1 if any test fails (LANG-010).

Start with: sql/00_dq_view.sql, then pipeline/dq.py, then pipeline/components.py
```
