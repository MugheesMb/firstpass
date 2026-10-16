#!/usr/bin/env bash
# Deploy the API to Cloud Run (Singapore) and the web app to Firebase Hosting.
# Usage: PROJECT_ID=my-project ./scripts/deploy.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-southeast1}"
BUCKET="${BUCKET:-${PROJECT_ID}-firstpass-docs}"
SA="firstpass-run@${PROJECT_ID}.iam.gserviceaccount.com"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORIGINS="https://${PROJECT_ID}.web.app,https://${PROJECT_ID}.firebaseapp.com,http://localhost:5173"

echo "== 1/3 Deploying the API to Cloud Run (${REGION})"
gcloud run deploy firstpass-api --project "$PROJECT_ID" --region "$REGION" --source "$ROOT/backend" \
  --service-account "$SA" --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 300 --max-instances 5 \
  --set-env-vars "^@^AI_MODE=gemini@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@GOOGLE_CLOUD_LOCATION=${GEMINI_LOCATION:-global}@GOOGLE_GENAI_USE_VERTEXAI=TRUE@STORE_BACKEND=firestore@FILE_BACKEND=gcs@GCS_BUCKET=${BUCKET}@MODEL_EXTRACT=${MODEL_EXTRACT:-gemini-3.8-flash}@MODEL_REASON=${MODEL_REASON:-gemini-3.1-pro-preview}@MODEL_REASON_FALLBACK=${MODEL_EXTRACT:-gemini-3.8-flash}@ALLOW_ORIGINS=${ORIGINS}"

API_URL="$(gcloud run services describe firstpass-api --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "API: ${API_URL}"
curl -fsS "${API_URL}/api/health" && echo

echo "== 2/3 Building the web app against ${API_URL}"
(cd "$ROOT/frontend" && npm ci && VITE_API_BASE="$API_URL" npm run build)

echo "== 3/3 Deploying the web app to Firebase Hosting"
(cd "$ROOT" && npx -y firebase-tools@13.29.1 deploy --only hosting --project "$PROJECT_ID")
echo "== Warming the cache with the demo cases (a few minutes, makes the demo fast)"
python3 "$ROOT/scripts/warm_demo.py" "$API_URL" || echo "Warm-up failed; run it again later: python3 scripts/warm_demo.py $API_URL"
echo "Done. Open https://${PROJECT_ID}.web.app"
