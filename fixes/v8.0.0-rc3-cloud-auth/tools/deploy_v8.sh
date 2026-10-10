#!/usr/bin/env bash
# Deploy the existing RC3 backend with corrected Cloud authentication helpers.
set -euo pipefail
FCC_PROJECT="${1:?Usage: bash tools/deploy_v8.sh PROJECT_ID FIREBASE_KEY_SECRET[:VERSION] [REGION]}"
FCC_KEY_REFERENCE="${2:?Provide a Secret Manager reference, never the key value}"
FCC_REGION="${3:-southamerica-east1}"
[[ "$FCC_PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || { echo 'Invalid project ID'; exit 2; }
[[ "$FCC_KEY_REFERENCE" =~ ^[A-Za-z0-9_-]+:[0-9]+$ ]] || { echo 'Use SECRET_NAME:VERSION_NUMBER'; exit 2; }
[[ "$FCC_REGION" =~ ^[a-z0-9-]+$ ]] || exit 2
FCC_FIX_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
FCC_SOURCE_PATH="${4:-$FCC_FIX_ROOT/../../candidates/v8.0.0-rc3}"
[[ -f "$FCC_SOURCE_PATH/backend/Dockerfile" ]] || { echo 'RC3 backend not found; provide its package directory as argument 4.'; exit 2; }
FCC_ROOT="$(cd -- "$FCC_SOURCE_PATH" && pwd)"
FCC_API='fcc-api-v8'
FCC_WORKER='fcc-worker-v8'
FCC_API_SA="fcc-v8-api@${FCC_PROJECT}.iam.gserviceaccount.com"
FCC_WORKER_SA="fcc-v8-worker@${FCC_PROJECT}.iam.gserviceaccount.com"
FCC_BUILD_SA="fcc-v8-build@${FCC_PROJECT}.iam.gserviceaccount.com"
FCC_SCHEDULER_SA="fcc-v8-scheduler@${FCC_PROJECT}.iam.gserviceaccount.com"
FCC_GOOGLE_CLIENT_ID="$(python3 "$FCC_FIX_ROOT/tools/firebase_google_client.py" --project "$FCC_PROJECT")"
[[ "$FCC_GOOGLE_CLIENT_ID" =~ ^[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$ ]] || { echo 'Invalid Google OAuth client ID'; exit 2; }

gcloud run deploy "$FCC_API" --project "$FCC_PROJECT" --region "$FCC_REGION" \
  --source "$FCC_ROOT/backend" \
  --build-service-account "projects/$FCC_PROJECT/serviceAccounts/$FCC_BUILD_SA" \
  --service-account "$FCC_API_SA" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --concurrency 20 --max-instances 3 --timeout 300 \
  --set-env-vars "FCC_GCP_PROJECT=$FCC_PROJECT,FCC_ROLE=api,FCC_COOKIE_SECURE=true,FCC_TRUST_PROXY_HEADERS=true,FCC_GOOGLE_CLIENT_ID=$FCC_GOOGLE_CLIENT_ID" \
  --set-secrets "FCC_FIREBASE_API_KEY=$FCC_KEY_REFERENCE"
FCC_API_URL="$(gcloud run services describe "$FCC_API" --project "$FCC_PROJECT" --region "$FCC_REGION" --format='value(status.url)')"
python3 "$FCC_FIX_ROOT/tools/firebase_google_client.py" --project "$FCC_PROJECT" --authorize-origin "$FCC_API_URL" >/dev/null
gcloud run services update "$FCC_API" --project "$FCC_PROJECT" --region "$FCC_REGION" \
  --update-env-vars "FCC_PUBLIC_ORIGIN=$FCC_API_URL"
FCC_IMAGE="$(gcloud run services describe "$FCC_API" --project "$FCC_PROJECT" --region "$FCC_REGION" --format='value(spec.template.spec.containers[0].image)')"

gcloud run deploy "$FCC_WORKER" --project "$FCC_PROJECT" --region "$FCC_REGION" \
  --image "$FCC_IMAGE" --service-account "$FCC_WORKER_SA" --no-allow-unauthenticated \
  --memory 1Gi --cpu 1 --concurrency 1 --max-instances 1 --timeout 1800 \
  --set-env-vars "FCC_GCP_PROJECT=$FCC_PROJECT,FCC_ROLE=worker,FCC_PUBLIC_ORIGIN=$FCC_API_URL"
FCC_WORKER_URL="$(gcloud run services describe "$FCC_WORKER" --project "$FCC_PROJECT" --region "$FCC_REGION" --format='value(status.url)')"
FCC_POLICY="$(gcloud run services get-iam-policy "$FCC_WORKER" --project "$FCC_PROJECT" --region "$FCC_REGION" --format=json)"
if ! python3 -c 'import json,sys; p=json.load(sys.stdin); sys.exit(any(m in ("allUsers","allAuthenticatedUsers") for b in p.get("bindings",[]) for m in b.get("members",[])))' <<< "$FCC_POLICY"; then
  echo 'Worker has a public IAM binding; correct its policy before scheduling.'
  exit 3
fi
gcloud run services add-iam-policy-binding "$FCC_WORKER" --project "$FCC_PROJECT" --region "$FCC_REGION" \
  --member "serviceAccount:$FCC_SCHEDULER_SA" --role roles/run.invoker

FCC_JOB_ACTION='create'
if gcloud scheduler jobs describe fcc-v8-sync --project "$FCC_PROJECT" --location "$FCC_REGION" >/dev/null 2>&1; then FCC_JOB_ACTION='update'; fi
gcloud scheduler jobs "$FCC_JOB_ACTION" http fcc-v8-sync --project "$FCC_PROJECT" --location "$FCC_REGION" \
  --schedule '0 */4 * * *' --time-zone America/Sao_Paulo \
  --uri "$FCC_WORKER_URL/internal/sync" --http-method POST --attempt-deadline 1800s \
  --oidc-service-account-email "$FCC_SCHEDULER_SA" --oidc-token-audience "$FCC_WORKER_URL" \
  --max-retry-attempts 1
printf 'Web: %s/app\nAndroid ApiBase: %s\n' "$FCC_API_URL" "$FCC_API_URL"
printf 'Google OAuth: authorize this JavaScript origin in Google Auth Platform > Clients: %s\n' "$FCC_API_URL"
printf 'Android: register com.douglas.fantasycommandcenter and the signing certificate SHA-1 in Firebase.\n'
