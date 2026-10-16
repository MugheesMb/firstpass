const KIND = { case: "Case", upload: "Upload", check: "Check", decision: "Decision", draft: "Draft" };

export default function ActivityView({ kase }) {
  if (!kase) return null;
  const events = [...(kase.events || [])].reverse();
  const days = [];
  for (const e of events) {
    const d = new Date(e.at).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
    if (!days.length || days[days.length - 1][0] !== d) days.push([d, []]);
    days[days.length - 1][1].push(e);
  }
  return (
    <div className="step-body">
      {days.length === 0 && <p className="muted">Nothing has happened on this case yet.</p>}
      {days.map(([d, list]) => (
        <section key={d} className="panel">
          <h2>{d}</h2>
          <ol className="log">
            {list.map((e, i) => (
              <li key={i} className={`k-${e.kind}`}>
                <time dateTime={e.at}>{new Date(e.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
                <span className="log-kind">{KIND[e.kind] || e.kind}</span>
                <span className="log-text">{e.text}</span>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
