import json
import math
import re
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from app.settings import get_settings
from app.telemetry import rag_duration, rag_quality, tracer

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "runbooks.json"
CURRENT_RETRIEVAL: ContextVar[list[dict[str, Any]]] = ContextVar(
    "current_retrieval", default=[]
)


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
    # Small deterministic lexical score, normalized to 0..1.
    return min(1.0, overlap / max(1.0, math.sqrt(len(q))))


def retrieve_runbooks(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    top_k = top_k or settings.top_k
    scored = []
    for doc in _load_runbooks():
        score = _score(query, doc)
        scored.append({**doc, "score": round(score, 4)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def search_runbooks(query: str) -> dict[str, Any]:
    """Search SRE runbooks for evidence before answering an operational question.

    Args:
        query: The user's SRE, Cloud Run, Kubernetes, API, latency, or incident question.

    Returns:
        Matching runbook passages and lexical relevance scores.
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
