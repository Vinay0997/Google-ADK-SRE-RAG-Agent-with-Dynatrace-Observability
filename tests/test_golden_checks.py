"""Unit tests for the golden-case schema and failure checks."""

import json

import pytest

from evals import run_golden


def good_body(
    answer="Inspect pod events and the previous container logs for errors.",
    doc_id="gke-crashloop",
    evaluator="gemini-judge",
    groundedness=0.9,
):
    return {
        "answer": answer,
        "trace_id": "abc123",
        "retrieved_documents": [
            {"id": doc_id, "title": "Runbook", "content": "steps"}
        ],
        "evaluation": {
            "groundedness": groundedness,
            "answer_relevance": 0.9,
            "hallucination_risk": 0.1,
            "evaluator": evaluator,
        },
    }


def base_case(**overrides):
    case = {
        "id": "test-case",
        "question": "How should I troubleshoot a crashing pod?",
        "expected_documents": ["gke-crashloop"],
        "required_facts": ["events", "logs"],
    }
    case.update(overrides)
    return case


def test_passing_case(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    assert run_golden.failure_reasons(base_case(), good_body()) == []


def test_retrieval_miss(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    body = good_body(doc_id="cloud-run-latency")
    reasons = run_golden.failure_reasons(base_case(), body)
    assert "retrieval_miss_expected_document" in reasons


def test_missing_required_facts(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    body = good_body(answer="Reboot the cluster.")
    reasons = run_golden.failure_reasons(base_case(), body)
    assert "missing_required_facts" in reasons


def test_heuristic_fallback_fails_when_llm_judge_required(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    body = good_body(evaluator="local-heuristic")
    reasons = run_golden.failure_reasons(base_case(), body)
    assert "llm_judge_not_used" in reasons


def test_heuristic_allowed_when_judge_not_required(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "false")
    body = good_body(evaluator="local-heuristic")
    reasons = run_golden.failure_reasons(base_case(), body)
    assert "llm_judge_not_used" not in reasons


def test_refusal_case_skips_judge_check(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    case = base_case(
        expect_refusal=True,
        expected_documents=None,
        required_facts=None,
    )
    del case["expected_documents"]
    del case["required_facts"]
    body = {
        "answer": "I can only answer SRE troubleshooting questions based on the runbooks.",
        "trace_id": "abc",
        "retrieved_documents": [],
        "evaluation": {
            "groundedness": 1.0,
            "answer_relevance": 0.0,
            "hallucination_risk": 0.0,
            "evaluator": "refusal-rule",
        },
    }
    assert run_golden.failure_reasons(case, body) == []


def test_prohibited_term_fails(monkeypatch):
    monkeypatch.setenv("REQUIRE_LLM_JUDGE", "true")
    case = {
        "id": "no-evidence",
        "question": "What is the lease amount?",
        "expect_refusal": True,
        "prohibited_terms": ["$"],
    }
    body = good_body(answer="The lease is $4,000 per month.")
    reasons = run_golden.failure_reasons(case, body)
    assert "prohibited_term_present" in reasons


def test_load_cases_validates_golden_file():
    cases = run_golden.load_cases()
    assert len(cases) >= 11
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_load_cases_rejects_empty_list(monkeypatch, tmp_path):
    path = tmp_path / "golden.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setattr(run_golden, "Path", lambda *a: path)
    with pytest.raises(ValueError):
        run_golden.load_cases()


def test_load_cases_rejects_bad_list_field(monkeypatch, tmp_path):
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "question": "q",
                    "expected_documents": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_golden, "Path", lambda *a: path)
    with pytest.raises(ValueError):
        run_golden.load_cases()
