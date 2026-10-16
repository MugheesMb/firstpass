# FirstPass test pack: bamboo kitchenware, Da Nang (Viet Nam) to Osaka (Japan)

A **fictional** Letter of Credit presentation in **layouts FirstPass has never seen**. The LC arrives as an
advising bank's cover letter with a raw SWIFT MT700 printout. The invoice and packing list have line-item tables,
and the bill of lading is a boxed carrier form. Every page is marked SPECIMEN, and the companies, banks and
insurer are invented.

- `pdf/`: clean digital PDFs.
- `phone_photos/`: the same documents as rotated, shaded, slightly blurred photos, which is a harder test.
  The LC is one 2-page PDF made from two photos.

## How to test on https://twosync-bf161.web.app
1. **Exporter profile:** Company name `Mekong Bamboo Crafts Co., Ltd.`, goods ready on `05 Nov 2026`. Start a new case.
2. **Read the Letter of Credit:** upload `01_letter_of_credit.pdf`.
3. **Review LC terms:** run the review.
4. **Add shipping documents:** upload files 02 to 06. Each document type should be recognised automatically.
5. **Run the compliance check:** use presentation date `25 Nov 2026`.
6. **Examiner's report:** compare the findings with the list below.

## What FirstPass should find

**LC-term risks** (step 3):
| Expect | Why |
|---|---|
| Soft clause | 47A.2: the inspection certificate must be signed by the **applicant's** representative. The buyer can block payment by not signing. |
| Expiry abroad | 31D: the credit expires in **Osaka, at the issuing bank's counters**. Documents must reach Japan in time, not just Da Nang. |
| Possibly | The AI review may also mention the USD 90 discrepancy fee (47A.3), or that charges outside Japan are for the beneficiary (71D). Both are reasonable. |

**Document discrepancies** (steps 5 and 6):
| Rule | Discrepancy | Where |
|---|---|---|
| R02 | **Shipped 3 days late.** On board 18 Nov 2026; latest shipment date (44C) 15 Nov 2026. | B/L on-board notation vs LC 44C |
| R10 | **Gross weight differs.** Packing list 4,860.00 kg; B/L 4,680.00 kgs. | Packing list total vs B/L |
| R15 | **Insurance under 110%.** Insured USD 45,090.00 (invoice value); LC requires 110% of CIF, i.e. USD 49,599.00. | Insurance certificate vs LC 46A.5 |

**Possibly flagged for review:** "confirm the inspection certificate is included". It is required by 47A.2 but is
not in this pack. That is correct behaviour.

**Everything else is consistent** and should not be flagged: amount, currency, LC number on every document,
ports, consignee "to order of Naniwa Commerce Bank, Ltd.", freight prepaid, clean on-board, origin Viet Nam,
7,200 units, 300 cartons, CIF Osaka, insurance dated before shipment.

Anything flagged beyond this is a false alarm or a reading error, and worth sending back to fix.

## What fixing it looks like (for the video)
- **R10 and R15** are curable: the carrier corrects the weight, and the insurer reissues for USD 49,599.00.
- **R02 (late shipment)** can't be fixed by a new document. Use **Request waiver** to ask the buyer to accept it.
