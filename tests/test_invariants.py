"""Invariant test suite — validates business rule invariants on realized_arr_monthly."""

from google.cloud import bigquery

from tests.conftest import TARGET_MONTH, run_query

_MONTH_PARAM = [
    bigquery.ScalarQueryParameter("target_month", "DATE", TARGET_MONTH.isoformat())
]


def test_inv_t01_deployment_capped() -> None:
    """INV-001: deployment_score must never exceed 1.0."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND deployment_score > 1.0
    """, params=_MONTH_PARAM)
    cnt = int(df["cnt"][0])
    assert cnt == 0, f"Expected 0 rows with deployment_score > 1.0, got {cnt}"


def test_inv_t02_realized_le_contracted() -> None:
    """INV-002: realized_arr must never exceed contracted_arr."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND realized_arr > contracted_arr
    """, params=_MONTH_PARAM)
    cnt = int(df["cnt"][0])
    assert cnt == 0, f"Expected 0 rows with realized_arr > contracted_arr, got {cnt}"


def test_inv_t03_shelfware_override() -> None:
    """INV-003: rows with deployment_score=0 AND sustained_usage_score=0 must have prs=0 and shelfware_override=TRUE."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND deployment_score = 0.0
          AND sustained_usage_score = 0.0
          AND (prs != 0.0 OR shelfware_override != TRUE)
    """, params=_MONTH_PARAM)
    cnt = int(df["cnt"][0])
    assert cnt == 0, (
        f"Expected all D=0/S=0 accounts to have prs=0.0 and shelfware_override=TRUE, "
        f"found {cnt} violation(s)"
    )


def test_inv_t04_shelfware_accounts_zero_prs() -> None:
    """INV-003: accounts with shelfware_override=TRUE must have realized_arr=0."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
          AND shelfware_override = TRUE
          AND realized_arr != 0
    """, params=_MONTH_PARAM)
    cnt = int(df["cnt"][0])
    assert cnt == 0, (
        f"Expected 0 shelfware accounts with realized_arr != 0, got {cnt}"
    )


def test_inv_t05_portfolio_prs_weighted() -> None:
    """INV-010: portfolio_summary.portfolio_prs must match ARR-weighted average within 0.0001."""
    df = run_query("""
        WITH
        stored AS (
            SELECT portfolio_prs
            FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary`
            WHERE month = @target_month
        ),
        computed AS (
            SELECT ROUND(SAFE_DIVIDE(SUM(prs * contracted_arr), SUM(contracted_arr)), 4) AS portfolio_prs
            FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
            WHERE month = @target_month
        )
        SELECT
            stored.portfolio_prs  AS stored_prs,
            computed.portfolio_prs AS computed_prs
        FROM stored CROSS JOIN computed
    """, params=_MONTH_PARAM)
    stored = float(df["stored_prs"][0])
    computed = float(df["computed_prs"][0])
    assert abs(stored - computed) <= 0.0001, (
        f"portfolio_prs mismatch: stored={stored}, computed={computed}, "
        f"delta={abs(stored - computed):.6f}"
    )
