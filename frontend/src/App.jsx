import { useEffect, useState } from "react";
import { api } from "./api.js";
import StepProfile from "./steps/StepProfile.jsx";
import StepReadLc from "./steps/StepReadLc.jsx";
import StepTerms from "./steps/StepTerms.jsx";
import StepDocs from "./steps/StepDocs.jsx";
import StepCheck from "./steps/StepCheck.jsx";
import StepReport from "./steps/StepReport.jsx";
import EvidenceDrawer from "./components/EvidenceDrawer.jsx";
import AgentChat from "./components/AgentChat.jsx";
import CasesView from "./views/CasesView.jsx";
import IssuesView from "./views/IssuesView.jsx";
import ActivityView from "./views/ActivityView.jsx";

const VIEWS = {
  cases: { title: "Your cases", hint: "Every Letter of Credit you are working on, with what is still open", C: CasesView },
  issues: { title: "Issues board", hint: "Every finding on this case, by what you decided to do about it", C: IssuesView },
  activity: { title: "Activity log", hint: "Uploads, checks and decisions on this case, with times", C: ActivityView },
};

const STEPS = [
  { title: "Exporter profile", hint: "Who is presenting, and when goods are ready", C: StepProfile },
  { title: "Read the Letter of Credit", hint: "Gemini reads every MT700 field and where it sits on the page", C: StepReadLc },
  { title: "Review LC terms", hint: "Find risky terms while one email to the buyer can still fix them", C: StepTerms },
  { title: "Add shipping documents", hint: "Invoice, bill of lading, packing list, origin and insurance", C: StepDocs },
  { title: "Run the compliance check", hint: "Every document against the LC, and against each other", C: StepCheck },
  { title: "Examiner's report", hint: "What a bank checker would see, before they see it", C: StepReport },
];

function progress(k) {
  if (!k) return [false, false, false, false, false, false];
  const lc = k.documents.some((d) => d.doc_type === "letter_of_credit");
  const docs = k.documents.filter((d) => d.doc_type !== "letter_of_credit").length;
  return [!!k.company_name, lc, !!k.lc_review, docs > 0, !!k.document_check, !!k.document_check];
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [demos, setDemos] = useState([]);
  const [kase, setKase] = useState(null);
  const [step, setStep] = useState(0);
  const [view, setView] = useState("cases"); // "cases" | "step" | "issues" | "activity"
  const [evidence, setEvidence] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }));
    api.demos().then(setDemos).catch(() => {});
  }, []);
  useEffect(() => setEvidence(null), [step, view]);

  async function run(label, fn) {
    setBusy(label);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  const done = progress(kase);
  const reachable = (i) => i === 0 || (kase && (i <= 3 ? done[i - 1] || done[i] : i === 4 ? done[1] : done[4]));
  const S = view === "step" ? STEPS[step] : VIEWS[view];
  const goto = (i) => { setView("step"); setStep(i); };
  const openCase = (c) => { setKase(c); goto(c.document_check ? 5 : c.lc_review ? 3 : c.documents.length ? 1 : 0); };
  const shared = { kase, setKase, run, busy, demos, health, onEvidence: setEvidence, next: () => goto(step + 1), goto,
                   openCase, setView, newCase: () => { setKase(null); goto(0); } };
  const open = kase ? [kase.lc_review, kase.document_check].flatMap((r) => r?.findings || []).filter((f) => f.status === "open").length : 0;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-brand">
          <span className="mark" aria-hidden="true">
            <svg viewBox="0 0 32 32"><path d="M8 17l5 5 11-12" /></svg>
          </span>
          <div>
            <div className="wordmark">FirstPass</div>
            <div className="rail-tag">Letter of Credit checks, before the bank does</div>
          </div>
        </div>

        <nav className="rail-nav" aria-label="Workspace">
          <button className={view === "cases" ? "on" : ""} onClick={() => setView("cases")}>All cases</button>
          {kase && (
            <>
              <button className={view === "issues" ? "on" : ""} onClick={() => setView("issues")}>
                Issues board {open > 0 && <span className="badge">{open}</span>}
              </button>
              <button className={view === "activity" ? "on" : ""} onClick={() => setView("activity")}>Activity log</button>
            </>
          )}
        </nav>

        <ol className={`route ${view !== "step" ? "dim" : ""}`}>
          {STEPS.map((s, i) => (
            <li key={s.title} className={`${view === "step" && i === step ? "here" : ""} ${done[i] ? "done" : ""}`}>
              <button onClick={() => reachable(i) && goto(i)} disabled={!reachable(i)} aria-current={view === "step" && i === step ? "step" : undefined}>
                <span className="node">{done[i] ? "✓" : i + 1}</span>
                <span className="route-text">
                  <span className="route-title">{s.title}</span>
                  <span className="route-hint">{s.hint}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>

        <div className="rail-foot">
          {kase ? (
            <div className="case-tag">
              <span>Case <code>{kase.id}</code></span>
              <span>{kase.company_name || "No company yet"}</span>
            </div>
          ) : (
            <div className="case-tag"><span>No case open</span></div>
          )}
          {health && (
            <span className={`mode ${health.ai_mode === "gemini" ? "live" : ""}`}>
              {health.ok === false ? "API offline" : health.ai_mode === "gemini" ? "Gemini live" : "Mock mode, offline"}
              <small>
                {health.ai_mode === "gemini" ? `Reads with ${health.model_extract}, judges with ${health.model_reason}` : "Extraction uses ground-truth files"}
              </small>
            </span>
          )}
        </div>
      </aside>

      <div className={`stage ${evidence ? "with-drawer" : ""}`}>
        <div className="stage-main">
          <header className="stage-head">
            <span className="count">
              {view === "step" ? `Step ${step + 1} of ${STEPS.length}` : view === "cases" ? "Workspace" : kase?.company_name || "This case"}
            </span>
            <h1>{S.title}</h1>
            <p>{S.hint}.</p>
          </header>
          {error && <div className="alert" role="alert">{error}</div>}
          {busy && <div className="toast" role="status"><span className="spinner" /> {busy}</div>}
          <S.C {...shared} />
          <footer className="legal">
            FirstPass flags likely discrepancies under ICC UCP 600. It does not decide whether a bank will pay; confirm
            disputed points with your bank. Demo cases use fictional companies.
          </footer>
        </div>
        {evidence && kase && <EvidenceDrawer kase={kase} finding={evidence} onClose={() => setEvidence(null)} />}
      </div>

      {health?.ai_mode === "gemini" && kase && <AgentChat kase={kase} />}
    </div>
  );
}
