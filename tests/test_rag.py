from app import rag


def setup_lexical(monkeypatch):
    monkeypatch.setenv("BQ_RAG_ENABLED", "false")
    monkeypatch.setattr(
        rag,
        "_load_runbooks",
        lambda: [
            {
                "id": "restricted",
                "title": "GKE CrashLoopBackOff",
                "tags": ["gke"],
                "content": "Inspect pod events and container logs.",
                "allowed_roles": ["sre"],
            },
            {
                "id": "missing-acl",
                "title": "GKE CrashLoopBackOff",
                "tags": ["gke"],
                "content": "This document has no access metadata.",
            },
        ],
    )


def test_sre_can_retrieve_authorized_document(monkeypatch):
    setup_lexical(monkeypatch)
    results = rag.retrieve_runbooks("GKE CrashLoopBackOff", role="sre")
    assert [doc["id"] for doc in results] == ["restricted"]


def test_viewer_cannot_retrieve_restricted_documents(monkeypatch):
    setup_lexical(monkeypatch)
    assert rag.retrieve_runbooks("GKE CrashLoopBackOff", role="viewer") == []


def test_second_search_is_blocked(monkeypatch):
    calls = []
    monkeypatch.setattr(
        rag, "retrieve_runbooks",
        lambda query: calls.append(query) or [],
    )
    token = rag.SEARCH_BUDGET.set({"calls": 0})
    try:
        first = rag.search_runbooks("first")
        second = rag.search_runbooks("second")
        assert first["status"] == "success"
        assert second["status"] == "blocked"
        assert calls == ["first"]
    finally:
        rag.SEARCH_BUDGET.reset(token)


def test_search_without_request_context_is_blocked():
    token = rag.SEARCH_BUDGET.set(None)
    try:
        result = rag.search_runbooks("GKE CrashLoopBackOff")
        assert result["status"] == "blocked"
        assert result["reason"] == "missing_request_context"
    finally:
        rag.SEARCH_BUDGET.reset(token)


def test_retrieval_evidence_reaches_parent_context(monkeypatch):
    from contextvars import copy_context

    matches = [{
        "id": "test-runbook",
        "title": "Test runbook",
        "content": "Inspect service latency.",
        "score": 0.9,
        "backend": "test",
    }]
    monkeypatch.setattr(rag, "retrieve_runbooks", lambda query: matches)

    evidence_token = rag.CURRENT_RETRIEVAL.set([])
    budget_token = rag.SEARCH_BUDGET.set({"calls": 0})
    try:
        result = copy_context().run(rag.search_runbooks, "service latency")
        assert result["status"] == "success"
        assert rag.CURRENT_RETRIEVAL.get() == matches
    finally:
        rag.SEARCH_BUDGET.reset(budget_token)
        rag.CURRENT_RETRIEVAL.reset(evidence_token)
