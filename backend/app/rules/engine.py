from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

from ..models import Case, CheckReport, DocType, FindingKind
from . import document_rules, lc_rules  # noqa: F401  (registers rules)
from .base import DOCUMENT_RULES, LC_RULES, Ctx

log = logging.getLogger(__name__)
_SEV = {"high": 0, "medium": 1, "low": 2}


class CountingJudge:
    """Wraps the judge to count AI calls and time spent in them (for the pipeline trace)."""

    def __init__(self, inner):
        self.inner, self.calls, self.ms = inner, 0, 0.0

    def __getattr__(self, name):
        fn = getattr(self.inner, name)

        def wrapped(*a, **k):
            t0 = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                self.calls += 1
                self.ms += (time.perf_counter() - t0) * 1000
        return wrapped


def _run(rules, ctx: Ctx, mode: str) -> CheckReport:
    from ..config import settings
    from ..normalize import to_date, to_number

    judge = CountingJudge(ctx.judge)
    ctx.judge = judge
    docs = ctx.case.documents
    trace = [dict(stage="Read documents", detail=f"{sum(d.extraction.get('fields_found', 0) for d in docs)} fields from "
                  f"{len(docs)} document(s)", ms=sum(d.extraction.get("ms", 0) for d in docs),
                  model=docs[0].extraction.get("model") if docs else None)]
    t0 = time.perf_counter()
    dates = amounts = 0
    for d in docs:
        for k, v in d.data.items():
            if not isinstance(v, str):
                continue
            if "date" in k and to_date(v):
                dates += 1
            elif any(w in k for w in ("amount", "weight", "quantity", "count")) and to_number(v) is not None:
                amounts += 1
    trace.append(dict(stage="Normalise values", detail=f"{dates} dates and {amounts} amounts or quantities converted",
                      ms=round((time.perf_counter() - t0) * 1000, 1)))
    t1 = time.perf_counter()
    ran = []
    for r in rules:
        try:
            r.fn(ctx)
            ran.append(f"{r.rule_id} {r.name}")
        except Exception as e:  # noqa: BLE001 - one broken rule must not hide the others
            log.exception("rule %s failed", r.rule_id)
            ran.append(f"{r.rule_id} {r.name} (error: {e})")
    total_ms = (time.perf_counter() - t1) * 1000
    trace.append(dict(stage="Apply rules", detail=f"{len(ran)} checks against UCP 600 and the LC terms",
                      ms=round(total_ms - judge.ms, 1)))
    trace.append(dict(stage="AI judgement", detail=f"{judge.calls} judgement call(s) on wording and free-text terms",
                      ms=round(judge.ms, 1), model=settings.model_reason if settings.use_gemini else "rule-based stand-in (mock mode)"))
    ctx.findings.sort(key=lambda f: (_SEV[f.severity.value], f.rule_id))
    trace.append(dict(stage="Explain findings", detail=f"{len(ctx.findings)} finding(s), each with rule, evidence and fix", ms=0))
    n = {k: sum(1 for f in ctx.findings if f.kind == k) for k in FindingKind}
    if not ctx.findings:
        summary = (f"No issues found in the {len(ran)} checks performed. "
                   "This is not a guarantee that the bank will accept the documents.")
    elif mode == "lc_review":
        summary = f"{n[FindingKind.LC_RISK]} risky term(s) to resolve before accepting this LC."
    else:
        summary = (f"{n[FindingKind.DISCREPANCY]} discrepancy(ies), {n[FindingKind.POSSIBLE]} possible issue(s), "
                   f"{n[FindingKind.NEEDS_REVIEW]} item(s) to check by hand.")
    return CheckReport(mode=mode, findings=ctx.findings, checks_run=ran, summary=summary, trace=trace)


def review_lc(case: Case, judge, today: Optional[date] = None) -> CheckReport:
    if not case.first(DocType.LC):
        return CheckReport(mode="lc_review", findings=[], checks_run=[], summary="Upload the Letter of Credit first.")
    return _run(LC_RULES, Ctx(case=case, judge=judge, today=today or date.today()), "lc_review")


def check_documents(case: Case, judge, presentation_date: Optional[date]) -> CheckReport:
    if not case.first(DocType.LC):
        return CheckReport(mode="document_check", findings=[], checks_run=[], summary="Upload the Letter of Credit first.")
    ctx = Ctx(case=case, judge=judge, presentation_date=presentation_date or date.today())
    return _run(DOCUMENT_RULES, ctx, "document_check")
