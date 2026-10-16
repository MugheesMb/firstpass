"""Data models.

Extraction models use plain strings for dates and amounts on purpose: Gemini returns
what is printed on the document, and `normalize.py` converts it. That keeps the
extraction step honest ("what does the paper say?") and the maths step exact.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocType(str, Enum):
    LC = "letter_of_credit"
    INVOICE = "commercial_invoice"
    BL = "bill_of_lading"
    PACKING_LIST = "packing_list"
    COO = "certificate_of_origin"
    INSURANCE = "insurance_certificate"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------
# Evidence: where on the page a value came from
# --------------------------------------------------------------------------
class FieldEvidence(BaseModel):
    field: str = Field(description="Name of the extracted field this evidence supports")
    page: int = Field(default=1, description="1-based page number")
    box_2d: Optional[list[int]] = Field(
        default=None,
        description="[ymin, xmin, ymax, xmax] of the value on the page image, normalised 0-1000",
    )
    text: Optional[str] = Field(default=None, description="Exact text as printed")
    confidence: Optional[float] = Field(default=None, description="0-1 confidence in the reading")


class _Doc(BaseModel):
    evidence: list[FieldEvidence] = Field(default_factory=list)
    unreadable_fields: list[str] = Field(
        default_factory=list, description="Fields present on the document but not legible"
    )


# --------------------------------------------------------------------------
# Document schemas (one per document type)
# --------------------------------------------------------------------------
class LetterOfCredit(_Doc):
    lc_number: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    expiry_place: Optional[str] = Field(default=None, description="City/country where the LC expires (field 31D)")
    applicant: Optional[str] = None
    applicant_country: Optional[str] = None
    beneficiary: Optional[str] = None
    beneficiary_country: Optional[str] = None
    issuing_bank: Optional[str] = None
    currency: Optional[str] = None
    amount: Optional[str] = None
    amount_tolerance_pct: Optional[str] = Field(
        default=None, description="Percentage tolerance, e.g. '10' if the credit says 'about' or '+/-10%'"
    )
    latest_shipment_date: Optional[str] = None
    presentation_days: Optional[str] = Field(default=None, description="Days after shipment for presentation (field 48)")
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    partial_shipments: Optional[str] = Field(default=None, description="'allowed' or 'prohibited'")
    transhipment: Optional[str] = Field(default=None, description="'allowed' or 'prohibited'")
    incoterm: Optional[str] = Field(default=None, description="e.g. CIF Rotterdam, FOB Karachi")
    goods_description: Optional[str] = None
    quantity: Optional[str] = None
    quantity_unit: Optional[str] = None
    country_of_origin: Optional[str] = None
    bl_consignee_required: Optional[str] = Field(default=None, description="Consignee wording required on the B/L")
    documents_required: list[str] = Field(default_factory=list, description="Each document required (field 46A)")
    additional_conditions: list[str] = Field(default_factory=list, description="Each condition (field 47A)")


class CommercialInvoice(_Doc):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    issuer: Optional[str] = Field(default=None, description="Seller who issued the invoice")
    made_out_to: Optional[str] = Field(default=None, description="Buyer the invoice is addressed to")
    lc_number: Optional[str] = None
    currency: Optional[str] = None
    total_amount: Optional[str] = None
    quantity: Optional[str] = None
    quantity_unit: Optional[str] = None
    goods_description: Optional[str] = None
    incoterm: Optional[str] = None


class BillOfLading(_Doc):
    bl_number: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    vessel: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    issue_date: Optional[str] = None
    on_board_date: Optional[str] = None
    on_board_notation: Optional[bool] = Field(default=None, description="True if the B/L states goods are shipped on board")
    clauses: list[str] = Field(default_factory=list, description="Any clauses about defective goods or packaging")
    packages_count: Optional[str] = None
    gross_weight_kg: Optional[str] = None
    goods_description: Optional[str] = None
    freight: Optional[str] = Field(default=None, description="'prepaid' or 'collect'")


class PackingList(_Doc):
    packages_count: Optional[str] = None
    quantity: Optional[str] = None
    quantity_unit: Optional[str] = None
    gross_weight_kg: Optional[str] = None
    net_weight_kg: Optional[str] = None
    goods_description: Optional[str] = None


class CertificateOfOrigin(_Doc):
    exporter: Optional[str] = None
    consignee: Optional[str] = None
    country_of_origin: Optional[str] = None
    goods_description: Optional[str] = None
    issue_date: Optional[str] = None
    issuer: Optional[str] = None


class InsuranceCertificate(_Doc):
    issue_date: Optional[str] = None
    effective_date: Optional[str] = Field(default=None, description="Date cover starts, if stated")
    currency: Optional[str] = None
    insured_amount: Optional[str] = None
    risks_covered: Optional[str] = None
    goods_description: Optional[str] = None


SCHEMAS: dict[DocType, type[_Doc]] = {
    DocType.LC: LetterOfCredit,
    DocType.INVOICE: CommercialInvoice,
    DocType.BL: BillOfLading,
    DocType.PACKING_LIST: PackingList,
    DocType.COO: CertificateOfOrigin,
    DocType.INSURANCE: InsuranceCertificate,
}


# --------------------------------------------------------------------------
# Case, documents and findings
# --------------------------------------------------------------------------
class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingKind(str, Enum):
    DISCREPANCY = "discrepancy"    # rule clearly broken
    POSSIBLE = "possible"          # judgement call; human should decide
    NEEDS_REVIEW = "needs_review"  # data missing or unreadable
    LC_RISK = "lc_risk"            # Mode A: risky LC term


class FindingStatus(str, Enum):
    OPEN = "open"
    FIXED = "fixed"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"


class EvidenceRef(BaseModel):
    doc_id: str
    doc_type: DocType
    field: str
    value: Optional[str] = None
    page: int = 1
    box_2d: Optional[list[int]] = None


class Finding(BaseModel):
    id: str
    rule_id: str
    kind: FindingKind
    severity: Severity
    title: str
    detail: str
    ucp_ref: Optional[str] = None
    lc_ref: Optional[str] = None
    suggested_fix: Optional[str] = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: FindingStatus = FindingStatus.OPEN
    # stable across re-checks (rule + documents/fields involved), so decisions carry over
    fingerprint: str = ""
    note: Optional[str] = None
    history: list[dict] = Field(default_factory=list)  # {at, status, note, by}
    first_seen_run: Optional[int] = None


class StoredDocument(BaseModel):
    id: str
    doc_type: DocType
    filename: str
    page_count: int = 1
    data: dict = Field(default_factory=dict)  # extracted fields (one of SCHEMAS, dumped)
    extraction: dict = Field(default_factory=dict)  # model, ms, fields_found, avg_confidence, low_confidence
    version: int = 1
    uploaded_at: Optional[str] = None


class CheckReport(BaseModel):
    mode: str  # "lc_review" | "document_check"
    findings: list[Finding]
    checks_run: list[str]
    summary: str
    trace: list[dict] = Field(default_factory=list)  # pipeline stages with counts and timings
    run: int = 1
    at: Optional[str] = None
    diff: dict = Field(default_factory=dict)  # vs previous run: new, resolved, still_open, carried
    resolved: list["Finding"] = Field(default_factory=list)  # found in an earlier run, gone now


class Case(BaseModel):
    id: str
    company_name: Optional[str] = None
    goods_ready_date: Optional[str] = None
    presentation_date: Optional[str] = None
    documents: list[StoredDocument] = Field(default_factory=list)
    lc_review: Optional[CheckReport] = None
    document_check: Optional[CheckReport] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source: Optional[str] = None  # sample case folder this case was loaded from, if any
    events: list[dict] = Field(default_factory=list)  # activity log: {at, kind, text}
    runs: list[dict] = Field(default_factory=list)    # one summary per check run

    def docs_of(self, t: DocType) -> list[StoredDocument]:
        return [d for d in self.documents if d.doc_type == t]

    def first(self, t: DocType) -> Optional[StoredDocument]:
        docs = self.docs_of(t)
        return docs[0] if docs else None
