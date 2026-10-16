import { api } from "../api.js";
import Dropzone from "../components/Dropzone.jsx";

// SWIFT MT700 field tags, so the extracted LC reads like the credit the exporter received.
export const LC_FIELDS = [
  [":20:", "lc_number", "Documentary credit number"],
  [":31C:", "issue_date", "Date of issue"],
  [":31D:", "expiry_date", "Date of expiry"],
  [":31D:", "expiry_place", "Place of expiry"],
  [":50:", "applicant", "Applicant"],
  [":59:", "beneficiary", "Beneficiary"],
  [":32B:", "amount", "Currency and amount"],
  [":39A:", "amount_tolerance_pct", "Amount tolerance"],
  [":43P:", "partial_shipments", "Partial shipments"],
  [":43T:", "transhipment", "Transhipment"],
  [":44E:", "port_of_loading", "Port of loading"],
  [":44F:", "port_of_discharge", "Port of discharge"],
  [":44C:", "latest_shipment_date", "Latest date of shipment"],
  [":45A:", "goods_description", "Description of goods"],
  [":45A:", "quantity", "Quantity"],
  [":45A:", "incoterm", "Trade terms"],
  [":45A:", "country_of_origin", "Origin"],
  [":46A:", "documents_required", "Documents required"],
  [":47A:", "additional_conditions", "Additional conditions"],
  [":48:", "presentation_days", "Period for presentation"],
];

export const swiftDate = (v) => (/^\d{6}$/.test(v || "") ? `${v.slice(4)}/${v.slice(2, 4)}/20${v.slice(0, 2)}` : v);

export function evidenceFor(doc, field, title) {
  const e = (doc.data.evidence || []).find((x) => x.field === field) || {};
  const v = doc.data[field];
  return {
    id: `${doc.id}-${field}`,
    title,
    evidence: [{ doc_id: doc.id, doc_type: doc.doc_type, field, value: Array.isArray(v) ? v.join(" | ") : v, page: e.page || 1, box_2d: e.box_2d }],
  };
}

export function ExtractionStats({ x }) {
  if (!x || !x.fields_total) return null;
  return (
    <dl className="xstats">
      <div><dt>Fields read</dt><dd>{x.fields_found} of {x.fields_total}</dd></div>
      <div><dt>Average confidence</dt><dd>{x.avg_confidence != null ? `${Math.round(x.avg_confidence * 100)}%` : "n/a"}</dd></div>
      <div><dt>Time</dt><dd>{x.ms >= 1000 ? `${(x.ms / 1000).toFixed(1)} s` : `${x.ms} ms`}</dd></div>
      <div><dt>Read by</dt><dd>{x.model}</dd></div>
    </dl>
  );
}

export default function StepReadLc({ kase, setKase, run, onEvidence, next }) {
  const lc = kase?.documents.find((d) => d.doc_type === "letter_of_credit");
  const conf = Object.fromEntries((lc?.data.evidence || []).map((e) => [e.field, e.confidence]));

  async function upload(file) {
    const d = await run("Gemini is reading the Letter of Credit", () => api.upload(kase.id, file, "letter_of_credit"));
    if (d) setKase(await api.getCase(kase.id));
  }

  return (
    <div className="step-body">
      <Dropzone onFile={upload} compact={!!lc}
                title={lc ? `Replace ${lc.filename}` : "Drop the Letter of Credit here, or choose a file"}
                sub={lc ? null : "PDF, scan or phone photo. SWIFT MT700 or bank letter format."} />
      {lc && (
        <section className="panel">
          <div className="panel-head">
            <h2>What Gemini read</h2>
            <ExtractionStats x={lc.extraction} />
          </div>
          <table className="fields">
            <tbody>
              {LC_FIELDS.filter(([, k]) => lc.data[k] != null && lc.data[k] !== "" && !(Array.isArray(lc.data[k]) && !lc.data[k].length)).map(([tag, k, l]) => {
                const v = lc.data[k];
                const c = conf[k];
                return (
                  <tr key={k} onClick={() => onEvidence(evidenceFor(lc, k, l))} tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && onEvidence(evidenceFor(lc, k, l))}>
                    <td className="tag"><code>{tag}</code></td>
                    <th scope="row">{l}</th>
                    <td className="val">
                      {Array.isArray(v) ? <ol>{v.map((x, i) => <li key={i}>{x}</li>)}</ol> : k.endsWith("date") ? swiftDate(v) : v}
                    </td>
                    <td className="conf">
                      {c != null && (
                        <span className={`meter ${c < 0.8 ? "low" : ""}`} title={`Confidence ${Math.round(c * 100)}%`}>
                          <span style={{ width: `${Math.round(c * 100)}%` }} />
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="muted">Select any field to see where it was read on the page.</p>
          <div className="actions"><button className="btn primary" onClick={next}>Continue to LC review</button></div>
        </section>
      )}
    </div>
  );
}
