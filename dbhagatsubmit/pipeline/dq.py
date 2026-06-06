import pathlib

from google.cloud import bigquery

SQL_PATH = pathlib.Path(__file__).parent.parent / "sql" / "01_dq_preprocessing.sql"


def run_dq_preprocessing(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
) -> dict[str, int]:
    """Execute DQ pre-processing: create clean view and populate dq_report.

    Runs two SQL statements in order:
      1. CREATE OR REPLACE VIEW clean_usage_logs — excludes rows that fail any
         DQ rule (DQ-001 orphaned, DQ-002 pre-2024, DQ-005 negative credits).
      2. INSERT INTO dq_report — writes one audit row per failing source record,
         assigning a single dq_rule in priority order (001 > 002 > 005).

    Args:
        client: Authenticated BigQuery client.
        project_id: GCP project that owns the dataset.
        dataset_id: BigQuery dataset name (e.g. 'gcs_north_star').

    Returns:
        A dict with keys ``orphaned``, ``rogue``, and ``negative`` whose values
        are the counts of rows flagged by DQ-001, DQ-002, and DQ-005 respectively
        during this run.
    """
    sql = SQL_PATH.read_text()
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    for stmt in statements:
        client.query(stmt).result()

    counts = _fetch_run_counts(client, project_id, dataset_id)
    return counts


def _fetch_run_counts(
    client: bigquery.Client,
    project_id: str,
    dataset_id: str,
) -> dict[str, int]:
    query = f"""
        SELECT
          COUNTIF(dq_rule = 'DQ-001') AS orphaned,
          COUNTIF(dq_rule = 'DQ-002') AS rogue,
          COUNTIF(dq_rule = 'DQ-005') AS negative
        FROM `{project_id}.{dataset_id}.dq_report`
        WHERE run_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE)
    """
    row = next(iter(client.query(query).result()))
    return {
        "orphaned": row.orphaned,
        "rogue": row.rogue,
        "negative": row.negative,
    }
