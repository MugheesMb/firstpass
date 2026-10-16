"""Fresh test pack in layouts FirstPass has never seen. Fictional parties, marked SPECIMEN."""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

OUT = Path(__file__).resolve().parents[1] / "docs" / "test_pack" / "pdf"; OUT.mkdir(parents=True, exist_ok=True)
W, H = A4
LC_NO = "NCB/IMP/26/04417"
EXP = "MEKONG BAMBOO CRAFTS CO., LTD."
EXP_ADDR = ["Lot B7, Hoa Khanh Industrial Zone", "Lien Chieu District, Da Nang, Viet Nam"]
BUY = "KANSAI HOME LIVING K.K."
BUY_ADDR = ["3-12-8 Utsubo-Honmachi, Nishi-ku", "Osaka 550-0004, Japan"]
BANK = "NANIWA COMMERCE BANK, LTD."
ITEMS = [("BC-L40", "Bamboo cutting board, large 40 x 28 cm", 2400, "pcs", 6.80),
         ("ST-35", "Bamboo serving tray with handles, 35 cm", 1800, "pcs", 9.40),
         ("US-5", "Bamboo kitchen utensil set, 5 pieces", 3000, "sets", 3.95)]
TOTAL = sum(q * p for _, _, q, _, p in ITEMS)  # 45,090.00

def new(name):
    c = canvas.Canvas(str(OUT / name), pagesize=A4)
    c.setTitle(name.replace(".pdf", "").replace("_", " ").title())
    return c

def specimen(c):
    c.setFont("Helvetica", 7); c.setFillColor(colors.HexColor("#888888"))
    c.drawCentredString(W / 2, 9 * mm, "SPECIMEN - fictional companies and bank - FirstPass test pack, not a real trade document")
    c.setFillColor(colors.black)

def box(c, x, y, w, h, label=None, lines=(), size=9, bold_first=False):
    c.setLineWidth(0.6); c.rect(x, y, w, h)
    ty = y + h - 9
    if label:
        c.setFont("Helvetica", 6.5); c.drawString(x + 3, ty, label.upper()); ty -= 11
    for i, ln in enumerate(lines):
        c.setFont("Helvetica-Bold" if (bold_first and i == 0) else "Helvetica", size)
        c.drawString(x + 4, ty, ln); ty -= size + 3

# 1. LC: advising bank's cover letter + raw SWIFT print, monospace, 2 pages ---------------------------
def lc():
    c = new("01_letter_of_credit.pdf")
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, H-22*mm, "ANNAM TRADE BANK")
    c.setFont("Helvetica", 8.5); c.drawString(20*mm, H-27*mm, "Trade Finance Operations - 112 Bach Dang, Hai Chau, Da Nang, Viet Nam")
    c.line(20*mm, H-30*mm, W-20*mm, H-30*mm)
    y = H-40*mm
    for ln in ["Our ref: ATB/ADV/26/1188                                              Date: 03 October 2026", "",
               f"To: {EXP}", *[f"    {a}" for a in EXP_ADDR], "",
               "ADVICE OF IRREVOCABLE DOCUMENTARY CREDIT",
               "",
               f"We advise, without any engagement on our part, that we have received the following SWIFT MT700 from",
               f"{BANK}, Osaka. Please check the terms carefully. If they cannot be complied with, ask the applicant",
               "to arrange an amendment. This credit is subject to UCP 600.", ""]:
        c.setFont("Helvetica-Bold" if ln.startswith("ADVICE") else "Helvetica", 9.5 if ln.startswith("ADVICE") else 9); c.drawString(20*mm, y, ln); y -= 12
    c.setFont("Courier", 8.6)
    swift = [
     "{1:F01ATBKVNVXAXXX0000000000}{2:O7000915261002NCBKJPJSAXXX}",
     "---------------------------------------------------------------",
     ":27:  SEQUENCE OF TOTAL", "      1/1",
     ":40A: FORM OF DOCUMENTARY CREDIT", "      IRREVOCABLE",
     f":20:  DOCUMENTARY CREDIT NUMBER", f"      {LC_NO}",
     ":31C: DATE OF ISSUE", "      261002",
     ":40E: APPLICABLE RULES", "      UCP LATEST VERSION",
     ":31D: DATE AND PLACE OF EXPIRY", "      261210 OSAKA, JAPAN AT THE COUNTERS OF THE ISSUING BANK",
     f":50:  APPLICANT", f"      {BUY}", *[f"      {a.upper()}" for a in BUY_ADDR],
     f":59:  BENEFICIARY", f"      {EXP}", *[f"      {a.upper()}" for a in EXP_ADDR],
     ":32B: CURRENCY CODE, AMOUNT", "      USD45090,00",
     ":39A: PERCENTAGE CREDIT AMOUNT TOLERANCE", "      05/05",
     ":41D: AVAILABLE WITH ... BY ...", "      ANY BANK BY NEGOTIATION",
     ":42C: DRAFTS AT ...", "      AT SIGHT",
     ":43P: PARTIAL SHIPMENTS", "      NOT ALLOWED",
     ":43T: TRANSHIPMENT", "      ALLOWED",
     ":44E: PORT OF LOADING/AIRPORT OF DEPARTURE", "      DA NANG PORT, VIET NAM",
     ":44F: PORT OF DISCHARGE/AIRPORT OF DESTINATION", "      OSAKA, JAPAN",
     ":44C: LATEST DATE OF SHIPMENT", "      261115",
    ]
    for ln in swift:
        if y < 22*mm:
            specimen(c); c.showPage(); c.setFont("Courier", 8.6); y = H-20*mm
        c.drawString(20*mm, y, ln); y -= 10.6
    swift2 = [
     ":45A: DESCRIPTION OF GOODS AND/OR SERVICES",
     "      BAMBOO KITCHENWARE, 7,200 UNITS IN TOTAL:",
     "      - 2,400 PCS BAMBOO CUTTING BOARD, LARGE 40 X 28 CM AT USD 6.80",
     "      - 1,800 PCS BAMBOO SERVING TRAY WITH HANDLES, 35 CM AT USD 9.40",
     "      - 3,000 SETS BAMBOO KITCHEN UTENSIL SET, 5 PIECES AT USD 3.95",
     "      CIF OSAKA, INCOTERMS 2020. ORIGIN: VIET NAM",
     ":46A: DOCUMENTS REQUIRED",
     "      1. SIGNED COMMERCIAL INVOICE IN 3 ORIGINALS INDICATING THIS CREDIT NUMBER.",
     f"      2. FULL SET (3/3) CLEAN ON BOARD OCEAN BILLS OF LADING MADE OUT TO ORDER OF",
     f"         {BANK}, MARKED FREIGHT PREPAID AND NOTIFY APPLICANT.",
     "      3. PACKING LIST IN 2 COPIES SHOWING GROSS AND NET WEIGHT.",
     "      4. CERTIFICATE OF ORIGIN ISSUED BY A CHAMBER OF COMMERCE IN VIET NAM.",
     "      5. INSURANCE CERTIFICATE IN DUPLICATE FOR 110 PCT OF CIF VALUE, COVERING",
     "         INSTITUTE CARGO CLAUSES (A), CLAIMS PAYABLE IN JAPAN.",
     ":47A: ADDITIONAL CONDITIONS",
     "      1. ALL DOCUMENTS MUST INDICATE THE CREDIT NUMBER.",
     "      2. AN INSPECTION CERTIFICATE ISSUED AND SIGNED BY AN AUTHORISED REPRESENTATIVE",
     f"         OF THE APPLICANT, {BUY}, MUST ACCOMPANY THE DOCUMENTS.",
     "      3. A DISCREPANCY FEE OF USD 90.00 WILL BE DEDUCTED FOR EACH DISCREPANT PRESENTATION.",
     ":71D: CHARGES", "      ALL BANKING CHARGES OUTSIDE JAPAN ARE FOR BENEFICIARY'S ACCOUNT.",
     ":48:  PERIOD FOR PRESENTATION IN DAYS", "      21/FROM THE DATE OF SHIPMENT",
     ":49:  CONFIRMATION INSTRUCTIONS", "      WITHOUT",
     "---------------------------------------------------------------",
     "{5:{CHK:4F1A22B90C3D}}",
    ]
    for ln in swift2:
        if y < 22*mm:
            specimen(c); c.showPage(); c.setFont("Courier", 8.6); y = H-20*mm
        c.drawString(20*mm, y, ln); y -= 10.6
    y -= 14; c.setFont("Helvetica", 9)
    c.drawString(20*mm, y, "For ANNAM TRADE BANK"); c.drawString(20*mm, y-26, "Authorised signature ____________________")
    specimen(c); c.save()

# 2. Commercial invoice: line-item table ------------------------------------------------------------
def invoice():
    c = new("02_commercial_invoice.pdf")
    c.setFont("Helvetica-Bold", 15); c.drawString(20*mm, H-22*mm, EXP)
    c.setFont("Helvetica", 8.5)
    c.drawString(20*mm, H-27*mm, ", ".join(EXP_ADDR) + "  -  Tel +84 236 373 0000  -  MST 0401234567")
    c.setFont("Helvetica-Bold", 18); c.drawRightString(W-20*mm, H-40*mm, "COMMERCIAL INVOICE")
    box(c, 20*mm, H-80*mm, 85*mm, 32*mm, "Sold to / Messrs", [BUY, *BUY_ADDR], bold_first=True)
    box(c, 105*mm, H-80*mm, 85*mm, 32*mm, "Invoice details",
        ["Invoice No.: MBC-INV-2611-031", "Date: 17 November 2026", f"L/C No.: {LC_NO}", f"Issuing bank: {BANK}"])
    box(c, 20*mm, H-100*mm, 170*mm, 20*mm, "Shipment",
        ["Vessel / voyage: CAPE KIRIN V.246N    From: Da Nang Port, Viet Nam    To: Osaka, Japan",
         "Terms: CIF Osaka, Incoterms 2020    Origin: Viet Nam    Packing: 300 export cartons"])
    y = H-110*mm
    cols = [20, 38, 120, 145, 165, 190]
    c.setFillColor(colors.HexColor("#e9ece8")); c.rect(20*mm, y-2, 170*mm, 13, fill=1, stroke=0); c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8.5)
    for x, t in zip(cols, ["Item", "Description of goods", "Quantity", "Unit price", "Amount (USD)"]):
        c.drawString(x*mm + 2, y + 2, t)
    y -= 16; c.setFont("Helvetica", 8.8)
    for code, desc, q, u, p in ITEMS:
        c.drawString(22*mm, y, code); c.drawString(40*mm, y, desc)
        c.drawRightString(142*mm, y, f"{q:,} {u}"); c.drawRightString(162*mm, y, f"{p:.2f}"); c.drawRightString(188*mm, y, f"{q*p:,.2f}")
        y -= 15
    c.line(20*mm, y+6, 190*mm, y+6)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40*mm, y-6, "TOTAL: BAMBOO KITCHENWARE, 7,200 UNITS"); c.drawRightString(142*mm, y-6, "7,200 units")
    c.drawRightString(188*mm, y-6, f"USD {TOTAL:,.2f}")
    c.setFont("Helvetica", 8.8)
    c.drawString(20*mm, y-26, "Say: US Dollars forty-five thousand and ninety only. CIF Osaka, Incoterms 2020.")
    c.drawString(20*mm, y-40, "We certify that the goods are of Vietnamese origin and that this invoice is true and correct.")
    c.drawString(130*mm, y-80, f"For {EXP}"); c.drawString(130*mm, y-106, "Nguyen Thi Lan, Director")
    specimen(c); c.save()

# 3. Bill of lading: boxed carrier form ----------------------------------------------------------------
def bl():
    c = new("03_bill_of_lading.pdf")
    c.setFont("Helvetica-Bold", 14); c.drawString(20*mm, H-20*mm, "ORIENT PACIFIC LINES")
    c.setFont("Helvetica", 8); c.drawString(20*mm, H-25*mm, "BILL OF LADING FOR OCEAN TRANSPORT OR MULTIMODAL TRANSPORT")
    c.setFont("Helvetica-Bold", 11); c.drawRightString(W-20*mm, H-20*mm, "B/L No. OPLU DAD 7781240")
    top = H-30*mm
    box(c, 20*mm, top-30*mm, 95*mm, 30*mm, "Shipper", [EXP, *EXP_ADDR], 8.5)
    box(c, 115*mm, top-30*mm, 75*mm, 30*mm, "Booking / export references", ["Booking No. DAD26110452", f"L/C No. {LC_NO}", "Original 1 of 3 (THREE)"], 8.5)
    box(c, 20*mm, top-58*mm, 95*mm, 28*mm, "Consignee (if 'To order' so indicate)", [f"TO ORDER OF {BANK}"], 8.5)
    box(c, 115*mm, top-58*mm, 75*mm, 28*mm, "Notify party", [BUY, *BUY_ADDR], 8)
    box(c, 20*mm, top-74*mm, 60*mm, 16*mm, "Vessel / voyage", ["CAPE KIRIN  V.246N"], 8.5)
    box(c, 80*mm, top-74*mm, 55*mm, 16*mm, "Port of loading", ["DA NANG PORT, VIET NAM"], 8.5)
    box(c, 135*mm, top-74*mm, 55*mm, 16*mm, "Port of discharge", ["OSAKA, JAPAN"], 8.5)
    box(c, 20*mm, top-140*mm, 170*mm, 66*mm, "Marks & nos / number and kind of packages / description of goods / gross weight / measurement",
        ["KHL / OSAKA / C/NO. 1-300", "",
         "300 (THREE HUNDRED) CARTONS SAID TO CONTAIN:",
         "BAMBOO KITCHENWARE, 7,200 UNITS",
         "1 X 40' HC CONTAINER  OPLU 4471026  SEAL VN 0098817  CY/CY", "",
         "GROSS WEIGHT: 4,680.00 KGS          MEASUREMENT: 48.600 CBM", "",
         "FREIGHT PREPAID", "SHIPPER'S LOAD, STOW AND COUNT"], 8.8)
    box(c, 20*mm, top-170*mm, 85*mm, 30*mm, "On board notation",
        ["SHIPPED ON BOARD", "Vessel: CAPE KIRIN V.246N", "Port: DA NANG PORT, VIET NAM", "Date: 18 NOV 2026"], 8.8)
    box(c, 105*mm, top-170*mm, 85*mm, 30*mm, "Place and date of issue",
        ["DA NANG, 18 NOV 2026", "", "Signed as carrier: ORIENT PACIFIC LINES", "by its agent ________________"], 8.5)
    c.setFont("Helvetica", 6.5)
    c.drawString(20*mm, top-176*mm, "Received in apparent good order and condition unless otherwise stated. Number of originals: THREE (3).")
    specimen(c); c.save()

# 4. Packing list: per-item and per-carton-range rows -------------------------------------------------
def packing():
    c = new("04_packing_list.pdf")
    c.setFont("Helvetica-Bold", 15); c.drawString(20*mm, H-22*mm, "PACKING / WEIGHT LIST")
    c.setFont("Helvetica", 9)
    for i, ln in enumerate([f"Exporter: {EXP}", f"Consignee: {BUY}", "Ref. invoice: MBC-INV-2611-031 of 17 Nov 2026",
                            f"L/C No.: {LC_NO}", "Shipping marks: KHL / OSAKA / C/NO. 1-300"]):
        c.drawString(20*mm, H-32*mm - i*12, ln)
    y = H-100*mm
    hdr = ["Carton nos.", "Item", "Description", "Qty", "Cartons", "Net kg", "Gross kg"]
    xs = [20, 45, 65, 120, 140, 158, 176]
    c.setFont("Helvetica-Bold", 8.5)
    for x, t in zip(xs, hdr): c.drawString(x*mm, y, t)
    c.line(20*mm, y-4, 192*mm, y-4); y -= 16; c.setFont("Helvetica", 8.6)
    rows = [("1-120", "BC-L40", "Cutting board, large", "2,400 pcs", "120", "2,016.00", "2,256.00"),
            ("121-210", "ST-35", "Serving tray, 35 cm", "1,800 pcs", "90", "1,404.00", "1,584.00"),
            ("211-300", "US-5", "Utensil set, 5 pcs", "3,000 sets", "90", "900.00", "1,020.00")]
    for r in rows:
        for x, t in zip(xs, r): c.drawString(x*mm, y, t)
        y -= 15
    c.line(20*mm, y+6, 192*mm, y+6); c.setFont("Helvetica-Bold", 8.8)
    for x, t in zip(xs, ["TOTAL", "", "Bamboo kitchenware", "7,200 units", "300", "4,320.00", "4,860.00"]): c.drawString(x*mm, y-6, t)
    c.setFont("Helvetica", 8.8)
    c.drawString(20*mm, y-32, "Total: 300 export cartons, net weight 4,320.00 kg, gross weight 4,860.00 kg, measurement 48.600 CBM.")
    c.drawString(130*mm, y-80, f"For {EXP}"); c.drawString(130*mm, y-106, "Authorised signature")
    specimen(c); c.save()

# 5. Certificate of origin: numbered form boxes --------------------------------------------------------
def coo():
    c = new("05_certificate_of_origin.pdf")
    c.setFont("Helvetica-Bold", 14); c.drawCentredString(W/2, H-20*mm, "CERTIFICATE OF ORIGIN")
    c.setFont("Helvetica", 8.5); c.drawCentredString(W/2, H-25*mm, "Issued by DA NANG CHAMBER OF COMMERCE AND INDUSTRY (specimen)   -   No. DN-CO-26-118204")
    top = H-32*mm
    box(c, 20*mm, top-32*mm, 85*mm, 32*mm, "1. Exporter (name, address, country)", [EXP, *EXP_ADDR], 8.5)
    box(c, 105*mm, top-32*mm, 85*mm, 32*mm, "2. Consignee (name, address, country)", [BUY, *BUY_ADDR], 8.5)
    box(c, 20*mm, top-52*mm, 85*mm, 20*mm, "3. Means of transport and route", ["By sea, CAPE KIRIN V.246N", "Da Nang Port to Osaka, Japan"], 8.5)
    box(c, 105*mm, top-52*mm, 85*mm, 20*mm, "4. Country of origin", ["VIET NAM"], 10)
    box(c, 20*mm, top-100*mm, 170*mm, 48*mm, "5. Marks, numbers, packages, description of goods, quantity",
        ["KHL / OSAKA / C/NO. 1-300", "300 cartons of bamboo kitchenware, 7,200 units:",
         "cutting boards, serving trays and kitchen utensil sets",
         f"Invoice MBC-INV-2611-031 dated 17 Nov 2026    L/C No. {LC_NO}"], 8.8)
    box(c, 20*mm, top-140*mm, 85*mm, 40*mm, "6. Declaration by the exporter",
        ["The undersigned declares that the above", "details are correct and that the goods were", "produced in Viet Nam.", "", "Da Nang, 17 Nov 2026"], 8.2)
    box(c, 105*mm, top-140*mm, 85*mm, 40*mm, "7. Certification",
        ["It is hereby certified that the declaration", "by the exporter is correct.", "", "Da Nang, 17 Nov 2026", "Stamp and signature"], 8.2)
    specimen(c); c.save()

# 6. Insurance certificate ------------------------------------------------------------------------------
def insurance():
    c = new("06_insurance_certificate.pdf")
    c.setFont("Helvetica-Bold", 14); c.drawString(20*mm, H-22*mm, "SONG HAN MARINE INSURANCE CORPORATION")
    c.setFont("Helvetica", 8.5); c.drawString(20*mm, H-27*mm, "Head office: 58 Tran Phu, Da Nang, Viet Nam (specimen insurer)")
    c.setFont("Helvetica-Bold", 13); c.drawString(20*mm, H-42*mm, "MARINE CARGO INSURANCE CERTIFICATE   No. SHM-MC-26-30917")
    y = H-58*mm
    rows = [("Assured", EXP), ("Claims payable to / at", f"Order of {BANK} / Osaka, Japan"),
            ("Insured value", f"USD {TOTAL:,.2f}"), ("Basis of valuation", "Invoice value"),
            ("Conveyance", "CAPE KIRIN V.246N, Da Nang Port to Osaka, Japan"),
            ("Subject matter insured", "300 cartons bamboo kitchenware, 7,200 units"),
            ("Conditions", "Institute Cargo Clauses (A) 1/1/2009, warehouse to warehouse"),
            ("References", f"Invoice MBC-INV-2611-031    L/C No. {LC_NO}"),
            ("Survey / claims agent in Japan", "Kinki Cargo Surveyors Co. (specimen), Osaka"),
            ("Place and date of issue", "Da Nang, 16 November 2026"), ("Number of originals", "Two (2)")]
    for k, v in rows:
        c.setFont("Helvetica", 8); c.drawString(20*mm, y, k.upper())
        c.setFont("Helvetica", 10); c.drawString(78*mm, y, v); c.setLineWidth(0.3); c.line(20*mm, y-4, 190*mm, y-4); y -= 19
    c.setFont("Helvetica", 8.5)
    c.drawString(20*mm, y-10, "This certificate represents and takes the place of the policy and conveys all rights of the original policy holder.")
    c.drawString(130*mm, y-60, "For SONG HAN MARINE INSURANCE CORP."); c.drawString(130*mm, y-86, "Authorised signatory")
    specimen(c); c.save()

for f in (lc, invoice, bl, packing, coo, insurance): f()
print(f"total {TOTAL:,.2f}; written to {OUT}")
