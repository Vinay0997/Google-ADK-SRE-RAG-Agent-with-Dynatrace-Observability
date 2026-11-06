cd ~/Google-ADK-SRE-RAG-Agent-with-Dynatrace-Observability
cp app/rag.py app/rag.py.bak

cat > app/rag.py <<'EOF'
import json
import logging
import math
import os
import re
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from app.settings import get_settings
from app.telemetry import rag_duration, rag_quality, tracer

logger = logging.getLogger(__name__)

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "runbooks.json"
CURRENT_RETRIEVAL: ContextVar[list[dict[str, Any]]] = ContextVar(
    "current_retrieval", default=[]
)
CURRENT_ROLE: ContextVar[str] = ContextVar("current_role", default="viewer")
VALID_ROLES = {"sre", "clinical_ops", "security_privacy", "viewer"}
_IDENT = re.compile(r"^[A-Za-z0-9_\-]+$")
_bq_client = None


def set_current_role(role: str | None) -> str:
    """Called by the request handler with a server-verified role."""
    safe = role if role in VALID_ROLES else "viewer"
    CURRENT_ROLE.set(safe)
    return safe


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9_\-]+", text.lower())
        if len(token) > 2
    }


def _load_runbooks() -> list[dict[str, Any]]:
    with KNOWLEDGE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _score(query: str, document: dict[str, Any]) -> float:
    q = _tokens(query)
    body = _tokens(
        " ".join(
            [
                document.get("title", ""),
                " ".join(document.get("tags", [])),
                document.get("content", ""),
            ]
        )
    )
    if not q or not body:
        return 0.0
    overlap = len(q & body)
    return min(1.0, overlap / max(1.0, math.sqrt(len(q))))


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _retrieve_bigquery(query: str, top_k: int, role: str) -> list[dict[str, Any]]:
    global _bq_client
    from google.cloud import bigquery

    dataset = os.getenv("BQ_DATASET", "agent_observability")
    chunks = os.getenv("BQ_CHUNKS_TABLE", "runbook_chunks")
    model = os.getenv("BQ_EMBED_MODEL", "embedding_model")
    for value in (dataset, chunks, model):
        if not _IDENT.match(value):
            raise ValueError(f"Invalid BigQuery identifier: {value}")

    if _bq_client is None:
        _bq_client = bigquery.Client()
    project = _bq_client.project

    sql = f"""
    SELECT base.doc_id AS id, base.title AS title, base.content AS content, distance
    FROM VECTOR_SEARCH(
      (SELECT * FROM `{project}.{dataset}.{chunks}` WHERE @role IN UNNEST(allowed_roles)),
      'embedding',
      (SELECT embedding FROM AI.GENERATE_EMBEDDING(
         MODEL `{project}.{dataset}.{model}`,
         (SELECT @query AS content),
         STRUCT('RETRIEVAL_QUERY' AS task_type))),
      top_k => {int(top_k)},
      distance_type => 'COSINE',
      options => '{{"use_brute_force":true}}')
    ORDER BY distance
    """
    job = _bq_client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("role", "STRING", role),
                bigquery.ScalarQueryParameter("query", "STRING", query),
            ]
        ),
    )
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "content": row["content"],
            "score": round(max(0.0, 1.0 - float(row["distance"])), 4),
            "backend": "bigquery",
        }
        for row in job.result()
    ]


def _retrieve_lexical(query: str, top_k: int) -> list[dict[str, Any]]:
    scored = []
    for doc in _load_runbooks():
        score = _score(query, doc)
        scored.append({**doc, "score": round(score, 4), "backend": "lexical"})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def retrieve_runbooks(
    query: str, top_k: int | None = None, role: str | None = None
) -> list[dict[str, Any]]:
    settings = get_settings()
    top_k = top_k or settings.top_k
    role = role if role in VALID_ROLES else CURRENT_ROLE.get()

    if _flag("BQ_RAG_ENABLED"):
        try:
            return _retrieve_bigquery(query, top_k, role)
        except Exception:
            logger.exception("BigQuery retrieval failed")
            if not _flag("BQ_RAG_FALLBACK"):
                return []
    return _retrieve_lexical(query, top_k)


def search_runbooks(query: str) -> dict[str, Any]:
    """Search SRE runbooks for evidence before answering an operational question.

    Args:
        query: The user's SRE, Cloud Run, Kubernetes, API, latency, or incident question.

    Returns:
        Matching runbook passages and relevance scores.
    """
    started = time.perf_counter()
    with tracer.start_as_current_span("rag.retrieve") as span:
        matches = retrieve_runbooks(query)
        CURRENT_RETRIEVAL.set(matches)
        elapsed = time.perf_counter() - started
        best_score = matches[0]["score"] if matches else 0.0

        span.set_attribute("rag.query.length", len(query))
        span.set_attribute("rag.top_k", len(matches))
        span.set_attribute("rag.best_score", best_score)
        span.set_attribute("rag.document_ids", ",".join(m["id"] for m in matches))
        span.set_attribute("rag.role", CURRENT_ROLE.get())
        span.set_attribute("rag.backend", matches[0].get("backend", "none") if matches else "none")

        rag_duration.record(elapsed)
        rag_quality.record(best_score)

        return {
            "status": "success",
            "matches": [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "content": m["content"],
                    "score": m["score"],
                }
                for m in matches
            ],
        }
EOF
python3 -c "import ast; ast.parse(open('app/rag.py').read()); print('syntax ok')"
grep -i bigquery requirements.txt
