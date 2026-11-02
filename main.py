import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from opentelemetry.trace import Status, StatusCode

from app.agent import root_agent
from app.evaluator import evaluate_response
from app.rag import CURRENT_RETRIEVAL, retrieve_runbooks
from app.settings import get_settings
from app.telemetry import (
    TELEMETRY,
    error_counter,
    request_counter,
    request_duration,
    tracer,
    workflow_success_counter,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sre-rag-demo")
settings = get_settings()

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name=settings.app_name,
    session_service=session_service,
    auto_create_session=True,
)

api = FastAPI(
    title="Google ADK SRE RAG Agent - Dynatrace Observability Demo",
    version="1.0.0",
    description="Personal interview demo: ADK + Cloud Run + OpenTelemetry + Dynatrace + RAG evaluation.",
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
        "docs": "/docs",
        "health": "/healthz",
        "ask": "POST /ask",
    }


@api.get("/healthz")
async def healthz():
    return {"status": "ok"}


@api.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    started = time.perf_counter()
    session_id = payload.session_id or f"session-{uuid.uuid4().hex[:12]}"
    CURRENT_RETRIEVAL.set([])
    request_counter.add(1, {"route": "/ask"})

    with tracer.start_as_current_span("agent.request") as request_span:
        trace_id = f"{request_span.get_span_context().trace_id:032x}"
        request_span.set_attribute("agent.session_id", session_id)
        request_span.set_attribute("agent.user_id", payload.user_id)
        request_span.set_attribute("agent.question.length", len(payload.question))

        try:
            content = types.Content(
                role="user",
                parts=[types.Part.from_text(text=payload.question)],
            )

            final_text = ""
            with tracer.start_as_current_span("agent.execute") as agent_span:
                async for event in runner.run_async(
                    user_id=payload.user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    calls = event.get_function_calls()
                    if calls:
                        agent_span.set_attribute(
                            "agent.tool.calls",
                            ",".join(call.name for call in calls),
                        )
                    if event.is_final_response() and event.content and event.content.parts:
                        pieces = [
                            part.text
                            for part in event.content.parts
                            if getattr(part, "text", None)
                        ]
                        if pieces:
                            final_text = "".join(pieces).strip()

            if not final_text:
                raise RuntimeError("ADK returned no final text response")

            contexts = CURRENT_RETRIEVAL.get()
            if not contexts:
                # Safety fallback for evaluation only. The agent instruction should normally call the tool.
                contexts = retrieve_runbooks(payload.question)
                request_span.set_attribute("rag.fallback_retrieval", True)

            evaluation = await evaluate_response(
                payload.question,
                final_text,
                contexts,
            )

            duration = time.perf_counter() - started
            request_duration.record(duration, {"route": "/ask"})
            workflow_success_counter.add(1, {"route": "/ask"})

            request_span.set_attribute("agent.workflow.success", True)
            request_span.set_attribute("agent.duration.seconds", duration)
            request_span.set_attribute("evaluation.groundedness", evaluation.groundedness)
            request_span.set_attribute("evaluation.hallucination_risk", evaluation.hallucination_risk)

            return AskResponse(
                answer=final_text,
                session_id=session_id,
                trace_id=trace_id,
                retrieved_documents=[
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "score": item["score"],
                    }
                    for item in contexts
                ],
                evaluation=evaluation.to_dict(),
                telemetry_exporter=TELEMETRY.exporter_mode,
                duration_seconds=round(duration, 4),
            )
        except Exception as exc:
            duration = time.perf_counter() - started
            request_duration.record(duration, {"route": "/ask"})
            error_counter.add(1, {"route": "/ask", "error.type": type(exc).__name__})
            request_span.record_exception(exc)
            request_span.set_status(Status(StatusCode.ERROR, str(exc)))
            request_span.set_attribute("agent.workflow.success", False)
            logger.exception("Agent request failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
