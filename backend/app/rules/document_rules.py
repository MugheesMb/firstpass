"""Mode B: check a presentation (shipping documents) against the LC and against each other.

UCP 600 article references are given for the checker's convenience. Verify them against the
official ICC text before relying on them in a demo or a real presentation.
"""
from __future__ import annotations

from typing import Optional

from datetime import timedelta

from ..models import DocType as D, FindingKind as K, Severity as S
from ..normalize import (currency_of, incoterm_code, is_countable, norm_text, same_company, same_place,
                         to_date, to_number)
from .base import Ctx, document_rule

DEFAULT_PRESENTATION_DAYS = 21  # UCP 600 Art. 14(c)


def shipment_date(c: Ctx):
    """Art. 20(a)(ii): the on-board notation date, otherwise the B/L issue date."""
    return to_date(c.get(D.BL, "on_board_date")) or to_date(c.get(D.BL, "issue_date"))


def shipment_field(c: Ctx) -> str:
    return "on_board_date" if c.get(D.BL, "on_board_date") else "issue_date"


def lc_tolerance_pct(c: Ctx) -> float:
    return to_number(c.get(D.LC, "amount_tolerance_pct")) or 0.0


# ---------------------------------------------------------------------------
@document_rule("R00", "Unreadable or missing data")
def unreadable(c: Ctx):
    for d in c.case.documents:
        for f in d.data.get("unreadable_fields", []) or []:
            c.add("R00", K.NEEDS_REVIEW, S.MEDIUM, f"Could not read '{f}' on the {d.doc_type.value.replace('_', ' ')}",
                  "This value is on the document but could not be read reliably. Check it by hand.",
                  fix="Upload a clearer scan or enter the value manually.", ev=((d.doc_type, f),))


@document_rule("R16", "All required documents presented")
def required_documents(c: Ctx):
    req = c.get(D.LC, "documents_required") or []
    # most specific first: an insurance clause may mention "invoice value"
    mapping = [("insurance", D.INSURANCE), ("origin", D.COO), ("packing", D.PACKING_LIST), ("weight list", D.PACKING_LIST),
               ("lading", D.BL), ("b/l", D.BL), ("transport document", D.BL), ("invoice", D.INVOICE)]
    for item in req:
        low = item.lower()
        t = next((t for k, t in mapping if k in low), None)
        if t is None:
            c.add("R16", K.NEEDS_REVIEW, S.LOW, "Confirm an additional required document is included",
                  f"The LC also requires: \"{item}\". FirstPass does not check this document type yet.",
                  ucp="Art. 2 (complying presentation)", lc_ref="46A", fix="Make sure this document is in the set.",
                  ev=((D.LC, "documents_required"),))
        elif not c.has(t):
            c.add("R16", K.DISCREPANCY, S.HIGH, f"Missing required document: {t.value.replace('_', ' ')}",
                  f"The LC requires \"{item}\" but it is not in this presentation.",
                  ucp="Art. 2 and 14 (complying presentation)", lc_ref="46A",
                  fix=f"Add the {t.value.replace('_', ' ')} before presenting.", ev=((D.LC, "documents_required"),))


@document_rule("R01", "Presentation on or before expiry")
def expiry(c: Ctx):
    exp = to_date(c.get(D.LC, "expiry_date"))
    if exp and c.presentation_date and c.presentation_date > exp:
        c.add("R01", K.DISCREPANCY, S.HIGH, "Presentation after LC expiry",
              f"Planned presentation {c.presentation_date:%d %b %Y} is after the expiry date {exp:%d %b %Y}.",
              ucp="Art. 6(e)", lc_ref="31D",
              fix="Present before expiry, or ask the buyer to extend the expiry date by amendment.",
              ev=((D.LC, "expiry_date"),))


@document_rule("R02", "Shipment by latest shipment date")
def latest_shipment(c: Ctx):
    latest, shp = to_date(c.get(D.LC, "latest_shipment_date")), shipment_date(c)
    if latest and shp and shp > latest:
        c.add("R02", K.DISCREPANCY, S.HIGH, "Shipped after the latest shipment date",
              f"Shipment date on the bill of lading is {shp:%d %b %Y}; the LC requires shipment by {latest:%d %b %Y} "
              f"({(shp - latest).days} day(s) late).",
              ucp="Art. 20(a)(ii) (date of shipment)", lc_ref="44C",
              fix="This cannot be fixed by editing documents. Ask the buyer to accept the discrepancy (waiver) or amend 44C.",
              ev=((D.BL, shipment_field(c)), (D.LC, "latest_shipment_date")))


@document_rule("R03", "Presentation within the presentation period")
def presentation_period(c: Ctx):
    shp = shipment_date(c)
    days = int(to_number(c.get(D.LC, "presentation_days")) or DEFAULT_PRESENTATION_DAYS)
    if shp and c.presentation_date and c.presentation_date > shp + timedelta(days=days):
        c.add("R03", K.DISCREPANCY, S.HIGH, "Presentation period exceeded",
              f"Documents must be presented within {days} days after shipment ({shp:%d %b %Y}), i.e. by "
              f"{shp + timedelta(days=days):%d %b %Y}. Planned presentation is {c.presentation_date:%d %b %Y}.",
              ucp="Art. 14(c)", lc_ref="48", fix="Present earlier. If already late, request a waiver from the buyer.",
              ev=((D.BL, shipment_field(c)), (D.LC, "presentation_days")))


@document_rule("R04", "Invoice currency")
def invoice_currency(c: Ctx):
    lc_cur = currency_of(c.get(D.LC, "currency"), c.get(D.LC, "amount"))
    inv_cur = currency_of(c.get(D.INVOICE, "currency"), c.get(D.INVOICE, "total_amount"))
    if lc_cur and inv_cur and lc_cur != inv_cur:
        c.add("R04", K.DISCREPANCY, S.HIGH, "Invoice currency differs from the LC",
              f"LC is in {lc_cur}; invoice is in {inv_cur}.", ucp="Art. 18(a)(iii)", lc_ref="32B",
              fix=f"Reissue the invoice in {lc_cur}.", ev=((D.INVOICE, "currency"), (D.LC, "currency")))


@document_rule("R05", "Invoice amount within LC amount")
def invoice_amount(c: Ctx):
    lc_amt, inv_amt = to_number(c.get(D.LC, "amount")), to_number(c.get(D.INVOICE, "total_amount"))
    if lc_amt is None or inv_amt is None:
        return
    tol = lc_tolerance_pct(c)
    limit = lc_amt * (1 + tol / 100)
    if inv_amt > limit + 0.005:
        c.add("R05", K.DISCREPANCY, S.HIGH, "Invoice amount exceeds the LC amount",
              f"Invoice total {inv_amt:,.2f} exceeds the LC amount {lc_amt:,.2f}"
              + (f" plus {tol:g}% tolerance ({limit:,.2f})" if tol else " (no tolerance allowed)")
              + f" by {inv_amt - limit:,.2f} ({(inv_amt / lc_amt - 1) * 100:.1f}% over).",
              ucp="Art. 18(b) and 30(a)", lc_ref="32B / 39A",
              fix=f"Reissue the invoice for no more than {limit:,.2f}, or ask the buyer to increase the LC amount.",
              ev=((D.INVOICE, "total_amount"), (D.LC, "amount")))


@document_rule("R06", "Invoice quantity within tolerance")
def invoice_quantity(c: Ctx):
    lc_q, inv_q = to_number(c.get(D.LC, "quantity")), to_number(c.get(D.INVOICE, "quantity"))
    if lc_q is None or inv_q is None:
        return
    tol = lc_tolerance_pct(c)
    unit = c.get(D.LC, "quantity_unit") or c.get(D.INVOICE, "quantity_unit")
    if not tol:
        tol = 0.0 if is_countable(unit) else 5.0  # Art. 30(b): 5% for non-countable goods
    partial_ok = norm_text(c.get(D.LC, "partial_shipments")) != "prohibited"
    over = inv_q > lc_q * (1 + tol / 100) + 1e-9
    under = inv_q < lc_q * (1 - tol / 100) - 1e-9 and not partial_ok
    if over or under:
        c.add("R06", K.DISCREPANCY, S.HIGH, "Invoice quantity outside LC tolerance",
              f"Invoice shows {inv_q:g} {unit or ''}; LC quantity is {lc_q:g} with {tol:g}% tolerance"
              + ("" if partial_ok else " and partial shipments prohibited") + ".",
              ucp="Art. 30(b) / 31", lc_ref="45A",
              fix="Correct the invoice quantity if it is a typing error; otherwise request a waiver or amendment.",
              ev=((D.INVOICE, "quantity"), (D.LC, "quantity")))


@document_rule("R07", "Invoice issuer and addressee")
def invoice_parties(c: Ctx):
    if not c.has(D.INVOICE, D.LC):
        return
    if same_company(c.get(D.INVOICE, "issuer"), c.get(D.LC, "beneficiary")) is False:
        c.add("R07", K.DISCREPANCY, S.HIGH, "Invoice not issued by the beneficiary",
              f"Invoice issuer \"{c.get(D.INVOICE, 'issuer')}\" does not match the LC beneficiary \"{c.get(D.LC, 'beneficiary')}\".",
              ucp="Art. 18(a)(i)", lc_ref="59", fix="Issue the invoice in the beneficiary's exact name.",
              ev=((D.INVOICE, "issuer"), (D.LC, "beneficiary")))
    if same_company(c.get(D.INVOICE, "made_out_to"), c.get(D.LC, "applicant")) is False:
        c.add("R07", K.DISCREPANCY, S.HIGH, "Invoice not made out to the applicant",
              f"Invoice is addressed to \"{c.get(D.INVOICE, 'made_out_to')}\"; the LC applicant is \"{c.get(D.LC, 'applicant')}\".",
              ucp="Art. 18(a)(ii)", lc_ref="50", fix="Address the invoice to the applicant exactly as named in the LC.",
              ev=((D.INVOICE, "made_out_to"), (D.LC, "applicant")))


@document_rule("R08", "Invoice goods description corresponds with the LC")
def invoice_description(c: Ctx):
    lc_d, inv_d = c.get(D.LC, "goods_description"), c.get(D.INVOICE, "goods_description")
    if not lc_d or not inv_d:
        return
    v = c.judge.invoice_description(lc_d, inv_d)
    if v.verdict == "mismatch":
        c.add("R08", K.DISCREPANCY, S.HIGH, "Invoice goods description does not correspond with the LC",
              f"LC: \"{lc_d}\". Invoice: \"{inv_d}\". {v.reason}", ucp="Art. 18(c)", lc_ref="45A",
              fix=f"Use the LC wording on the invoice: \"{lc_d}\".",
              ev=((D.INVOICE, "goods_description"), (D.LC, "goods_description")))
    elif v.verdict == "unclear":
        c.add("R08", K.POSSIBLE, S.MEDIUM, "Invoice goods description may not correspond",
              f"LC: \"{lc_d}\". Invoice: \"{inv_d}\". {v.reason}", ucp="Art. 18(c)", lc_ref="45A",
              fix="Safest option: copy the LC wording exactly.",
              ev=((D.INVOICE, "goods_description"), (D.LC, "goods_description")))


@document_rule("R09", "Other documents' descriptions do not conflict")
def other_descriptions(c: Ctx):
    lc_d = c.get(D.LC, "goods_description")
    if not lc_d:
        return
    for t in (D.BL, D.PACKING_LIST, D.COO, D.INSURANCE):
        d = c.get(t, "goods_description")
        if not d:
            continue
        v = c.judge.other_description(lc_d, d)
        if v.verdict in {"conflict", "unclear"}:
            c.add("R09", K.DISCREPANCY if v.verdict == "conflict" else K.POSSIBLE,
                  S.HIGH if v.verdict == "conflict" else S.MEDIUM,
                  f"Goods description on the {t.value.replace('_', ' ')} conflicts with the LC",
                  f"LC: \"{lc_d}\". {t.value.replace('_', ' ').capitalize()}: \"{d}\". {v.reason}",
                  ucp="Art. 14(e)", lc_ref="45A", fix="Describe the goods in terms consistent with the LC.",
                  ev=((t, "goods_description"), (D.LC, "goods_description")))


@document_rule("R10", "Data consistent across documents")
def cross_document(c: Ctx):
    def compare(label, a, b, rel=0.0, unit=""):
        (ta, fa), (tb, fb) = a, b
        va, vb = to_number(c.get(ta, fa)), to_number(c.get(tb, fb))
        if va is None or vb is None:
            return
        if abs(va - vb) > rel * max(abs(va), abs(vb)) + 1e-9:
            c.add("R10", K.DISCREPANCY, S.HIGH, f"{label} differs between documents",
                  f"{ta.value.replace('_', ' ').capitalize()}: {va:g}{unit}; {tb.value.replace('_', ' ')}: {vb:g}{unit}.",
                  ucp="Art. 14(d)", fix="Correct whichever document is wrong so all documents agree.",
                  ev=((ta, fa), (tb, fb)))

    compare("Number of packages", (D.BL, "packages_count"), (D.PACKING_LIST, "packages_count"))
    compare("Gross weight", (D.BL, "gross_weight_kg"), (D.PACKING_LIST, "gross_weight_kg"), rel=0.001, unit=" kg")
    compare("Quantity", (D.INVOICE, "quantity"), (D.PACKING_LIST, "quantity"))


@document_rule("R11", "Ports match the LC")
def ports(c: Ctx):
    for fld, label, lc_ref in (("port_of_loading", "Port of loading", "44E"), ("port_of_discharge", "Port of discharge", "44F")):
        if same_place(c.get(D.BL, fld), c.get(D.LC, fld)) is False:
            c.add("R11", K.DISCREPANCY, S.HIGH, f"{label} differs from the LC",
                  f"Bill of lading: \"{c.get(D.BL, fld)}\"; LC: \"{c.get(D.LC, fld)}\".", ucp="Art. 20(a)(iii)",
                  lc_ref=lc_ref, fix="Ask the carrier to correct the B/L if it is an error; otherwise request an amendment.",
                  ev=((D.BL, fld), (D.LC, fld)))


@document_rule("R12", "Bill of lading shows shipment on board")
def on_board(c: Ctx):
    if c.has(D.BL) and c.get(D.BL, "on_board_notation") is False:
        c.add("R12", K.DISCREPANCY, S.HIGH, "No 'shipped on board' notation on the bill of lading",
              "The B/L appears to be a 'received for shipment' B/L without a dated on-board notation.",
              ucp="Art. 20(a)(ii)", fix="Ask the carrier for a dated on-board notation or a 'shipped on board' B/L.",
              ev=((D.BL, "on_board_notation"),))


@document_rule("R13", "Clean bill of lading")
def clean_bl(c: Ctx):
    clauses = c.get(D.BL, "clauses") or []
    if clauses:
        c.add("R13", K.DISCREPANCY, S.HIGH, "Bill of lading is not clean",
              "The B/L carries clause(s) about the condition of goods or packaging: " + "; ".join(f'"{x}"' for x in clauses),
              ucp="Art. 27", fix="Resolve the issue with the carrier and obtain a clean B/L.", ev=((D.BL, "clauses"),))


@document_rule("R14", "Insurance effective by shipment date")
def insurance_date(c: Ctx):
    shp = shipment_date(c)
    eff_field = "effective_date" if c.get(D.INSURANCE, "effective_date") else "issue_date"
    ins = to_date(c.get(D.INSURANCE, eff_field))
    if shp and ins and ins > shp:
        c.add("R14", K.DISCREPANCY, S.HIGH, "Insurance dated after shipment",
              f"Insurance {eff_field.replace('_', ' ')} {ins:%d %b %Y} is later than shipment {shp:%d %b %Y}.",
              ucp="Art. 28(e)", fix="Ask the insurer to show cover effective no later than the shipment date.",
              ev=((D.INSURANCE, eff_field), (D.BL, shipment_field(c))))


@document_rule("R15", "Insurance amount and currency")
def insurance_amount(c: Ctx):
    if not c.has(D.INSURANCE):
        return
    lc_cur = currency_of(c.get(D.LC, "currency"), c.get(D.LC, "amount"))
    ins_cur = currency_of(c.get(D.INSURANCE, "currency"), c.get(D.INSURANCE, "insured_amount"))
    if lc_cur and ins_cur and lc_cur != ins_cur:
        c.add("R15", K.DISCREPANCY, S.HIGH, "Insurance currency differs from the LC",
              f"Insurance is in {ins_cur}; LC is in {lc_cur}.", ucp="Art. 28(f)(i)",
              fix=f"Insurance must be in {lc_cur}.", ev=((D.INSURANCE, "currency"),))
    ins_amt = to_number(c.get(D.INSURANCE, "insured_amount"))
    base = to_number(c.get(D.INVOICE, "total_amount"))
    if ins_amt is not None and base and incoterm_code(c.get(D.LC, "incoterm") or c.get(D.INVOICE, "incoterm")) in {"CIF", "CIP"}:
        if ins_amt < 1.10 * base - 0.01:
            c.add("R15", K.DISCREPANCY, S.HIGH, "Insurance cover below 110% of CIF/CIP value",
                  f"Insured amount {ins_amt:,.2f} is below 110% of the invoice value ({1.1 * base:,.2f}).",
                  ucp="Art. 28(f)(ii)", fix=f"Increase cover to at least {1.1 * base:,.2f}.",
                  ev=((D.INSURANCE, "insured_amount"), (D.INVOICE, "total_amount")))


@document_rule("R20", "Country of origin")
def origin(c: Ctx):
    lc_o, coo_o = c.get(D.LC, "country_of_origin"), c.get(D.COO, "country_of_origin")
    if lc_o and coo_o and norm_text(lc_o) not in norm_text(coo_o) and norm_text(coo_o) not in norm_text(lc_o):
        c.add("R20", K.DISCREPANCY, S.HIGH, "Country of origin differs from the LC",
              f"Certificate of origin: \"{coo_o}\"; LC requires origin \"{lc_o}\".", ucp="Art. 14(d)", lc_ref="45A",
              fix="Obtain a certificate showing the origin stated in the LC.",
              ev=((D.COO, "country_of_origin"), (D.LC, "country_of_origin")))


def consignee_required(c: Ctx) -> Optional[str]:
    """Who the B/L must be made out to: the extracted field, or else read from 46A wording."""
    req = c.get(D.LC, "bl_consignee_required")
    if req:
        return req
    import re

    for item in c.get(D.LC, "documents_required") or []:
        if re.search(r"bill", str(item), re.I):
            m = re.search(r"(?:made out|consigned)\s+(to\s+(?:the\s+)?order\s+of\s+[^,;.]+|to\s+[^,;.]+)", str(item), re.I)
            if m:
                return m.group(1).strip()[0].upper() + m.group(1).strip()[1:]
    return None


@document_rule("R21", "B/L consignee as required")
def consignee(c: Ctx):
    req, act = consignee_required(c), c.get(D.BL, "consignee")
    if req and act:
        from rapidfuzz import fuzz
        if fuzz.token_set_ratio(norm_text(req), norm_text(act)) < 85:
            c.add("R21", K.DISCREPANCY, S.HIGH, "B/L consignee not as required by the LC",
                  f"LC requires consignee \"{req}\"; B/L shows \"{act}\".", ucp="Art. 14(d)", lc_ref="46A",
                  fix=f"Ask the carrier to show the consignee as: \"{req}\".", ev=((D.BL, "consignee"), (D.LC, "bl_consignee_required")))


@document_rule("R22", "Trade term (Incoterm) matches")
def incoterm(c: Ctx):
    a, b = incoterm_code(c.get(D.LC, "incoterm")), incoterm_code(c.get(D.INVOICE, "incoterm"))
    if a and b and a != b:
        c.add("R22", K.DISCREPANCY, S.MEDIUM, "Invoice trade term differs from the LC",
              f"LC: {c.get(D.LC, 'incoterm')}; invoice: {c.get(D.INVOICE, 'incoterm')}.", ucp="Art. 18(c) / 14(d)",
              lc_ref="45A", fix=f"Show {c.get(D.LC, 'incoterm')} on the invoice.", ev=((D.INVOICE, "incoterm"), (D.LC, "incoterm")))


@document_rule("R23", "Freight notation consistent with trade term")
def freight(c: Ctx):
    term = incoterm_code(c.get(D.LC, "incoterm"))
    if term in {"CFR", "CIF", "CPT", "CIP"} and "collect" in norm_text(c.get(D.BL, "freight")):
        c.add("R23", K.DISCREPANCY, S.MEDIUM, "B/L shows 'freight collect' under a freight-paid trade term",
              f"Trade term {term} means the seller pays freight, but the B/L says \"{c.get(D.BL, 'freight')}\".",
              ucp="Art. 14(d) (verify against ISBP 821)", fix="Ask the carrier to mark the B/L 'freight prepaid'.",
              ev=((D.BL, "freight"), (D.LC, "incoterm")))


@document_rule("R24", "LC number on the invoice")
def lc_number(c: Ctx):
    a, b = c.get(D.LC, "lc_number"), c.get(D.INVOICE, "lc_number")
    if a and b and norm_text(a).replace(" ", "") != norm_text(b).replace(" ", ""):
        c.add("R24", K.DISCREPANCY, S.MEDIUM, "Invoice quotes the wrong LC number",
              f"Invoice shows LC number \"{b}\"; the LC number is \"{a}\".", ucp="Art. 14(d)", lc_ref="20",
              fix=f"Correct the LC number to {a}.", ev=((D.INVOICE, "lc_number"), (D.LC, "lc_number")))
