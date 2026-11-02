import asyncio
import time
import uuid

import streamlit as st
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


@st.cache_resource
def get_runner() -> Runner:
    return Runner(
        agent=root_agent,
        app_name=get_settings().app_name,
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )


async def answer_question(question: str, session_id: str) -> dict:
    """Run the ADK agent and return the same useful evidence as the API response."""
    started = time.perf_counter()
    CURRENT_RETRIEVAL.set([])
    request_counter.add(1, {"route": "streamlit"})

    with tracer.start_as_current_span("streamlit.agent.request") as request_span:
        trace_id = f"{request_span.get_span_context().trace_id:032x}"
        request_span.set_attribute("agent.session_id", session_id)
        request_span.set_attribute("agent.question.length", len(question))
        try:
            content = types.Content(
                role="user", parts=[types.Part.from_text(text=question)]
            )
            final_text = ""
            with tracer.start_as_current_span("agent.execute") as agent_span:
                async for event in get_runner().run_async(
                    user_id="streamlit-user",
                    session_id=session_id,
                    new_message=content,
                ):
                    calls = event.get_function_calls()
                    if calls:
                        agent_span.set_attribute(
                            "agent.tool.calls", ",".join(call.name for call in calls)
                        )
                    if event.is_final_response() and event.content and event.content.parts:
                        final_text = "".join(
                            part.text
                            for part in event.content.parts
                            if getattr(part, "text", None)
                        ).strip()

            if not final_text:
                raise RuntimeError("ADK returned no final text response")

            contexts = CURRENT_RETRIEVAL.get() or retrieve_runbooks(question)
            evaluation = await evaluate_response(question, final_text, contexts)
            duration = time.perf_counter() - started
            request_duration.record(duration, {"route": "streamlit"})
            workflow_success_counter.add(1, {"route": "streamlit"})
            request_span.set_attribute("agent.workflow.success", True)
            request_span.set_attribute("agent.duration.seconds", duration)

            return {
                "answer": final_text,
                "trace_id": trace_id,
                "retrieved_documents": contexts,
                "evaluation": evaluation.to_dict(),
                "duration_seconds": round(duration, 4),
            }
        except Exception as exc:
            duration = time.perf_counter() - started
            request_duration.record(duration, {"route": "streamlit"})
            error_counter.add(1, {"route": "streamlit", "error.type": type(exc).__name__})
            request_span.record_exception(exc)
            request_span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


st.set_page_config(page_title="SRE RAG Agent", page_icon="🔎", layout="wide")
settings = get_settings()

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:12]}"

st.title("SRE RAG Agent")
st.caption("Google ADK, grounded runbook retrieval, and Dynatrace-ready OpenTelemetry")

with st.sidebar:
    st.subheader("Runtime")
    st.write(f"Telemetry exporter: `{TELEMETRY.exporter_mode}`")
    if settings.google_genai_use_vertexai:
        st.info("Using Vertex AI. Configure Google Cloud credentials and a project before asking a question.")
    elif not settings.google_api_key:
        st.warning("Add GOOGLE_API_KEY to .env or Streamlit secrets before asking a question.")
    else:
        st.success("Using Gemini API-key authentication.")

with st.form("ask-form"):
    question = st.text_area(
        "What are you troubleshooting?",
        placeholder="Our service has high latency. What should I check?",
        height=120,
    )
    submitted = st.form_submit_button("Ask the agent", type="primary")

if submitted:
    if len(question.strip()) < 3:
        st.error("Enter a question with at least three characters.")
    else:
        with st.spinner("Searching runbooks and generating a grounded answer..."):
            try:
                result = asyncio.run(
                    answer_question(question.strip(), st.session_state.session_id)
                )
            except Exception as exc:
                st.error(f"The agent request failed: {exc}")
            else:
                st.subheader("Answer")
                st.write(result["answer"])

                left, middle, right = st.columns(3)
                left.metric("Groundedness", f"{result['evaluation']['groundedness']:.0%}")
                middle.metric("Relevance", f"{result['evaluation']['answer_relevance']:.0%}")
                right.metric("Hallucination risk", f"{result['evaluation']['hallucination_risk']:.0%}")

                with st.expander("Retrieved runbooks"):
                    for document in result["retrieved_documents"]:
                        st.markdown(f"**{document['title']}** — score {document['score']}")
                        st.write(document["content"])

                with st.expander("Request details"):
                    st.json(
                        {
                            "trace_id": result["trace_id"],
                            "duration_seconds": result["duration_seconds"],
                            "evaluator": result["evaluation"]["evaluator"],
                            "notes": result["evaluation"]["notes"],
                        }
                    )
