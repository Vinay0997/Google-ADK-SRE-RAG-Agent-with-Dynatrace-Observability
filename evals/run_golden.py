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


def _is_refusal(body: dict) -> bool:
    evaluation = body.get("evaluation") or {}
    answer = str(body.get("answer") or "").strip().lower()

    return (
        evaluation.get("evaluator") == "refusal-rule"
        or any(hint in answer for hint in REFUSAL_HINTS)
    )


def check_case(item: dict, body: dict) -> bool:
    """Check scores and whether the response matches the expected behavior."""
    evaluation = body.get("evaluation") or {}
    groundedness = float(evaluation.get("groundedness", 0.0))
    hallucination_risk = float(
        evaluation.get("hallucination_risk", 1.0)
    )

    answer = str(body.get("answer") or "").strip()
    retrieved_documents = body.get("retrieved_documents") or []
    is_refusal = _is_refusal(body)

    if item.get("expect_refusal", False):
        return (
            bool(answer)
            and is_refusal
            and hallucination_risk <= HALLUCINATION_MAX
        )

    return (
        bool(answer)
        and bool(retrieved_documents)
        and not is_refusal
        and groundedness >= GROUNDEDNESS_MIN
        and hallucination_risk <= HALLUCINATION_MAX
    )


def _failure_reasons(item: dict, body: dict) -> list[str]:
    """Explain failures using the same checks as check_case."""
    evaluation = body.get("evaluation") or {}
    groundedness = float(evaluation.get("groundedness", 0.0))
    hallucination_risk = float(
        evaluation.get("hallucination_risk", 1.0)
    )

    answer = str(body.get("answer") or "").strip()
    is_refusal = _is_refusal(body)
    reasons = []

    if not answer:
        reasons.append("empty_answer")

    # Using this form also rejects non-finite NaN scores.
    if not hallucination_risk <= HALLUCINATION_MAX:
        reasons.append("hallucination_risk_above_limit_or_invalid")

    if item.get("expect_refusal", False):
        if not is_refusal:
            reasons.append("expected_refusal_not_detected")
    else:
        if is_refusal:
            reasons.append("unexpected_refusal")
        if not body.get("retrieved_documents"):
            reasons.append("missing_retrieved_evidence")
        if not groundedness >= GROUNDEDNESS_MIN:
            reasons.append("groundedness_below_threshold_or_invalid")

    return reasons


def main() -> int:
    golden_path = Path(__file__).with_name("golden.json")

    try:
        cases = json.loads(golden_path.read_text(encoding="utf-8"))

        if not isinstance(cases, list) or not cases:
            raise ValueError("golden.json must contain a non-empty list")

        for index, item in enumerate(cases):
            if not isinstance(item, dict):
                raise ValueError(f"Case {index} must be an object")

            for field in ("id", "question"):
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Case {index} must have a non-empty {field}"
                    )

            if (
                "expect_refusal" in item
                and not isinstance(item["expect_refusal"], bool)
            ):
                raise ValueError(
                    f"Case {item['id']} expect_refusal must be boolean"
                )

    except (OSError, ValueError) as exc:
        print(f"ERROR loading golden cases: {exc}", file=sys.stderr)
        return 1

    failures = 0

    print(
        f"Running {len(cases)} golden cases against {AGENT_URL}",
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

                        ok = check_case(item, body)
                        reasons = _failure_reasons(item, body)

                        print(
                            "DETAIL "
                            + json.dumps(
                                {
                                    "case": case_id,
                                    "role": role,
                                    "expect_refusal": expect_refusal,
                                    "detected_refusal": _is_refusal(body),
                                    "passed": ok,
                                    "failure_reasons": reasons,
                                    "trace_id": body.get("trace_id"),
                                    "retrieved_documents": body.get(
                                        "retrieved_documents", []
                                    ),
                                    "evaluation": body.get(
                                        "evaluation", {}
                                    ),
                                    "answer_preview": str(
                                        body.get("answer") or ""
                                    )[:300],
                                }
                            ),
                            flush=True,
                        )

                        span.set_attribute(
                            "eval.target_trace_id",
                            str(body.get("trace_id") or ""),
                        )
                        span.set_attribute(
                            "eval.failure_reasons", reasons
                        )

                        evaluation = body.get("evaluation") or {}
                        score_hist.record(
                            float(
                                evaluation.get("groundedness", 0.0)
                            ),
                            {"case": case_id},
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

    print(
        "SUMMARY "
        + json.dumps(
            {
                "total": len(cases),
                "passed": len(cases) - failures,
                "failed": failures,
            }
        ),
        flush=True,
    )

    return 1 if failures else 0


def shutdown_telemetry() -> None:
    """Flush and stop this standalone runner's telemetry providers."""
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
                    f"Telemetry shutdown error: {exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    try:
        exit_code = main()
    finally:
        shutdown_telemetry()

    sys.exit(exit_code)
