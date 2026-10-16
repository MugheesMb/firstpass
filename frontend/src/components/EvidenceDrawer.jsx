import { useEffect, useState } from "react";
import { api, label } from "../api.js";

// Shows the page each value came from, with the value highlighted.
// box_2d is [ymin, xmin, ymax, xmax] normalised to 0-1000 (Gemini's convention).
export default function EvidenceDrawer({ kase, finding, onClose }) {
  const [i, setI] = useState(0);
  useEffect(() => setI(0), [finding.id]);
  const ev = finding.evidence[i];
  const doc = kase.documents.find((d) => d.id === ev?.doc_id);

  return (
    <aside className="drawer">
      <div className="drawer-head">
        <div>
          <div className="muted">Evidence</div>
          <b>{finding.title}</b>
        </div>
        <button className="btn quiet" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="tabs">
        {finding.evidence.map((e, k) => (
          <button key={k} className={k === i ? "on" : ""} onClick={() => setI(k)}>
            {label(e.doc_type)}: {e.field.replaceAll("_", " ")}
          </button>
        ))}
      </div>
      {ev && (
        <>
          <p className="ev-value">
            <span className="muted">Value read:</span> {ev.value ?? "—"}
          </p>
          {doc ? (
            <div className="page">
              <img src={api.pageUrl(kase.id, doc.id, ev.page || 1)} alt={`${label(ev.doc_type)} page ${ev.page || 1}`} />
              {ev.box_2d && (
                <div
                  className="hl"
                  style={{
                    top: `${ev.box_2d[0] / 10}%`,
                    left: `${ev.box_2d[1] / 10}%`,
                    height: `${(ev.box_2d[2] - ev.box_2d[0]) / 10}%`,
                    width: `${(ev.box_2d[3] - ev.box_2d[1]) / 10}%`,
                  }}
                />
              )}
            </div>
          ) : (
            <p className="muted">Document not available.</p>
          )}
        </>
      )}
    </aside>
  );
}
