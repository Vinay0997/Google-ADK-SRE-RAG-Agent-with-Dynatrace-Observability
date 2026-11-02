import asyncio
import json
import re
from dataclasses import dataclass, asdict

from google import genai

from app.settings import get_settings
from app.telemetry import (
    groundedness_metric,
    hallucination_metric,
    relevance_metric,
    tracer,
)


@dataclass
class EvaluationResult:
    groundedness: float
    answer_relevance: float
    hallucination_risk: float
    evaluator: str
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _heuristic_score(question: str, answer: str, contexts: list[dict]) -> EvaluationResult:
    evidence = " ".join(item.get("content", "") for item in contexts).lower()
    answer_tokens = set(re.findall(r"[a-zA-Z0-9_\-]+", answer.lower()))
    evidence_tokens = set(re.findall(r"[a-zA-Z0-9_\-]+", evidence))
    question_tokens = set(re.findall(r"[a-zA-Z0-9_\-]+", question.lower()))

    supported = len(answer_tokens & evidence_tokens) / max(1, len(answer_tokens))
    relevance = len(answer_tokens & question_tokens) / max(1, len(question_tokens))
    groundedness = _clamp(supported * 1.5)
    answer_relevance = _clamp(relevance * 2.0)
    return EvaluationResult(
        groundedness=groundedness,
        answer_relevance=answer_relevance,
        hallucination_risk=_clamp(1.0 - groundedness),
        evaluator="local-heuristic",
        notes="Fallback deterministic lexical evaluator.",
    )


def _llm_evaluate_sync(question: str, answer: str, contexts: list[dict]) -> EvaluationResult:
    settings = get_settings()
    evidence = "\n\n".join(
        f"[{item.get('title')}] {item.get('content')}" for item in contexts
    )
    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )
    prompt = f"""
You are evaluating a RAG answer.
Return ONLY valid JSON with numeric values from 0.0 to 1.0:
{{"groundedness": 0.0, "answer_relevance": 0.0, "notes": "short reason"}}

Groundedness: how fully the answer is supported by the supplied evidence.
Answer relevance: how directly the answer addresses the user's question.
Do not reward unsupported details.

QUESTION:
{question}

EVIDENCE:
{evidence}

ANSWER:
{answer}
""".strip()
    response = client.models.generate_content(
        model=settings.evaluator_model,
        contents=prompt,
    )
    text = (response.text or "").strip()
    # Strip accidental markdown fences if returned.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    data = json.loads(text)
    groundedness = _clamp(data.get("groundedness", 0.0))
    relevance = _clamp(data.get("answer_relevance", 0.0))
    return EvaluationResult(
        groundedness=groundedness,
        answer_relevance=relevance,
        hallucination_risk=_clamp(1.0 - groundedness),
        evaluator="gemini-judge",
        notes=str(data.get("notes", ""))[:300],
    )


async def evaluate_response(question: str, answer: str, contexts: list[dict]) -> EvaluationResult:
    settings = get_settings()
    with tracer.start_as_current_span("evaluation.rag_quality") as span:
        try:
            if settings.use_llm_evaluator and settings.google_cloud_project:
                result = await asyncio.to_thread(
                    _llm_evaluate_sync, question, answer, contexts
                )
            else:
                result = _heuristic_score(question, answer, contexts)
        except Exception as exc:
            result = _heuristic_score(question, answer, contexts)
            result.notes = f"LLM evaluator unavailable; used fallback: {type(exc).__name__}"

        span.set_attribute("evaluation.groundedness", result.groundedness)
        span.set_attribute("evaluation.answer_relevance", result.answer_relevance)
        span.set_attribute("evaluation.hallucination_risk", result.hallucination_risk)
        span.set_attribute("evaluation.evaluator", result.evaluator)

        attrs = {"evaluator": result.evaluator}
        groundedness_metric.record(result.groundedness, attributes=attrs)
        relevance_metric.record(result.answer_relevance, attributes=attrs)
        hallucination_metric.record(result.hallucination_risk, attributes=attrs)
        return result
