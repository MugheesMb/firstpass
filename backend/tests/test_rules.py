"""Every planted error type must be caught on its own, and a clean case must stay clean.

Runs fully offline (AI_MODE=mock): extraction comes from the generator's ground truth,
so these tests check the rules engine, not Gemini.
"""
import random
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "datagen"))

from generate import BUYERS, DOC_ERRORS, GOODS, LC_ERRORS, Spec, build  # noqa: E402

from app import pipeline  # noqa: E402
from app.models import FindingKind  # noqa: E402
from app.normalize import same_company, same_place, to_date, to_number  # noqa: E402

COUNTED = {FindingKind.DISCREPANCY, FindingKind.POSSIBLE}


def _run(tmp_path, doc_errors=(), lc_errors=(), goods=0, buyer=0):
    spec = Spec("t", GOODS[goods], BUYERS[buyer], random.Random(3), list(doc_errors), list(lc_errors), cif=True)
    build(spec, tmp_path / "t")
    case = pipeline.load_demo_case(tmp_path / "t")
    doc = pipeline.run_document_check(case)
    lc = pipeline.run_lc_review(case)
    return ({f.rule_id for f in doc.findings if f.kind in COUNTED},
            {f.rule_id for f in lc.findings if f.kind == FindingKind.LC_RISK}, doc, lc)


def test_clean_case_has_no_findings(tmp_path):
    d, l, doc, _ = _run(tmp_path)
    assert d == set() and l == set()
    assert "No issues found" in doc.summary and "not a guarantee" in doc.summary


@pytest.mark.parametrize("err", sorted(DOC_ERRORS))
def test_each_document_error_detected(tmp_path, err):
    d, _, _, _ = _run(tmp_path, doc_errors=[err])
    assert d == {DOC_ERRORS[err]}, f"{err}: expected {DOC_ERRORS[err]}, got {d}"


@pytest.mark.parametrize("err", sorted(LC_ERRORS))
def test_each_lc_risk_detected(tmp_path, err):
    _, l, _, _ = _run(tmp_path, lc_errors=[err])
    assert LC_ERRORS[err] in l


@pytest.mark.parametrize("g", range(len(GOODS)))
def test_every_product_line_clean(tmp_path, g):
    d, l, _, _ = _run(tmp_path, goods=g, buyer=g % len(BUYERS))
    assert d == set() and l == set()


def test_findings_carry_evidence_boxes(tmp_path):
    _, _, doc, _ = _run(tmp_path, doc_errors=["late_shipment"])
    f = next(f for f in doc.findings if f.rule_id == "R02")
    assert f.evidence and all(e.box_2d and len(e.box_2d) == 4 for e in f.evidence)
    assert f.ucp_ref and f.suggested_fix


def test_normalisation():
    assert to_date("261104") == date(2026, 11, 4)
    assert to_date("06/11/2026") == date(2026, 11, 6)
    assert to_date("November 06, 2026") == date(2026, 11, 6)
    assert to_date("2026-11-04") == date(2026, 11, 4)
    assert to_number("USD 51,500.00") == 51500.0
    assert to_number("10/10") == 10
    assert same_company("Indus Home Textiles (Pvt) Ltd", "INDUS HOME TEXTILES PRIVATE LIMITED")
    assert not same_company("Nordhaven Retail B.V.", "Nordhaven Sourcing Services B.V.")
    assert same_place("Karachi, Pakistan", "Port of Karachi, Pakistan")
    assert not same_place("Karachi, Pakistan", "Port Qasim, Pakistan")


def test_consignee_rule_reads_46a_when_field_missing():
    """If extraction leaves bl_consignee_required empty, R21 still works from the 46A wording."""
    import json
    from pathlib import Path

    from app import pipeline
    from app.ai.judge import MockJudge
    from app.models import DocType

    d = Path(__file__).resolve().parents[2] / "data" / "testset" / "case_014"
    case = pipeline.load_demo_case(d)
    case.first(DocType.LC).data["bl_consignee_required"] = None
    rep = pipeline.run_document_check(case, judge=MockJudge())
    assert "R21" in {f.rule_id for f in rep.findings}
