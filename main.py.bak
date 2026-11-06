import asyncio
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.agent import root_agent
from app.bq_sink import write_execution_row
from app.evaluator import evaluate_response
from app.genai import estimate_cost_usd, messages_json
from app.rag import CURRENT_RETRIEVAL, retrieve_runbooks
from app.settings import get_settings
from app.telemetry import (
    TELEMETRY,
    cost_counter,
    emit_judge_result,
    error_counter,
    request_counter,
    request_duration,
    token_usage,
    tracer,
    workflow_success_counter,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sre-rag-demo")
settings = get_settings()
POD_NAME = os.getenv("POD_NAME", "local")
PROVIDER = "gcp.vertex_ai" if settings.google_genai_use_vertexai else "gcp.gemini"
_background: set[asyncio.Task] = set()

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=settings.app_name,
    session_service=session_service,
    auto_create_session=True,
)

api = FastAPI(
    title="Google ADK SRE RAG Agent - Dynatrace Observability",
    version="1.1.0",
    description="ADK + GKE + OpenTelemetry Collector + Dynatrace AI Observability + BigQuery audit sink.",
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    user_id: str = "demo-user"
    session_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    session_id: str
    trace_id: str
    retrieved_documents: list[dict]
    evaluation: dict
    telemetry_exporter: str
    duration_seconds: float
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    pod_name: str


@api.middleware("http")
async def trace_http_request(request: Request, call_next):
    with tracer.start_as_current_span(f"http {request.method} {request.url.path}") as span:
        span.set_attribute("http.request.method", request.method)
        span.set_attribute("url.path", request.url.path)
        try:
            response = await call_next(request)
            span.set_attribute("http.response.status_code", response.status_code)
            return response
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@api.get("/")
async def root():
    return {
        "service": settings.otel_service_name,
        "status": "ready",
        "telemetry_exporter": TELEMETRY.exporter_mode,
        "bigquery_sink": settings.bq_enabled,
        "pod": POD_NAME,
        "docs": "/docs",
        "health": "/healthz",
        "ask": "POST /ask",
    }


@api.get("/healthz")
async def healthz():
    return {"status": "ok"}


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


@api.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    started = time.perf_counter()
    session_id = payload.session_id or f"session-{uuid.uuid4().hex[:12]}"
    CURRENT_RETRIEVAL.set([])
    request_counter.add(1, {"route": "/ask"})
    model = settings.model_name
    llm_span = None
    in_tok = out_tok = 0
    tool_names: list[str] = []

    with tracer.start_as_current_span("agent.request") as request_span:
        trace_id = f"{request_span.get_span_context().trace_id:032x}"
        request_span.set_attribute("agent.session_id", session_id)
        request_span.set_attribute("agent.user_id", payload.user_id)
        request_span.set_attribute("agent.question.length", len(payload.question))

        try:
            content = types.Content(role="user", parts=[types.Part.from_text(text=payload.question)])
            final_text = ""

            with tracer.start_as_current_span("agent.execute") as agent_span:
                # GenAI inference span: Dynatrace AI Observability reads gen_ai.* from it.
                # It is ended after evaluation so judge results attach to the same span.
                llm_span = tracer.start_span(f"chat {model}", kind=SpanKind.CLIENT)
                async for event in runner.run_async(
                    user_id=payload.user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    usage = getattr(event, "usage_metadata", None)
                    if usage:
                        in_tok += getattr(usage, "prompt_token_count", 0) or 0
                        out_tok += getattr(usage, "candidates_token_count", 0) or 0
                    calls = event.get_function_calls()
                    if calls:
                        tool_names.extend(call.name for call in calls)
                        agent_span.set_attribute("agent.tool.calls", ",".join(tool_names))
                    if event.is_final_response() and event.content and event.content.parts:
                        pieces = [p.text for p in event.content.parts if getattr(p, "text", None)]
                        if pieces:
                            final_text = "".join(pieces).strip()
                llm_end_ns = time.time_ns()

            if not final_text:
                raise RuntimeError("ADK returned no final text response")

            contexts = CURRENT_RETRIEVAL.get()
            if not contexts:
                contexts = retrieve_runbooks(payload.question)
                request_span.set_attribute("rag.fallback_retrieval", True)

            evaluation = await evaluate_response(payload.question, final_text, contexts)

            duration = time.perf_counter() - started
            cost = estimate_cost_usd(in_tok, out_tok)
            attrs = {"gen_ai.request.model": model}
            token_usage.record(in_tok, {**attrs, "gen_ai.token.type": "input"})
            token_usage.record(out_tok, {**attrs, "gen_ai.token.type": "output"})
            cost_counter.add(cost, attrs)
            request_duration.record(duration, {"route": "/ask"})
            workflow_success_counter.add(1, {"route": "/ask"})

            llm_span.set_attribute("gen_ai.operation.name", "chat")
            llm_span.set_attribute("gen_ai.provider.name", PROVIDER)
            llm_span.set_attribute("gen_ai.request.model", model)
            llm_span.set_attribute("gen_ai.response.model", model)
            llm_span.set_attribute("gen_ai.conversation.id", session_id)
            llm_span.set_attribute("gen_ai.usage.input_tokens", in_tok)
            llm_span.set_attribute("gen_ai.usage.output_tokens", out_tok)
            llm_span.set_attribute("gen_ai.usage.cost_usd", cost)
            llm_span.set_attribute("rag.context.ids", ",".join(str(c["id"]) for c in contexts))
            if settings.capture_prompts:
                llm_span.set_attribute("gen_ai.input.messages", messages_json("user", payload.question))
                llm_span.set_attribute(
                    "gen_ai.output.messages", messages_json("assistant", final_text, "stop")
                )

            emit_judge_result(
                llm_span,
                "groundedness",
                evaluation.groundedness,
                evaluation.groundedness >= settings.groundedness_threshold,
            )
            emit_judge_result(
                llm_span,
                "hallucination_risk",
                evaluation.hallucination_risk,
                evaluation.hallucination_risk <= settings.hallucination_threshold,
            )
            for key, value in evaluation.to_dict().items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    llm_span.set_attribute(f"evaluation.{key}", value)
                    request_span.set_attribute(f"evaluation.{key}", value)
            llm_span.end(end_time=llm_end_ns)

            request_span.set_attribute("agent.workflow.success", True)
            request_span.set_attribute("agent.duration.seconds", duration)

            _fire_and_forget(
                write_execution_row(
                    {
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "user_id": payload.user_id,
                        "question": payload.question,
                        "answer": final_text,
                        "model": model,
                        "provider": PROVIDER,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "estimated_cost_usd": cost,
                        "duration_seconds": round(duration, 4),
                        "tool_calls": ",".join(tool_names),
                        "retrieved_doc_ids": ",".join(str(c["id"]) for c in contexts),
                        "groundedness": evaluation.groundedness,
                        "hallucination_risk": evaluation.hallucination_risk,
                        "workflow_success": True,
                        "error": None,
                        "pod_name": POD_NAME,
                    }
                )
            )

            return AskResponse(
                answer=final_text,
                session_id=session_id,
                trace_id=trace_id,
                retrieved_documents=[
                    {"id": c["id"], "title": c["title"], "score": c["score"]} for c in contexts
                ],
                evaluation=evaluation.to_dict(),
                telemetry_exporter=TELEMETRY.exporter_mode,
                duration_seconds=round(duration, 4),
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                estimated_cost_usd=cost,
                pod_name=POD_NAME,
            )
        except Exception as exc:
            duration = time.perf_counter() - started
            request_duration.record(duration, {"route": "/ask"})
            error_counter.add(1, {"route": "/ask", "error.type": type(exc).__name__})
            if llm_span is not None:
                llm_span.record_exception(exc)
                llm_span.set_status(Status(StatusCode.ERROR, str(exc)))
                llm_span.end()
            request_span.record_exception(exc)
            request_span.set_status(Status(StatusCode.ERROR, str(exc)))
            request_span.set_attribute("agent.workflow.success", False)
            logger.exception("Agent request failed")
            _fire_and_forget(
                write_execution_row(
                    {
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "user_id": payload.user_id,
                        "question": payload.question,
                        "model": model,
                        "provider": PROVIDER,
                        "duration_seconds": round(duration, 4),
                        "workflow_success": False,
                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                        "pod_name": POD_NAME,
                    }
                )
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc
