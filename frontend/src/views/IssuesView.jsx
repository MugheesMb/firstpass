import { useState } from "react";
import { api, label } from "../api.js";
import { Decision, DiffBanner, History } from "../components/FindingCard.jsx";
import EmailModal from "../components/EmailModal.jsx";

const TABS = [
  ["open", "Open", "Needs a decision: fix it, accept it with a reason, or dispute it."],
  ["fixed", "Marked fixed", "You said these are fixed. Re-run the check to confirm; anything still present reopens."],
  ["resolved", "Resolved by re-check", "Found in an earlier run and no longer present."],
  ["accepted", "Accepted", "Kept as they are. Discrepancies here can go into a waiver request to the buyer."],
  ["disputed", "Disputed", "You disagree with the finding. Keep the reason ready for your bank."],
];

const EMPTY = {
  open: "Nothing open. Every finding has a decision.",
  fixed: "Nothing marked fixed and waiting for a re-check.",
  resolved: "Nothing resolved yet. Upload a corrected document and re-run the check.",
  accepted: "Nothing accepted.",
  disputed: "Nothing disputed.",
};

export default function IssuesView({ kase, setKase, run, onEvidence, goto }) {
  const [tab, setTab] = useState("open");
  const [email, setEmail] = useState(null);
  if (!kase) return null;

  const tagged = [
    ...(kase.lc_review?.findings || []).map((f) => ({ ...f, source: "LC review" })),
    ...(kase.document_check?.findings || []).map((f) => ({ ...f, source: "Document check" })),
  ];
  const resolved = (kase.document_check?.resolved || []).map((f) => ({ ...f, source: "Document check" }))
    .concat((kase.lc_review?.resolved || []).map((f) => ({ ...f, source: "LC review" })));
  const list = (k) => (k === "resolved" ? resolved : tagged.filter((f) => f.status === k));
  const items = list(tab);
  const waivable = tagged.filter((f) => f.status === "accepted" && f.source === "Document check" && f.kind !== "needs_review").length;

  async function recheck() {
    const r = await run("Re-running the compliance check", () => api.check(kase.id, kase.presentation_date));
    if (r) setKase(await api.getCase(kase.id));
  }

  async function waiver() {
    const e = await run("Drafting the waiver request", () => api.waiverRequest(kase.id));
    if (e) {
      setEmail(e);
      setKase(await api.getCase(kase.id));
    }
  }

  return (
    <div className="step-body">
      <div className="actions">
        <button className="btn primary" onClick={recheck} disabled={!kase.document_check}>Re-run the compliance check</button>
        <button className="btn" onClick={waiver} disabled={!waivable}
                title={waivable ? "" : "Accept a discrepancy first"}>
          Draft waiver request to the buyer{waivable ? ` (${waivable})` : ""}
        </button>
        {!kase.document_check && <button className="btn quiet" onClick={() => goto(4)}>Run the first check</button>}
      </div>
      <DiffBanner report={kase.document_check} />

      <div className="board-tabs" role="tablist">
        {TABS.map(([k, name]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {name} <span className="n">{list(k).length}</span>
          </button>
        ))}
      </div>
      <p className="muted">{TABS.find(([k]) => k === tab)[2]}</p>

      {items.length === 0 ? (
        <section className="panel empty"><p>{EMPTY[tab]}</p></section>
      ) : (
        <ul className="board">
          {items.map((f) => (
            <li key={f.id + f.source} className={`sev-${f.severity}`}>
              <div className="b-main">
                <div className="finding-head">
                  <span className={`chip chip-${f.severity}`}>{f.severity}</span>
                  <span className="kind">{f.source}</span>
                  {f.ucp_ref && <span className="ref">UCP 600 {f.ucp_ref}</span>}
                  <span className="ref">First seen in run {f.first_seen_run || 1}</span>
                </div>
                <h4>{f.title}</h4>
                <p className="b-docs">{[...new Set(f.evidence.map((e) => label(e.doc_type)))].join(", ")}</p>
                {f.note && <p className="decision-note"><b>Reason:</b> {f.note}</p>}
                <History f={f} />
              </div>
              <div className="b-actions">
                {f.evidence?.length > 0 && <button className="btn quiet" onClick={() => onEvidence(f)}>Evidence</button>}
                {tab !== "resolved" && <Decision f={f} kase={kase} run={run} setKase={setKase} />}
              </div>
            </li>
          ))}
        </ul>
      )}
      <EmailModal title="Waiver request" email={email} onClose={() => setEmail(null)} />
    </div>
  );
}
