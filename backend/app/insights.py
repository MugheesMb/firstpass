"""Views derived from a checked case: cross-document consistency grid, date timeline, readiness.

Nothing here makes new judgements. Every 'issue' mark comes from an open finding whose
evidence points at that document and field, so the grid always agrees with the findings list.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from datetime import date

from .models import Case, DocType as D, FindingKind, FindingStatus, Severity
from .normalize import to_date, to_number

COLUMNS = [D.LC, D.INVOICE, D.BL, D.PACKING_LIST, D.COO, D.INSURANCE]

# row label -> ({doc type: field}, rules that can flag this row)
ROWS: list[tuple[str, dict, set]] = [
    ("Goods description", {D.LC: "goods_description", D.INVOICE: "goods_description", D.BL: "goods_description",
                           D.PACKING_LIST: "goods_description", D.COO: "goods_description", D.INSURANCE: "goods_description"},
     {"R08", "R09"}),
    ("Quantity", {D.LC: "quantity", D.INVOICE: "quantity", D.PACKING_LIST: "quantity"}, {"R06", "R10"}),
    ("Value", {D.LC: "amount", D.INVOICE: "total_amount", D.INSURANCE: "insured_amount"}, {"R05", "R15"}),
    ("Currency", {D.LC: "currency", D.INVOICE: "currency", D.INSURANCE: "currency"}, {"R04", "R15"}),
    ("Packages", {D.BL: "packages_count", D.PACKING_LIST: "packages_count"}, {"R10"}),
    ("Gross weight", {D.BL: "gross_weight_kg", D.PACKING_LIST: "gross_weight_kg"}, {"R10"}),
    ("Port of loading", {D.LC: "port_of_loading", D.BL: "port_of_loading"}, {"R11"}),
    ("Port of discharge", {D.LC: "port_of_discharge", D.BL: "port_of_discharge"}, {"R11"}),
    ("Seller", {D.LC: "beneficiary", D.INVOICE: "issuer", D.BL: "shipper", D.COO: "exporter"}, {"R07"}),
    ("Buyer", {D.LC: "applicant", D.INVOICE: "made_out_to", D.BL: "notify_party", D.COO: "consignee"}, {"R07"}),
    ("Consignee", {D.LC: "bl_consignee_required", D.BL: "consignee"}, {"R21"}),
    ("Trade terms", {D.LC: "incoterm", D.INVOICE: "incoterm", D.BL: "freight"}, {"R22", "R23"}),
    ("Credit number", {D.LC: "lc_number", D.INVOICE: "lc_number"}, {"R24"}),
    ("Country of origin", {D.LC: "country_of_origin", D.COO: "country_of_origin"}, {"R20"}),
    ("Shipment and cover dates", {D.LC: "latest_shipment_date", D.BL: "on_board_date", D.INSURANCE: "issue_date"},
     {"R02", "R14"}),
]

PENALTY = {Severity.HIGH: 30, Severity.MEDIUM: 12, Severity.LOW: 4}


def _required_types(case: Case) -> set:
    req = " ".join(case.first(D.LC).data.get("documents_required") or []).lower() if case.first(D.LC) else ""
    keys = {D.INSURANCE: "insurance", D.COO: "origin", D.PACKING_LIST: "packing", D.BL: "lading", D.INVOICE: "invoice"}
    return {D.LC} | {t for t, k in keys.items() if k in req} if req else set(COLUMNS)


def matrix(case: Case) -> dict:
    findings = [f for f in (case.document_check.findings if case.document_check else []) if f.status == FindingStatus.OPEN]
    flagged: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        for e in f.evidence:
            flagged.setdefault((e.doc_type.value, e.field), []).append(f.id)
    required = _required_types(case)
    rows = []
    for label, fields, rules in ROWS:
        cells = {}
        for col in COLUMNS:
            fld = fields.get(col)
            doc = case.first(col)
            if fld is None:
                cells[col.value] = {"status": "n/a"}
                continue
            if doc is None:
                cells[col.value] = {"status": "missing" if col in required else "not required"}
                continue
            val = doc.data.get(fld)
            if fld == "on_board_date" and not val:
                fld, val = "issue_date", doc.data.get("issue_date")
            ids = [i for i in flagged.get((col.value, fld), []) if i.split("-")[0] in rules]
            if col == D.LC:
                status = "issue" if ids else "reference"
            else:
                status = "issue" if ids else ("ok" if val not in (None, "", []) else "blank")
            cells[col.value] = {"status": status, "value": None if val is None else str(val), "findings": ids}
        rows.append({"label": label, "cells": cells})
    return {"columns": [c.value for c in COLUMNS], "rows": rows, "checked": case.document_check is not None}


def timeline(case: Case) -> list[dict]:
    lc, bl = case.first(D.LC), case.first(D.BL)
    g = (lambda d, f: d.data.get(f) if d else None)
    ship = to_date(g(bl, "on_board_date")) or to_date(g(bl, "issue_date"))
    days = int(to_number(g(lc, "presentation_days")) or 21)
    expiry = to_date(g(lc, "expiry_date"))
    deadline = None
    if ship:
        deadline = ship + timedelta(days=days)
        if expiry and expiry < deadline:
            deadline = expiry
    points = [
        ("lc_issued", "LC issued", to_date(g(lc, "issue_date")), "lc"),
        ("goods_ready", "Goods ready", to_date(case.goods_ready_date), "you"),
        ("latest_shipment", "Latest shipment allowed", to_date(g(lc, "latest_shipment_date")), "limit"),
        ("shipped", "Shipped on board", ship, "event"),
        ("presentation", "Planned presentation", to_date(case.presentation_date), "you"),
        ("deadline", f"Presentation deadline ({days} days or expiry)", deadline, "limit"),
        ("expiry", "LC expiry", expiry, "limit"),
    ]
    return sorted([{"key": k, "label": l, "date": d.isoformat(), "kind": kind} for k, l, d, kind in points if d],
                  key=lambda p: p["date"])


def readiness(case: Case) -> Optional[dict]:
    rep = case.document_check
    if not rep:
        return None
    open_f = [f for f in rep.findings if f.status == FindingStatus.OPEN]
    score = 100
    for f in open_f:
        score -= 5 if f.kind == FindingKind.NEEDS_REVIEW else PENALTY[f.severity]
    score = max(0, score)
    high = sum(1 for f in open_f if f.severity == Severity.HIGH and f.kind != FindingKind.NEEDS_REVIEW)
    if not open_f:
        verdict = "Ready to present"
    elif high:
        verdict = "Fix before presenting"
    else:
        verdict = "Review before presenting"
    return {"score": score, "verdict": verdict, "open": len(open_f), "high": high,
            "resolved": len(rep.findings) - len(open_f) + len(rep.resolved), "checks": len(rep.checks_run),
            "method": "Starts at 100; each open high, medium or low finding subtracts 30, 12 or 4 points "
                      "(5 for items to check by hand). A guide to priority, not a prediction of bank acceptance."}


def insights(case: Case) -> dict:
    return {"matrix": matrix(case), "timeline": timeline(case), "readiness": readiness(case)}


def case_summary(case: Case) -> dict:
    """One row on the cases dashboard."""
    lc = case.first(D.LC)
    g = (lambda f: lc.data.get(f) if lc else None)
    expiry = to_date(g("expiry_date"))
    counts = {s.value: 0 for s in FindingStatus}
    for rep in (case.lc_review, case.document_check):
        for f in (rep.findings if rep else []):
            counts[f.status.value] += 1
    if case.document_check:
        counts["fixed"] += len(case.document_check.resolved)
    stage = ("Report ready" if case.document_check else "Documents added" if len(case.documents) > 1
             else "LC reviewed" if case.lc_review else "LC read" if lc else "Profile only")
    r = readiness(case)
    return {"id": case.id, "company": case.company_name, "lc_number": g("lc_number"), "applicant": g("applicant"),
            "amount": g("amount"), "expiry": expiry.isoformat() if expiry else None,
            "days_to_expiry": (expiry - date.today()).days if expiry else None,
            "readiness": r["score"] if r else None, "verdict": r["verdict"] if r else None,
            "counts": counts, "documents": len(case.documents), "stage": stage,
            "updated_at": case.updated_at, "runs": len(case.runs)}
