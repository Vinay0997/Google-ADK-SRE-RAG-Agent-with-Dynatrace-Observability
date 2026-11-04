import os
import uuid

import requests
import streamlit as st

AGENT_URL = os.getenv("AGENT_URL", "http://google-adk-sre-agent").rstrip("/")

st.set_page_config(page_title="SRE RAG Agent (GKE)", layout="wide")
st.title("Google ADK SRE RAG Agent")
st.caption(f"Running on GKE. Agent endpoint: {AGENT_URL}")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"ui-{uuid.uuid4().hex[:10]}"

question = st.text_area("Ask an SRE question", "A GKE pod is in CrashLoopBackOff. What should I inspect first?")

if st.button("Ask", type="primary"):
    with st.spinner("Calling agent..."):
        try:
            r = requests.post(
                f"{AGENT_URL}/ask",
                json={"question": question, "user_id": "ui-user", "session_id": st.session_state.session_id},
                timeout=180,
            )
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()

    st.subheader("Answer")
    st.write(body["answer"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Duration (s)", body["duration_seconds"])
    c2.metric("Tokens in/out", f'{body["input_tokens"]}/{body["output_tokens"]}')
    c3.metric("Est. cost (USD)", body["estimated_cost_usd"])
    c4.metric("Served by pod", body["pod_name"])
    st.subheader("Evaluation")
    st.json(body["evaluation"])
    st.subheader("Retrieved runbooks")
    st.dataframe(body["retrieved_documents"])
    st.code(f'trace_id: {body["trace_id"]}\nexporter: {body["telemetry_exporter"]}')
