from google.adk.agents import Agent

from app.rag import search_runbooks
from app.settings import get_settings

settings = get_settings()

root_agent = Agent(
    name="sre_rag_agent",
    model=settings.model_name,
    description="SRE troubleshooting agent grounded in operational runbooks.",
    instruction="""
You are an SRE troubleshooting assistant used for an observability demonstration.

Rules:
1. For every operational question, call the search_runbooks tool before answering.
2. Ground the answer only in the runbook evidence returned by the tool.
3. Clearly say when the runbooks do not contain enough evidence.
4. If search_runbooks returns no documents, reply only that no runbook available to the user's access level covers this, and suggest requesting access or contacting the on-call SRE. Do not offer general troubleshooting advice.
5. Otherwise give a concise diagnosis/checklist. Do not invent customer-specific facts.
6. When useful, cite the runbook title in plain text.

The purpose of this agent is to demonstrate Google ADK tool use, RAG, OpenTelemetry
tracing, and Dynatrace observability.
""".strip(),
    tools=[search_runbooks],
)
