"""FirstPass API (FastAPI). Run locally: uvicorn app.main:app --reload --port 8080"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import insights as insights_mod, pipeline, storage
from .ai.judge import get_judge
from .config import settings
from .extraction import render
from .models import Case, CheckReport, DocType, FindingKind, FindingStatus, StoredDocument

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="FirstPass API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.allow_origins, allow_methods=["*"], allow_headers=["*"])


def _case(case_id: str) -> Case:
    case = storage.cases().get(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


class NewCase(BaseModel):
    company_name: Optional[str] = None
    goods_ready_date: Optional[str] = None


class CheckRequest(BaseModel):
    presentation_date: Optional[str] = None


class StatusUpdate(BaseModel):
    status: FindingStatus
    note: Optional[str] = None


@app.get("/api/health")
def health():
    return {"ok": True, "ai_mode": settings.ai_mode, "model_extract": settings.model_extract,
            "model_reason": settings.model_reason}


@app.post("/api/cases", response_model=Case)
def create_case(body: NewCase):
    return pipeline.new_case(body.company_name, body.goods_ready_date)


@app.get("/api/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    return _case(case_id)


@app.patch("/api/cases/{case_id}", response_model=Case)
def update_case(case_id: str, body: NewCase):
    case = _case(case_id)
    case.company_name = body.company_name or case.company_name
    case.goods_ready_date = body.goods_ready_date or case.goods_ready_date
    storage.cases().save(case)
    return case


@app.post("/api/cases/{case_id}/documents", response_model=StoredDocument)
async def upload(case_id: str, file: UploadFile = File(...), doc_type: Optional[str] = Form(None)):
    case = _case(case_id)
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "file too large (20 MB max)")
    t = DocType(doc_type) if doc_type else None
    return pipeline.add_document(case, data, file.filename or "upload.pdf", file.content_type, t)


@app.get("/api/cases/{case_id}/documents/{doc_id}/pages/{page}.png")
def page_image(case_id: str, doc_id: str, page: int):
    case = _case(case_id)
    doc = next((d for d in case.documents if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "document not found")
    data = storage.files().get(pipeline.file_key(case_id, doc_id, doc.filename))
    if data is None:
        raise HTTPException(404, "file missing")
    png = render.page_png(data, doc.filename, page)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/cases/{case_id}/insights")
def insights(case_id: str):
    """Consistency grid, date timeline and readiness score for the examiner's report."""
    return insights_mod.insights(_case(case_id))


@app.post("/api/cases/{case_id}/lc-review", response_model=CheckReport)
def lc_review(case_id: str):
    return pipeline.run_lc_review(_case(case_id))


@app.post("/api/cases/{case_id}/check", response_model=CheckReport)
def check(case_id: str, body: CheckRequest):
    return pipeline.run_document_check(_case(case_id), body.presentation_date)


@app.patch("/api/cases/{case_id}/findings/{finding_id}", response_model=Case)
def set_status(case_id: str, finding_id: str, body: StatusUpdate):
    case = _case(case_id)
    if body.status in (FindingStatus.ACCEPTED, FindingStatus.DISPUTED) and not (body.note or "").strip():
        raise HTTPException(400, "Give a short reason when you accept or dispute a finding")
    if not pipeline.set_finding_status(case, finding_id, body.status, (body.note or "").strip() or None):
        raise HTTPException(404, "finding not found")
    return case


@app.get("/api/cases")
def list_cases():
    """Cases dashboard."""
    return [insights_mod.case_summary(c) for c in storage.cases().list()]


@app.post("/api/cases/{case_id}/waiver-request")
def waiver_request(case_id: str):
    """Draft a request to the buyer to accept discrepancies that cannot be fixed (UCP 600 Art. 16(b))."""
    case = _case(case_id)
    items = pipeline.waiver_candidates(case)
    if not items:
        raise HTTPException(400, "Accept at least one discrepancy first: only accepted discrepancies go in a waiver request")
    lc = case.first(DocType.LC)
    draft = get_judge().waiver_request(lc.data if lc else {}, [json.loads(f.model_dump_json()) for f in items],
                                       case.company_name).model_dump()
    pipeline.log(case, "draft", f"Waiver request drafted for {len(items)} discrepancy(ies)")
    storage.cases().save(case)
    return draft


@app.post("/api/cases/{case_id}/findings/{finding_id}/draft-fix")
def draft_fix(case_id: str, finding_id: str):
    case = _case(case_id)
    f = next((f for rep in (case.lc_review, case.document_check) if rep for f in rep.findings if f.id == finding_id), None)
    if not f:
        raise HTTPException(404, "finding not found")
    involved = {e.doc_type.value for e in f.evidence}
    docs = {d.doc_type.value: {k: v for k, v in d.data.items() if k != "evidence"}
            for d in case.documents if d.doc_type.value in involved}
    text = get_judge().draft_fix(json.loads(f.model_dump_json()), docs)
    pipeline.log(case, "draft", f"Fix drafted: {f.title}")
    storage.cases().save(case)
    return {"text": text}


@app.post("/api/cases/{case_id}/amendment-email")
def amendment_email(case_id: str):
    case = _case(case_id)
    lc = case.first(DocType.LC)
    if not lc or not case.lc_review:
        raise HTTPException(400, "run the LC review first")
    risks = [json.loads(f.model_dump_json()) for f in case.lc_review.findings
             if f.kind == FindingKind.LC_RISK and f.status != FindingStatus.ACCEPTED]
    draft = get_judge().amendment_email(lc.data, risks, case.company_name).model_dump()
    pipeline.log(case, "draft", f"Amendment request drafted for {len(risks)} LC term(s)")
    storage.cases().save(case)
    return draft


def _case_dirs():
    """Sample cases: hand-picked demos first, then any generated test-set folders."""
    for group, root in [("demo", settings.demo_dir)] + [("test set", d) for d in settings.extra_case_dirs]:
        if root.exists():
            for p in sorted(root.iterdir()):
                if (p / "case.json").exists():
                    yield group, p


ERROR_LABELS = {
    "late_shipment": "shipped late", "late_presentation": "presented late", "expired": "LC expired",
    "amount_over": "invoice over LC amount", "currency": "wrong currency", "qty_mismatch_pl": "quantity mismatch",
    "packages_mismatch": "package count mismatch", "weight_mismatch": "weight mismatch",
    "description_invoice": "invoice description differs", "description_conflict_bl": "B/L description conflicts",
    "invoice_party": "invoice to wrong party", "port_pol": "wrong port of loading", "no_onboard": "no on-board notation",
    "claused": "claused B/L", "insurance_late": "insurance dated late", "insurance_under": "insurance under 110%",
    "missing_doc": "document missing", "origin": "wrong origin", "consignee": "wrong consignee",
    "incoterm": "trade term differs", "freight_collect": "freight collect", "lc_number": "wrong LC number",
    "soft_clause": "soft clause", "tight_timeline": "tight shipment date", "expiry_abroad": "expires abroad",
    "name_mismatch": "beneficiary name differs", "hard_doc": "hard-to-get document", "short_presentation": "short presentation period",
    "insurance_fob": "insurance under FOB", "expiry_squeeze": "early expiry",
}


@app.get("/api/demo")
def list_demos():
    out = []
    for group, p in _case_dirs():
        m = json.loads((p / "case.json").read_text())
        doc_err, lc_err = m.get("planted_document_errors", []), m.get("planted_lc_errors", [])
        out.append({"name": p.name, "group": group, "goods": m.get("goods"), "incoterm": m.get("incoterm"),
                    "document_problems": [ERROR_LABELS.get(e, e) for e in doc_err],
                    "lc_problems": [ERROR_LABELS.get(e, e) for e in lc_err],
                    "expected_rules": m.get("expected_document_rules", []) + m.get("expected_lc_rules", [])})
    return out


def _sample_dir(name: Optional[str]):
    return next((p for _, p in _case_dirs() if p.name == name), None) if name else None


@app.get("/api/cases/{case_id}/sample-corrections")
def sample_corrections(case_id: str):
    """Corrected documents shipped with a sample case, for showing the fix and re-check loop."""
    d = _sample_dir(_case(case_id).source)
    f = d / "corrections.json" if d else None
    return json.loads(f.read_text()) if f and f.exists() else []


@app.post("/api/cases/{case_id}/sample-corrections/{doc_type}", response_model=StoredDocument)
def apply_sample_correction(case_id: str, doc_type: str):
    case = _case(case_id)
    d = _sample_dir(case.source)
    item = next((c for c in sample_corrections(case_id) if c["doc_type"] == doc_type), None)
    if not d or not item:
        raise HTTPException(404, "no corrected sample for this document")
    pdf = d / item["file"]
    sidecar = json.loads((d / item["truth"]).read_text()) if not settings.use_gemini else None
    doc = pipeline.add_document(case, pdf.read_bytes(), f"{pdf.stem}_corrected.pdf", "application/pdf",
                                DocType(doc_type), sidecar)
    pipeline.log(case, "upload", f"Corrected sample used: {item['fixes']}")
    storage.cases().save(case)
    return doc


@app.post("/api/demo/{name}", response_model=Case)
def load_demo(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(404, "demo case not found")
    path = _sample_dir(name)
    if path is None:
        raise HTTPException(404, "demo case not found")
    return pipeline.load_demo_case(path)


# ---------------------------------------------------------------- ADK agent chat
class AgentMessage(BaseModel):
    message: str
    case_id: Optional[str] = None
    session_id: Optional[str] = None


_runner = None


@app.post("/api/agent")
async def agent_chat(body: AgentMessage):
    """Chat with the ADK agent. Needs AI_MODE=gemini (the agent itself runs on Gemini)."""
    if not settings.use_gemini:
        raise HTTPException(400, "The assistant needs AI_MODE=gemini")
    global _runner
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from firstpass_agent.agent import root_agent

    if _runner is None:
        _runner = InMemoryRunner(agent=root_agent, app_name="firstpass")
    sid = body.session_id
    if not sid:
        sid = (await _runner.session_service.create_session(app_name="firstpass", user_id="web")).id
    text = body.message if not body.case_id else f"[case_id: {body.case_id}] {body.message}"
    reply = ""
    async for event in _runner.run_async(user_id="web", session_id=sid,
                                         new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if event.is_final_response() and event.content and event.content.parts:
            reply = "".join(p.text or "" for p in event.content.parts)
    return {"session_id": sid, "reply": reply}
