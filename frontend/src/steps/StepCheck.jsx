import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Report } from "../components/FindingCard.jsx";
import PipelineRun from "../components/PipelineRun.jsx";

export default function StepCheck({ kase, setKase, run, onEvidence, next }) {
  const [pres, setPres] = useState("");
  const [running, setRunning] = useState(false);
  useEffect(() => setPres(kase?.presentation_date || ""), [kase?.id]);

  async function check() {
    setRunning(true);
    const started = Date.now();
    const r = await run("Running the compliance check", () => api.check(kase.id, pres));
    // let the stage sequence finish visibly even when the backend is very fast (mock mode)
    const wait = Math.max(0, 2600 - (Date.now() - started));
    if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) await new Promise((res) => setTimeout(res, wait));
    setRunning(false);
    if (r) setKase(await api.getCase(kase.id));
  }

  const docs = kase?.documents.length || 0;
  return (
    <div className="step-body">
      <section className="panel form inline">
        <label>
          <span>Date you plan to present documents to the bank</span>
          <input type="date" value={pres} onChange={(e) => setPres(e.target.value)} />
          <small>Checked against the presentation period and the LC expiry.</small>
        </label>
        <button className="btn primary big" onClick={check} disabled={running || !docs}>
          {kase?.document_check ? "Run the check again" : `Check ${docs} documents`}
        </button>
      </section>

      <PipelineRun running={running} trace={!running && kase?.document_check?.trace} />
      {!running && <Report report={kase?.document_check} kase={kase} run={run} setKase={setKase} onEvidence={onEvidence} />}
      {!running && kase?.document_check && (
        <div className="actions"><button className="btn primary" onClick={next}>Open the examiner's report</button></div>
      )}
    </div>
  );
}
