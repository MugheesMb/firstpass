import { useEffect, useState } from "react";
import { api, when } from "../api.js";

function expiryText(days) {
  if (days == null) return "";
  if (days < 0) return `expired ${-days} day${days === -1 ? "" : "s"} ago`;
  if (days === 0) return "expires today";
  return `in ${days} day${days === 1 ? "" : "s"}`;
}
const fmtDate = (iso) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");

export default function CasesView({ run, openCase, newCase, kase }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    api.cases().then(setRows).catch(() => setRows([]));
  }, [kase?.updated_at]);

  async function open(id) {
    const c = await run("Opening case", () => api.getCase(id));
    if (c) openCase(c);
  }

  if (!rows) return <p className="muted">Loading cases…</p>;
  const openTotal = rows.reduce((n, r) => n + r.counts.open, 0);
  const soon = rows.filter((r) => r.days_to_expiry != null && r.days_to_expiry >= 0 && r.days_to_expiry <= 14).length;

  return (
    <div className="step-body">
      <div className="actions">
        <button className="btn primary" onClick={newCase}>Start a new case</button>
        {rows.length > 0 && (
          <p className="muted inline-note">
            {rows.length} case{rows.length === 1 ? "" : "s"}, {openTotal} open issue{openTotal === 1 ? "" : "s"}
            {soon ? `, ${soon} LC${soon === 1 ? "" : "s"} expiring within 14 days` : ""}.
          </p>
        )}
      </div>

      {rows.length === 0 ? (
        <section className="panel empty">
          <h2>No cases yet</h2>
          <p>Start a case when a buyer's bank issues a Letter of Credit, or open a sample case to see how FirstPass works.</p>
          <button className="btn" onClick={newCase}>Open a sample case</button>
        </section>
      ) : (
        <section className="panel flush">
          <table className="cases dash">
            <thead>
              <tr>
                <th scope="col">Exporter and credit</th>
                <th scope="col">Buyer</th>
                <th scope="col">Amount</th>
                <th scope="col">Expiry</th>
                <th scope="col">Stage</th>
                <th scope="col">Readiness</th>
                <th scope="col">Issues</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={kase?.id === r.id ? "current" : ""} onClick={() => open(r.id)} tabIndex={0}
                    onKeyDown={(e) => e.key === "Enter" && open(r.id)}>
                  <td>
                    <b>{r.company || "Unnamed exporter"}</b>
                    <span className="sub"><code>{r.lc_number || "LC not read yet"}</code></span>
                  </td>
                  <td>{r.applicant || ""}</td>
                  <td className="num">{r.amount || ""}</td>
                  <td>
                    <span className="nowrap">{fmtDate(r.expiry)}</span>
                    <span className={`sub ${r.days_to_expiry != null && r.days_to_expiry <= 7 ? "urgent" : ""}`}>{expiryText(r.days_to_expiry)}</span>
                  </td>
                  <td>{r.stage}<span className="sub">{r.runs} run{r.runs === 1 ? "" : "s"}</span></td>
                  <td>
                    {r.readiness == null ? <span className="muted">Not checked</span> : (
                      <span className={`ready ${r.readiness >= 80 ? "good" : r.readiness >= 50 ? "mid" : "bad"}`}>{r.readiness}</span>
                    )}
                  </td>
                  <td>
                    <span className="counts">
                      {r.counts.open > 0 && <span className="c-open">{r.counts.open} open</span>}
                      {r.counts.fixed > 0 && <span className="c-fixed">{r.counts.fixed} fixed</span>}
                      {r.counts.accepted > 0 && <span className="c-acc">{r.counts.accepted} accepted</span>}
                      {r.counts.disputed > 0 && <span className="c-dis">{r.counts.disputed} disputed</span>}
                      {!Object.values(r.counts).some(Boolean) && <span className="muted">None</span>}
                    </span>
                  </td>
                  <td className="muted">{when(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
