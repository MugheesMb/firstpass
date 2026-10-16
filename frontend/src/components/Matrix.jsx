import { SHORT } from "../api.js";

// Cross-document consistency grid. The LC column is the standard; every other column is
// compared against it. Issue marks come from open findings, so the grid and the list agree.
const show = (v) => (/^\d{6}$/.test(v || "") ? `${v.slice(4)}/${v.slice(2, 4)}/20${v.slice(0, 2)}` : v);

export default function Matrix({ matrix, findings, onEvidence }) {
  if (!matrix) return null;
  const byId = Object.fromEntries((findings || []).map((f) => [f.id, f]));
  return (
    <div className="matrix-wrap">
      <table className="matrix">
        <colgroup><col className="label-col" />{matrix.columns.map((c) => <col key={c} />)}</colgroup>
        <thead>
          <tr>
            <th scope="col">Field</th>
            {matrix.columns.map((c) => (
              <th key={c} scope="col" className={c === "letter_of_credit" ? "ref-col" : ""}>{SHORT[c]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.rows.map((r) => (
            <tr key={r.label}>
              <th scope="row">{r.label}</th>
              {matrix.columns.map((c) => {
                const cell = r.cells[c];
                const f = cell.findings?.length ? byId[cell.findings[0]] : null;
                if (cell.status === "n/a") return <td key={c} className="na" aria-label="Not applicable" />;
                if (cell.status === "missing") return <td key={c} className="missing">Not uploaded</td>;
                if (cell.status === "not required") return <td key={c} className="missing">Not required</td>;
                return (
                  <td key={c} className={c === "letter_of_credit" ? `reference ${cell.status === "issue" ? "ref-flag" : ""}` : cell.status}
                      title={cell.value || ""}>
                    {cell.status === "issue" && c !== "letter_of_credit" ? (
                      <button className="stamp" onClick={() => f && onEvidence(f)} title={f ? f.title : "Issue"}>
                        <span className="stamp-mark">✕</span>
                        <span className="cell-val">{show(cell.value) || "missing"}</span>
                      </button>
                    ) : (
                      <span className="cell-in">
                        {cell.status === "ok" && <span className="tick" aria-label="Consistent">✓</span>}
                        <span className="cell-val">{show(cell.value) || "blank"}</span>
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
