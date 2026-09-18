#!/usr/bin/env bash
# Deploy MAIS BARATO: Cloud Run (escala a zero) + Postgres/PostGIS gerenciado EXTERNO
# (Neon/Supabase free) — sem Cloud SQL. Você passa o DATABASE_URL do provedor.
#
# Uso:
#   PROJECT=<proj> \
#   DATABASE_URL='postgresql://user:pass@ep-xxx.neon.tech/incorpodata?sslmode=require' \
#   JWT_SECRET='<segredo>' bash deploy/deploy_cloudrun.sh
set -euo pipefail

PROJECT="${PROJECT:?defina PROJECT}"
REGION="${REGION:-southamerica-east1}"
SERVICE="${SERVICE:-incorpodata}"
DATABASE_URL="${DATABASE_URL:?defina DATABASE_URL do Neon/Supabase}"
JWT_SECRET="${JWT_SECRET:?defina JWT_SECRET}"
PG_CONTAINER="${PG_CONTAINER:-terraiq-postgis}"   # Postgres LOCAL de origem
SRC_DB="${SRC_DB:-terraiq}"
SRC_USER="${SRC_USER:-terraiq}"
LOAD_DATA="${LOAD_DATA:-1}"                        # 0 = pular carga (só re-deploy de código)

gcloud config set project "$PROJECT" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com >/dev/null

# psql normaliza o driver do SQLAlchemy de volta p/ libpq
PSQL_URL="${DATABASE_URL/postgresql+psycopg2:/postgresql:}"

if [ "$LOAD_DATA" = "1" ]; then
  echo "→ dump local (geo, zoning, market, app) + PostGIS…"
  docker exec "$PG_CONTAINER" pg_dump -U "$SRC_USER" --no-owner --no-privileges \
    -n geo -n zoning -n market -n app "$SRC_DB" > /tmp/incorpodata_dump.sql
  echo "→ carregando no banco externo (CREATE EXTENSION postgis + restore)…"
  psql "$PSQL_URL" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS postgis;"
  psql "$PSQL_URL" -v ON_ERROR_STOP=1 -f /tmp/incorpodata_dump.sql >/dev/null
  echo "→ conferência: $(psql "$PSQL_URL" -tAc 'select count(*) from geo.lotes') lotes"
fi

echo "→ deploy no Cloud Run…"
# Delimitador custom (^##^): REGISTER_INVITE_CODE pode conter vírgulas (vários códigos),
# que quebrariam o --set-env-vars padrão. REGISTER_INVITE_CODE vazio/ausente → registro FECHADO.
ENV_VARS="DATABASE_URL=${DATABASE_URL}##JWT_SECRET=${JWT_SECRET}"
if [ -n "${REGISTER_INVITE_CODE:-}" ]; then
  ENV_VARS="${ENV_VARS}##REGISTER_INVITE_CODE=${REGISTER_INVITE_CODE}"
  echo "  · registro por convite: ON"
else
  echo "  · registro por convite: OFF (defina REGISTER_INVITE_CODE p/ liberar cadastro)"
fi
gcloud run deploy "$SERVICE" \
  --source . --region "$REGION" --allow-unauthenticated \
  --set-env-vars "^##^${ENV_VARS}" \
  --memory 512Mi --cpu 1 --port 8080 --timeout 60

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "✓ no ar: $URL   (health: $URL/api/health)"
