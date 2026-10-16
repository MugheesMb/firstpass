"""The FirstPass pipeline: upload -> extract -> check -> explain. Used by the API, the ADK
agent and the evaluation script, so all three behave identically."""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from .ai.judge import get_judge
from .extraction import render
from .extraction.extractor import get_extractor
from .config import settings
from .models import SCHEMAS, Case, CheckReport, DocType, Finding, FindingKind, FindingStatus, StoredDocument
from .normalize import to_date
from .rules import engine
from . import storage


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(case: Case, kind: str, text: str) -> None:
    case.events.append({"at": now(), "kind": kind, "text": text})
    case.updated_at = now()


def label(t: DocType) -> str:
    return "Letter of Credit" if t == DocType.LC else t.value.replace("_", " ")


def new_case(company_name: Optional[str] = None, goods_ready_date: Optional[str] = None) -> Case:
    case = Case(id=uuid.uuid4().hex[:12], company_name=company_name, goods_ready_date=goods_ready_date,
                created_at=now(), updated_at=now())
    log(case, "case", f"Case opened{f' for {company_name}' if company_name else ''}")
    storage.cases().save(case)
    return case


def extraction_stats(t: DocType, fields: dict, ms: int) -> dict:
    """What the extractor read: shown in the UI and used in the deck's technical slide."""
    skip = {"evidence", "unreadable_fields"}
    names = [k for k in (SCHEMAS[t].model_fields if t in SCHEMAS else {}) if k not in skip]
    found = [k for k in names if fields.get(k) not in (None, "", [])]
    conf = {e["field"]: e.get("confidence") for e in fields.get("evidence", []) if e.get("confidence") is not None}
    vals = [conf[k] for k in found if k in conf]
    return dict(model=settings.model_extract if settings.use_gemini else "ground truth (mock mode)", ms=ms,
                fields_total=len(names), fields_found=len(found),
                avg_confidence=round(sum(vals) / len(vals), 3) if vals else None,
                low_confidence=sorted(k for k in found if conf.get(k) is not None and conf[k] < 0.8),
                unreadable=fields.get("unreadable_fields", []))


def file_key(case_id: str, doc_id: str, filename: str) -> str:
    return f"{case_id}/{doc_id}/{Path(filename).name}"


def add_document(case: Case, data: bytes, filename: str, mime: Optional[str] = None,
                 doc_type: Optional[DocType] = None, sidecar: Optional[dict] = None, extractor=None,
                 pre: Optional[tuple] = None) -> StoredDocument:
    """`pre` = (doc_type, fields, ms) when extraction already ran (e.g. in parallel)."""
    if pre:
        t, fields, ms = pre
    else:
        extractor = extractor or get_extractor()
        t0 = time.perf_counter()
        t, fields = extractor.extract(data, filename, mime, doc_type, sidecar)
        ms = round((time.perf_counter() - t0) * 1000)
    prev = case.first(t) if t != DocType.UNKNOWN else None
    doc = StoredDocument(id=uuid.uuid4().hex[:10], doc_type=t, filename=Path(filename).name,
                         page_count=render.page_count(data, filename, mime), data=fields,
                         extraction=extraction_stats(t, fields, ms), version=(prev.version + 1) if prev else 1,
                         uploaded_at=now())
    storage.files().put(file_key(case.id, doc.id, filename), data)
    x = doc.extraction
    log(case, "upload", f"{label(t).capitalize()} uploaded: {doc.filename}"
        + (f" (version {doc.version}, replaces version {prev.version})" if prev else "")
        + f". {x['fields_found']} of {x['fields_total']} fields read.")
    # one document per type in the MVP: a new upload replaces the previous one of that type
    case.documents = [d for d in case.documents if d.doc_type != t or t == DocType.UNKNOWN] + [doc]
    storage.cases().save(case)
    return doc


def _merge(prev: Optional[CheckReport], rep: CheckReport) -> CheckReport:
    """Compare with the previous run: carry decisions over, reopen 'fixed' items that are still
    there, and record what was resolved."""
    rep.run = (prev.run + 1) if prev else 1
    rep.at = now()
    if not prev:
        for f in rep.findings:
            f.first_seen_run = 1
        return rep
    old = {f.fingerprint: f for f in prev.findings}
    new, still, carried = [], 0, 0
    for f in rep.findings:
        p = old.get(f.fingerprint)
        if not p:
            f.first_seen_run = rep.run
            new.append(f.title)
            continue
        f.first_seen_run, f.history, f.note = p.first_seen_run or prev.run, list(p.history), p.note
        if p.status in (FindingStatus.ACCEPTED, FindingStatus.DISPUTED):
            f.status = p.status
            carried += 1
        else:
            still += 1
            if p.status == FindingStatus.FIXED:
                f.history.append({"at": now(), "status": "open", "note": f"Still present in run {rep.run}", "by": "FirstPass"})
    current = {f.fingerprint for f in rep.findings}
    gone = []
    for fp, p in old.items():
        if fp not in current:
            r = p.model_copy(deep=True)
            r.status = FindingStatus.FIXED
            r.history.append({"at": now(), "status": "fixed", "note": f"No longer found in run {rep.run}", "by": "FirstPass"})
            gone.append(r)
    rep.resolved = [r for r in prev.resolved if r.fingerprint not in current] + gone
    rep.diff = {"previous_run": prev.run, "new": new, "resolved": [g.title for g in gone],
                "still_open": still, "carried": carried}
    return rep


def _record_run(case: Case, rep: CheckReport, name: str) -> None:
    open_n = sum(1 for f in rep.findings if f.status == FindingStatus.OPEN)
    case.runs.append({"mode": rep.mode, "run": rep.run, "at": rep.at, "findings": len(rep.findings), "open": open_n,
                      "new": len(rep.diff.get("new", [])) if rep.diff else len(rep.findings),
                      "resolved": len(rep.diff.get("resolved", []))})
    d = rep.diff
    change = (f" ({len(d['new'])} new, {len(d['resolved'])} resolved, {d['still_open']} still open)" if d else "")
    log(case, "check", f"{name} run {rep.run}: {len(rep.findings)} finding(s){change}")


def run_lc_review(case: Case, judge=None) -> CheckReport:
    report = _merge(case.lc_review, engine.review_lc(case, judge or get_judge()))
    case.lc_review = report
    _record_run(case, report, "LC term review")
    storage.cases().save(case)
    return report


def run_document_check(case: Case, presentation_date: Optional[str] = None, judge=None) -> CheckReport:
    if presentation_date:
        case.presentation_date = presentation_date
    pres = to_date(case.presentation_date) or date.today()
    report = _merge(case.document_check, engine.check_documents(case, judge or get_judge(), pres))
    case.document_check = report
    _record_run(case, report, "Compliance check")
    storage.cases().save(case)
    return report


def find_finding(case: Case, finding_id: str) -> Optional[Finding]:
    return next((f for rep in (case.lc_review, case.document_check) if rep for f in rep.findings if f.id == finding_id), None)


def set_finding_status(case: Case, finding_id: str, status: FindingStatus, note: Optional[str] = None) -> Optional[Finding]:
    f = find_finding(case, finding_id)
    if not f:
        return None
    f.status = status
    if note:
        f.note = note
    f.history.append({"at": now(), "status": status.value, "note": note, "by": "you"})
    verb = {"open": "Reopened", "fixed": "Marked fixed", "accepted": "Accepted", "disputed": "Disputed"}[status.value]
    log(case, "decision", f"{verb}: {f.title}" + (f". Reason: {note}" if note else ""))
    storage.cases().save(case)
    return f


def waiver_candidates(case: Case) -> list[Finding]:
    """Discrepancies the exporter has accepted: they cannot be fixed, so the buyer is asked to waive them."""
    rep = case.document_check
    return [f for f in (rep.findings if rep else [])
            if f.status == FindingStatus.ACCEPTED and f.kind in (FindingKind.DISCREPANCY, FindingKind.POSSIBLE)]


def load_demo_case(demo_dir: Path, extractor=None) -> Case:
    """Load a generated case folder (see datagen/). Uses ground-truth sidecars in mock mode;
    in Gemini mode the same PDFs go through real extraction."""
    meta = json.loads((demo_dir / "case.json").read_text())
    case = new_case(meta.get("company_name"), meta.get("goods_ready_date"))
    case.source = demo_dir.name
    log(case, "case", f"Sample case loaded: {demo_dir.name}")
    case.presentation_date = meta.get("presentation_date")
    # Read all documents in parallel: with Gemini this keeps a 6-document case well under a minute.
    from concurrent.futures import ThreadPoolExecutor

    extractor = extractor or get_extractor()
    jobs = []
    for f in meta["files"]:
        pdf = demo_dir / f["file"]
        sidecar = json.loads((demo_dir / f["truth"]).read_text()) if not settings.use_gemini else None
        jobs.append((pdf, DocType(f["doc_type"]), sidecar, pdf.read_bytes()))

    def read(job):
        pdf, dt, sidecar, data = job
        t0 = time.perf_counter()
        t, fields = extractor.extract(data, pdf.name, "application/pdf", dt, sidecar)
        return t, fields, round((time.perf_counter() - t0) * 1000)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(read, jobs))
    for (pdf, dt, sidecar, data), pre in zip(jobs, results):
        add_document(case, data, pdf.name, "application/pdf", dt, sidecar, pre=pre)
    storage.cases().save(case)
    return case
