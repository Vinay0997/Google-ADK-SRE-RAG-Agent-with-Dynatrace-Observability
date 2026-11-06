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
REFUSAL_HINTS = ("don't have", "do not have", "not enough", "no information", "cannot find", "can't find", "not available", "do not contain", "does not contain", "not contain any", "unavailable", "i can only answer")

pass_counter = meter.create_counter("eval.golden.pass.count", description="Golden cases passed")
fail_counter = meter.create_counter("eval.golden.fail.count", description="Golden cases failed")
score_hist = meter.create_histogram("eval.golden.groundedness", description="Groundedness per golden case")


def check_case(item: dict, body: dict) -> bool:
    ev = body.get("evaluation", {})
    grounded = float(ev.get("groundedness", 0.0))
    risk = float(ev.get("hallucination_risk", 1.0))
    if item.get("expect_refusal"):
        answer = body.get("answer", "").lower()
        return risk <= HALLUCINATION_MAX and any(h in answer for h in REFUSAL_HINTS)
    return grounded >= GROUNDEDNESS_MIN and risk <= HALLUCINATION_MAX


def main() -> int:
    cases = json.loads((Path(__file__).parent / "golden.json").read_text())
    failures = 0
    with tracer.start_as_current_span("eval.golden_run") as run:
        run.set_attribute("eval.cases", len(cases))
        for item in cases:
            with tracer.start_as_current_span("eval.golden_case") as span:
                span.set_attribute("eval.case.id", item["id"])
                try:
                    resp = requests.post(
                        f"{AGENT_URL}/ask",
                        json={"question": item["question"], "user_id": "golden-eval"},
                        timeout=180,
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    ok = check_case(item, body)
                    span.set_attribute("eval.target_trace_id", body.get("trace_id", ""))
                    score_hist.record(float(body.get("evaluation", {}).get("groundedness", 0.0)), {"case": item["id"]})
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    ok = False
                span.set_attribute("eval.passed", ok)
                (pass_counter if ok else fail_counter).add(1, {"case": item["id"]})
                failures += 0 if ok else 1
                print(f"{'PASS' if ok else 'FAIL'} {item['id']}")
        run.set_attribute("eval.failures", failures)
    metrics.get_meter_provider().force_flush()
    trace.get_tracer_provider().force_flush()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
