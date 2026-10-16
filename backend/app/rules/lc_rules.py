"""Mode A: review the LC terms BEFORE the exporter accepts the credit.

A bad term fixed now costs one email to the buyer. The same term discovered after shipment
costs discrepancy fees and weeks of delay.
"""
from __future__ import annotations

import re

from ..models import DocType as D, FindingKind as K, Severity as S
from ..normalize import incoterm_code, norm_text, same_company, to_date, to_number
from .base import Ctx, lc_rule

SOFT_CLAUSE = re.compile(
    r"(signed|issued|countersigned|approved|authori[sz]ed)\s+by\s+(the\s+)?(applicant|buyer|importer)"
    r"|applicant'?s?\s+(approval|consent|acceptance|confirmation)"
    r"|subject\s+to\s+(the\s+)?(applicant|buyer|approval|receipt)"
    r"|at\s+the\s+(sole\s+)?discretion",
    re.I,
)
NAMED_ISSUER = re.compile(r"issued\s+by\s+([A-Z][A-Za-z0-9&.\- ]{2,40})")
LEGALISED = re.compile(r"legali[sz]ed|consulari[sz]ed|attested by .*embassy|consulate", re.I)


@lc_rule("A09", "Expiry after latest shipment date")
def expiry_before_shipment(c: Ctx):
    exp, latest = to_date(c.get(D.LC, "expiry_date")), to_date(c.get(D.LC, "latest_shipment_date"))
    if exp and latest and exp < latest:
        c.add("A09", K.LC_RISK, S.HIGH, "LC expires before the latest shipment date",
              f"Expiry {exp:%d %b %Y} is earlier than latest shipment {latest:%d %b %Y}. The credit cannot be used as written.",
              lc_ref="31D / 44C", fix="Ask the buyer to extend the expiry date.",
              ev=((D.LC, "expiry_date"), (D.LC, "latest_shipment_date")))


@lc_rule("A01", "Enough time to ship")
def timeline(c: Ctx):
    ready, latest = to_date(c.case.goods_ready_date), to_date(c.get(D.LC, "latest_shipment_date"))
    if not ready or not latest:
        return
    gap = (latest - ready).days
    if gap < 0:
        c.add("A01", K.LC_RISK, S.HIGH, "Goods will be ready after the latest shipment date",
              f"Your goods are expected ready on {ready:%d %b %Y}, {abs(gap)} day(s) after the latest shipment date {latest:%d %b %Y}.",
              lc_ref="44C", fix=f"Request an amendment extending the latest shipment date by at least {abs(gap) + 10} days.",
              ev=((D.LC, "latest_shipment_date"),))
    elif gap < 7:
        c.add("A01", K.LC_RISK, S.MEDIUM, "Very little time between goods ready and latest shipment",
              f"Only {gap} day(s) between goods ready ({ready:%d %b %Y}) and the latest shipment date ({latest:%d %b %Y}). "
              "Any delay in booking, inspection or customs means late shipment.",
              lc_ref="44C", fix="Request at least 10-14 extra days on the latest shipment date.",
              ev=((D.LC, "latest_shipment_date"),))


@lc_rule("A02", "Presentation window after shipment")
def squeezed_window(c: Ctx):
    exp, latest = to_date(c.get(D.LC, "expiry_date")), to_date(c.get(D.LC, "latest_shipment_date"))
    days = int(to_number(c.get(D.LC, "presentation_days")) or 21)
    if exp and latest and 0 <= (exp - latest).days < days:
        c.add("A02", K.LC_RISK, S.MEDIUM, "Expiry date shortens the presentation period",
              f"If you ship on the latest shipment date you will have only {(exp - latest).days} day(s) to present, "
              f"not {days}.", ucp="Art. 6(e) / 14(c)", lc_ref="31D / 48",
              fix=f"Ask for expiry at least {days} days after the latest shipment date.",
              ev=((D.LC, "expiry_date"), (D.LC, "latest_shipment_date")))


@lc_rule("A03", "Presentation period length")
def short_presentation(c: Ctx):
    days = to_number(c.get(D.LC, "presentation_days"))
    if days is not None and days < 10:
        c.add("A03", K.LC_RISK, S.MEDIUM, f"Short presentation period ({days:g} days)",
              "Collecting the B/L, insurance and certificates usually takes over a week.",
              lc_ref="48", fix="Request 21 days after shipment (the UCP 600 default).", ev=((D.LC, "presentation_days"),))


@lc_rule("A04", "Place of expiry")
def expiry_abroad(c: Ctx):
    place, country = c.get(D.LC, "expiry_place"), c.get(D.LC, "beneficiary_country")
    if place and country and norm_text(country) not in norm_text(place):
        c.add("A04", K.LC_RISK, S.HIGH, "LC expires outside your country",
              f"The LC expires in \"{place}\". Your documents must physically reach that place before expiry, "
              "which eats into your presentation time.", ucp="Art. 6(d)", lc_ref="31D",
              fix=f"Ask for the place of expiry to be {country} (at the advising/nominated bank's counters).",
              ev=((D.LC, "expiry_place"),))


@lc_rule("A05", "Conditions outside the exporter's control (soft clauses)")
def soft_clauses(c: Ctx):
    items = (c.get(D.LC, "additional_conditions") or []) + (c.get(D.LC, "documents_required") or [])
    for item in items:
        if SOFT_CLAUSE.search(item):
            fld = "additional_conditions" if item in (c.get(D.LC, "additional_conditions") or []) else "documents_required"
            c.add("A05", K.LC_RISK, S.HIGH, "Condition that depends on the buyer (soft clause)",
                  f"\"{item}\". The buyer can block payment simply by not providing or signing this.",
                  lc_ref="46A / 47A", fix="Ask for this condition to be deleted, or replaced by a document from an independent party.",
                  ev=((D.LC, fld),))


@lc_rule("A06", "Insurance requirement vs trade term")
def insurance_vs_incoterm(c: Ctx):
    term = incoterm_code(c.get(D.LC, "incoterm"))
    wants_ins = any("insurance" in x.lower() for x in (c.get(D.LC, "documents_required") or []))
    if wants_ins and term in {"EXW", "FCA", "FAS", "FOB", "CFR", "CPT"}:
        c.add("A06", K.LC_RISK, S.MEDIUM, f"LC asks you for insurance under {term}",
              f"Under {term} the buyer normally arranges insurance, but the LC requires an insurance document from you.",
              lc_ref="45A / 46A", fix="Confirm who insures. Either remove the insurance document or change the trade term to CIF/CIP and price it.",
              ev=((D.LC, "incoterm"), (D.LC, "documents_required")))


@lc_rule("A07", "Beneficiary name matches your company")
def beneficiary_name(c: Ctx):
    if c.case.company_name and same_company(c.case.company_name, c.get(D.LC, "beneficiary")) is False:
        c.add("A07", K.LC_RISK, S.HIGH, "Beneficiary name does not match your company",
              f"LC beneficiary: \"{c.get(D.LC, 'beneficiary')}\"; your registered name: \"{c.case.company_name}\". "
              "Every document you issue must match the LC exactly.", lc_ref="59",
              fix=f"Request an amendment of the beneficiary name to \"{c.case.company_name}\".", ev=((D.LC, "beneficiary"),))


@lc_rule("A08", "Documents that may be hard to obtain")
def hard_documents(c: Ctx):
    for item in c.get(D.LC, "documents_required") or []:
        m = NAMED_ISSUER.search(item)
        named = m and not re.search(r"applicant|beneficiary|carrier|master|insurer|chamber", m.group(1), re.I)
        if named or LEGALISED.search(item):
            c.add("A08", K.LC_RISK, S.MEDIUM, "Required document may be slow or hard to obtain",
                  f"\"{item}\". Confirm you can obtain it, in this exact form, within the presentation period.",
                  lc_ref="46A", fix="If not, ask to replace it with a document you can obtain, or remove the named issuer.",
                  ev=((D.LC, "documents_required"),))


@lc_rule("A99", "AI review of free-text terms")
def ai_review(c: Ctx):
    lc = c.doc(D.LC)
    if not lc:
        return
    from rapidfuzz import fuzz

    found = [f for f in c.findings if f.kind == K.LC_RISK]
    already = [f"{f.title}: {f.detail}" for f in found]
    for r in c.judge.review_lc(lc.data, c.case.company_name, already):
        # safety net: skip an AI risk about the same clause a rule already flagged
        if r.clause and any(fuzz.partial_ratio(r.clause.lower(), f.detail.lower()) >= 85 for f in found):
            continue
        sev = {"high": S.HIGH, "medium": S.MEDIUM}.get((r.severity or "").lower(), S.LOW)
        c.add("A99", K.LC_RISK, sev, r.title, r.detail + (f" (Clause: {r.clause})" if r.clause else ""),
              fix=r.suggested_amendment, ev=((D.LC, "additional_conditions"),))
