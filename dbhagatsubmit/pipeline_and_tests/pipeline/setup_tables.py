import pathlib
import re

from google.cloud import bigquery

from pipeline.config import PROJECT_ID, DATASET_ID

SQL_PATH = pathlib.Path(__file__).parent.parent / "sql" / "00_setup_tables.sql"

_TABLE_NAME_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`[^`]+\.([^`]+)`", re.IGNORECASE
)


def main() -> None:
    client = bigquery.Client(project=PROJECT_ID)
    sql = SQL_PATH.read_text()

    # BigQuery requires each DDL statement to be run individually.
    statements = [s.strip() for s in sql.split(";") if s.strip()]

    for stmt in statements:
        match = _TABLE_NAME_RE.search(stmt)
        table_name = match.group(1) if match else "(unknown)"
        client.query(stmt).result()
        print(f"Created table: {table_name}")


if __name__ == "__main__":
    main()
