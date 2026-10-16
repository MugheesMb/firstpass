from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_demo_flow():
    assert client.get("/api/health").json()["ok"]
    demos = client.get("/api/demo").json()
    names = {d["name"]: d for d in demos}
    assert "demo_faisalabad_towels" in names and names["demo_faisalabad_towels"]["group"] == "demo"
    assert "shipped late" in names["demo_faisalabad_towels"]["document_problems"]
    assert names["demo_clean"]["document_problems"] == []
    assert any(d["group"] == "test set" for d in demos)  # data/testset is listed in development
    tc = next(d for d in demos if d["group"] == "test set" and d["document_problems"])
    loaded = client.post(f"/api/demo/{tc['name']}").json()
    rep_tc = client.post(f"/api/cases/{loaded['id']}/check", json={}).json()
    assert {f["rule_id"] for f in rep_tc["findings"] if f["kind"] in ("discrepancy", "possible")} >= set(
        r for r in tc["expected_rules"] if r.startswith("R"))

    case = client.post("/api/demo/demo_faisalabad_towels").json()
    cid = case["id"]
    assert len(case["documents"]) == 6

    lc = client.post(f"/api/cases/{cid}/lc-review").json()
    assert {f["rule_id"] for f in lc["findings"]} >= {"A01", "A05"}

    rep = client.post(f"/api/cases/{cid}/check", json={}).json()
    assert {f["rule_id"] for f in rep["findings"]} == {"R02", "R05", "R08"}

    doc = case["documents"][0]
    img = client.get(f"/api/cases/{cid}/documents/{doc['id']}/pages/1.png")
    assert img.status_code == 200 and img.content[:4] == b"\x89PNG"

    fid = rep["findings"][0]["id"]
    assert client.post(f"/api/cases/{cid}/findings/{fid}/draft-fix").json()["text"]
    updated = client.patch(f"/api/cases/{cid}/findings/{fid}", json={"status": "fixed"}).json()
    assert updated["document_check"]["findings"][0]["status"] == "fixed"

    ins = client.get(f"/api/cases/{cid}/insights").json()
    assert ins["readiness"]["open"] == 2 and ins["readiness"]["verdict"] == "Fix before presenting"
    value = next(r for r in ins["matrix"]["rows"] if r["label"] == "Value")
    assert value["cells"]["commercial_invoice"]["status"] == "issue"
    assert next(r for r in ins["matrix"]["rows"] if r["label"] == "Packages")["cells"]["bill_of_lading"]["status"] == "ok"
    keys = [p["key"] for p in ins["timeline"]]
    assert keys.index("latest_shipment") < keys.index("shipped")  # shipped late in this demo
    assert rep["trace"] and rep["trace"][0]["stage"] == "Read documents"
    assert case["documents"][0]["extraction"]["fields_found"] > 0

    email = client.post(f"/api/cases/{cid}/amendment-email").json()
    assert "amendment" in email["subject"].lower() and email["body"]


def test_upload_unknown_file_in_mock_mode():
    cid = client.post("/api/cases", json={"company_name": "Test Exports Ltd"}).json()["id"]
    from pathlib import Path

    pdf = Path(__file__).resolve().parents[1] / "demo_cases" / "demo_clean" / "lc.pdf"
    r = client.post(f"/api/cases/{cid}/documents", files={"file": ("lc.pdf", pdf.read_bytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["doc_type"] == "letter_of_credit"
