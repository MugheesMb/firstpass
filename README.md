# FirstPass

**Letter of Credit checks, before the bank does.** AI Builder Cup 2026, BFSI theme.

**Live app:** https://twosync-bf161.web.app (Gemini on Vertex AI, Cloud Run in Singapore, Firebase Hosting)

Most Letter of Credit (LC) document sets are refused by banks the first time (industry estimates: 65-80%),
costing exporters USD 25-500 in fees per refusal plus payment delays. FirstPass helps small exporters:

1. **Review the LC before accepting it.** Flags risky or impossible terms (tight shipment dates, buyer-controlled
   "soft clauses", expiry abroad, a misspelt beneficiary name) and drafts the amendment request to the buyer.
2. **Check the shipping documents before presenting them.** Cross-checks the invoice, bill of lading, packing list,
   certificate of origin and insurance against the LC and each other under UCP 600. Every finding cites the rule,
   links to the exact spot on the document and suggests the fix.

## How it works

```
Upload (PDF / phone photo) ─► Cloud Storage
  ─► Gemini (gemini-3.8-flash, structured JSON): every field + page + box + confidence
  ─► Python: normalise dates, amounts, names, ports        (exact, no AI)
  ─► Rules engine: 22 document checks + 10 LC-term checks  (exact, no AI)
  ─► Gemini (gemini-3.1-pro-preview, falls back to Flash): judgement calls
       - does the invoice description correspond with the LC (Art. 18(c))?
       - do other documents conflict (Art. 14(e))?  - risky free-text LC terms?
       - draft the fix / the amendment email
  ─► Firestore ─► Web app: findings with click-to-evidence
ADK agent (firstpass_agent/) uses the same pipeline as tools, for the chat assistant.
```

Design rule: **Gemini reads and judges; code does the arithmetic and dates.** That split is what makes the
results reliable, and it is the story for the "Technical Merit" criterion.

| Layer | Technology |
|---|---|
| Web app | React 18 + Vite, deployed on **Firebase Hosting** (`/api/**` rewritten to Cloud Run) |
| API | Python 3.12, FastAPI, on **Cloud Run** (asia-southeast1, Singapore) |
| AI | **Gemini on Vertex AI** via the `google-genai` SDK, structured output; **Agent Development Kit** for the assistant |
| Storage | Firestore (cases, findings), Cloud Storage (uploaded documents) |
| Docs | PyMuPDF renders pages to PNG, so Gemini's boxes line up with the evidence viewer |

## The app: six steps

| Step | What the user sees | Backed by |
|---|---|---|
| 1. Exporter profile | Company name and goods-ready date, or open a sample case | `POST /api/cases`, `/api/demo/{name}` |
| 2. Read the Letter of Credit | Every MT700 field with its SWIFT tag, a confidence meter, and click-to-source on the page | Gemini extraction + `extraction` stats per document |
| 3. Review LC terms | Shipment-window timeline, risky terms, draft amendment email to the buyer | `POST /lc-review`, `/amendment-email`, `/insights` |
| 4. Add shipping documents | One sheet per document with fields read, confidence and fields to check by hand | upload per document type |
| 5. Run the compliance check | The pipeline runs stage by stage, then shows real counts and timings; findings with evidence and fixes | `POST /check` (`trace` in the report) |
| 6. Examiner's report | Readiness score, cross-document consistency grid, dates against the credit, numbered fix list, print to PDF | `GET /insights` |

Around the six steps there is a workspace:

| Feature | What it does |
|---|---|
| **All cases** | Dashboard of every LC: buyer, amount, expiry countdown (red within 7 days), stage, readiness, open, fixed, accepted and disputed counts |
| **Issues board** | Tabs for Open, Marked fixed, Resolved by re-check, Accepted, Disputed. Accepting or disputing requires a reason, which is stored with a history of every decision |
| **Fix and re-check** | Re-run the check after uploading a corrected document. Decisions carry over (matched by a stable fingerprint of rule + documents + fields); an item you marked fixed that is still present is reopened; items no longer found move to Resolved. A banner shows "2 resolved, 0 new, 1 still present" |
| **Waiver request** | Drafts the email asking the buyer to accept discrepancies that cannot be fixed (UCP 600 Art. 16(b)), from the items you accepted |
| **Activity log** | Every upload (with version), check run, decision with reason, and draft, timestamped |
| **Corrected samples** | The two problem demos ship corrected documents, so the fix and re-check loop can be shown in mock mode. In mock mode any generated PDF is also recognised by its content when uploaded by hand |

The consistency grid never makes its own judgements: a cell is marked only when an open finding's evidence points at
that document and field, so the grid and the findings list always agree. The readiness score is a simple, stated
formula (100 minus 30/12/4 per open high/medium/low finding) and is labelled as a priority guide, not a prediction.

Design: harbour-ink sidebar with the steps on a route line; Big Shoulders Display for titles and the score,
IBM Plex Sans for text, IBM Plex Mono only for SWIFT field tags. Fonts are bundled (`@fontsource`), so the demo
works offline. Works down to phone width; respects reduced-motion; prints the report cleanly.

## Repository

```
backend/
  app/
    models.py            document schemas (one per type) + findings
    extraction/          page rendering, Gemini extractor, mock extractor
    rules/               document_rules.py (Mode B), lc_rules.py (Mode A), engine.py
    ai/                  Gemini client + judge (description checks, LC review, drafting)
    pipeline.py          upload -> extract -> check (shared by API, agent, eval)
    main.py              FastAPI routes
  firstpass_agent/       ADK agent (adk web)
  demo_cases/            3 hand-picked cases for the demo video
  tests/                 43 tests, run offline
datagen/generate.py      synthetic LC presentations with planted errors + answer key
datagen/scanify.py       turn PDFs into phone-photo-like JPGs
data/testset/            40 generated cases (10 clean, 30 with 1-3 planted errors)
eval/run_eval.py         benchmark: recall / precision / false alarms, plus plain-Gemini baseline
frontend/                React app
scripts/                 setup_gcp.sh, deploy.sh
```

## Run it locally (no Google account needed)

Mock mode uses the generator's ground truth instead of Gemini, so you can build the UI and rules today.

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
AI_MODE=mock uvicorn app.main:app --reload --port 8080

# frontend (second terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Step 1 lists three hand-picked demos and the **40-case test set** (10 clean, 30 with planted problems), each
labelled with its planted problems and filterable by problem type, so you can open any kind of discrepancy or
check a clean case for false alarms. The test set is listed automatically when `data/testset` exists
(set `EXTRA_CASE_DIRS` to change it; it is not copied into the Docker image).

Open **"Bath towels, Faisalabad to Rotterdam"**. Review LC terms shows 2 risks; Check documents shows
3 discrepancies (late shipment, invoice 3% over, description mismatch). Click *View evidence*.

Tests: `cd backend && pytest -q` (every planted error type is caught on its own; clean cases stay clean).

## Switch on Gemini

```bash
gcloud auth application-default login
export AI_MODE=gemini GOOGLE_CLOUD_PROJECT=your-project GOOGLE_CLOUD_LOCATION=global GOOGLE_GENAI_USE_VERTEXAI=TRUE
uvicorn app.main:app --reload --port 8080
```

- Model ids are in `.env.example`. **Check both models are enabled in your project** (Vertex AI Model Garden) before
  relying on them; `gemini-3.1-pro-preview` is a preview model and may change. The judge falls back to Flash automatically.
- Temperature is left at the model default (Google's recommendation for Gemini 3 models).
- Demo cases now go through real Gemini extraction (the PDFs are read, not the ground truth).

## Benchmark results (real Gemini, 15 Oct 2026)

20 generated LC presentations (6 clean, 14 with 1-3 planted discrepancies), chosen with `--cover 20` so that together
they include all 18 planted document-rule types and all 8 LC-term rules. Real Gemini calls, no cache.
Full report: [`docs/FirstPass_Benchmark.pdf`](docs/FirstPass_Benchmark.pdf).

| | FirstPass | Plain Gemini prompt |
|---|---|---|
| Planted document discrepancies caught | **32 / 32** | 32 / 32 |
| False alarms | **0** | 3 |
| Clean presentations wrongly flagged | **0 of 6** | 2 of 6 |
| Risky LC terms flagged before shipment | **12 / 12** | not offered |
| Evidence on the page, UCP 600 / MT700 reference, drafted fix | every finding | no |

Limits: generated documents with fictional parties, clean digital PDFs (not scans); 4 of 22 document rules have no
planted case yet. `docs/test_pack/` has a case in layouts the system was not built on, plus phone-photo versions.

```bash
AI_MODE=mock   python eval/run_eval.py                                            # rules logic vs answer key
AI_MODE=gemini python eval/run_eval.py --cover 20 --workers 3 --baseline          # the run above
AI_MODE=gemini python eval/run_eval.py --only case_012,case_014 --workers 3       # re-run named cases
```

## Deploy (Cloud Run in Singapore + Firebase Hosting)

Step-by-step guide for the team: **GO_LIVE.md**.

```bash
PROJECT_ID=your-project ./scripts/setup_gcp.sh    # once: APIs, Firestore, bucket, service account
cp .firebaserc.example .firebaserc               # put your project id in it
PROJECT_ID=your-project ./scripts/deploy.sh
```

Notes:
- The web app calls Cloud Run directly (VITE_API_BASE, set by deploy.sh), so long Gemini reads are not cut off by Firebase Hosting's 60-second rewrite limit. Demo cases read their documents in parallel.
- The API is public for the hackathon (no sign-in). Add Firebase Auth before real users upload real documents.
- No API keys: Cloud Run uses the `firstpass-run` service account with Vertex AI, Firestore and bucket roles.

## Status

- Done: Gemini extraction and judging, rules engine, six-step app, issues board, ADK agent, Cloud Run + Firebase
  deployment, result cache, benchmark above.
- To do: verify every UCP 600 article reference in `rules/*.py` against the ICC text; test on real (anonymised)
  presentations, scans and photos; add sign-in (Firebase Auth) before real users upload real documents.

## Known limitations

- One document per type per case; sea transport only; sight LCs; ~22 core rules, not full UCP 600 / ISBP 821.
- Mock mode cannot read new uploads (it needs ground truth); use Gemini mode for anything not generated.
- Findings are decision support, not a bank decision. The app never says "approved".
