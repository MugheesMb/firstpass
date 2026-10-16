// A ruled date scale: LC limits, your plans and what actually happened, on one line.
const fmt = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export default function Timeline({ points }) {
  if (!points || points.length < 2) return null;
  const t = (p) => new Date(p.date + "T00:00:00").getTime();
  const min = t(points[0]);
  const max = t(points[points.length - 1]);
  const span = Math.max(max - min, 86400000);
  const pos = (p) => 2 + ((t(p) - min) / span) * 96;
  // lanes: 0 below, 1 above, 2 further below, 3 further above; a label needs ~13% of width
  const lanes = [];
  const laneOf = points.map((p) => {
    const x = pos(p);
    let l = [0, 1, 2, 3].find((k) => lanes[k] === undefined || x - lanes[k] > 13);
    if (l === undefined) l = 0;
    lanes[l] = x;
    return l;
  });
  const by = Object.fromEntries(points.map((p) => [p.key, p]));
  const late = by.shipped && by.latest_shipment && by.shipped.date > by.latest_shipment.date;
  const overdue = by.presentation && by.deadline && by.presentation.date > by.deadline.date;
  const band = (a, b, cls) =>
    by[a] && by[b] && (
      <div className={`tl-band ${cls}`} style={{ left: `${pos(by[a])}%`, width: `${Math.max(pos(by[b]) - pos(by[a]), 0.6)}%` }} />
    );

  return (
    <figure className="timeline" aria-label="Key dates">
      <div className="tl-track">
        {band("lc_issued", "latest_shipment", "ship-window")}
        {band("shipped", "deadline", "present-window")}
        {late && band("latest_shipment", "shipped", "breach")}
        {overdue && band("deadline", "presentation", "breach")}
        {points.map((p, i) => {
          const bad = (p.key === "shipped" && late) || (p.key === "presentation" && overdue);
          return (
            <div key={p.key} className={`tl-pin ${p.kind} ${bad ? "bad" : ""} lane-${laneOf[i]}`} style={{ left: `${pos(p)}%` }}>
              <span className="tl-dot" />
              <span className="tl-label">
                <b>{fmt(p.date)}</b>
                {p.label}
              </span>
            </div>
          );
        })}
      </div>
      <figcaption>
        <span className="key ship-window" /> Shipment window
        <span className="key present-window" /> Presentation window
        {(late || overdue) && (<><span className="key breach" /> Outside the LC terms</>)}
      </figcaption>
      <ul className="tl-list">
        {points.map((p) => <li key={p.key}><b>{fmt(p.date)}</b> {p.label}</li>)}
      </ul>
    </figure>
  );
}
