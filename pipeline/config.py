import os
from dotenv import load_dotenv

load_dotenv()

_project_id = os.getenv("BIGQUERY_PROJECT_ID")
if not _project_id:
    raise ValueError("BIGQUERY_PROJECT_ID environment variable is not set")

PROJECT_ID: str = _project_id
DATASET_ID: str = os.getenv("BIGQUERY_DATASET_ID", "gcs_north_star")
