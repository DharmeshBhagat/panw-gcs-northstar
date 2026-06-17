"""DQ test suite — validates clean_usage_logs view and dq_report audit log."""

from tests.conftest import TARGET_MONTH, run_query


def test_dq_t01_no_orphaned_logs() -> None:
    """clean_usage_logs must contain zero orphaned account_ids (DQ-001)."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.clean_usage_logs`
        WHERE account_id NOT IN (
            SELECT account_id FROM `{PROJECT_ID}.{DATASET_ID}.accounts`
        )
    """)
    cnt = int(df["cnt"][0])
    assert cnt == 0, f"Expected 0 orphaned logs in clean_usage_logs, got {cnt}"


def test_dq_t02_no_rogue_dates() -> None:
    """clean_usage_logs must contain zero pre-2024 dates (DQ-002)."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.clean_usage_logs`
        WHERE date < DATE('2024-01-01')
    """)
    cnt = int(df["cnt"][0])
    assert cnt == 0, f"Expected 0 pre-2024 dates in clean_usage_logs, got {cnt}"


def test_dq_t03_orphaned_flagged_in_report() -> None:
    """dq_report must contain at least one DQ-001 (orphaned) row."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.dq_report`
        WHERE dq_rule = 'DQ-001'
    """)
    cnt = int(df["cnt"][0])
    assert cnt > 0, f"Expected DQ-001 rows in dq_report, got {cnt}"


def test_dq_t04_rogue_flagged_in_report() -> None:
    """dq_report must contain at least one DQ-002 (rogue date) row."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.dq_report`
        WHERE dq_rule = 'DQ-002'
    """)
    cnt = int(df["cnt"][0])
    assert cnt > 0, f"Expected DQ-002 rows in dq_report, got {cnt}"


def test_dq_t05_no_negative_consumption() -> None:
    """clean_usage_logs must contain zero rows with negative compute credits (DQ-005)."""
    df = run_query("""
        SELECT COUNT(*) AS cnt
        FROM `{PROJECT_ID}.{DATASET_ID}.clean_usage_logs`
        WHERE compute_credits_consumed < 0
    """)
    cnt = int(df["cnt"][0])
    assert cnt == 0, f"Expected 0 negative-consumption rows in clean_usage_logs, got {cnt}"
