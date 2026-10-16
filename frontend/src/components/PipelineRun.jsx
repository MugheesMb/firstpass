import { useEffect, useState } from "react";

// While a check runs, the stages light up in order; when the result arrives, each stage shows
// the real counts and timings returned by the backend (report.trace).
const STAGES = ["Read documents", "Normalise values", "Apply rules", "AI judgement", "Explain findings"];

export default function PipelineRun({ running, trace }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!running) return;
    setTick(0);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const id = setInterval(() => setTick((t) => Math.min(t + 1, STAGES.length - 1)), 650);
    return () => clearInterval(id);
  }, [running]);

  if (!running && !trace?.length) return null;
  const rows = running ? STAGES.map((s) => ({ stage: s })) : trace;
  return (
    <ol className={`pipeline ${running ? "running" : "finished"}`} aria-live="polite">
      {rows.map((r, i) => {
        const state = running ? (i < tick ? "done" : i === tick ? "active" : "wait") : "done";
        return (
          <li key={r.stage} className={state}>
            <span className="p-node" />
            <span className="p-name">{r.stage}</span>
            <span className="p-detail">
              {running ? (state === "active" ? "working" : state === "done" ? "done" : "") : r.detail}
              {!running && r.model && <em> using {r.model}</em>}
            </span>
            {!running && <span className="p-ms">{r.ms >= 1000 ? `${(r.ms / 1000).toFixed(1)} s` : `${Math.round(r.ms)} ms`}</span>}
          </li>
        );
      })}
    </ol>
  );
}
