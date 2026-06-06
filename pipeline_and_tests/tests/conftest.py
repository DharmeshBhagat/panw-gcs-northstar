import datetime
import os

import pandas as pd
import pytest
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPICallError

PROJECT_ID: str = os.environ["BIGQUERY_PROJECT_ID"]
DATASET_ID: str = os.environ.get("BIGQUERY_DATASET_ID", "gcs_north_star")
TARGET_MONTH: datetime.date = datetime.date(2024, 12, 1)

_client: bigquery.Client = bigquery.Client(project=PROJECT_ID)


def run_query(sql: str, params: list | None = None) -> pd.DataFrame:
    """Execute a BigQuery SQL string and return results as a DataFrame.

    Replaces ``{PROJECT_ID}`` and ``{DATASET_ID}`` placeholders in the SQL
    string with the module-level constants before execution.

    Args:
        sql: SQL query string. May contain ``{PROJECT_ID}`` and
            ``{DATASET_ID}`` placeholders.
        params: Optional list of
            ``google.cloud.bigquery.ScalarQueryParameter`` objects for
            parameterized queries.

    Returns:
        A pandas DataFrame whose columns match the SELECT aliases in the
        query.

    Raises:
        AssertionError: If BigQuery returns an API error, re-raised with
            the original SQL included for debugging.
    """
    sql = sql.replace("{PROJECT_ID}", PROJECT_ID).replace("{DATASET_ID}", DATASET_ID)
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    try:
        job = _client.query(sql, job_config=job_config)
        return job.result().to_dataframe()
    except GoogleAPICallError as exc:
        raise AssertionError(f"BigQuery error executing query:\n{sql}") from exc


@pytest.fixture(scope="session")
def bq_client() -> bigquery.Client:
    """Session-scoped BigQuery client for use in tests.

    Returns:
        An authenticated ``bigquery.Client`` targeting ``PROJECT_ID``.
    """
    return bigquery.Client(project=PROJECT_ID)
