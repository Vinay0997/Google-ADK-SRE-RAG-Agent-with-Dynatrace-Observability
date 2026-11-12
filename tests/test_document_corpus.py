"""Validate the document corpus and its golden eval wiring.

These tests keep the Aurelius Health Systems policy documents compatible
with the retrieval guardrails, the BigQuery seed script in sync with the
knowledge base, and the golden cases actually retrievable.
"""

import json
from pathlib import Path

from app import rag

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "knowledge" / "documents.json"
SEED_SQL_PATH = REPO_ROOT / "bigquery" / "seed_documents.sql"
GOLDEN_PATH = REPO_ROOT / "evals" / "golden.json"
REQUIRED_FIELDS = ("id", "title", "tags", "content", "category", "source", "allowed_roles")


def load_corpus() -> list[dict]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def load_cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_corpus_documents_have_required_fields():
    for doc in load_corpus():
        for field in REQUIRED_FIELDS:
            assert doc.get(field), f"{doc.get('id')} missing {field}"


def test_corpus_doc_ids_are_unique():
    doc_ids = [doc["id"] for doc in load_corpus()]
    assert len(doc_ids) == len(set(doc_ids))


def test_corpus_roles_are_valid_and_non_empty():
    for doc in load_corpus():
        assert doc["allowed_roles"], doc["id"]
        assert set(doc["allowed_roles"]) <= rag.VALID_ROLES, doc["id"]


def test_corpus_sources_exist_in_documents_folder():
    for doc in load_corpus():
        assert (REPO_ROOT / doc["source"]).is_file(), doc["source"]


def test_corpus_content_passes_sanitization_unchanged():
    """No corpus document may contain instruction-like text the guardrails filter."""
    for doc in load_corpus():
        assert rag._sanitize_content(doc["content"]) == doc["content"], doc["id"]


def test_corpus_content_fits_context_limits():
    for doc in load_corpus():
        assert len(doc["content"]) <= 4000, doc["id"]


def test_golden_cases_reference_existing_documents():
    corpus_ids = {doc["id"] for doc in load_corpus()}
    for case in load_cases():
        for doc_id in case.get("expected_documents", []):
            assert doc_id in corpus_ids, f"{case['id']} references unknown {doc_id}"


def test_golden_questions_retrieve_expected_documents():
    """Each answer case must retrieve its expected document under its role."""
    corpus = load_corpus()
    for case in load_cases():
        if case.get("expect_refusal"):
            continue

        role = case.get("role", "viewer")
        expected = case["expected_documents"][0]
        results = rag.retrieve_documents(case["question"], role=role)
        ids = [doc["id"] for doc in results]

        assert expected in ids, (
            f"{case['id']} (role={role}) retrieved {ids}, expected {expected}"
        )
        score = next(doc["score"] for doc in results if doc["id"] == expected)
        assert score >= 0.3, f"{case['id']} scored {score} below the retrieval threshold"
        assert any(doc["id"] == expected for doc in corpus)


def test_seed_sql_matches_corpus_documents():
    """The BigQuery seed script must reference the same doc_ids and content."""
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")
    for doc in load_corpus():
        assert f'"{doc["id"]}"' in sql, doc["id"]
        assert doc["content"] in sql, f"{doc['id']} content diverged from the corpus"
