"""Decisions, re-checks, corrected documents, waiver requests and the activity log."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import pipeline, storage
from app.main import app
from app.models import DocType

client = TestClient(app)
DEMO = Path(__file__).resolve().parents[1] / "demo_cases" / "demo_faisalabad_towels"


def _by_rule(rep):
    return {f["rule_id"]: f for f in rep["findings"]}


def test_fix_recheck_loop():
    cid = client.post("/api/demo/demo_faisalabad_towels").json()["id"]
    run1 = client.post(f"/api/cases/{cid}/check", json={}).json()
    assert run1["run"] == 1 and set(_by_rule(run1)) == {"R02", "R05", "R08"}
    late, over = _by_rule(run1)["R02"], _by_rule(run1)["R05"]

    # accepting or disputing needs a reason
    assert client.patch(f"/api/cases/{cid}/findings/{late['id']}", json={"status": "accepted"}).status_code == 400
    client.patch(f"/api/cases/{cid}/findings/{late['id']}", json={"status": "accepted", "note": "Buyer agreed by phone"})
    client.patch(f"/api/cases/{cid}/findings/{over['id']}", json={"status": "fixed"})  # claimed fixed, but not re-uploaded

    run2 = client.post(f"/api/cases/{cid}/check", json={}).json()
    f2 = _by_rule(run2)
    assert run2["run"] == 2
    assert f2["R02"]["status"] == "accepted" and f2["R02"]["note"] == "Buyer agreed by phone"   # decision carried over
    assert f2["R05"]["status"] == "open" and "Still present" in f2["R05"]["history"][-1]["note"]  # fixed claim reopened
    assert run2["diff"]["new"] == [] and run2["diff"]["resolved"] == []

    # upload a corrected invoice (amount and description now match the LC)
    case = storage.cases().get(cid)
    truth = json.loads((DEMO / "commercial_invoice.truth.json").read_text())
    lc = json.loads((DEMO / "lc.truth.json").read_text())["data"]
    truth["data"]["total_amount"], truth["data"]["goods_description"] = lc["amount"], lc["goods_description"]
    doc = pipeline.add_document(case, (DEMO / "commercial_invoice.pdf").read_bytes(), "commercial_invoice_v2.pdf",
                                "application/pdf", DocType.INVOICE, truth)
    assert doc.version == 2

    run3 = client.post(f"/api/cases/{cid}/check", json={}).json()
    assert set(_by_rule(run3)) == {"R02"}
    assert sorted(run3["diff"]["resolved"]) == sorted([over["title"], _by_rule(run1)["R08"]["title"]])
    assert {r["rule_id"] for r in run3["resolved"]} == {"R05", "R08"}

    # waiver request covers the accepted, unfixable discrepancy
    w = client.post(f"/api/cases/{cid}/waiver-request").json()
    assert "Shipped after the latest shipment date" in w["body"] and "16(b)" in w["body"]

    full = client.get(f"/api/cases/{cid}").json()
    kinds = [e["kind"] for e in full["events"]]
    assert kinds.count("check") == 3 and "decision" in kinds and "draft" in kinds
    assert any("replaces version 1" in e["text"] for e in full["events"])
    assert [r["run"] for r in full["runs"] if r["mode"] == "document_check"] == [1, 2, 3]

    row = next(r for r in client.get("/api/cases").json() if r["id"] == cid)
    assert row["counts"]["accepted"] == 1 and row["counts"]["fixed"] == 2 and row["lc_number"]
    assert row["readiness"] == 100  # nothing open: the remaining item is accepted


def test_waiver_needs_accepted_items():
    cid = client.post("/api/demo/demo_clean").json()["id"]
    client.post(f"/api/cases/{cid}/check", json={})
    assert client.post(f"/api/cases/{cid}/waiver-request").status_code == 400


def test_sample_corrections_and_reupload():
    cid = client.post("/api/demo/demo_sialkot_footballs").json()["id"]
    run1 = client.post(f"/api/cases/{cid}/check", json={}).json()
    assert set(_by_rule(run1)) == {"R10", "R11", "R14"}
    items = client.get(f"/api/cases/{cid}/sample-corrections").json()
    assert {i["doc_type"] for i in items} == {"bill_of_lading", "insurance_certificate"}
    for i in items:
        assert client.post(f"/api/cases/{cid}/sample-corrections/{i['doc_type']}").status_code == 200
    run2 = client.post(f"/api/cases/{cid}/check", json={}).json()
    assert run2["findings"] == [] and len(run2["diff"]["resolved"]) == 3

    # in mock mode a sample PDF uploaded by hand is recognised by its content
    pdf = Path(__file__).resolve().parents[1] / "demo_cases" / "demo_clean" / "commercial_invoice.pdf"
    cid2 = client.post("/api/cases", json={}).json()["id"]
    doc = client.post(f"/api/cases/{cid2}/documents", files={"file": ("my_invoice.pdf", pdf.read_bytes(), "application/pdf")}).json()
    assert doc["doc_type"] == "commercial_invoice" and doc["data"]["total_amount"]


def test_ai_review_does_not_repeat_a_rule_finding():
    """The AI LC review gets the rule findings and any risk on the same clause is dropped."""
    from app.ai.judge import LcRisk, MockJudge

    seen = {}

    class Judge(MockJudge):
        def review_lc(self, lc, company_name, already=()):
            seen["already"] = list(already)
            return [LcRisk(title="Soft clause", detail="buyer controls payment", severity="high",
                           clause="Inspection certificate signed by the applicant's representative must accompany the documents."),
                    LcRisk(title="Something new", detail="different risk", severity="medium", clause="Unique clause XYZ")]

    from pathlib import Path
    from app import pipeline

    demo = Path(__file__).resolve().parents[1] / "demo_cases" / "demo_faisalabad_towels"
    case = pipeline.load_demo_case(demo)
    rep = pipeline.run_lc_review(case, judge=Judge())
    ai = [f for f in rep.findings if f.rule_id == "A99"]
    assert any("soft clause" in a.lower() for a in seen["already"])
    assert [f.title for f in ai] == ["Something new"]
