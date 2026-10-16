# Going live: Gemini, Cloud Run, Firebase, GitHub

Do everything in **Google Cloud Shell** (the `>_` button at the top right of console.cloud.google.com).
It already has `gcloud`, Python, Node and your login, so nothing needs installing on your laptop.

## 1. Google Cloud project (5 minutes)
1. console.cloud.google.com → project picker → **New project**. Name it `firstpass`. Note the **project ID**
   (for example `firstpass-473210`), which can differ from the name.
2. **Billing** → link a billing account (hackathon credits, or the free trial). Gemini and Cloud Run need billing.
3. **Billing → Budgets & alerts** → create a budget of USD 20 with email alerts.

## 2. Upload the project to Cloud Shell
1. Open Cloud Shell. Menu (⋮) → **Upload** → choose `firstpass.zip`.
2. Run:
```bash
unzip -q firstpass.zip && cd firstpass
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID
chmod +x scripts/*.sh
./scripts/setup_gcp.sh
```
This enables the APIs, creates Firestore (Singapore), a private bucket for documents and the
`firstpass-run` service account with Vertex AI, Firestore and bucket access.

## 3. Prove Gemini works (most important step)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -q -r requirements-dev.txt
gcloud auth application-default login        # follow the link, paste the code
AI_MODE=gemini GOOGLE_CLOUD_PROJECT=$PROJECT_ID python ../scripts/gemini_smoke.py
```
Good result: most fields correct, evidence boxes returned, verdict `mismatch`.

If a model is not found: Vertex AI → **Model Garden**, search "Gemini", pick the newest Flash and Pro models
available to your project, then add `MODEL_EXTRACT=<flash id> MODEL_REASON=<pro id>` in front of the command.
If it says location not supported, also add `GOOGLE_CLOUD_LOCATION=us-central1`.
Use the same values in step 5.

## 4. Benchmark on Gemini (the numbers for your deck)
```bash
AI_MODE=gemini GOOGLE_CLOUD_PROJECT=$PROJECT_ID python ../eval/run_eval.py --limit 6 --out ../eval/results_try.json
AI_MODE=gemini GOOGLE_CLOUD_PROJECT=$PROJECT_ID python ../eval/run_eval.py --out ../eval/results_gemini.json
AI_MODE=gemini GOOGLE_CLOUD_PROJECT=$PROJECT_ID python ../eval/run_eval.py --baseline --out ../eval/results_baseline.json
```
The full runs take a while (40 cases × 6 documents). Report recall, precision and false alarms on clean
cases, FirstPass against the one-prompt baseline. Download the JSON files (⋮ → Download) for the deck.

## 5. Connect Firebase and deploy
1. console.firebase.google.com → **Add project** → choose your existing Google Cloud project → continue
   (Analytics not needed). Then **Build → Hosting → Get started** and click through (no commands needed there).
2. In Cloud Shell, from the `firstpass` folder:
```bash
deactivate 2>/dev/null; cd ~/firstpass
npx -y firebase-tools@13.29.1 login --no-localhost
sed "s/your-project-id/$PROJECT_ID/" .firebaserc.example > .firebaserc
PROJECT_ID=$PROJECT_ID ./scripts/deploy.sh
```
If you changed models or location in step 3, put the same values before the command, for example
`MODEL_EXTRACT=... MODEL_REASON=... GEMINI_LOCATION=us-central1 PROJECT_ID=$PROJECT_ID ./scripts/deploy.sh`.

The script deploys the API to Cloud Run in Singapore, builds the web app pointed at it, and publishes
it at **https://PROJECT_ID.web.app**.

## 6. Test the live app
- The sidebar should say **Gemini live**.
- Open the towels sample. Reading 6 documents with Gemini takes roughly 20-60 seconds the first time.
- Run all six steps, then the issues board: accept, dispute, upload the corrected invoice, re-check, waiver request.
- Upload 2-3 phone photos of printed, stamped documents. This is what convinces judges.

## 7. Put the code on GitHub (needed for submission)
github.com → **New repository** `firstpass` (public or private as the rules allow). Then in Cloud Shell:
```bash
cd ~/firstpass
git init && git add . && git commit -m "FirstPass: LC document checks with Gemini"
git branch -M main
git remote add origin https://github.com/YOUR_USER/firstpass.git
git push -u origin main      # use a GitHub personal access token as the password
```

## If something breaks
| Symptom | Fix |
|---|---|
| `PERMISSION_DENIED` on aiplatform | Re-run `./scripts/setup_gcp.sh`; check billing is linked |
| `404 model not found` | Use a model from Model Garden: `gcloud run services update firstpass-api --region asia-southeast1 --update-env-vars MODEL_EXTRACT=<id>,MODEL_REASON=<id>` |
| Web app says the API is offline, or CORS error in the browser console | Re-run `deploy.sh`; it sets the allowed web addresses |
| Anything else | `gcloud run services logs read firstpass-api --region asia-southeast1 --limit 50` and paste it to Claude |

Costs: Cloud Run and Firestore stay near zero at hackathon traffic. Gemini is the main cost; the benchmark
runs are the biggest item, still usually a few dollars. Keep the budget alert on.
