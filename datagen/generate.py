"""Generate synthetic Letter of Credit presentations with planted discrepancies.

Each case folder contains six PDFs (LC, invoice, B/L, packing list, certificate of origin,
insurance when CIF), a ground-truth JSON per document (values exactly as printed + the box
where each value sits on the page) and case.json with the answer key.

All companies, banks and people are fictional.

Usage:
  python datagen/generate.py --out data/testset --n 40 --seed 7
  python datagen/generate.py --demo --out backend/demo_cases
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

W, H = A4

# ----------------------------------------------------------------------------- catalogue
GOODS = [
    dict(key="towels", exporter="Indus Home Textiles (Pvt) Ltd", city="Faisalabad", country="Pakistan", pol="Karachi, Pakistan",
         desc="100% cotton bath towels, 500 GSM, size 70 x 140 cm", alt="100% cotton bath sheets, 500 GSM, size 70 x 140 cm",
         general="Cotton bath towels", conflict="Polyester bed sheets", unit="pcs", price=3.20, qty=(12000, 30000),
         per_carton=50, kg_per_unit=0.62),
    dict(key="footballs", exporter="Sialkot Pro Sports (Pvt) Ltd", city="Sialkot", country="Pakistan", pol="Karachi, Pakistan",
         desc="Hand-stitched PU leather footballs, size 5, FIFA Quality", alt="Machine-stitched PU leather footballs, size 5, FIFA Quality",
         general="Footballs", conflict="Cricket bats", unit="pcs", price=8.50, qty=(3000, 9000), per_carton=25, kg_per_unit=0.45),
    dict(key="rice", exporter="Lahore Grain Exports Ltd", city="Lahore", country="Pakistan", pol="Karachi, Pakistan",
         desc="Pakistani basmati rice 1121 steam, crop 2026, packed in 25 kg PP bags",
         alt="Pakistani long grain rice 1121 steam, crop 2026, packed in 25 kg PP bags",
         general="Basmati rice", conflict="Brown sugar", unit="MT", price=1150.0, qty=(50, 200), per_carton=None, kg_per_unit=1000),
    dict(key="gloves", exporter="Kasur Leather Works (Pvt) Ltd", city="Kasur", country="Pakistan", pol="Karachi, Pakistan",
         desc="Leather safety gloves, cow split leather, size L", alt="Leather work gloves, cow split leather, size L",
         general="Leather gloves", conflict="Cotton face masks", unit="pairs", price=1.85, qty=(20000, 60000), per_carton=120, kg_per_unit=0.15),
    dict(key="polo", exporter="Meghna Knit Composite Ltd", city="Gazipur", country="Bangladesh", pol="Chittagong, Bangladesh",
         desc="Men's 100% cotton knitted polo shirts, assorted colours", alt="Men's cotton blend knitted polo shirts, assorted colours",
         general="Cotton polo shirts", conflict="Denim jeans", unit="pcs", price=4.10, qty=(10000, 40000), per_carton=60, kg_per_unit=0.22),
    dict(key="cashew", exporter="Saigon Nut Traders JSC", city="Ho Chi Minh City", country="Vietnam", pol="Ho Chi Minh City, Vietnam",
         desc="Vietnamese cashew kernels WW320, packed in vacuum tins", alt="Vietnamese cashew kernels WW240, packed in vacuum tins",
         general="Cashew kernels", conflict="Black pepper", unit="MT", price=7200.0, qty=(15, 60), per_carton=None, kg_per_unit=1000),
]
BUYERS = [
    dict(name="Nordhaven Retail B.V.", city="Rotterdam", country="Netherlands", pod="Rotterdam, Netherlands",
         bank="Rotterdam Mercantile Bank N.V.", agent="Nordhaven Sourcing Services B.V."),
    dict(name="Hanse Sport GmbH", city="Hamburg", country="Germany", pod="Hamburg, Germany",
         bank="Hanseatic Trade Bank AG", agent="Hanse Sourcing Agency GmbH"),
    dict(name="Gulf Pantry Trading LLC", city="Dubai", country="UAE", pod="Jebel Ali, UAE",
         bank="Gulf Commercial Bank PJSC", agent="Pantry Logistics FZE"),
    dict(name="Lion City Provisions Pte Ltd", city="Singapore", country="Singapore", pod="Singapore",
         bank="Straits Merchant Bank Ltd", agent="Lion City Buying Office Pte Ltd"),
    dict(name="Maple Leaf Outfitters Inc", city="Vancouver", country="Canada", pod="Vancouver, Canada",
         bank="Pacific Northern Bank", agent="Maple Leaf Trading Agents Inc"),
]
VESSELS = ["MV Kota Harmoni", "MV Indus Star", "MSC Arabian Pearl (fictional)", "MV Straits Voyager", "MV Bay of Bengal Trader"]

# error name -> (mode, rule id, needs CIF)
DOC_ERRORS = {
    "late_shipment": "R02", "late_presentation": "R03", "expired": "R01", "amount_over": "R05", "currency": "R04",
    "qty_mismatch_pl": "R10", "packages_mismatch": "R10", "weight_mismatch": "R10", "description_invoice": "R08",
    "description_conflict_bl": "R09", "invoice_party": "R07", "port_pol": "R11", "no_onboard": "R12", "claused": "R13",
    "insurance_late": "R14", "insurance_under": "R15", "missing_doc": "R16", "origin": "R20", "consignee": "R21",
    "incoterm": "R22", "freight_collect": "R23", "lc_number": "R24",
}
CIF_ONLY = {"insurance_late", "insurance_under", "freight_collect"}
LC_ERRORS = {"soft_clause": "A05", "tight_timeline": "A01", "expiry_abroad": "A04", "name_mismatch": "A07",
             "hard_doc": "A08", "short_presentation": "A03", "insurance_fob": "A06", "expiry_squeeze": "A02"}
INCOMPATIBLE = [{"expired", "late_presentation"}, {"expired", "short_presentation"}, {"late_presentation", "short_presentation"},
                {"expired", "expiry_squeeze"}, {"late_presentation", "expiry_squeeze"}, {"insurance_fob", "incoterm"},
                {"no_onboard", "late_shipment"}, {"currency", "amount_over"}]


# ----------------------------------------------------------------------------- pdf helper
class Pdf:
    def __init__(self, path: Path, title: str, issuer_lines: list[str]):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.c.setTitle(title)
        self.ev: list[dict] = []
        self.y = H - 50
        self.c.setFont("Helvetica-Bold", 11)
        for i, line in enumerate(issuer_lines):
            self.c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 11 if i == 0 else 8.5)
            self.c.drawString(50, self.y, line)
            self.y -= 13 if i == 0 else 11
        self.y -= 10
        self.c.setFont("Helvetica-Bold", 15)
        self.c.drawCentredString(W / 2, self.y, title)
        self.y -= 8
        self.c.line(50, self.y, W - 50, self.y)
        self.y -= 22

    def _box(self, fld, x0, ytop, x1, ybot, text):
        self.ev.append(dict(field=fld, page=1, text=text, confidence=1.0,
                            box_2d=[int((H - ytop) / H * 1000), int(x0 / W * 1000), int((H - ybot) / H * 1000), int(x1 / W * 1000)]))

    def row(self, label: str, fld: str | None, value, x_val: float = 215, fs: float = 9.5, width: float = 330):
        if value is None or value == "":
            return
        text = str(value)
        self.c.setFont("Helvetica-Bold", fs)
        self.c.drawString(50, self.y, label)
        self.c.setFont("Helvetica", fs)
        lines = simpleSplit(text, "Helvetica", fs, width)
        top = self.y + fs * 0.85
        maxw = 0
        for ln in lines:
            self.c.drawString(x_val, self.y, ln)
            maxw = max(maxw, self.c.stringWidth(ln, "Helvetica", fs))
            self.y -= fs + 3.5
        if fld:
            self._box(fld, x_val - 1, top, x_val + maxw + 1, self.y + fs + 3.5 - fs * 0.3, text)
        self.y -= 4

    def list_rows(self, label: str, fld: str, items: list[str], fs: float = 9.0):
        self.c.setFont("Helvetica-Bold", fs)
        self.c.drawString(50, self.y, label)
        self.y -= fs + 5
        top = self.y + fs * 0.85
        maxx = 0
        for i, it in enumerate(items, 1):
            for ln in simpleSplit(f"{i}. {it}", "Helvetica", fs, 470):
                self.c.setFont("Helvetica", fs)
                self.c.drawString(70, self.y, ln)
                maxx = max(maxx, 70 + self.c.stringWidth(ln, "Helvetica", fs))
                self.y -= fs + 3
        if items:
            self._box(fld, 69, top, maxx + 1, self.y + fs + 3 - fs * 0.3, " | ".join(items))
        self.y -= 6

    def stamp(self, fld: str, text: str, value):
        self.c.saveState()
        self.c.setStrokeColorRGB(0.1, 0.25, 0.6)
        self.c.setFillColorRGB(0.1, 0.25, 0.6)
        self.c.setFont("Helvetica-Bold", 12)
        w = self.c.stringWidth(text, "Helvetica-Bold", 12)
        x, y = W - 70 - w, 170
        self.c.rect(x - 8, y - 8, w + 16, 26, stroke=1, fill=0)
        self.c.drawString(x, y, text)
        self.c.restoreState()
        self._box(fld, x - 8, y + 18, x + w + 8, y - 8, text)

    def signature(self, who: str):
        self.c.setFont("Helvetica", 8.5)
        self.c.line(50, 120, 230, 120)
        self.c.drawString(50, 108, f"For and on behalf of {who}")
        self.c.drawString(50, 97, "Authorised signatory")

    def save(self):
        self.c.setFont("Helvetica-Oblique", 7)
        self.c.drawString(50, 40, "SYNTHETIC TEST DOCUMENT - fictional parties - generated for FirstPass evaluation")
        self.c.showPage()
        self.c.save()


def swift(d: date) -> str:
    return d.strftime("%y%m%d")


def money(cur: str, v: float) -> str:
    return f"{cur} {v:,.2f}"


def human(d: date, style: int) -> str:
    return [d.strftime("%d %b %Y"), d.strftime("%d/%m/%Y"), d.strftime("%B %d, %Y")][style % 3]


# ----------------------------------------------------------------------------- case model
@dataclass
class Spec:
    case_id: str
    goods: dict
    buyer: dict
    rng: random.Random
    doc_errors: list[str] = field(default_factory=list)
    lc_errors: list[str] = field(default_factory=list)
    cif: bool = True
    rng_seed: int = 0


def build(spec: Spec, out: Path) -> dict:
    r, g, b = spec.rng, spec.goods, spec.buyer
    de, le = set(spec.doc_errors), set(spec.lc_errors)
    out.mkdir(parents=True, exist_ok=True)
    dstyle = r.randint(0, 2)

    cur = "EUR" if b["country"] in {"Netherlands", "Germany"} and r.random() < 0.4 else "USD"
    term = "FOB" if "insurance_fob" in le else ("CIF" if spec.cif or (de & CIF_ONLY) else "CFR")
    incoterm = f"{term} {b['pod'].split(',')[0]}" if term in {"CIF", "CFR"} else f"FOB {g['pol'].split(',')[0]}"
    lo, hi = g["qty"]
    qty = r.randint(lo, hi) if g["unit"] != "MT" else r.randint(lo, hi)
    if g["per_carton"]:
        qty = qty // g["per_carton"] * g["per_carton"]
    lc_amount = round(qty * g["price"], 2)
    tolerance = 10 if r.random() < 0.3 else 0

    issue = date(2026, 9, 1) + timedelta(days=r.randint(0, 25))
    latest = issue + timedelta(days=r.randint(40, 60))
    pres_days = 7 if "short_presentation" in le else 21
    expiry = latest + timedelta(days=(10 if "expiry_squeeze" in le else 25 + r.randint(0, 5)))
    ship = latest - timedelta(days=r.randint(2, 6))
    if "late_shipment" in de:
        ship = latest + timedelta(days=r.randint(1, 3))
    pres = ship + timedelta(days=(5 if pres_days == 7 else 10))
    if "late_presentation" in de:
        pres = ship + timedelta(days=r.randint(23, 26))
    if "expired" in de:
        expiry = ship + timedelta(days=12)
        pres = expiry + timedelta(days=3)
    goods_ready = latest - timedelta(days=(3 if "tight_timeline" in le else 15))

    lc_no = f"{b['bank'].split()[0][:3].upper()}/LC/26/{r.randint(1000, 9999)}"
    consignee_req = f"To order of {b['bank']}"
    docs_req = [
        "Signed commercial invoice in 3 originals",
        f"Full set of clean on board ocean bills of lading made out to order of {b['bank']}, marked freight "
        f"{'prepaid' if term in {'CIF', 'CFR'} else 'collect'}, notify applicant",
        "Packing list in 2 copies",
        f"Certificate of origin issued by the Chamber of Commerce in {g['country']}",
    ]
    if term == "CIF" or "insurance_fob" in le:
        docs_req.append("Insurance certificate covering 110% of CIF value, Institute Cargo Clauses (A)")
    if "hard_doc" in le:
        docs_req.append("Pre-shipment inspection certificate issued by Bureau Veritas Group")
    conditions = ["All documents must show this credit number.", "Third party documents acceptable except commercial invoice."]
    if "soft_clause" in le:
        conditions.append("Inspection certificate signed by the applicant's representative must accompany the documents.")
    expiry_place = f"{b['city']}, {b['country']}" if "expiry_abroad" in le else g["pol"]

    # ---------------- Letter of credit (MT700 style)
    lc = Pdf(out / "lc.pdf", "IRREVOCABLE DOCUMENTARY CREDIT (MT700)", [b["bank"], f"Trade Services, {b['city']}, {b['country']}"])
    lc.row(":20: Documentary credit number", "lc_number", lc_no)
    lc.row(":31C: Date of issue", "issue_date", swift(issue))
    lc.row(":31D: Date of expiry", "expiry_date", swift(expiry))
    lc.row("      Place of expiry", "expiry_place", expiry_place)
    lc.row(":50: Applicant", "applicant", b["name"])
    lc.row("      Applicant country", "applicant_country", b["country"])
    lc.row(":59: Beneficiary", "beneficiary", g["exporter"])
    lc.row("      Beneficiary country", "beneficiary_country", g["country"])
    lc.row(":32B: Currency code, amount", "amount", money(cur, lc_amount))
    if tolerance:
        lc.row(":39A: Percentage credit amount tolerance", "amount_tolerance_pct", f"{tolerance}/{tolerance}")
    lc.row(":43P: Partial shipments", "partial_shipments", r.choice(["prohibited", "allowed"]))
    lc.row(":43T: Transhipment", "transhipment", "allowed")
    lc.row(":44E: Port of loading", "port_of_loading", g["pol"])
    lc.row(":44F: Port of discharge", "port_of_discharge", b["pod"])
    lc.row(":44C: Latest date of shipment", "latest_shipment_date", swift(latest))
    lc.row(":45A: Description of goods", "goods_description", g["desc"])
    lc.row("      Quantity", "quantity", f"{qty:,}")
    lc.row("      Unit", "quantity_unit", g["unit"])
    lc.row("      Trade terms", "incoterm", incoterm)
    lc.row("      Origin", "country_of_origin", g["country"])
    lc.list_rows(":46A: Documents required", "documents_required", docs_req)
    lc.list_rows(":47A: Additional conditions", "additional_conditions", conditions)
    lc.row(":48: Period for presentation", "presentation_days", f"{pres_days} days after date of shipment")
    lc.save()
    lc_data = dict(lc_number=lc_no, issue_date=swift(issue), expiry_date=swift(expiry), expiry_place=expiry_place,
                   applicant=b["name"], applicant_country=b["country"], beneficiary=g["exporter"], beneficiary_country=g["country"],
                   issuing_bank=b["bank"], currency=cur, amount=money(cur, lc_amount),
                   amount_tolerance_pct=f"{tolerance}/{tolerance}" if tolerance else None,
                   latest_shipment_date=swift(latest), presentation_days=f"{pres_days} days after date of shipment",
                   port_of_loading=g["pol"], port_of_discharge=b["pod"],
                   partial_shipments=next(e["text"] for e in lc.ev if e["field"] == "partial_shipments"), transhipment="allowed",
                   incoterm=incoterm, goods_description=g["desc"], quantity=f"{qty:,}", quantity_unit=g["unit"],
                   country_of_origin=g["country"], bl_consignee_required=consignee_req, documents_required=docs_req,
                   additional_conditions=conditions, evidence=lc.ev)
    # the consignee requirement lives inside 46A; add evidence pointing at the documents list
    lc_data["evidence"] = lc.ev + [dict(next(e for e in lc.ev if e["field"] == "documents_required"), field="bl_consignee_required")]

    # ---------------- Invoice
    inv_total = lc_amount
    if "amount_over" in de:
        inv_total = round(lc_amount * (1 + tolerance / 100) * 1.03, 2)
    inv_cur = ("EUR" if cur == "USD" else "USD") if "currency" in de else cur
    inv_desc = g["alt"] if "description_invoice" in de else g["desc"]
    inv_to = b["agent"] if "invoice_party" in de else b["name"]
    inv_term = f"FOB {g['pol'].split(',')[0]}" if "incoterm" in de else incoterm
    inv_lc = lc_no[:-1] + str((int(lc_no[-1]) + 1) % 10) if "lc_number" in de else lc_no
    inv_no = f"INV-{r.randint(10000, 99999)}"
    inv_date = ship - timedelta(days=2)
    inv = Pdf(out / "commercial_invoice.pdf", "COMMERCIAL INVOICE", [g["exporter"], f"{g['city']}, {g['country']}"])
    inv.row("Invoice no.", "invoice_number", inv_no)
    inv.row("Date", "invoice_date", human(inv_date, dstyle))
    inv.row("Seller", "issuer", g["exporter"])
    inv.row("Buyer", "made_out_to", inv_to)
    inv.row("Documentary credit no.", "lc_number", inv_lc)
    inv.row("Terms of delivery", "incoterm", inv_term)
    inv.row("Description of goods", "goods_description", inv_desc)
    inv.row("Quantity", "quantity", f"{qty:,}")
    inv.row("Unit", "quantity_unit", g["unit"])
    inv.row("Unit price", None, f"{inv_cur} {inv_total / qty:,.4f}")
    inv.row("Currency", "currency", inv_cur)
    inv.row("Total amount", "total_amount", money(inv_cur, inv_total), fs=11)
    inv.signature(g["exporter"])
    inv.save()
    inv_data = dict(invoice_number=inv_no, invoice_date=human(inv_date, dstyle), issuer=g["exporter"], made_out_to=inv_to,
                    lc_number=inv_lc, currency=inv_cur, total_amount=money(inv_cur, inv_total), quantity=f"{qty:,}",
                    quantity_unit=g["unit"], goods_description=inv_desc, incoterm=inv_term, evidence=inv.ev)

    # ---------------- Packing list
    if g["per_carton"]:
        packages = qty // g["per_carton"]
        pkg_word = "cartons"
    else:
        packages = int(qty * 1000 / 25)
        pkg_word = "bags"
    net = round(qty * g["kg_per_unit"], 1)
    gross = round(net * 1.04, 1)
    pl_qty = qty - (g["per_carton"] or 1) * 2 if "qty_mismatch_pl" in de else qty
    pl = Pdf(out / "packing_list.pdf", "PACKING LIST", [g["exporter"], f"{g['city']}, {g['country']}"])
    pl.row("Invoice ref.", None, inv_no)
    pl.row("Description of goods", "goods_description", g["general"] + f", as per invoice {inv_no}")
    pl.row("Number of packages", "packages_count", f"{packages:,} {pkg_word}")
    pl.row("Total quantity", "quantity", f"{pl_qty:,}")
    pl.row("Unit", "quantity_unit", g["unit"])
    pl.row("Net weight", "net_weight_kg", f"{net:,.1f} kg")
    pl.row("Gross weight", "gross_weight_kg", f"{gross:,.1f} kg")
    pl.signature(g["exporter"])
    pl.save()
    pl_data = dict(packages_count=f"{packages:,} {pkg_word}", quantity=f"{pl_qty:,}", quantity_unit=g["unit"],
                   gross_weight_kg=f"{gross:,.1f} kg", net_weight_kg=f"{net:,.1f} kg",
                   goods_description=g["general"] + f", as per invoice {inv_no}", evidence=pl.ev)

    # ---------------- Bill of lading
    bl_pkgs = packages + 3 if "packages_mismatch" in de else packages
    bl_gross = round(gross * 1.03, 1) if "weight_mismatch" in de else gross
    bl_pol = "Port Qasim, Pakistan" if ("port_pol" in de and "Pakistan" in g["pol"]) else (
        "Mongla, Bangladesh" if "port_pol" in de and "Bangladesh" in g["pol"] else ("Da Nang, Vietnam" if "port_pol" in de else g["pol"]))
    bl_cons = b["name"] if "consignee" in de else consignee_req
    bl_desc = g["conflict"] if "description_conflict_bl" in de else g["general"]
    freight = "collect" if ("freight_collect" in de or term == "FOB") else "prepaid"
    onboard = "no_onboard" not in de
    clauses = ["3 cartons torn and resealed"] if "claused" in de else []
    bl_no = f"BL{r.randint(100000, 999999)}"
    vessel = r.choice(VESSELS)
    bl = Pdf(out / "bill_of_lading.pdf", "BILL OF LADING", ["Oceanic Lines Carrier Services (fictional)", "Combined transport bill of lading"])
    bl.row("B/L no.", "bl_number", bl_no)
    bl.row("Shipper", "shipper", g["exporter"])
    bl.row("Consignee", "consignee", bl_cons)
    bl.row("Notify party", "notify_party", b["name"])
    bl.row("Vessel", "vessel", vessel)
    bl.row("Port of loading", "port_of_loading", bl_pol)
    bl.row("Port of discharge", "port_of_discharge", b["pod"])
    bl.row("Description of goods", "goods_description", bl_desc)
    bl.row("Number of packages", "packages_count", f"{bl_pkgs:,} {pkg_word}")
    bl.row("Gross weight", "gross_weight_kg", f"{bl_gross:,.1f} kg")
    bl.row("Freight", "freight", f"Freight {freight}")
    bl.row("Place and date of issue", "issue_date", human(ship, dstyle))
    if onboard:
        bl.row("Shipped on board date", "on_board_date", human(ship, dstyle))
    for cl in clauses:
        bl.row("Remarks", "clauses", cl)
    bl.stamp("on_board_notation", "SHIPPED ON BOARD" if onboard else "RECEIVED FOR SHIPMENT", onboard)
    bl.signature("the Carrier, as agent")
    bl.save()
    bl_data = dict(bl_number=bl_no, shipper=g["exporter"], consignee=bl_cons, notify_party=b["name"], vessel=vessel,
                   port_of_loading=bl_pol, port_of_discharge=b["pod"], issue_date=human(ship, dstyle),
                   on_board_date=human(ship, dstyle) if onboard else None, on_board_notation=onboard, clauses=clauses,
                   packages_count=f"{bl_pkgs:,} {pkg_word}", gross_weight_kg=f"{bl_gross:,.1f} kg", goods_description=bl_desc,
                   freight=f"Freight {freight}", evidence=bl.ev)

    # ---------------- Certificate of origin
    origin = "China" if "origin" in de else g["country"]
    coo_date = ship - timedelta(days=1)
    coo = Pdf(out / "certificate_of_origin.pdf", "CERTIFICATE OF ORIGIN", [f"{g['city']} Chamber of Commerce & Industry (fictional)", g["country"]])
    coo.row("Exporter", "exporter", g["exporter"])
    coo.row("Consignee", "consignee", b["name"])
    coo.row("Description of goods", "goods_description", g["general"])
    coo.row("Country of origin", "country_of_origin", origin)
    coo.row("Date of issue", "issue_date", human(coo_date, dstyle))
    coo.row("Issued by", "issuer", f"{g['city']} Chamber of Commerce & Industry")
    coo.signature(f"{g['city']} Chamber of Commerce & Industry")
    coo.save()
    coo_data = dict(exporter=g["exporter"], consignee=b["name"], country_of_origin=origin, goods_description=g["general"],
                    issue_date=human(coo_date, dstyle), issuer=f"{g['city']} Chamber of Commerce & Industry", evidence=coo.ev)

    files = [("lc.pdf", "letter_of_credit", lc_data), ("commercial_invoice.pdf", "commercial_invoice", inv_data),
             ("bill_of_lading.pdf", "bill_of_lading", bl_data), ("packing_list.pdf", "packing_list", pl_data)]
    if "missing_doc" not in de:
        files.append(("certificate_of_origin.pdf", "certificate_of_origin", coo_data))
    else:
        (out / "certificate_of_origin.pdf").unlink(missing_ok=True)

    # ---------------- Insurance
    if any("insurance" in x.lower() for x in docs_req):
        ins_date = ship + timedelta(days=2) if "insurance_late" in de else ship - timedelta(days=1)
        ins_amt = round(inv_total * (1.0 if "insurance_under" in de else 1.1), 2)
        ins = Pdf(out / "insurance_certificate.pdf", "MARINE CARGO INSURANCE CERTIFICATE", ["Harbourside General Insurance (fictional)", g["city"]])
        ins.row("Assured", None, g["exporter"])
        ins.row("Date of issue", "issue_date", human(ins_date, dstyle))
        ins.row("Conveyance", None, f"{vessel} from {g['pol']} to {b['pod']}")
        ins.row("Subject matter insured", "goods_description", g["general"])
        ins.row("Currency", "currency", cur)
        ins.row("Sum insured", "insured_amount", money(cur, ins_amt))
        ins.row("Conditions", "risks_covered", "Institute Cargo Clauses (A)")
        ins.signature("Harbourside General Insurance")
        ins.save()
        files.append(("insurance_certificate.pdf", "insurance_certificate",
                      dict(issue_date=human(ins_date, dstyle), currency=cur, insured_amount=money(cur, ins_amt),
                           risks_covered="Institute Cargo Clauses (A)", goods_description=g["general"], evidence=ins.ev)))

    meta_files = []
    for fname, dtype, data in files:
        truth = f"{Path(fname).stem}.truth.json"
        (out / truth).write_text(json.dumps({"doc_type": dtype, "data": data}, indent=1))
        meta_files.append({"file": fname, "doc_type": dtype, "truth": truth})

    expected_doc = sorted({DOC_ERRORS[e] for e in de})
    expected_lc = {LC_ERRORS[e] for e in le}
    if (expiry - latest).days < pres_days:  # an early expiry also squeezes the presentation window
        expected_lc.add("A02")
    company = "Indus Textile Mills Ltd" if "name_mismatch" in le else g["exporter"]
    meta = dict(case_id=spec.case_id, company_name=company, goods_ready_date=goods_ready.isoformat(),
                presentation_date=pres.isoformat(), goods=g["key"], incoterm=incoterm, currency=cur,
                planted_document_errors=sorted(de), planted_lc_errors=sorted(le),
                expected_document_rules=expected_doc, expected_lc_rules=sorted(expected_lc), files=meta_files)
    (out / "case.json").write_text(json.dumps(meta, indent=1))
    return meta


def pick_errors(r: random.Random, pool: dict, k: int, cif: bool, chosen=()) -> list[str]:
    names = [e for e in pool if cif or e not in CIF_ONLY]
    out: list[str] = []
    for e in r.sample(names, len(names)):
        if len(out) >= k:
            break
        trial = set(out) | {e} | set(chosen)
        if any(pair <= trial for pair in INCOMPATIBLE):
            continue
        out.append(e)
    return out


def generate(out: Path, n: int, seed: int) -> list[dict]:
    r = random.Random(seed)
    metas = []
    n_clean = max(1, n // 4)
    for i in range(n):
        g, b = r.choice(GOODS), r.choice(BUYERS)
        cif = r.random() < 0.6
        doc_err = [] if i < n_clean else pick_errors(r, DOC_ERRORS, r.randint(1, 3), cif)
        lc_err = pick_errors(r, LC_ERRORS, 1, cif, doc_err) if (i >= n_clean and r.random() < 0.5) else []
        if not cif and any(e in CIF_ONLY for e in doc_err):
            cif = True
        spec = Spec(f"case_{i:03d}", g, b, random.Random(seed * 1000 + i), doc_err, lc_err, cif)
        metas.append(build(spec, out / spec.case_id))
    (out / "answer_key.json").write_text(json.dumps(
        {m["case_id"]: {"document": m["expected_document_rules"], "lc": m["expected_lc_rules"]} for m in metas}, indent=1))
    return metas


def corrections(out: Path, spec: Spec, keep_errors: list[str], docs: dict[str, str]) -> None:
    """Rebuild the same case with some errors removed and keep the corrected documents, so the
    fix -> re-upload -> re-check loop can be shown without retyping documents.
    Only errors that do not consume random numbers may be removed (late_shipment does)."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    build(Spec(spec.case_id, spec.goods, spec.buyer, random.Random(spec.rng_seed), keep_errors, spec.lc_errors, spec.cif), tmp)
    (out / "corrected").mkdir(exist_ok=True)
    items = []
    for fname, fixes in docs.items():
        stem = Path(fname).stem
        shutil.copy(tmp / fname, out / "corrected" / fname)
        shutil.copy(tmp / f"{stem}.truth.json", out / "corrected" / f"{stem}.truth.json")
        doc_type = json.loads((tmp / f"{stem}.truth.json").read_text())["doc_type"]
        items.append({"doc_type": doc_type, "file": f"corrected/{fname}", "truth": f"corrected/{stem}.truth.json", "fixes": fixes})
    (out / "corrections.json").write_text(json.dumps(items, indent=1))
    shutil.rmtree(tmp)


def demos(out: Path) -> None:
    """Hand-picked cases for the 3-minute demo video, with corrected documents for the re-check loop."""
    towels, footballs = GOODS[0], GOODS[1]
    nl, sg = BUYERS[0], BUYERS[3]
    s1 = Spec("demo_faisalabad_towels", towels, nl, random.Random(11),
              ["late_shipment", "amount_over", "description_invoice"], ["soft_clause", "tight_timeline"])
    s1.rng_seed = 11
    build(s1, out / s1.case_id)
    corrections(out / s1.case_id, s1, ["late_shipment"],
                {"commercial_invoice.pdf": "Invoice reissued for the LC amount, with the LC goods description"})
    s2 = Spec("demo_sialkot_footballs", footballs, sg, random.Random(12),
              ["insurance_late", "port_pol", "packages_mismatch"], ["expiry_abroad"])
    s2.rng_seed = 12
    build(s2, out / s2.case_id)
    corrections(out / s2.case_id, s2, [], {
        "bill_of_lading.pdf": "Carrier corrected the port of loading and the number of packages",
        "insurance_certificate.pdf": "Insurer reissued the certificate dated before shipment"})
    cashew = next(x for x in GOODS if x["key"] == "cashew")
    build(Spec("demo_clean", cashew, sg, random.Random(13), [], []), out / "demo_clean")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/testset")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo:
        demos(Path(a.out))
        print(f"demo cases written to {a.out}")
    else:
        ms = generate(Path(a.out), a.n, a.seed)
        print(f"{len(ms)} cases written to {a.out} ({sum(1 for m in ms if not m['planted_document_errors'])} clean)")
