import asyncio
import logging
from datetime import datetime, timezone

from app.settings import get_settings

logger = logging.getLogger(__name__)
_client = None


def _table_id() -> str:
    s = get_settings()
    return f"{s.google_cloud_project}.{s.bq_dataset}.{s.bq_table}"


def _insert(row: dict) -> None:
    global _client
    from google.cloud import bigquery

    if _client is None:
        _client = bigquery.Client(project=get_settings().google_cloud_project)
    errors = _client.insert_rows_json(_table_id(), [row])
    if errors:
        logger.error("BigQuery insert errors: %s", errors)


async def write_execution_row(row: dict) -> None:
    # Never let the audit sink break a user request.
    if not get_settings().bq_enabled:
        return
    row.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        await asyncio.to_thread(_insert, row)
    except Exception:
        logger.exception("BigQuery write failed")
