// Thin client for the FirstPass API. All paths are relative (/api/...): Vite proxies them in
// development and Firebase Hosting rewrites them to Cloud Run in production.
// VITE_API_BASE = the Cloud Run URL in production (calls go straight to Cloud Run: no 60-second
// Firebase Hosting limit). Empty in development, where Vite proxies /api to localhost:8080.
const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

async function call(method, path, body, isForm = false) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(`${BASE}/api${path}`, opts);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      msg = (await res.json()).detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  health: () => call("GET", "/health"),
  demos: () => call("GET", "/demo"),
  loadDemo: (name) => call("POST", `/demo/${name}`),
  newCase: (body) => call("POST", "/cases", body),
  getCase: (id) => call("GET", `/cases/${id}`),
  updateCase: (id, body) => call("PATCH", `/cases/${id}`, body),
  upload: (id, file, docType) => {
    const fd = new FormData();
    fd.append("file", file);
    if (docType) fd.append("doc_type", docType);
    return call("POST", `/cases/${id}/documents`, fd, true);
  },
  insights: (id) => call("GET", `/cases/${id}/insights`),
  lcReview: (id) => call("POST", `/cases/${id}/lc-review`),
  check: (id, presentation_date) => call("POST", `/cases/${id}/check`, { presentation_date: presentation_date || null }),
  cases: () => call("GET", "/cases"),
  setStatus: (id, fid, status, note) => call("PATCH", `/cases/${id}/findings/${fid}`, { status, note: note || null }),
  sampleCorrections: (id) => call("GET", `/cases/${id}/sample-corrections`),
  applySampleCorrection: (id, t) => call("POST", `/cases/${id}/sample-corrections/${t}`),
  waiverRequest: (id) => call("POST", `/cases/${id}/waiver-request`),
  draftFix: (id, fid) => call("POST", `/cases/${id}/findings/${fid}/draft-fix`),
  amendmentEmail: (id) => call("POST", `/cases/${id}/amendment-email`),
  agent: (message, case_id, session_id) => call("POST", "/agent", { message, case_id, session_id }),
  pageUrl: (caseId, docId, page) => `${BASE}/api/cases/${caseId}/documents/${docId}/pages/${page}.png`,
};

export const DOC_TYPES = [
  ["commercial_invoice", "Commercial invoice"],
  ["bill_of_lading", "Bill of lading"],
  ["packing_list", "Packing list"],
  ["certificate_of_origin", "Certificate of origin"],
  ["insurance_certificate", "Insurance certificate"],
];

export const SHORT = {
  letter_of_credit: "LC",
  commercial_invoice: "Invoice",
  bill_of_lading: "Bill of lading",
  packing_list: "Packing list",
  certificate_of_origin: "Origin cert.",
  insurance_certificate: "Insurance",
};

export const label = (t) =>
  t === "letter_of_credit" ? "Letter of Credit" : (DOC_TYPES.find(([k]) => k === t) || [t, t.replaceAll("_", " ")])[1];

export const when = (iso) =>
  iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
