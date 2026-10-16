import { useEffect, useState } from "react";
import { api } from "../api.js";

const DEMO_INFO = {
  demo_faisalabad_towels: {
    title: "Bath towels, Faisalabad to Rotterdam",
    text: "Two risky LC terms. After shipment: late on board, invoice 3% over the credit, goods described differently.",
  },
  demo_sialkot_footballs: {
    title: "Footballs, Sialkot to Singapore",
    text: "LC expires in Singapore. After shipment: insurance dated late, wrong port of loading, package counts disagree.",
  },
  demo_clean: {
    title: "Cashew nuts, Ho Chi Minh City to Singapore",
    text: "A clean presentation from a Vietnamese exporter, to show what a pass looks like.",
  },
};

function Problems({ d }) {
  if (!d.document_problems.length && !d.lc_problems.length) return <span className="pchips"><span className="pchip clean">clean</span></span>;
  return (
    <span className="pchips">
      {d.lc_problems.map((p) => <span key={"l" + p} className="pchip lc" title="LC term risk">{p}</span>)}
      {d.document_problems.map((p) => <span key={"d" + p} className="pchip doc" title="Document discrepancy">{p}</span>)}
    </span>
  );
}

export default function StepProfile({ kase, setKase, run, demos, next, newCase, health }) {
  const [company, setCompany] = useState("");
  const [ready, setReady] = useState("");
  const [filter, setFilter] = useState("");
  const featured = demos.filter((d) => d.group === "demo");
  const testset = demos.filter((d) => d.group !== "demo");
  const problems = [...new Set(testset.flatMap((d) => [...d.document_problems, ...d.lc_problems]))].sort();
  const shown = testset.filter((d) =>
    !filter ? true : filter === "__clean" ? !d.document_problems.length && !d.lc_problems.length
      : [...d.document_problems, ...d.lc_problems].includes(filter));
  useEffect(() => {
    setCompany(kase?.company_name || "");
    setReady(kase?.goods_ready_date || "");
  }, [kase?.id]);

  async function save(e) {
    e.preventDefault();
    const body = { company_name: company || null, goods_ready_date: ready || null };
    const c = await run("Saving profile", () => (kase ? api.updateCase(kase.id, body) : api.newCase(body)));
    if (c) {
      setKase(c);
      next();
    }
  }

  async function demo(name) {
    const label = health?.ai_mode === "gemini"
      ? "Gemini is reading the 6 documents of this case (up to a minute the first time, seconds after that)"
      : "Loading sample case";
    const c = await run(label, () => api.loadDemo(name));
    if (c) {
      setKase(c);
      next();
    }
  }

  return (
    <div className="step-body">
      {kase && (
        <div className="panel editing">
          <p>
            You are editing the open case for <strong>{kase.company_name || "an unnamed exporter"}</strong>.
            Changes here update that case.
          </p>
          <button type="button" className="btn" onClick={newCase}>Start a different case</button>
        </div>
      )}
      <form className="panel form" onSubmit={save}>
        <label>
          <span>Company name, exactly as registered</span>
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Example Exports (Pvt) Ltd" required />
          <small>FirstPass checks the LC beneficiary name against this.</small>
        </label>
        <label>
          <span>Date the goods will be ready to ship</span>
          <input type="date" value={ready} onChange={(e) => setReady(e.target.value)} />
          <small>Used to test whether the latest shipment date is realistic.</small>
        </label>
        <div className="actions">
          <button className="btn primary">{kase ? "Save and continue" : "Start a new case"}</button>
        </div>
      </form>

      {featured.length > 0 && (
        <section className="demos">
          <h2>{kase ? "Or open a different sample case" : "Or open a sample case"}</h2>
          <p className="muted">Fictional exporters and banks, with realistic documents and planted problems.</p>
          <div className="demo-list">
            {featured.map((d) => (
              <button key={d.name} className="demo" onClick={() => demo(d.name)}>
                <span className="demo-title">{DEMO_INFO[d.name]?.title || d.name}</span>
                <span className="demo-text">{DEMO_INFO[d.name]?.text}</span>
                <Problems d={d} />
                <span className="demo-go">Open case</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {testset.length > 0 && (
        <section className="panel testset">
          <div className="panel-head">
            <h2>Test set: {testset.length} generated cases</h2>
            <p className="muted">
              {testset.filter((d) => !d.document_problems.length).length} clean, the rest with one to three planted
              problems. Use these to see every kind of discrepancy, and to check for false alarms on clean cases.
            </p>
          </div>
          <div className="filter">
            <label>
              <span>Show</span>
              <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                <option value="">All cases</option>
                <option value="__clean">Clean cases only</option>
                {problems.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          </div>
          <table className="cases">
            <thead>
              <tr><th scope="col">Case</th><th scope="col">Goods and terms</th><th scope="col">Planted problems</th><th /></tr>
            </thead>
            <tbody>
              {shown.map((d) => (
                <tr key={d.name}>
                  <td><code>{d.name}</code></td>
                  <td>{d.goods}, {d.incoterm}</td>
                  <td><Problems d={d} /></td>
                  <td><button className="btn small" onClick={() => demo(d.name)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
