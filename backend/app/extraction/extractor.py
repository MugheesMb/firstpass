"""Document classification and field extraction.

GeminiExtractor: real extraction with Gemini (structured output, one schema per doc type).
MockExtractor:   reads a ground-truth sidecar produced by datagen/ (offline dev and tests).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

from ..config import settings
from ..models import SCHEMAS, DocType
from . import render

log = logging.getLogger(__name__)

TYPE_HINTS = {
    DocType.LC: "Letter of Credit / documentary credit (often a SWIFT MT700 with numbered fields like 31D, 44C, 46A, 47A)",
    DocType.INVOICE: "Commercial invoice",
    DocType.BL: "Bill of lading (ocean or multimodal transport document)",
    DocType.PACKING_LIST: "Packing list / weight list",
    DocType.COO: "Certificate of origin",
    DocType.INSURANCE: "Insurance certificate or policy",
}

EXTRACT_SYSTEM = (
    "You extract data from international trade documents for a documentary-credit checker. "
    "Copy values exactly as printed (do not correct spelling, do not convert units or dates). "
    "If a field is not on the document, leave it null. If it is present but illegible, leave it null "
    "and add its name to unreadable_fields. For every non-null field, add an evidence entry with the "
    "page number, the exact printed text and box_2d = [ymin, xmin, ymax, xmax] normalised to 0-1000 "
    "on that page image, plus your confidence from 0 to 1."
)


class Classification(BaseModel):
    doc_type: str = Field(description="One of: " + ", ".join(t.value for t in TYPE_HINTS))
    confidence: float


# Longest plausible printed value per field; anything longer is a runaway generation, not data.
LONG_FIELDS = {"goods_description": 2000, "risks_covered": 300, "consignee": 300, "bl_consignee_required": 300,
               "notify_party": 300, "applicant": 300, "beneficiary": 300, "issuer": 300, "made_out_to": 300,
               "shipper": 300, "exporter": 300, "issuing_bank": 300, "expiry_place": 200}
LIST_ITEM_MAX = 1500  # real 46A/47A entries can be long
DEFAULT_MAX = 120
_JUNK = re.compile(r"<\s*/?\s*(div|strong|h\d|ul|li|p|span|br)\b|https?://|&nbsp;", re.I)


def find_problems(fields: dict) -> list[str]:
    """Fields whose value cannot be a printed trade-document value (too long, HTML, URLs)."""
    bad = []
    for k, v in fields.items():
        if k in ("evidence", "unreadable_fields"):
            continue
        if isinstance(v, str) and (len(v) > LONG_FIELDS.get(k, DEFAULT_MAX) or _JUNK.search(v)):
            bad.append(k)
        elif isinstance(v, list) and any(isinstance(x, str) and (len(x) > LIST_ITEM_MAX or _JUNK.search(x)) for x in v):
            bad.append(k)
    return bad


def quarantine(fields: dict, bad: list[str]) -> dict:
    """Blank implausible values and flag them for a human, instead of feeding junk to the rules."""
    for k in bad:
        fields[k] = [] if isinstance(fields.get(k), list) else None
        fields["evidence"] = [e for e in fields.get("evidence", []) if e.get("field") != k]
        fields.setdefault("unreadable_fields", [])
        if k not in fields["unreadable_fields"]:
            fields["unreadable_fields"].append(k)
    return fields


def classify_by_name(filename: str) -> DocType:
    n = filename.lower()
    for key, t in [("lc", DocType.LC), ("credit", DocType.LC), ("mt700", DocType.LC), ("invoice", DocType.INVOICE),
                   ("lading", DocType.BL), ("bl", DocType.BL), ("packing", DocType.PACKING_LIST),
                   ("origin", DocType.COO), ("coo", DocType.COO), ("insurance", DocType.INSURANCE)]:
        if key in n.replace("-", "_").split("_") or key in n:
            return t
    return DocType.UNKNOWN


def _known_files() -> dict:
    """sha256 -> ground truth for every generated PDF on disk (mock mode only)."""
    import hashlib
    import json

    if not hasattr(_known_files, "cache"):
        roots = [settings.demo_dir] + list(settings.extra_case_dirs)
        found = {}
        for root in roots:
            if root.exists():
                for pdf in root.rglob("*.pdf"):
                    truth = pdf.with_name(pdf.stem + ".truth.json")
                    if truth.exists():
                        found[hashlib.sha256(pdf.read_bytes()).hexdigest()] = json.loads(truth.read_text())
        _known_files.cache = found
    return _known_files.cache


class MockExtractor:
    def extract(self, data: bytes, filename: str, mime: Optional[str], doc_type: Optional[DocType],
                sidecar: Optional[dict]) -> tuple[DocType, dict]:
        if not sidecar:
            import hashlib

            sidecar = _known_files().get(hashlib.sha256(data).hexdigest())
        if sidecar:
            t = DocType(sidecar["doc_type"])
            schema = SCHEMAS[t]
            return t, schema.model_validate(sidecar["data"]).model_dump()
        t = doc_type or classify_by_name(filename)
        if t in SCHEMAS:
            model = SCHEMAS[t]()
            model.unreadable_fields = ["(mock mode: no ground truth for this upload; set AI_MODE=gemini)"]
            return t, model.model_dump()
        return DocType.UNKNOWN, {}


class GeminiExtractor:
    def classify(self, pages: list[bytes]) -> DocType:
        from ..ai.gemini import generate_json, png_part

        prompt = "Which type of trade document is this? " + "; ".join(f"{t.value} = {h}" for t, h in TYPE_HINTS.items())
        res = generate_json(settings.model_extract, [png_part(pages[0]), prompt], Classification,
                            thinking=settings.thinking_extract, max_tokens=2048, cache=True)
        try:
            return DocType(res.doc_type)
        except ValueError:
            return DocType.UNKNOWN

    def extract(self, data: bytes, filename: str, mime: Optional[str], doc_type: Optional[DocType],
                sidecar: Optional[dict]) -> tuple[DocType, dict]:
        from ..ai import cache
        from ..ai.gemini import generate_json, png_part

        ck = cache.key("extract", settings.model_extract, settings.thinking_extract, settings.render_dpi,
                       doc_type.value if doc_type else None, data)
        if (hit := cache.get(ck)) is not None:
            return DocType(hit["doc_type"]), hit["fields"]
        pages = render.to_pngs(data, filename, mime)
        t = doc_type if doc_type and doc_type != DocType.UNKNOWN else self.classify(pages)
        if t not in SCHEMAS:
            return DocType.UNKNOWN, {}
        prompt = (
            f"This is a {TYPE_HINTS[t]} with {len(pages)} page(s), shown in order. "
            "Extract every field in the schema. Lists (documents_required, additional_conditions, clauses) "
            "must contain one item per numbered/bulleted entry, copied in full. "
            "Text fields hold a single value: give a description once, never once per carton, row or line, "
            "and never repeat the same text."
            + (" For bl_consignee_required, copy who the bills of lading must be made out or consigned to, "
               "as stated in the documents required (46A), e.g. 'To order of <bank>'." if t == DocType.LC else "")
        )
        parts = [png_part(p) for p in pages] + [prompt]
        fields: dict = {}
        last_error: Exception | None = None
        for attempt in (1, 2):  # one retry if the output is implausible, cut off or not valid JSON
            try:
                # Supporting documents are short: a lower limit makes a runaway reply fail fast.
                limit = settings.max_output_tokens if t == DocType.LC else min(8192, settings.max_output_tokens)
                fields = generate_json(settings.model_extract, parts, SCHEMAS[t], EXTRACT_SYSTEM,
                                       thinking=settings.thinking_extract, max_tokens=limit).model_dump()
            except Exception as e:  # noqa: BLE001
                last_error = e
                log.warning("extraction attempt %d of %s failed: %s", attempt, filename, e)
                continue
            bad = find_problems(fields)
            no_boxes = not any(e.get("box_2d") for e in fields.get("evidence", []))
            if not bad and not no_boxes:
                break
            log.warning("extraction attempt %d of %s: implausible fields %s, boxes missing=%s", attempt, filename, bad, no_boxes)
        if not fields and last_error:
            # Do not fail the whole case over one unreadable document: return it empty and flagged,
            # so the check still runs and a person is asked to look at this document.
            log.error("could not read %s after 2 attempts: %s", filename, last_error)
            fields = SCHEMAS[t]().model_dump()
            fields["unreadable_fields"] = ["(whole document: Gemini could not read it, please check manually)"]
            return t, fields
        fields = quarantine(fields, find_problems(fields))
        cache.put(ck, {"doc_type": t.value, "fields": fields})
        return t, fields


def get_extractor():
    return GeminiExtractor() if settings.use_gemini else MockExtractor()
