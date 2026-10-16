#!/usr/bin/env bash
# One-time Google Cloud setup. Usage: PROJECT_ID=my-project ./scripts/setup_gcp.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-southeast1}"          # Singapore
BUCKET="${BUCKET:-${PROJECT_ID}-firstpass-docs}"
SA="firstpass-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable aiplatform.googleapis.com run.googleapis.com firestore.googleapis.com \
  storage.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firebasehosting.googleapis.com

# Firestore (Native mode, default database) and a private bucket for uploaded documents
gcloud firestore databases create --location="$REGION" || echo "Firestore already exists"
gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access || echo "Bucket exists"

# Service account the Cloud Run service runs as (no API keys anywhere)
gcloud iam service-accounts create firstpass-run --display-name="FirstPass Cloud Run" || echo "SA exists"
for role in roles/aiplatform.user roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA}" --role="$role" --condition=None >/dev/null
done
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" --role=roles/storage.objectAdmin >/dev/null
echo "Done. Bucket: ${BUCKET}  Service account: ${SA}"
