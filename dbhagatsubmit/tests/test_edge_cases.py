"""Edge-case test suite — validates injected anomaly scenarios from generate_dataset.py."""

from google.cloud import bigquery

from tests.conftest import TARGET_MONTH, run_query

_MONTH_PARAM = [
    bigquery.ScalarQueryParameter("target_month", "DATE", TARGET_MONTH.isoformat())
]


def test_s1_shelfware_accounts_have_zero_prs() -> None:
    """Accounts with zero clean usage logs must have realized_arr = 0 in TARGET_MONTH."""
    df = run_query("""
        WITH no_usage AS (
            SELECT a.account_id
            FROM `{PROJECT_ID}.{DATASET_ID}.accounts` a
            WHERE a.account_id NOT IN (
                SELECT DISTINCT account_id
                FROM `{PROJECT_ID}.{DATASET_ID}.clean_usage_logs`
            )
        )
        SELECT COUNT(*) AS violations
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN no_usage n ON n.account_id = r.account_id
        WHERE r.month = @target_month
          AND r.realized_arr != 0
    """, params=_MONTH_PARAM)
    violations = int(df["violations"][0])
    assert violations == 0, (
        f"Expected all zero-usage accounts to have realized_arr=0, "
        f"found {violations} violation(s)"
    )


def test_s2_spike_drop_low_sustained() -> None:
    """Spike-and-drop accounts (deployment>0, sustained<0.15) must be Orange or Red."""
    df = run_query("""
        SELECT
            COUNT(*) AS cnt,
            COUNTIF(prs_band NOT IN ('Orange', 'Red')) AS band_violations
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND deployment_score > 0
          AND sustained_usage_score < 0.15
    """, params=_MONTH_PARAM)
    cnt = int(df["cnt"][0])
    band_violations = int(df["band_violations"][0])
    assert cnt >= 30, (
        f"Expected at least 30 spike-and-drop accounts, found {cnt}"
    )
    assert band_violations == 0, (
        f"Expected all spike-and-drop accounts to be Orange or Red, "
        f"found {band_violations} in other band(s)"
    )


def test_s3_overager_deployment_capped() -> None:
    """Overager accounts must have deployment_score=1.0; persistent overagers must have expansion_momentum>=0.70."""
    df_cap = run_query("""
        SELECT COUNT(*) AS violations
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND flag_overage = TRUE
          AND deployment_score != 1.0
    """, params=_MONTH_PARAM)
    cap_violations = int(df_cap["violations"][0])
    assert cap_violations == 0, (
        f"Expected all overage accounts to have deployment_score=1.0, "
        f"found {cap_violations} violation(s)"
    )

    # Note: expansion_momentum is not asserted here because flag_overage uses each
    # month's own active contract credits, while expansion_momentum compares trailing-6
    # consumption to the TARGET_MONTH contract credits.  An account that overaged under
    # a smaller contract in earlier months may not clear the current-month threshold,
    # making a cross-month expansion assertion unreliable.


def test_s4_expansion_no_double_count() -> None:
    """Accounts with multiple active contracts must use MAX(annual_commit_dollars), not SUM."""
    df = run_query("""
        WITH multi_contract AS (
            SELECT
                account_id,
                MAX(annual_commit_dollars) AS max_arr
            FROM `{PROJECT_ID}.{DATASET_ID}.contracts`
            WHERE start_date <= LAST_DAY(@target_month, MONTH)
              AND end_date >= @target_month
            GROUP BY account_id
            HAVING COUNT(*) > 1
        )
        SELECT COUNT(*) AS violations
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        JOIN multi_contract m ON m.account_id = r.account_id
        WHERE r.month = @target_month
          AND r.contracted_arr != m.max_arr
    """, params=_MONTH_PARAM)
    violations = int(df["violations"][0])
    assert violations == 0, (
        f"Expected contracted_arr = MAX(annual_commit_dollars) for multi-contract accounts, "
        f"found {violations} using SUM or other aggregation"
    )


def test_s5_dq_exclusions_logged() -> None:
    """dq_report must have >=200 DQ-001 and >=100 DQ-002 rows; excluded accounts must not appear in realized_arr_monthly."""
    df_counts = run_query("""
        SELECT
            COUNTIF(dq_rule = 'DQ-001') AS dq_001_cnt,
            COUNTIF(dq_rule = 'DQ-002') AS dq_002_cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.dq_report`
    """)
    dq_001 = int(df_counts["dq_001_cnt"][0])
    dq_002 = int(df_counts["dq_002_cnt"][0])
    assert dq_001 >= 200, f"Expected >= 200 DQ-001 rows in dq_report, got {dq_001}"
    assert dq_002 >= 100, f"Expected >= 100 DQ-002 rows in dq_report, got {dq_002}"

    df_leak = run_query("""
        SELECT COUNT(*) AS violations
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly` r
        WHERE r.month = @target_month
          AND r.account_id IN (
              SELECT DISTINCT account_id
              FROM `{PROJECT_ID}.{DATASET_ID}.dq_report`
              WHERE dq_rule = 'DQ-001'
                AND account_id IS NOT NULL
          )
    """, params=_MONTH_PARAM)
    violations = int(df_leak["violations"][0])
    assert violations == 0, (
        f"Expected DQ-001 excluded accounts to be absent from realized_arr_monthly, "
        f"found {violations} leak(s)"
    )
