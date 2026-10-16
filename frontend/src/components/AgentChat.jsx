import { useState } from "react";
import { api } from "../api.js";

export default function AgentChat({ kase }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState([
    { who: "bot", text: "Ask me about this LC or your documents, e.g. “What should I fix first?”" },
  ]);
  const [text, setText] = useState("");
  const [sid, setSid] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(e) {
    e.preventDefault();
    if (!text.trim()) return;
    const q = text;
    setText("");
    setMsgs((m) => [...m, { who: "me", text: q }]);
    setBusy(true);
    try {
      const r = await api.agent(q, kase.id, sid);
      setSid(r.session_id);
      setMsgs((m) => [...m, { who: "bot", text: r.reply || "(no answer)" }]);
    } catch (err) {
      setMsgs((m) => [...m, { who: "bot", text: `Error: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return <button className="chat-fab" onClick={() => setOpen(true)}>Ask FirstPass</button>;
  return (
    <div className="chat">
      <div className="chat-head">
        <b>FirstPass assistant</b>
        <button className="btn ghost" onClick={() => setOpen(false)}>✕</button>
      </div>
      <div className="chat-body">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.who}`}>{m.text}</div>
        ))}
        {busy && <div className="msg bot">…</div>}
      </div>
      <form onSubmit={send} className="chat-input">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a question" />
        <button className="btn primary" disabled={busy}>Send</button>
      </form>
    </div>
  );
}
