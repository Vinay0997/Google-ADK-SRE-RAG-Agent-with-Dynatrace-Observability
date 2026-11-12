import asyncio
from types import SimpleNamespace

from app import evaluator


def configure_test(monkeypatch):
    monkeypatch.setattr(
        evaluator,
        "get_settings",
        lambda: SimpleNamespace(
            use_llm_evaluator=True,
            google_cloud_project="test-project",
        ),
    )

    def unexpected_llm_call(*args, **kwargs):
        raise AssertionError("LLM judge should not be called")

    monkeypatch.setattr(
        evaluator, "_llm_evaluate_sync", unexpected_llm_call
    )


def test_exact_scope_refusal_uses_rule(monkeypatch):
    configure_test(monkeypatch)

    result = asyncio.run(
        evaluator.evaluate_response(
            "What is our office lease amount?",
            "I can only answer questions based on the documented policies and procedures.",
            [],
        )
    )

    assert result.evaluator == "refusal-rule"
    assert result.hallucination_risk == 0.0
    assert result.answer_relevance == 0.0
    assert "does not establish whether refusing the question was appropriate" in result.notes


def test_scope_sentence_with_extra_claim_is_not_exact_rule(monkeypatch):
    monkeypatch.setattr(
        evaluator,
        "get_settings",
        lambda: SimpleNamespace(
            use_llm_evaluator=False,
            google_cloud_project="",
        ),
    )

    result = asyncio.run(
        evaluator.evaluate_response(
            "What is our office lease amount?",
            (
                "I can only answer questions based on the documented "
                "policies and procedures. The annual lease is 500000 dollars."
            ),
            [],
        )
    )

    assert result.evaluator == "local-heuristic"
    assert result.hallucination_risk == 1.0


def test_no_evidence_refusal_does_not_claim_access_denial(monkeypatch):
    configure_test(monkeypatch)

    result = asyncio.run(
        evaluator.evaluate_response(
            "How should we troubleshoot RAG groundedness?",
            "No policy available to your access level covers this issue.",
            [],
        )
    )

    assert result.evaluator == "refusal-rule"
    assert "No documents permitted" not in result.notes
    assert "not established" in result.notes
