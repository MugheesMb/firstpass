"""Turn printed values into comparable values. No AI here: this must be exact."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from dateutil import parser as dparser
from rapidfuzz import fuzz

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def to_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    s = str(v).strip()
    # SWIFT style YYMMDD (e.g. 261015)
    if re.fullmatch(r"\d{6}", s):
        try:
            return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:]))
        except ValueError:
            return None
    try:
        # dayfirst: trade documents in Asia/Europe usually print DD/MM/YYYY
        return dparser.parse(s, dayfirst=not re.match(r"^\d{4}-", s), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def to_number(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = _NUM.search(str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def currency_of(*vals: Optional[str]) -> Optional[str]:
    for v in vals:
        if v:
            m = re.search(r"\b([A-Z]{3})\b", str(v).upper())
            if m:
                return m.group(1)
    return None


_COMPANY_NOISE = r"\b(pvt|private|ltd|limited|llc|inc|co|company|corp|corporation|plc|pte|sdn|bhd|gmbh|bv|sa)\b"


def norm_text(v: Optional[str]) -> str:
    if not v:
        return ""
    s = str(v).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9%\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_company(v: Optional[str]) -> str:
    s = re.sub(_COMPANY_NOISE, " ", norm_text(v))
    return re.sub(r"\s+", " ", s).strip()


def same_company(a: Optional[str], b: Optional[str], threshold: int = 90) -> Optional[bool]:
    if not a or not b:
        return None
    na, nb = norm_company(a), norm_company(b)
    return fuzz.token_set_ratio(na, nb) >= threshold


def same_place(a: Optional[str], b: Optional[str], threshold: int = 85) -> Optional[bool]:
    """'Karachi, Pakistan' == 'Port of Karachi'. 'Any port in Pakistan' handled loosely."""
    if not a or not b:
        return None
    na = re.sub(r"\b(port|of|seaport|harbour|harbor|terminal)\b", " ", norm_text(a))
    nb = re.sub(r"\b(port|of|seaport|harbour|harbor|terminal)\b", " ", norm_text(b))
    na, nb = re.sub(r"\s+", " ", na).strip(), re.sub(r"\s+", " ", nb).strip()
    if "any" in na.split() or "any" in nb.split():
        return fuzz.partial_ratio(na, nb) >= 60
    return fuzz.token_set_ratio(na, nb) >= threshold


def same_value(a: Optional[str], b: Optional[str], rel_tol: float = 0.0) -> Optional[bool]:
    x, y = to_number(a), to_number(b)
    if x is None or y is None:
        return None
    if rel_tol == 0:
        return abs(x - y) < 1e-9
    return abs(x - y) <= rel_tol * max(abs(x), abs(y))


def incoterm_code(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    m = re.search(r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b", str(v).upper())
    return m.group(1) if m else None


COUNTABLE_UNITS = {"pcs", "pieces", "piece", "units", "unit", "cartons", "carton", "sets", "set", "pairs", "pair",
                   "boxes", "box", "bales", "bale", "dozen", "doz", "rolls", "roll", "nos", "no"}


def is_countable(unit: Optional[str]) -> bool:
    return norm_text(unit) in COUNTABLE_UNITS


_STOP = {"and", "the", "of", "for", "with", "as", "per", "in", "a", "an", "to", "on", "proforma", "invoice", "no",
         "dated", "according", "goods", "terms", "made", "from", "pakistan", "origin"}


def keywords(v: Optional[str]) -> set[str]:
    return {w for w in norm_text(v).split() if len(w) > 2 and w not in _STOP and not w.isdigit()}
