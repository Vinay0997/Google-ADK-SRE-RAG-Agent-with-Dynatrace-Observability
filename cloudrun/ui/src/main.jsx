import React, {useState} from "react";
import {createRoot} from "react-dom/client";
import ReactMarkdown from "react-markdown";
import "./style.css";

const examples = [
  "What caused the claims-engine outage?",
  "A FHIR gateway pod keeps restarting. What do I check?",
  "The patient portal is slow. What should I check?",
  "What is the capital of France?"
];

function App() {
  const [question, setQuestion] = useState(examples[0]);
  const [role, setRole] = useState("sre");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  async function ask(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    setCopied(false);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 180000);

    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          question: question.trim(),
          role,
          user_id: "react-demo",
          session_id: `react-${crypto.randomUUID()}`
        }),
        signal: controller.signal
      });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); }
      catch { throw new Error(`Server returned a non-JSON response (${response.status}).`); }
      if (!response.ok)
        throw new Error(JSON.stringify(data.detail ?? data));
      setResult(data);
    } catch (err) {
      setError(err.name === "AbortError"
        ? "The request exceeded 180 seconds. Check the backend trace before retrying."
        : err.message);
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  const ev = result?.evaluation ?? {};
  const formatScore = value =>
    typeof value === "number" ? value.toFixed(2) : "Not reported";

  return (
    <main>
      <header>
        <div className="eyebrow">GOOGLE ADK · GKE · DYNATRACE</div>
        <h1>SRE Agent Observatory</h1>
        <p>Runbook-grounded troubleshooting with request-level evidence.</p>
      </header>

      <div className="notice">
        Demonstration only. Roles are simulated, not authenticated.
        Use fictional data; do not submit credentials or sensitive information.
      </div>

      <section>
        <h2>Ask the agent</h2>
        <div className="examples">
          {examples.map(text => (
            <button key={text} type="button" disabled={busy}
              onClick={() => setQuestion(text)}>{text}</button>
          ))}
        </div>

        <form onSubmit={ask}>
          <label htmlFor="question">Operational question</label>
          <textarea id="question" value={question}
            onChange={e => setQuestion(e.target.value)}
            minLength={3} maxLength={4000} required disabled={busy} />

          <div className="controls">
            <label>Simulated role
              <select value={role} disabled={busy}
                onChange={e => setRole(e.target.value)}>
                <option value="sre">SRE</option>
                <option value="viewer">Viewer</option>
              </select>
            </label>
            <button className="primary" disabled={busy || question.trim().length < 3}>
              {busy ? "Processing request…" : "Send question"}
            </button>
          </div>
        </form>
        {busy && <p role="status">Waiting for retrieval, generation and evaluation…</p>}
        {error && <div className="error" role="alert">{error}</div>}
      </section>

      {result && <>
        <div className="metrics">
          <Metric title="Request duration"
            value={`${Number(result.duration_seconds).toFixed(1)} s`} />
          <Metric title="Groundedness" value={formatScore(ev.groundedness)} />
          <Metric title="Answer relevance" value={formatScore(ev.answer_relevance)} />
          <Metric title="Hallucination risk" value={formatScore(ev.hallucination_risk)} />
        </div>

        <section>
          <h2>Agent answer</h2>
          <ReactMarkdown skipHtml>{result.answer ?? ""}</ReactMarkdown>
        </section>

        <section>
          <h2>Retrieved evidence</h2>
          {result.retrieved_documents?.length
            ? result.retrieved_documents.map((doc, i) => (
              <div className="document" key={`${doc.id}-${i}`}>
                <strong>{doc.title}</strong>
                <div>{doc.id} · Retrieval score: {formatScore(doc.score)}</div>
              </div>
            ))
            : <p>No retrieved documents reported for this request.</p>}
        </section>

        <section>
          <h2>Evaluation and telemetry</h2>
          <p>Evaluator: {ev.evaluator ?? "Not reported"}</p>
          <p>{ev.notes}</p>
          <p className="muted">
            Judge scores are diagnostic signals, not guarantees of correctness.
            Response token and cost values are those reported by the backend.
          </p>
          <dl>
            <dt>Model</dt><dd>{result.model}</dd>
            <dt>Input / output tokens</dt>
            <dd>{result.input_tokens} / {result.output_tokens}</dd>
            <dt>Estimated cost</dt>
            <dd>US${Number(result.estimated_cost_usd ?? 0).toFixed(6)}</dd>
            <dt>Pod</dt><dd>{result.pod_name}</dd>
            <dt>Trace ID</dt><dd><code>{result.trace_id}</code></dd>
          </dl>
          <button onClick={async () => {
            try {
              await navigator.clipboard.writeText(result.trace_id);
              setCopied(true);
            } catch { setError("Copy unavailable. Select and copy the trace ID manually."); }
          }}>{copied ? "Trace ID copied" : "Copy trace ID"}</button>
        </section>
      </>}
    </main>
  );
}

function Metric({title, value}) {
  return <div className="metric"><span>{title}</span><strong>{value}</strong></div>;
}

createRoot(document.getElementById("root")).render(<App />);
