import argparse
import datetime
import logging
import pathlib
import sys
import time
from typing import Optional

from google.cloud import bigquery

from pipeline.config import PROJECT_ID, DATASET_ID

logger = logging.getLogger(__name__)

SQL_DIR = pathlib.Path(__file__).parent.parent / "sql"

ALL_MONTHS: list[datetime.date] = [datetime.date(2024, m, 1) for m in range(1, 13)]


def execute_sql_file(
    client: bigquery.Client,
    sql_path: pathlib.Path,
    params: Optional[list[bigquery.ScalarQueryParameter]] = None,
) -> int:
    """Read, substitute, and execute a SQL file against BigQuery.

    Reads the SQL file, replaces hardcoded project and dataset identifiers
    with the values from pipeline.config so the file is portable across
    environments. Splits on semicolons and runs each non-empty statement
    in order.

    Args:
        client: Authenticated BigQuery client.
        sql_path: Path to the SQL file to execute.
        params: Optional query parameters for parameterized statements.

    Returns:
        Number of rows affected by the last DML statement executed,
        or 0 if the last statement was DDL or a view definition.
    """
    sql = sql_path.read_text()
    sql = sql.replace("panw-gcs-northstar-498507", PROJECT_ID)
    sql = sql.replace("gcs_north_star", DATASET_ID)

    statements = [s.strip() for s in sql.split(";") if s.strip()]
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])

    last_affected = 0
    for stmt in statements:
        job = client.query(stmt, job_config=job_config)
        job.result()
        if job.num_dml_affected_rows is not None:
            last_affected = job.num_dml_affected_rows

    return last_affected


def run_dq_preprocessing(client: bigquery.Client) -> None:
    """Execute DQ pre-processing SQL once at pipeline start.

    Creates the clean_usage_logs view and appends failing rows to dq_report.
    This step is not month-scoped and must run before any monthly steps.

    Args:
        client: Authenticated BigQuery client.
    """
    rows = execute_sql_file(client, SQL_DIR / "01_dq_preprocessing.sql")
    logger.info("DQ preprocessing complete — %d rows flagged in dq_report", rows)


def run_month(
    client: bigquery.Client,
    target_month: datetime.date,
) -> tuple[int, int]:
    """Execute the three per-month pipeline steps for a single month.

    Runs realized_arr_monthly → csm_monthly_summary → portfolio_summary
    in dependency order. Each step is idempotent (DELETE + INSERT).

    Args:
        client: Authenticated BigQuery client.
        target_month: First day of the month to process (e.g. 2024-03-01).

    Returns:
        A tuple of (account_rows, csm_rows) inserted for the month.
    """
    params = [bigquery.ScalarQueryParameter("target_month", "DATE", target_month.isoformat())]

    account_rows = execute_sql_file(client, SQL_DIR / "02_realized_arr_monthly.sql", params)
    csm_rows = execute_sql_file(client, SQL_DIR / "03_csm_monthly_summary.sql", params)
    execute_sql_file(client, SQL_DIR / "04_portfolio_summary.sql", params)

    return account_rows, csm_rows


def main() -> None:
    """Entry point for the PANW GCS North Star pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="PANW GCS North Star pipeline runner")
    parser.add_argument(
        "--month",
        default=None,
        help="Single month to process as YYYY-MM-DD. Omit to run all 12 months of 2024.",
    )
    args = parser.parse_args()

    months = [datetime.date.fromisoformat(args.month)] if args.month else ALL_MONTHS

    client = bigquery.Client(project=PROJECT_ID)
    start = time.monotonic()

    try:
        run_dq_preprocessing(client)

        for target_month in months:
            logger.info("Processing month: %s", target_month)
            account_rows, csm_rows = run_month(client, target_month)
            logger.info(
                "Month %s: %d account rows, %d CSM rows",
                target_month, account_rows, csm_rows,
            )

        logger.info("Pipeline complete in %.1fs", time.monotonic() - start)
        sys.exit(0)

    except Exception:
        logger.exception("Pipeline failed after %.1fs", time.monotonic() - start)
        sys.exit(1)


if __name__ == "__main__":
    main()
