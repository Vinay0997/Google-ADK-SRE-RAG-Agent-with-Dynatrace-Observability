import os
import uuid

import requests
import streamlit as st


AGENT_URL = os.getenv(
    "AGENT_URL", "http://google-adk-sre-agent"
).rstrip("/")

AGENT_AUTH_ENABLED = os.getenv(
    "AGENT_AUTH_ENABLED", "false"
).lower() in {"true", "1", "yes"}

AGENT_AUDIENCE = os.getenv("AGENT_AUDIENCE", AGENT_URL)

ROLES = ["viewer", "sre", "security_privacy", "compliance"]

SAMPLE_QUESTIONS = {
    "Passwords and MFA": "What is our password and MFA policy?",
    "IT incident response": "What is the SOP for IT incident response?",
    "Data retention": "What is our data retention policy?",
    "Disaster recovery (SRE only)": "What does the disaster recovery runbook cover?",
    "Access control (restricted)": "What does our access control policy require?",
    "Out-of-scope question": (
        "What is our company's 2027 Nashville office lease amount?"
    ),
}


def new_session():
    st.session_state.session_id = f"ui-{uuid.uuid4().hex[:12]}"
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_request", None)


def request_headers():
    headers = {"Content-Type": "application/json"}

    if AGENT_AUTH_ENABLED:
        response = requests.get(
            "http://metadata.google.internal/"
            "computeMetadata/v1/instance/service-accounts/default/identity",
            headers={"Metadata-Flavor": "Google"},
            params={"audience": AGENT_AUDIENCE},
            timeout=10,
        )
        response.raise_for_status()
        headers["Authorization"] = f"Bearer {response.text.strip()}"

    return headers


st.set_page_config(
    page_title="SRE RAG Agent | Observability Demo",
    layout="wide",
)

if "session_id" not in st.session_state:
    new_session()

if "question" not in st.session_state:
    st.session_state.question = SAMPLE_QUESTIONS["Claims-engine outage"]


with st.sidebar:
    st.header("Demo controls")

    role = st.selectbox(
        "Simulated user role",
        ROLES,
        key="role",
        on_change=new_session,
    )

    st.caption(
        "Demo only: the selected role is client-supplied. "
        "This is not a verified login or production authorization."
    )

    st.divider()
    st.subheader("Sample questions")

    sample = st.selectbox(
        "Choose a scenario",
        list(SAMPLE_QUESTIONS),
    )

    if st.button("Load sample question", use_container_width=True):
        st.session_state.question = SAMPLE_QUESTIONS[sample]

    st.button(
        "New conversation",
        on_click=new_session,
        use_container_width=True,
    )

    st.divider()
    st.caption("Current session")
    st.code(st.session_state.session_id, language=None)

    with st.expander("Backend configuration"):
        st.write("Agent endpoint")
        st.code(AGENT_URL, language=None)
        st.write(
            "Agent authentication:",
            "Enabled" if AGENT_AUTH_ENABLED else "Disabled",
        )


st.title("Google ADK Policy RAG Agent")
st.caption(
    "Role-aware document retrieval | BigQuery audit | "
    "Response evaluation | Dynatrace observability"
)

st.info(
    "Demo: ask about the access control policy as viewer, "
    "then switch to security_privacy and ask the same question."
)

with st.form("ask_form"):
    question = st.text_area(
        "Ask an operational question",
        key="question",
        height=120,
        max_chars=4000,
    )
    submitted = st.form_submit_button("Ask agent", type="primary")


if submitted:
    clean_question = question.strip()

    if len(clean_question) < 3:
        st.warning("Enter a question with at least three characters.")
        st.stop()

    st.session_state.pop("last_result", None)
    st.session_state.pop("last_request", None)

    payload = {
        "question": clean_question,
        "user_id": f"demo-{role}",
        "session_id": st.session_state.session_id,
        "role": role,
    }

    with st.spinner("Retrieving evidence and evaluating the response..."):
        try:
            response = requests.post(
                f"{AGENT_URL}/ask",
                headers=request_headers(),
                json=payload,
                timeout=(10, 180),
            )
            response.raise_for_status()
            body = response.json()

            if not isinstance(body, dict) or "answer" not in body:
                raise ValueError("The agent returned an unexpected response.")

        except requests.exceptions.HTTPError as exc:
            st.error(f"Agent request failed: {exc}")
            if exc.response is not None:
                st.code(exc.response.text[:2000], language=None)
            st.stop()

        except (requests.exceptions.RequestException, ValueError) as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    st.session_state.session_id = body.get(
        "session_id", st.session_state.session_id
    )
    st.session_state.last_result = body
    st.session_state.last_request = payload


if "last_result" in st.session_state:
    body = st.session_state.last_result
    payload = st.session_state.last_request
    documents = body.get("retrieved_documents") or []
    evaluation = body.get("evaluation") or {}

    st.divider()
    st.caption(
        f"Result for role: {payload['role']} | "
        f"Question: {payload['question']}"
    )

    answer_column, evidence_column = st.columns([3, 2])

    with answer_column:
        st.subheader("Agent answer")
        st.markdown(body["answer"])

    with evidence_column:
        st.subheader("Retrieved evidence")

        if documents:
            st.success(f"{len(documents)} document(s) returned.")
            st.dataframe(
                documents,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "No documents returned. This alone does not establish "
                "whether the cause was access filtering, relevance, "
                "or a retrieval failure."
            )

    st.subheader("Response evaluation")

    metric_columns = st.columns(3)
    for column, label, key in [
        (metric_columns[0], "Groundedness", "groundedness"),
        (metric_columns[1], "Answer relevance", "answer_relevance"),
        (metric_columns[2], "Hallucination risk", "hallucination_risk"),
    ]:
        value = evaluation.get(key)
        column.metric(
            label,
            f"{value:.2f}" if isinstance(value, (int, float)) else "N/A",
        )

    st.caption(
        f"Evaluator: {evaluation.get('evaluator', 'unknown')} | "
        "Groundedness/relevance: higher is better. "
        "Hallucination risk: lower is better."
    )

    if evaluation.get("evaluator") == "refusal-rule":
        st.caption(
            "These scores come from a refusal-wording rule, not an "
            "independent LLM assessment or an authorization check."
        )

    if evaluation.get("notes"):
        st.write(evaluation["notes"])

    st.subheader("Execution details")

    c1, c2, c3, c4 = st.columns(4)
    duration = body.get("duration_seconds")
    cost = body.get("estimated_cost_usd")

    c1.metric(
        "Duration (s)",
        f"{duration:.2f}" if isinstance(duration, (int, float)) else "N/A",
    )
    c2.metric(
        "Tokens in / out",
        f"{body.get('input_tokens', 0)} / "
        f"{body.get('output_tokens', 0)}",
    )
    c3.metric(
        "Estimated cost (USD)",
        f"{cost:.6f}" if isinstance(cost, (int, float)) else "N/A",
    )
    c4.metric("Model", body.get("model", "unknown"))

    st.code(
        f"trace_id: {body.get('trace_id', 'unknown')}\n"
        f"session_id: {body.get('session_id', 'unknown')}\n"
        f"telemetry_exporter: "
        f"{body.get('telemetry_exporter', 'unknown')}\n"
        f"reported_instance: {body.get('pod_name', 'unknown')}",
        language=None,
    )

    with st.expander("Full API response"):
        st.json(body)
