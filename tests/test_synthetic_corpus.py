"""Validate the synthetic runbook corpus and its golden eval wiring.

These tests keep the synthetic documents compatible with the retrieval
guardrails and the BigQuery seed script in sync with the JSONL corpus.
"""

import json
from pathlib import Path

from app import rag

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "synthetic" / "aurelius_runbooks.jsonl"
SEED_SQL_PATH = REPO_ROOT / "bigquery" / "add_synthetic_runbooks.sql"
GOLDEN_PATH = REPO_ROOT / "evals" / "golden.json"
REQUIRED_FIELDS = ("doc_id", "title", "content", "category", "source", "allowed_roles")


def load_corpus() -> list[dict]:
    return [
        json.loads(line)
        for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_corpus_documents_have_required_fields():
    for doc in load_corpus():
        for field in REQUIRED_FIELDS:
            assert doc.get(field), f"{doc.get('doc_id')} missing {field}"


def test_corpus_doc_ids_are_unique():
    doc_ids = [doc["doc_id"] for doc in load_corpus()]
    assert len(doc_ids) == len(set(doc_ids))


def test_corpus_roles_are_valid():
    for doc in load_corpus():
        assert set(doc["allowed_roles"]) <= rag.VALID_ROLES, doc["doc_id"]


def test_corpus_content_passes_sanitization_unchanged():
    """No synthetic document may contain instruction-like text the guardrails filter."""
    for doc in load_corpus():
        assert rag._sanitize_content(doc["content"]) == doc["content"], doc["doc_id"]


def test_corpus_content_fits_context_limits():
    for doc in load_corpus():
        assert len(doc["content"]) <= 4000, doc["doc_id"]


def test_golden_cases_reference_existing_documents():
    corpus_ids = {doc["doc_id"] for doc in load_corpus()}
    knowledge_ids = {
        doc["id"]
        for doc in json.loads(
            (REPO_ROOT / "knowledge" / "runbooks.json").read_text(encoding="utf-8")
        )
    }
    known_ids = corpus_ids | knowledge_ids | {"rag-quality"}

    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for case in cases:
        for doc_id in case.get("expected_documents", []):
            assert doc_id in known_ids, f"{case['id']} references unknown {doc_id}"


def test_golden_questions_score_above_retrieval_threshold():
    """Golden questions must actually retrieve their expected synthetic document."""
    settings = type(
        "S",
        (),
        {"top_k": 3, "rag_min_score": 0.3, "rag_max_doc_chars": 4000, "rag_max_context_chars": 12000},
    )()
    corpus = load_corpus()
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    for case in cases:
        expected = case.get("expected_documents", [])
        if not any(doc_id.startswith("aur-") for doc_id in expected):
            continue
        docs = [doc for doc in corpus if doc["doc_id"] in expected]
        assert len(docs) == len(expected), case["id"]

        for doc in docs:
            score = rag._score(case["question"], doc)
            assert score >= settings.rag_min_score, (
                f"{case['id']} scores {score:.3f} below the retrieval threshold "
                f"for {doc['doc_id']}"
            )


def test_seed_sql_matches_corpus_documents():
    """The BigQuery seed script must reference the same doc_ids and content."""
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")
    for doc in load_corpus():
        if doc["doc_id"] not in ("aur-09", "aur-10", "aur-11", "aur-12"):
            continue
        assert doc["doc_id"] in sql, doc["doc_id"]
        assert doc["content"] in sql, f"{doc['doc_id']} content diverged from the corpus"
