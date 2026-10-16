import { useEffect, useState } from "react";
import { api, DOC_TYPES, label } from "../api.js";
import Dropzone from "../components/Dropzone.jsx";
import { evidenceFor, ExtractionStats } from "./StepReadLc.jsx";

const nice = (k) => k.replaceAll("_", " ").replace(/\bkg\b/, "(kg)").replace(/\blc\b/, "LC").replace(/\bbl\b/, "B/L").replace(/^./, (c) => c.toUpperCase());

export default function StepDocs({ kase, setKase, run, onEvidence, next }) {
  const [openType, setOpenType] = useState(null);
  const [fixes, setFixes] = useState([]);
  useEffect(() => {
    if (kase?.source) api.sampleCorrections(kase.id).then(setFixes).catch(() => setFixes([]));
    else setFixes([]);
  }, [kase?.id]);

  async function useFix(t) {
    const d = await run(`Uploading the corrected ${label(t).toLowerCase()}`, () => api.applySampleCorrection(kase.id, t));
    if (d) {
      setKase(await api.getCase(kase.id));
      setOpenType(t);
    }
  }
  const byType = Object.fromEntries((kase?.documents || []).map((d) => [d.doc_type, d]));
  const count = DOC_TYPES.filter(([t]) => byType[t]).length;
  const required = byType.letter_of_credit?.data.documents_required || [];

  async function upload(type, file) {
    const d = await run(`Gemini is reading the ${type.replaceAll("_", " ")}`, () => api.upload(kase.id, file, type));
    if (d) {
      setKase(await api.getCase(kase.id));
      setOpenType(type);
    }
  }

  return (
    <div className="step-body">
      {required.length > 0 && (
        <section className="panel required">
          <h2>The LC asks for</h2>
          <ol>{required.map((r, i) => <li key={i}>{r}</li>)}</ol>
        </section>
      )}

      {fixes.length > 0 && (
        <section className="panel corrections">
          <h2>Corrected documents for this sample</h2>
          <p className="muted">
            After the first check, upload a corrected document and run the check again: fixed problems move to
            "Resolved by re-check" on the issues board.
          </p>
          <ul>
            {fixes.map((f) => {
              const d = byType[f.doc_type];
              const used = d && d.filename.includes("_corrected");
              return (
                <li key={f.doc_type}>
                  <span><b>{label(f.doc_type)}</b>: {f.fixes}</span>
                  <button className="btn small" onClick={() => useFix(f.doc_type)} disabled={used}>
                    {used ? `Uploaded as version ${d.version}` : "Upload corrected version"}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="sheets">
        {DOC_TYPES.map(([type, name]) => {
          const d = byType[type];
          const fields = d ? Object.entries(d.data).filter(([k, v]) => !["evidence", "unreadable_fields"].includes(k) && v != null && v !== "" && !(Array.isArray(v) && !v.length)) : [];
          return (
            <article key={type} className={`sheet ${d ? "has" : ""}`}>
              <header>
                <h3>{name}</h3>
                {d && <span className="ok-mark">Read</span>}
              </header>
              {d ? (
                <>
                  <p className="sheet-file">{d.filename}{d.version > 1 ? `, version ${d.version}` : ""}</p>
                  <ExtractionStats x={d.extraction} />
                  {d.extraction?.low_confidence?.length > 0 && (
                    <p className="warn-text">Check by hand: {d.extraction.low_confidence.map(nice).join(", ")}</p>
                  )}
                  <div className="sheet-actions">
                    <button className="btn quiet" onClick={() => setOpenType(openType === type ? null : type)} aria-expanded={openType === type}>
                      {openType === type ? "Hide fields" : `Show ${fields.length} fields`}
                    </button>
                    <Dropzone compact onFile={(f) => upload(type, f)} title="Replace" />
                  </div>
                  {openType === type && (
                    <dl className="kv">
                      {fields.map(([k, v]) => (
                        <div key={k} onClick={() => onEvidence(evidenceFor(d, k, `${name}: ${nice(k)}`))}>
                          <dt>{nice(k)}</dt>
                          <dd>{typeof v === "boolean" ? (v ? "Yes" : "No") : Array.isArray(v) ? v.join("; ") : String(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </>
              ) : (
                <Dropzone onFile={(f) => upload(type, f)} title="Add this document" sub="PDF or photo" />
              )}
            </article>
          );
        })}
      </div>

      <div className="actions">
        <button className="btn primary" onClick={next} disabled={!count}>
          {count ? `Continue with ${count} of 5 documents` : "Add at least one document"}
        </button>
      </div>
    </div>
  );
}
