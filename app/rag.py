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

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "documents.json"
CURRENT_RETRIEVAL: ContextVar[list[dict[str, Any]]] = ContextVar(
    "current_retrieval", default=[]
)
CURRENT_ROLE: ContextVar[str] = ContextVar("current_role", default="viewer")
VALID_ROLES = {"sre", "security_privacy", "compliance", "viewer"}
SEARCH_BUDGET: ContextVar[dict[str, int] | None] = ContextVar(
    "search_budget", default=None
)


def reset_search_budget() -> None:
    SEARCH_BUDGET.set({"calls": 0})

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


def _load_documents() -> list[dict[str, Any]]:
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
    chunks = os.getenv("BQ_CHUNKS_TABLE", "runbook_chunks")  # table name retained for deploy compatibility; stores policy document chunks
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
        if 1.0 - float(row["distance"]) >= float(os.getenv("BQ_MIN_SCORE", "0.55"))
    ]


def _retrieve_lexical(
    query: str, top_k: int, role: str
) -> list[dict[str, Any]]:
    settings = get_settings()
    min_score = getattr(settings, "rag_min_score", 0.3)
    scored = []
    for doc in _load_documents():
        allowed_roles = doc.get("allowed_roles")
        if not isinstance(allowed_roles, list) or role not in allowed_roles:
            continue
        score = _score(query, doc)
        if score < min_score:
            continue
        scored.append({**doc, "score": round(score, 4), "backend": "lexical"})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


# Retrieved document text is untrusted evidence. These patterns neutralize
# instruction-like text aimed at the model so a poisoned document cannot
# override the agent's rules or permissions. Filtering is defense in depth;
# the agent instruction still tells the model to treat documents as data.
_INJECTION_PATTERNS = [
    re.compile(
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.IGNORECASE
    ),
    re.compile(
        r"disregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)?\s*instructions",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:reveal|share|print|repeat)\s+(?:your\s+)?system\s+prompt", re.IGNORECASE
    ),
    re.compile(
        r"you\s+are\s+now\s+(?:an?\s+)?(?:sre|admin|administrator|root)", re.IGNORECASE
    ),
    re.compile(
        r"elevate\s+(?:your\s+|my\s+)?(?:role|access|permissions?)", re.IGNORECASE
    ),
    re.compile(
        r"grant\s+(?:me|the\s+user)\s+\S+\s+(?:access|role|permissions?)",
        re.IGNORECASE,
    ),
]
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SANITIZED_MARKER = "[filtered instruction-like text]"


def _sanitize_content(text: str) -> str:
    sanitized = _CONTROL_CHARS.sub("", text or "")
    for pattern in _INJECTION_PATTERNS:
        sanitized = pattern.sub(_SANITIZED_MARKER, sanitized)
    return sanitized


def _apply_context_guardrails(
    matches: list[dict[str, Any]], settings: Any
) -> list[dict[str, Any]]:
    """Apply content sanitization and size limits to retrieved evidence."""
    max_doc = getattr(settings, "rag_max_doc_chars", 4000)
    max_total = getattr(settings, "rag_max_context_chars", 12000)
    stats = {"sanitized_docs": 0, "truncated_docs": 0, "dropped_docs": 0}

    cleaned: list[dict[str, Any]] = []
    budget = max_total
    for match in matches:
        content = match.get("content") or ""
        sanitized = _sanitize_content(content)
        if sanitized != content:
            stats["sanitized_docs"] += 1
            content = sanitized
        if len(content) > max_doc:
            content = content[:max_doc]
            stats["truncated_docs"] += 1
        if len(content) > budget:
            stats["dropped_docs"] += 1
            continue
        budget -= len(content)
        cleaned.append({**match, "content": content})

    if any(stats.values()):
        logger.info("Retrieval guardrails applied: %s", stats)
        with tracer.start_as_current_span("guardrail.retrieval_filter") as span:
            span.set_attribute("guardrail.name", "retrieval_content")
            span.set_attribute("guardrail.action", "filter")
            for key, value in stats.items():
                span.set_attribute(f"guardrail.{key}", value)

    return cleaned


def retrieve_documents(
    query: str, top_k: int | None = None, role: str | None = None
) -> list[dict[str, Any]]:
    settings = get_settings()
    top_k = top_k or settings.top_k
    role = role if role in VALID_ROLES else CURRENT_ROLE.get()

    matches: list[dict[str, Any]]
    if _flag("BQ_RAG_ENABLED"):
        try:
            matches = _retrieve_bigquery(query, top_k, role)
        except Exception:
            logger.exception("BigQuery retrieval failed")
            if not _flag("BQ_RAG_FALLBACK"):
                matches = []
            else:
                matches = _retrieve_lexical(query, top_k, role)
    else:
        matches = _retrieve_lexical(query, top_k, role)

    return _apply_context_guardrails(matches, settings)


def search_documents(query: str) -> dict[str, Any]:
    """Search company policy and SOP documents for evidence before answering.

    Args:
        query: The user's question about policies, procedures, security,
            compliance, HR, or governance documentation.

    Returns:
        Matching document passages and relevance scores.
    """
    budget = SEARCH_BUDGET.get()
    reason = None
    if budget is None:
        reason = "missing_request_context"
    elif budget["calls"] >= 1:
        reason = "retrieval_call_limit"

    if reason is not None:
        with tracer.start_as_current_span("guardrail.decision") as span:
            span.set_attribute("guardrail.name", "retrieval_budget")
            span.set_attribute("guardrail.action", "block")
            span.set_attribute("guardrail.reason", reason)
            span.set_attribute("agent.user_role", CURRENT_ROLE.get())
        return {
            "status": "blocked",
            "reason": reason,
            "matches": [],
            "message": (
                "Do not search again. Use only evidence already returned. "
                "If it is insufficient, state that limitation."
            ),
        }

    budget["calls"] += 1
    started = time.perf_counter()
    with tracer.start_as_current_span("rag.retrieve") as span:
        matches = retrieve_documents(query)
        evidence = CURRENT_RETRIEVAL.get()
        evidence.clear()
        evidence.extend(matches)
        elapsed = time.perf_counter() - started
        best_score = matches[0]["score"] if matches else 0.0

        span.set_attribute("rag.query.length", len(query))
        span.set_attribute("rag.top_k", len(matches))
        span.set_attribute("rag.best_score", best_score)
        span.set_attribute("rag.document_ids", ",".join(m["id"] for m in matches))
        span.set_attribute("rag.role", CURRENT_ROLE.get())
        span.set_attribute(
            "rag.backend", matches[0].get("backend", "none") if matches else "none"
        )

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
