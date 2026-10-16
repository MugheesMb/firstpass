"""FirstPass assistant built with Google's Agent Development Kit (ADK).

The agent does not re-implement any checks: its tools call the same pipeline as the API,
so its answers always match the findings on screen.

Try it locally (from backend/):  adk web   -> pick "firstpass_agent"
Needs: GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION=global
"""
from __future__ import annotations

import json

from google.adk.agents import Agent

from app import pipeline, storage
from app.ai.judge import get_judge
from app.config import settings
from app.models import DocType, FindingKind


def _case(case_id: str):
    case = storage.cases().get(case_id)
    if not case:
        raise ValueError(f"No case with id {case_id}")
    return case


def _brief(report) -> dict:
    return {"summary": report.summary, "findings": [
        {"id": f.id, "rule": f.rule_id, "kind": f.kind.value, "severity": f.severity.value, "title": f.title,
         "detail": f.detail, "ucp": f.ucp_ref, "lc_field": f.lc_ref, "fix": f.suggested_fix, "status": f.status.value}
        for f in report.findings]}


def get_case_summary(case_id: str) -> dict:
    """List the documents in a case and the key values extracted from each one.

    Args:
        case_id: The FirstPass case id.
    """
    case = _case(case_id)
    return {"company": case.company_name, "goods_ready_date": case.goods_ready_date,
            "presentation_date": case.presentation_date,
            "documents": [{"type": d.doc_type.value, "file": d.filename,
                           "fields": {k: v for k, v in d.data.items() if k not in {"evidence", "unreadable_fields"} and v}}
                          for d in case.documents]}


def review_lc_terms(case_id: str) -> dict:
    """Review the Letter of Credit terms for risks BEFORE the exporter accepts the LC.

    Args:
        case_id: The FirstPass case id.
    """
    return _brief(pipeline.run_lc_review(_case(case_id)))


def check_presentation(case_id: str, presentation_date: str = "") -> dict:
    """Check the shipping documents against the LC and against each other (UCP 600).

    Args:
        case_id: The FirstPass case id.
        presentation_date: Planned date of presenting documents to the bank, YYYY-MM-DD. Empty means today.
    """
    return _brief(pipeline.run_document_check(_case(case_id), presentation_date or None))


def draft_amendment_email(case_id: str) -> dict:
    """Draft an email to the buyer requesting amendments for the open LC risks. Run review_lc_terms first.

    Args:
        case_id: The FirstPass case id.
    """
    case = _case(case_id)
    if not case.lc_review:
        pipeline.run_lc_review(case)
    risks = [json.loads(f.model_dump_json()) for f in case.lc_review.findings if f.kind == FindingKind.LC_RISK]
    lc = case.first(DocType.LC)
    return get_judge().amendment_email(lc.data if lc else {}, risks, case.company_name).model_dump()


INSTRUCTION = """You are FirstPass, an assistant for small exporters who are paid by Letter of Credit (LC).
Always use the tools to answer: never guess a date, amount or rule. Workflow:
1. If the user has not accepted the LC yet, call review_lc_terms and explain each risk and the amendment to ask for.
2. After shipment, call check_presentation and explain each discrepancy in plain English: what is wrong, which
   document, the UCP 600 article, and exactly how to fix it. Group by severity, most serious first.
3. Offer draft_amendment_email when there are LC risks.
Never say documents are 'approved' or 'will be paid'. Say 'no issues found in the checks performed'.
You are not a lawyer or a bank; for disputed points recommend confirming with the advising bank."""

root_agent = Agent(
    name="firstpass",
    model=settings.model_reason_fallback,
    description="Checks Letter of Credit terms and shipping documents for discrepancies before the bank does.",
    instruction=INSTRUCTION,
    tools=[get_case_summary, review_lc_terms, check_presentation, draft_amendment_email],
)
