import { useState } from "react";

export default function Dropzone({ onFile, title, sub, compact }) {
  const [over, setOver] = useState(false);
  return (
    <label
      className={`drop ${over ? "over" : ""} ${compact ? "compact" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); e.dataTransfer.files[0] && onFile(e.dataTransfer.files[0]); }}
    >
      <input type="file" accept=".pdf,image/*" onChange={(e) => e.target.files[0] && onFile(e.target.files[0])} />
      <span className="drop-title">{title}</span>
      {sub && <span className="drop-sub">{sub}</span>}
    </label>
  );
}
