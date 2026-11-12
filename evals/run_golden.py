import json
import os
import sys
from pathlib import Path

import requests
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

from app.telemetry import meter, tracer


AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8080").rstrip("/")
GROUNDEDNESS_MIN = float(os.getenv("GROUNDEDNESS_MIN", "0.6"))
HALLUCINATION_MAX = float(os.getenv("HALLUCINATION_MAX", "0.4"))
REQUIRE_LLM_JUDGE = os.getenv("REQUIRE_LLM_JUDGE", "true").strip().lower() == "true"
EVAL_REPORT = os.getenv("EVAL_REPORT", "").strip()

OPTIONAL_STRING_LISTS = ("expected_documents", "required_facts", "prohibited_terms")


def _require_llm_judge() -> bool:
    """Read the judge requirement at call time so overrides apply."""
    return os.getenv("REQUIRE_LLM_JUDGE", "true").strip().lower() == "true"

REFUSAL_HINTS = (
    "don't have",
    "do not have",
    "not enough",
    "no information",
    "cannot find",
    "can't find",
    "not available",
    "do not contain",
    "does not contain",
    "not contain any",
    "unavailable",
    "i can only answer",
    "no runbook",
)

pass_counter = meter.create_counter(
    "eval.golden.pass.count",
    description="Golden cases passed",
)
fail_counter = meter.create_counter(
    "eval.golden.fail.count",
    description="Golden cases failed",
)
score_hist = meter.create_histogram(
    "eval.golden.groundedness",
    description="Groundedness per golden case",
)


def is_refusal(body: dict) -> bool:
    """Detect refusals using the rule evaluator and answer phrases."""
    evaluation = body.get("evaluation") or {}
    answer = str(body.get("answer") or "").strip().lower()

    return (
        evaluation.get("evaluator") == "refusal-rule"
        or any(hint in answer for hint in REFUSAL_HINTS)
    )


def failure_reasons(item: dict, body: dict) -> list[str]:
    """Return the reasons a response fails its expected behavior."""
    evaluation = body.get("evaluation") or {}
    if not isinstance(evaluation, dict):
        raise ValueError("Response evaluation must be a JSON object")

    groundedness = float(evaluation.get("groundedness", 0.0))
    risk = float(evaluation.get("hallucination_risk", 1.0))
    answer = str(body.get("answer") or "").strip()
    documents = body.get("retrieved_documents") or []
    evaluator_name = str(evaluation.get("evaluator") or "")
    refused = is_refusal(body)
    reasons = []

    if not answer:
        reasons.append("empty_answer")

    if item.get("prohibited_terms"):
        if prohibited_terms_found(item, answer):
            reasons.append("prohibited_term_present")

    if not 0.0 <= risk <= 1.0:
        reasons.append("invalid_hallucination_risk")
    elif risk > HALLUCINATION_MAX:
        reasons.append("hallucination_risk_above_limit")

    if item.get("expect_refusal", False):
        if not refused:
            reasons.append("expected_refusal_not_detected")
    else:
        if refused:
            reasons.append("unexpected_refusal")

        if item.get("expected_documents") and not retrieval_hit(item, body):
            reasons.append("retrieval_miss_expected_document")

        if item.get("required_facts") and missing_facts(item, answer):
            reasons.append("missing_required_facts")

        if _require_llm_judge() and evaluator_name != "gemini-judge":
            reasons.append("llm_judge_not_used")

        if not isinstance(documents, list) or not documents:
            reasons.append("missing_retrieved_evidence")

        if not 0.0 <= groundedness <= 1.0:
            reasons.append("invalid_groundedness")
        elif groundedness < GROUNDEDNESS_MIN:
            reasons.append("groundedness_below_threshold")

    return reasons


def check_case(item: dict, body: dict) -> bool:
    return not failure_reasons(item, body)


def load_cases() -> list[dict]:
    path = Path(__file__).with_name("golden.json")
    cases = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(cases, list) or not cases:
        raise ValueError("golden.json must contain a non-empty list")

    seen_ids = set()

    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise ValueError(f"Case {index} must be an object")

        for field in ("id", "question"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Case {index} requires a non-empty {field}"
                )

        if item["id"] in seen_ids:
            raise ValueError(f"Duplicate case ID: {item['id']}")
        seen_ids.add(item["id"])

        if "role" in item:
            role = item["role"]
            if not isinstance(role, str) or not role.strip():
                raise ValueError(
                    f"Case {item['id']} requires a non-empty role"
                )

        if (
            "expect_refusal" in item
            and not isinstance(item["expect_refusal"], bool)
        ):
            raise ValueError(
                f"Case {item['id']} expect_refusal must be boolean"
            )

        for field in OPTIONAL_STRING_LISTS:
            if field not in item:
                continue
            values = item[field]
            if not isinstance(values, list) or not values:
                raise ValueError(
                    f"Case {item['id']} {field} must be a non-empty list"
                )
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Case {item['id']} {field} entries must be non-empty strings"
                    )

    return cases


def missing_facts(item: dict, answer: str) -> list[str]:
    """Return required facts absent from the answer (case-insensitive)."""
    lowered = answer.lower()
    return [
        fact for fact in item.get("required_facts", []) if fact.lower() not in lowered
    ]


def prohibited_terms_found(item: dict, answer: str) -> list[str]:
    """Return prohibited terms present in the answer (case-insensitive)."""
    lowered = answer.lower()
    return [
        term for term in item.get("prohibited_terms", []) if term.lower() in lowered
    ]


def retrieval_hit(item: dict, body: dict) -> bool:
    """Check an expected document appears among the retrieved documents."""
    expected = item.get("expected_documents", [])
    documents = body.get("retrieved_documents") or []
    retrieved_ids = {
        str(doc.get("id")) for doc in documents if isinstance(doc, dict)
    }
    return any(doc_id in retrieved_ids for doc_id in expected)


def main() -> int:
    if not 0.0 <= GROUNDEDNESS_MIN <= 1.0:
        print(
            "ERROR GROUNDEDNESS_MIN must be between 0 and 1",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if not 0.0 <= HALLUCINATION_MAX <= 1.0:
        print(
            "ERROR HALLUCINATION_MAX must be between 0 and 1",
            file=sys.stderr,
            flush=True,
        )
        return 1

    try:
        cases = load_cases()
    except (OSError, ValueError) as exc:
        print(
            f"ERROR loading golden cases: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    failures = 0
    retrieval_hits = 0
    retrieval_expected = 0
    evaluator_counts: dict[str, int] = {}
    report_cases: list[dict] = []

    print(
        f"Running {len(cases)} golden cases against {AGENT_URL} "
        f"(REQUIRE_LLM_JUDGE={str(REQUIRE_LLM_JUDGE).lower()})",
        flush=True,
    )

    with requests.Session() as session:
        with tracer.start_as_current_span("eval.golden_run") as run:
            run.set_attribute("eval.cases", len(cases))
            run.set_attribute("eval.target_url", AGENT_URL)

            for item in cases:
                case_id = item["id"]
                role = item.get("role", "sre")
                expect_refusal = item.get("expect_refusal", False)

                with tracer.start_as_current_span(
                    "eval.golden_case"
                ) as span:
                    span.set_attribute("eval.case.id", case_id)
                    span.set_attribute("agent.user_role", role)
                    span.set_attribute(
                        "eval.expect_refusal", expect_refusal
                    )

                    ok = False

                    try:
                        response = session.post(
                            f"{AGENT_URL}/ask",
                            json={
                                "question": item["question"],
                                "user_id": "golden-eval",
                                "role": role,
                            },
                            timeout=180,
                        )
                        response.raise_for_status()
                        body = response.json()

                        if not isinstance(body, dict):
                            raise ValueError(
                                "Backend response must be a JSON object"
                            )

                        reasons = failure_reasons(item, body)
                        ok = not reasons

                        evaluation = body.get("evaluation") or {}
                        target_trace_id = str(
                            body.get("trace_id") or ""
                        )
                        evaluator_name = str(evaluation.get("evaluator") or "")
                        documents = body.get("retrieved_documents") or []
                        retrieved_ids = [
                            str(doc.get("id"))
                            for doc in documents
                            if isinstance(doc, dict)
                        ]
                        case_hit = retrieval_hit(item, body)
                        facts_missing = missing_facts(
                            item, str(body.get("answer") or "")
                        )
                        evaluator_counts[evaluator_name or "unknown"] = (
                            evaluator_counts.get(evaluator_name or "unknown", 0) + 1
                        )
                        if item.get("expected_documents"):
                            retrieval_expected += 1
                            if case_hit:
                                retrieval_hits += 1
                        report_cases.append(
                            {
                                "case": case_id,
                                "role": role,
                                "expect_refusal": expect_refusal,
                                "detected_refusal": is_refusal(body),
                                "passed": ok,
                                "failure_reasons": reasons,
                                "trace_id": target_trace_id,
                                "retrieved_document_ids": retrieved_ids,
                                "expected_documents": item.get(
                                    "expected_documents", []
                                ),
                                "retrieval_hit": case_hit,
                                "missing_facts": facts_missing,
                                "prohibited_terms_found": prohibited_terms_found(
                                    item, str(body.get("answer") or "")
                                ),
                                "evaluation": evaluation,
                            }
                        )

                        print(
                            "DETAIL "
                            + json.dumps(
                                {
                                    "case": case_id,
                                    "role": role,
                                    "expect_refusal": expect_refusal,
                                    "detected_refusal": is_refusal(body),
                                    "passed": ok,
                                    "failure_reasons": reasons,
                                    "trace_id": target_trace_id,
                                    "retrieved_document_ids": retrieved_ids,
                                    "retrieval_hit": case_hit,
                                    "missing_facts": facts_missing,
                                    "evaluation": evaluation,
                                    "answer_preview": str(
                                        body.get("answer") or ""
                                    )[:300],
                                }
                            ),
                            flush=True,
                        )

                        span.set_attribute(
                            "eval.target_trace_id", target_trace_id
                        )
                        if reasons:
                            span.set_attribute(
                                "eval.failure_reasons", reasons
                            )

                        groundedness = float(
                            evaluation.get("groundedness", 0.0)
                        )
                        if 0.0 <= groundedness <= 1.0:
                            score_hist.record(
                                groundedness, {"case": case_id}
                            )

                        if not ok:
                            span.set_status(
                                Status(
                                    StatusCode.ERROR,
                                    "; ".join(reasons),
                                )
                            )

                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(
                            Status(StatusCode.ERROR, str(exc))
                        )

                        print(
                            "ERROR "
                            + json.dumps(
                                {
                                    "case": case_id,
                                    "error_type": type(exc).__name__,
                                    "message": str(exc),
                                }
                            ),
                            flush=True,
                        )
                        report_cases.append(
                            {
                                "case": case_id,
                                "role": role,
                                "passed": False,
                                "failure_reasons": [
                                    f"request_error:{type(exc).__name__}"
                                ],
                                "error_message": str(exc),
                            }
                        )
                        ok = False

                    span.set_attribute("eval.passed", ok)

                    if ok:
                        pass_counter.add(1, {"case": case_id})
                    else:
                        fail_counter.add(1, {"case": case_id})
                        failures += 1

                    print(
                        f"{'PASS' if ok else 'FAIL'} {case_id}",
                        flush=True,
                    )

            run.set_attribute("eval.failures", failures)
            if failures:
                run.set_status(
                    Status(
                        StatusCode.ERROR,
                        f"{failures} golden cases failed",
                    )
                )

    summary = {
        "total": len(cases),
        "passed": len(cases) - failures,
        "failed": failures,
        "retrieval_hits": retrieval_hits,
        "retrieval_expected": retrieval_expected,
        "evaluators": evaluator_counts,
        "require_llm_judge": REQUIRE_LLM_JUDGE,
    }

    print("SUMMARY " + json.dumps(summary), flush=True)

    if EVAL_REPORT:
        report_path = Path(EVAL_REPORT).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "agent_url": AGENT_URL,
                    "summary": summary,
                    "cases": report_cases,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"REPORT {report_path}", flush=True)

    return 1 if failures else 0


def shutdown_telemetry() -> None:
    """Shut down providers owned by this standalone evaluation process."""
    for provider in (
        trace.get_tracer_provider(),
        metrics.get_meter_provider(),
    ):
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception as exc:
                print(
                    f"ERROR telemetry shutdown: {exc}",
                    file=sys.stderr,
                    flush=True,
                )


if __name__ == "__main__":
    try:
        exit_code = main()
    finally:
        shutdown_telemetry()

    sys.exit(exit_code)
