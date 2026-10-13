#!/usr/bin/env bash
# Deploy cloud-only Sleeper BYE/OUT fix after automated checks.
# Usage: bash tools/deploy_sleeper_rc8.sh fantasy-command-center-2026 southamerica-east1
set -euo pipefail
PROJECT="${1:-fantasy-command-center-2026}"
REGION="${2:-southamerica-east1}"
API="fcc-api-v8"
WORKER="fcc-worker-v8"
SCHEDULER="fcc-v8-sync"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "Projeto: $PROJECT, região: $REGION"
gcloud run services describe "$API" --project="$PROJECT" --region="$REGION" >/dev/null
gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" >/dev/null
gcloud scheduler jobs describe "$SCHEDULER" --project="$PROJECT" --location="$REGION" >/dev/null
API_URL="$(gcloud run services describe "$API" --project="$PROJECT" --region="$REGION" --format='value(status.url)')"
test -n "$API_URL" || { echo "API URL não disponível"; exit 3; }
LIVE_VERSION="$(curl -fsS --max-time 25 "$API_URL/health" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("version",""))')"
echo "Versão do backend em produção: $LIVE_VERSION"
if [[ "$LIVE_VERSION" != "8.0.0-rc7" ]]; then
  echo "PARE: hotfix projetado exclusivamente para RC7. Não substitua $LIVE_VERSION sem comparar fontes."
  exit 4
fi
echo "Executando testes antes de publicar..."
python3 -m venv "$ROOT/.hotfix-venv"
"$ROOT/.hotfix-venv/bin/python" -m pip install --disable-pip-version-check -q -r "$ROOT/backend/requirements-dev.txt"
(cd "$ROOT/backend" && "$ROOT/.hotfix-venv/bin/python" -m pytest -q tests/test_sleeper_week_coverage.py tests/test_reliability.py tests/test_providers.py)
BEFORE_API="$(gcloud run services describe "$API" --project="$PROJECT" --region="$REGION" --format='value(status.latestReadyRevisionName)')"
BEFORE_WORKER="$(gcloud run services describe "$WORKER" --project="$PROJECT" --region="$REGION" --format='value(status.latestReadyRevisionName)')"
echo "Revisões anteriores para rollback: API=$BEFORE_API WORKER=$BEFORE_WORKER"
BUILD_SA="projects/$PROJECT/serviceAccounts/fcc-v8-build@$PROJECT.iam.gserviceaccount.com"
echo "Publicando API no Cloud Run sem alterar variáveis, permissões ou secrets..."
gcloud run deploy "$API" --source "$ROOT/backend" --project "$PROJECT" --region "$REGION" --build-service-account "$BUILD_SA" --quiet
NEW_VERSION="$(curl -fsS --max-time 25 "$API_URL/health" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("version",""))')"
if [[ "$NEW_VERSION" != "8.0.0-rc8" ]]; then
  echo "API não confirmou RC8. Rollback da API e investigação necessários. Worker não foi alterado."
  echo "gcloud run services update-traffic $API --project=$PROJECT --region=$REGION --to-revisions=$BEFORE_API=100"
  exit 5
fi
IMAGE="$(gcloud run services describe "$API" --project="$PROJECT" --region="$REGION" --format='value(spec.template.spec.containers[0].image)')"
test -n "$IMAGE" || { echo "Imagem da API não encontrada; worker não foi alterado."; exit 6; }
echo "Publicando o mesmo código no worker..."
gcloud run deploy "$WORKER" --image "$IMAGE" --project "$PROJECT" --region "$REGION" --quiet
echo "Solicitando sincronização das ligas..."
gcloud scheduler jobs run "$SCHEDULER" --project "$PROJECT" --location "$REGION"
echo "Deploy solicitado: API $NEW_VERSION. Confira logs do scheduler/worker e dados reais das duas ligas."
echo "Versões anteriores, para reversão se necessário:"
echo "gcloud run services update-traffic $API --project=$PROJECT --region=$REGION --to-revisions=$BEFORE_API=100"
echo "gcloud run services update-traffic $WORKER --project=$PROJECT --region=$REGION --to-revisions=$BEFORE_WORKER=100"
