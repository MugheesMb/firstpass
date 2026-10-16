import { useState } from "react";
import { api, label, when } from "../api.js";

const KIND = {
  discrepancy: "Discrepancy",
  possible: "Possible issue",
  needs_review: "Check by hand",
  lc_risk: "LC risk",
};
const STATUS_TEXT = { open: "Open", fixed: "Marked fixed", accepted: "Accepted", disputed: "Disputed" };
const NOTE_PROMPT = {
  accepted: "Why accept it? For example: buyer agreed to waive, or bank confirmed it is acceptable.",
  disputed: "Why do you disagree? For example: the B/L date is the on-board date, not the issue date.",
};

export function Decision({ f, kase, run, setKase }) {
  const [asking, setAsking] = useState(null);
  const [note, setNote] = useState("");
  const done = f.status !== "open";

  async function save(status, n) {
    const c = await run("Saving decision", () => api.setStatus(kase.id, f.id, status, n));
    if (c) {
      setKase(c);
      setAsking(null);
      setNote("");
    }
  }

  if (asking) {
    return (
      <form className="note-form" onSubmit={(e) => { e.preventDefault(); note.trim() && save(asking, note); }}>
        <label>
          <span>{NOTE_PROMPT[asking]}</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} autoFocus required />
        </label>
        <div className="actions">
          <button className="btn small primary" disabled={!note.trim()}>{asking === "accepted" ? "Accept with this reason" : "Dispute with this reason"}</button>
          <button type="button" className="btn small quiet" onClick={() => setAsking(null)}>Cancel</button>
        </div>
      </form>
    );
  }
  return !done ? (
    <>
      <button className="btn small" onClick={() => save("fixed")}>Mark fixed</button>
      <button className="btn small light" onClick={() => setAsking("accepted")}>Accept</button>
      <button className="btn small light" onClick={() => setAsking("disputed")}>Dispute</button>
    </>
  ) : (
    <button className="btn small light" onClick={() => save("open")}>Reopen</button>
  );
}

export function History({ f }) {
  if (!f.history?.length) return null;
  return (
    <details className="history">
      <summary>History ({f.history.length})</summary>
      <ol>
        {f.history.map((h, i) => (
          <li key={i}>
            <b>{STATUS_TEXT[h.status] || h.status}</b> by {h.by}, {when(h.at)}{h.note ? `: ${h.note}` : ""}
          </li>
        ))}
      </ol>
    </details>
  );
}

export default function FindingCard({ f, kase, run, setKase, onEvidence }) {
  const [fix, setFix] = useState("");
  const done = f.status !== "open";

  async function draft() {
    const r = await run("Drafting the fix", () => api.draftFix(kase.id, f.id));
    if (r) setFix(r.text);
  }

  return (
    <article className={`finding sev-${f.severity} ${done ? "done" : ""}`}>
      <div className="finding-head">
        <span className={`chip chip-${f.severity}`}>{f.severity}</span>
        <span className="kind">{KIND[f.kind]}</span>
        {f.ucp_ref && <span className="ref">UCP 600 {f.ucp_ref}</span>}
        {f.lc_ref && <span className="ref">LC field {f.lc_ref}</span>}
        {f.first_seen_run > 1 && <span className="ref">New in run {f.first_seen_run}</span>}
        {done && <span className={`status st-${f.status}`}>{STATUS_TEXT[f.status]}</span>}
      </div>
      <h4>{f.title}</h4>
      <p>{f.detail}</p>
      {f.suggested_fix && (
        <p className="fix">
          <b>How to fix:</b> {f.suggested_fix}
        </p>
      )}
      {f.note && <p className="decision-note"><b>Your reason:</b> {f.note}</p>}
      {fix && <pre className="draft">{fix}</pre>}
      <div className="finding-actions">
        {f.evidence?.length > 0 && (
          <button className="btn quiet" onClick={() => onEvidence(f)}>
            View evidence ({[...new Set(f.evidence.map((e) => label(e.doc_type)))].join(", ")})
          </button>
        )}
        {f.kind !== "lc_risk" && <button className="btn quiet" onClick={draft}>Draft the fix</button>}
        <Decision f={f} kase={kase} run={run} setKase={setKase} />
      </div>
      <History f={f} />
    </article>
  );
}

export function DiffBanner({ report }) {
  const d = report?.diff;
  if (!d || !d.previous_run) return null;
  return (
    <div className="diff" role="status">
      <b>Run {report.run} compared with run {d.previous_run}:</b>
      <span className={d.resolved.length ? "d-res" : ""}>{d.resolved.length} resolved</span>
      <span className={d.new.length ? "d-new" : ""}>{d.new.length} new</span>
      <span>{d.still_open} still present</span>
      {d.carried > 0 && <span>{d.carried} decision(s) kept</span>}
      {d.resolved.length > 0 && <span className="d-list">Resolved: {d.resolved.join("; ")}</span>}
    </div>
  );
}

export function Report({ report, ...rest }) {
  if (!report) return null;
  const open = report.findings.filter((f) => f.status === "open");
  const tone = report.findings.length === 0 ? "ok" : open.some((f) => f.severity === "high") ? "bad" : open.length ? "warn" : "ok";
  return (
    <div className="report">
      <DiffBanner report={report} />
      <div className={`summary summary-${tone}`}>
        <b>{report.findings.length === 0 ? "No issues found" : open.length ? `${open.length} open item(s)` : "Nothing open"}</b>
        <span>{report.summary}</span>
      </div>
      {report.findings.map((f) => (
        <FindingCard key={f.id} f={f} {...rest} />
      ))}
      <details className="checks">
        <summary>{report.checks_run.length} checks performed</summary>
        <ul>{report.checks_run.map((c) => <li key={c}>{c}</li>)}</ul>
      </details>
    </div>
  );
}
