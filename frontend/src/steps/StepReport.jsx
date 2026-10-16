import { useEffect, useState } from "react";
import { api, label } from "../api.js";
import Matrix from "../components/Matrix.jsx";
import Timeline from "../components/Timeline.jsx";

export default function StepReport({ kase, onEvidence, goto, setView }) {
  const [ins, setIns] = useState(null);
  useEffect(() => {
    if (kase) api.insights(kase.id).then(setIns).catch(() => {});
  }, [kase?.id, JSON.stringify(kase?.document_check?.findings.map((f) => f.status))]);

  if (!kase?.document_check) return <p className="muted">Run the compliance check first.</p>;
  if (!ins) return <p className="muted">Preparing the report…</p>;

  const r = ins.readiness;
  const lc = kase.documents.find((d) => d.doc_type === "letter_of_credit");
  const open = kase.document_check.findings.filter((f) => f.status === "open");
  const tone = r.open === 0 ? "pass" : r.high ? "fail" : "warn";

  return (
    <div className="step-body report-page">
      <section className={`verdict ${tone}`}>
        <div className="score" aria-label={`Readiness ${r.score} out of 100`}>
          <span className="score-n">{r.score}</span>
          <span className="score-of">/100</span>
        </div>
        <div className="verdict-text">
          <h2>{r.verdict}</h2>
          <p>
            {r.open} open item{r.open === 1 ? "" : "s"}, {r.high} high severity, {r.resolved} resolved, across {r.checks} checks
            for credit {lc?.data.lc_number || ""}.
          </p>
          <p className="muted small">{r.method}</p>
        </div>
        <button className="btn quiet no-print" onClick={() => window.print()}>Print or save as PDF</button>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Consistency across documents</h2>
          <p className="muted">The LC is the standard. Select a marked cell to see the evidence.</p>
        </div>
        <Matrix matrix={ins.matrix} findings={kase.document_check.findings} onEvidence={onEvidence} />
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Dates against the credit</h2></div>
        <Timeline points={ins.timeline} />
      </section>

      <section className="panel">
        <div className="panel-head"><h2>What to fix before presenting</h2></div>
        {open.length === 0 ? (
          <p>Nothing open. Keep this report with your presentation.</p>
        ) : (
          <ol className="fixlist">
            {open.map((f) => (
              <li key={f.id} className={`sev-${f.severity}`}>
                <button onClick={() => onEvidence(f)}>
                  <b>{f.title}</b>
                  <span>{f.suggested_fix}</span>
                  <small>{[...new Set(f.evidence.map((e) => label(e.doc_type)))].join(", ")}{f.ucp_ref ? `, UCP 600 ${f.ucp_ref}` : ""}</small>
                </button>
              </li>
            ))}
          </ol>
        )}
        <div className="actions no-print">
          <button className="btn" onClick={() => setView("issues")}>Decide on each issue</button>
          <button className="btn quiet" onClick={() => goto(4)}>Back to the findings</button>
        </div>
      </section>
    </div>
  );
}
