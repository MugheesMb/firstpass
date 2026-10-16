"""Judgement calls that need language understanding.

Rules that are pure arithmetic or dates live in rules/. This module only answers questions
like "does this invoice description correspond with the LC?" or "is this LC term risky?".
`MockJudge` gives deterministic answers so the whole pipeline runs offline and in tests.
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field

from ..config import settings
from ..normalize import keywords, norm_text


class Verdict(BaseModel):
    verdict: str = Field(description="One of: match, mismatch, unclear (invoice) or consistent, conflict, unclear (other documents)")
    reason: str = Field(description="One or two sentences a trade-finance officer would accept")


class LcRisk(BaseModel):
    title: str
    detail: str
    severity: str = Field(description="high, medium or low")
    clause: Optional[str] = Field(default=None, description="The LC field or clause text concerned")
    suggested_amendment: Optional[str] = None


class LcRiskList(BaseModel):
    risks: list[LcRisk] = Field(default_factory=list)


class DraftText(BaseModel):
    text: str


class EmailDraft(BaseModel):
    subject: str
    body: str


SYSTEM = (
    "You are a senior documentary credit checker applying ICC UCP 600 and ISBP 821. "
    "Be precise and conservative. Never invent facts that are not in the inputs. "
    "If the inputs do not support a firm conclusion, answer 'unclear'."
)


class MockJudge:
    """Deterministic stand-in for Gemini. Good enough to test the pipeline, not for production."""

    def invoice_description(self, lc_desc: str, inv_desc: str) -> Verdict:
        if norm_text(lc_desc) == norm_text(inv_desc):
            return Verdict(verdict="match", reason="Descriptions are identical.")
        lk, ik = keywords(lc_desc), keywords(inv_desc)
        if lk and lk <= ik:
            return Verdict(verdict="match", reason="Invoice contains every element of the LC description.")
        missing = ", ".join(sorted(lk - ik)) or "wording"
        return Verdict(verdict="mismatch", reason=f"Invoice description does not contain: {missing}.")

    def other_description(self, lc_desc: str, doc_desc: str) -> Verdict:
        if keywords(lc_desc) & keywords(doc_desc):
            return Verdict(verdict="consistent", reason="General description consistent with the LC.")
        return Verdict(verdict="conflict", reason="Description shares no key terms with the LC goods description.")

    def review_lc(self, lc: dict, company_name: Optional[str], already: list[str] = ()) -> list[LcRisk]:
        return []  # deterministic rules in rules/lc_rules.py cover the demo cases

    def draft_fix(self, finding: dict, docs: dict) -> str:
        fix = finding.get("suggested_fix") or "Correct the document so it matches the LC terms."
        return f"Suggested correction ({finding.get('title')}):\n{fix}"

    def amendment_email(self, lc: dict, risks: list[dict], company_name: Optional[str]) -> EmailDraft:
        lines = [f"- {r['title']}: {r.get('suggested_fix') or r['detail']}" for r in risks]
        body = (
            "Dear Sir/Madam,\n\n"
            f"Thank you for opening Letter of Credit {lc.get('lc_number') or ''}. Before we accept it, "
            "we kindly request the following amendments so that we can present compliant documents:\n\n"
            + "\n".join(lines)
            + "\n\nPlease ask your bank to issue the amendment at your earliest convenience.\n\n"
            f"Best regards,\n{company_name or '[Your company]'}"
        )
        return EmailDraft(subject=f"Request for amendment to LC {lc.get('lc_number') or ''}".strip(), body=body)


def _waiver_lines(findings: list[dict]) -> list[str]:
    return [f"{i}. {f['title']}: {f['detail']}" for i, f in enumerate(findings, 1)]


class _WaiverMixin:
    def waiver_request(self, lc: dict, findings: list[dict], company_name: Optional[str]) -> EmailDraft:
        body = (
            f"Dear {lc.get('applicant') or 'Sir/Madam'},\n\n"
            f"We are presenting documents under Letter of Credit {lc.get('lc_number') or ''} issued by "
            f"{(lc.get('issuing_bank') or 'your bank').rstrip('.')}. The presentation contains the following discrepancies, "
            "which cannot be corrected:\n\n" + "\n".join(_waiver_lines(findings)) +
            "\n\nThe goods were shipped as ordered. We kindly ask you to accept these discrepancies and to instruct "
            "your bank to waive them and honour the presentation, as provided for in UCP 600 Article 16(b).\n\n"
            f"Best regards,\n{company_name or '[Your company]'}"
        )
        return EmailDraft(subject=f"Request to accept discrepancies under LC {lc.get('lc_number') or ''}".strip(), body=body)


MockJudge.waiver_request = _WaiverMixin.waiver_request


class GeminiJudge(MockJudge):
    def invoice_description(self, lc_desc: str, inv_desc: str) -> Verdict:
        from .gemini import reason_json

        prompt = (
            "UCP 600 Art. 18(c): the goods description in the commercial invoice must correspond with that "
            "in the credit. Extra detail is acceptable if it does not conflict; a different product name, "
            "grade, size, material or quantity basis is a discrepancy.\n"
            f"LC description: {lc_desc!r}\nInvoice description: {inv_desc!r}\n"
            "Answer match, mismatch or unclear."
        )
        return reason_json([prompt], Verdict, SYSTEM, thinking=settings.thinking_judge)

    def other_description(self, lc_desc: str, doc_desc: str) -> Verdict:
        from .gemini import reason_json

        prompt = (
            "UCP 600 Art. 14(e): in documents other than the invoice, the goods may be described in general "
            "terms not conflicting with the credit. Decide whether the document description conflicts.\n"
            f"LC description: {lc_desc!r}\nDocument description: {doc_desc!r}\n"
            "Answer consistent, conflict or unclear."
        )
        return reason_json([prompt], Verdict, SYSTEM, thinking=settings.thinking_judge)

    def review_lc(self, lc: dict, company_name: Optional[str], already: list[str] = ()) -> list[LcRisk]:
        from .gemini import reason_json

        prompt = (
            "Review this Letter of Credit from the EXPORTER's (beneficiary's) point of view, before they accept it. "
            "List only terms that create a real risk of non-payment or a discrepant presentation: conditions "
            "outside the exporter's control (documents signed or approved by the applicant), documents that "
            "may be hard to obtain, internal contradictions, ambiguous wording, and unusual requirements. "
            "Do not repeat generic advice. Do not flag normal UCP 600 terms.\n"
            + ("Already flagged by the rule engine; do NOT repeat these or restate them in other words, "
               "only add different risks:\n- " + "\n- ".join(already) + "\n" if already else "")
            + f"Exporter name on file: {company_name or 'unknown'}\n"
            f"Extracted LC (JSON): {json.dumps({k: v for k, v in lc.items() if k != 'evidence'})}"
        )
        return reason_json([prompt], LcRiskList, SYSTEM).risks

    def draft_fix(self, finding: dict, docs: dict) -> str:
        from .gemini import reason_json

        prompt = (
            "Write the exact corrected wording (or corrective action) the exporter should use to cure this "
            "discrepancy. Keep it short and practical. If the document is issued by a third party (carrier, "
            "insurer, chamber), say who must reissue it.\n"
            f"Finding: {json.dumps(finding)}\nRelevant extracted documents: {json.dumps(docs)[:12000]}"
        )
        return reason_json([prompt], DraftText, SYSTEM).text

    def amendment_email(self, lc: dict, risks: list[dict], company_name: Optional[str]) -> EmailDraft:
        from .gemini import reason_json

        prompt = (
            "Draft a short, polite, professional email from the exporter to the buyer (LC applicant) requesting "
            "LC amendments for the issues below. Number each requested amendment and quote the LC field.\n"
            f"Exporter: {company_name or '[Your company]'}\nLC: {json.dumps({k: v for k, v in lc.items() if k != 'evidence'})}\n"
            f"Issues: {json.dumps(risks)}"
        )
        return reason_json([prompt], EmailDraft, SYSTEM)


def _gemini_waiver(self, lc: dict, findings: list[dict], company_name: Optional[str]) -> EmailDraft:
    from .gemini import reason_json

    prompt = (
        "Draft a short, professional email from the exporter (LC beneficiary) to the buyer (LC applicant) asking the "
        "buyer to accept the discrepancies below and instruct the issuing bank to waive them (UCP 600 Art. 16(b)). "
        "Be factual, list each discrepancy, do not admit liability beyond the facts, and keep a cooperative tone.\n"
        f"Exporter: {company_name or '[Your company]'}\n"
        f"LC: {json.dumps({k: v for k, v in lc.items() if k != 'evidence'})}\nDiscrepancies: {json.dumps(findings)}"
    )
    return reason_json([prompt], EmailDraft, SYSTEM)


GeminiJudge.waiver_request = _gemini_waiver


def get_judge():
    return GeminiJudge() if settings.use_gemini else MockJudge()
