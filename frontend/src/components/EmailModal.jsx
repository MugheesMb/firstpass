import { useState } from "react";

export default function EmailModal({ title, email, onClose }) {
  const [copied, setCopied] = useState(false);
  if (!email) return null;
  return (
    <div className="modal" onClick={onClose}>
      <div className="modal-box" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <p className="muted">Subject: {email.subject}</p>
        <pre className="draft">{email.body}</pre>
        <div className="actions">
          <button className="btn primary" onClick={() => { navigator.clipboard?.writeText(`${email.subject}\n\n${email.body}`); setCopied(true); }}>
            {copied ? "Copied" : "Copy email"}
          </button>
          <button className="btn quiet" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
