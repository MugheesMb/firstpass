"""Shared machinery for rules: a context object and a registry."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from ..models import (Case, DocType, EvidenceRef, Finding, FindingKind, Severity, StoredDocument)


@dataclass
class Rule:
    rule_id: str
    name: str
    fn: Callable[["Ctx"], None]


DOCUMENT_RULES: list[Rule] = []
LC_RULES: list[Rule] = []


def document_rule(rule_id: str, name: str):
    def deco(fn):
        DOCUMENT_RULES.append(Rule(rule_id, name, fn))
        return fn
    return deco


def lc_rule(rule_id: str, name: str):
    def deco(fn):
        LC_RULES.append(Rule(rule_id, name, fn))
        return fn
    return deco


@dataclass
class Ctx:
    case: Case
    judge: object
    presentation_date: Optional[date] = None
    today: date = field(default_factory=date.today)
    findings: list[Finding] = field(default_factory=list)

    # ---- document access -------------------------------------------------
    def doc(self, t: DocType) -> Optional[StoredDocument]:
        return self.case.first(t)

    def has(self, *types: DocType) -> bool:
        return all(self.doc(t) is not None for t in types)

    def get(self, t: DocType, fld: str):
        d = self.doc(t)
        return d.data.get(fld) if d else None

    def ev(self, t: DocType, fld: str) -> Optional[EvidenceRef]:
        d = self.doc(t)
        if not d:
            return None
        e = next((x for x in d.data.get("evidence", []) if x.get("field") == fld), None)
        val = d.data.get(fld)
        return EvidenceRef(
            doc_id=d.id, doc_type=t, field=fld,
            value=None if val is None else str(val),
            page=(e or {}).get("page") or 1,
            box_2d=(e or {}).get("box_2d"),
        )

    # ---- output ------------------------------------------------------------
    def add(self, rule_id: str, kind: FindingKind, severity: Severity, title: str, detail: str, *,
            ucp: Optional[str] = None, lc_ref: Optional[str] = None, fix: Optional[str] = None,
            ev: tuple = ()) -> None:
        refs = [r for r in (self.ev(t, f) for t, f in ev) if r is not None]
        key = rule_id + "|" + title + "|" + ",".join(sorted(f"{t.value}.{f}" for t, f in ev))
        fp = hashlib.sha1(key.encode()).hexdigest()[:12]
        fid = f"{rule_id}-{fp[:6]}"
        if any(f.id == fid for f in self.findings):
            fid = f"{fid}-{len(self.findings) + 1}"
        self.findings.append(Finding(
            fingerprint=fp, id=fid, rule_id=rule_id, kind=kind, severity=severity,
            title=title, detail=detail, ucp_ref=ucp, lc_ref=lc_ref, suggested_fix=fix, evidence=refs,
        ))
