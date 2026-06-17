"""Integration and dashboard test suite — validates end-to-end pipeline outputs."""

import os
import subprocess
import sys

from google.cloud import bigquery

from tests.conftest import PROJECT_ID, TARGET_MONTH, run_query

_MONTH_PARAM = [
    bigquery.ScalarQueryParameter("target_month", "DATE", TARGET_MONTH.isoformat())
]

_REQUIRED_COLUMNS = {
    "account_id", "month", "contracted_arr", "deployment_score",
    "sustained_usage_score", "technical_health_score", "expansion_momentum",
    "prs", "realized_arr", "prs_band", "shelfware_override", "flag_overage",
    "months_in_window", "rep_id", "rep_name", "region", "segment", "industry",
}


def test_int_t01_output_table_schema() -> None:
    """realized_arr_monthly must contain all required columns."""
    df = run_query("""
        SELECT column_name
        FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = 'realized_arr_monthly'
    """)
    actual = set(df["column_name"].tolist())
    missing = _REQUIRED_COLUMNS - actual
    assert not missing, f"realized_arr_monthly is missing columns: {missing}"


def test_int_t02_row_count() -> None:
    """Total rows across all months in realized_arr_monthly must be between 7000 and 15000."""
    df = run_query("""
        SELECT COUNT(*) AS total_rows
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
    """)
    total = int(df["total_rows"][0])
    assert 7000 <= total <= 15000, (
        f"Expected total rows between 7000 and 15000, got {total}"
    )


def test_int_t03_all_bands_present() -> None:
    """All 4 prs_bands (Green, Yellow, Orange, Red) must appear in TARGET_MONTH."""
    df = run_query("""
        SELECT ARRAY_AGG(DISTINCT prs_band ORDER BY prs_band) AS bands
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
    """, params=_MONTH_PARAM)
    bands = set(df["bands"][0])
    expected = {"Green", "Yellow", "Orange", "Red"}
    missing = expected - bands
    assert not missing, f"Missing prs_bands in TARGET_MONTH: {missing}"


def test_int_t04_idempotent() -> None:
    """Running the December pipeline twice must produce the same row count."""
    def row_count() -> int:
        df = run_query("""
            SELECT COUNT(*) AS cnt
            FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
            WHERE month = @target_month
        """, params=_MONTH_PARAM)
        return int(df["cnt"][0])

    env = {**os.environ, "BIGQUERY_PROJECT_ID": PROJECT_ID}
    cmd = [sys.executable, "pipeline/run_pipeline.py", "--month", TARGET_MONTH.isoformat()]

    r1 = subprocess.run(cmd, env=env, capture_output=True)
    assert r1.returncode == 0, f"First pipeline run failed:\n{r1.stderr.decode()}"
    count_after_first = row_count()

    r2 = subprocess.run(cmd, env=env, capture_output=True)
    assert r2.returncode == 0, f"Second pipeline run failed:\n{r2.stderr.decode()}"
    count_after_second = row_count()

    assert count_after_first == count_after_second, (
        f"Pipeline is not idempotent: first run={count_after_first}, "
        f"second run={count_after_second}"
    )


def test_int_t05_csm_level_complete() -> None:
    """csm_monthly_summary must have rows for all 12 months and all rep_ids from accounts."""
    df_months = run_query("""
        SELECT COUNT(DISTINCT month) AS month_count
        FROM `{PROJECT_ID}.{DATASET_ID}.csm_monthly_summary`
    """)
    month_count = int(df_months["month_count"][0])
    assert month_count == 12, (
        f"Expected csm_monthly_summary to cover 12 months, got {month_count}"
    )

    df_missing = run_query("""
        SELECT COUNT(*) AS missing_reps
        FROM (
            SELECT DISTINCT rep_id
            FROM `{PROJECT_ID}.{DATASET_ID}.accounts`
            WHERE rep_id IS NOT NULL
        ) a
        WHERE a.rep_id NOT IN (
            SELECT DISTINCT csm_id
            FROM `{PROJECT_ID}.{DATASET_ID}.csm_monthly_summary`
        )
    """)
    missing = int(df_missing["missing_reps"][0])
    assert missing == 0, (
        f"Expected all rep_ids from accounts to appear in csm_monthly_summary, "
        f"{missing} rep_id(s) missing"
    )


def test_dash_t01_portfolio_12_months() -> None:
    """portfolio_summary must have exactly 12 rows (one per month)."""
    df = run_query("""
        SELECT COUNT(*) AS row_count
        FROM `{PROJECT_ID}.{DATASET_ID}.portfolio_summary`
    """)
    row_count = int(df["row_count"][0])
    assert row_count == 12, (
        f"Expected portfolio_summary to have 12 rows, got {row_count}"
    )


def test_dash_t02_all_regions() -> None:
    """All 4 regions must appear in realized_arr_monthly for TARGET_MONTH."""
    df = run_query("""
        SELECT COUNT(DISTINCT region) AS region_count
        FROM `{PROJECT_ID}.{DATASET_ID}.realized_arr_monthly`
        WHERE month = @target_month
    """, params=_MONTH_PARAM)
    region_count = int(df["region_count"][0])
    assert region_count == 4, (
        f"Expected 4 distinct regions in TARGET_MONTH, got {region_count}"
    )
