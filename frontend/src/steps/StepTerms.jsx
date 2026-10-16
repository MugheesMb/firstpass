import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Report } from "../components/FindingCard.jsx";
import Timeline from "../components/Timeline.jsx";

export default function StepTerms({ kase, setKase, run, onEvidence, next }) {
  const [points, setPoints] = useState(null);
  const [email, setEmail] = useState(null);
  const [running, setRunning] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (kase) api.insights(kase.id).then((i) => setPoints(i.timeline.filter((p) => ["lc_issued", "goods_ready", "latest_shipment", "expiry"].includes(p.key)))).catch(() => {});
  }, [kase?.id, kase?.goods_ready_date]);

  async function review() {
    setRunning(true);
    const r = await run("Reviewing LC terms", () => api.lcReview(kase.id));
    setRunning(false);
    if (r) setKase(await api.getCase(kase.id));
  }

  async function draft() {
    const e = await run("Drafting the amendment request", () => api.amendmentEmail(kase.id));
    if (e) setEmail(e);
  }

  const open = kase?.lc_review?.findings.filter((f) => f.status === "open").length || 0;

  return (
    <div className="step-body">
      <section className="panel">
        <div className="panel-head"><h2>Your shipment window</h2></div>
        <Timeline points={points} />
      </section>

      <div className="actions">
        <button className="btn primary" onClick={review} disabled={running}>
          {kase?.lc_review ? "Review LC terms again" : "Review LC terms"}
        </button>
        {kase?.lc_review && open > 0 && <button className="btn" onClick={draft}>Draft amendment request to the buyer</button>}
        {kase?.lc_review && <button className="btn quiet" onClick={next}>Continue to documents</button>}
      </div>

      <Report report={kase?.lc_review} kase={kase} run={run} setKase={setKase} onEvidence={onEvidence} />

      {email && (
        <div className="modal" onClick={() => setEmail(null)}>
          <div className="modal-box" role="dialog" aria-label="Amendment request" onClick={(e) => e.stopPropagation()}>
            <h2>Amendment request</h2>
            <p className="muted">Subject: {email.subject}</p>
            <pre className="draft">{email.body}</pre>
            <div className="actions">
              <button className="btn primary" onClick={() => { navigator.clipboard?.writeText(`${email.subject}\n\n${email.body}`); setCopied(true); }}>
                {copied ? "Copied" : "Copy email"}
              </button>
              <button className="btn quiet" onClick={() => { setEmail(null); setCopied(false); }}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
