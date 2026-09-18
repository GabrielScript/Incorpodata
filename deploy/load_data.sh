#!/usr/bin/env bash
# Carrega a base local (geo/zoning/market/app) no Cloud SQL via dump + import por GCS.
# Habilita PostGIS antes do import (o dump referencia o tipo geometry).
# Chamado por deploy.sh; também roda sozinho com CONN/DB/DBUSER/DBPASS no ambiente.
set -euo pipefail

CONN="${CONN:?defina CONN (connectionName do Cloud SQL)}"
DB="${DB:-terraiq}"
DBUSER="${DBUSER:-terraiq}"
DBPASS="${DBPASS:?defina DBPASS}"
INSTANCE="${INSTANCE:-${CONN##*:}}"
PG_CONTAINER="${PG_CONTAINER:-terraiq-postgis}"   # Postgres LOCAL de origem (Docker)
PROJECT="$(gcloud config get-value project 2>/dev/null)"
BUCKET="${BUCKET:-gs://${PROJECT}-incorpodata-load}"

echo "  · dump local dos schemas de dados (geo, zoning, market, app)…"
docker exec "$PG_CONTAINER" pg_dump -U "$DBUSER" --no-owner --no-privileges \
  -n geo -n zoning -n market -n app "$DB" > /tmp/incorpodata_dump.sql
# PostGIS precisa existir antes de recriar tabelas com geometry:
{ echo "CREATE EXTENSION IF NOT EXISTS postgis;"; cat /tmp/incorpodata_dump.sql; } > /tmp/incorpodata_load.sql
echo "  · dump: $(wc -c < /tmp/incorpodata_load.sql) bytes"

echo "  · bucket + upload…"
gsutil mb -l "${REGION:-southamerica-east1}" "$BUCKET" 2>/dev/null || true
gsutil cp /tmp/incorpodata_load.sql "$BUCKET/load.sql"

# A service account do Cloud SQL precisa ler o objeto:
SA=$(gcloud sql instances describe "$INSTANCE" --format='value(serviceAccountEmailAddress)')
gsutil iam ch "serviceAccount:${SA}:objectViewer" "$BUCKET" 2>/dev/null || true

echo "  · habilitando PostGIS no Cloud SQL…"
# CREATE EXTENSION já vai no load.sql; o import roda como superuser do Cloud SQL.
echo "  · import (pode levar minutos)…"
gcloud sql import sql "$INSTANCE" "$BUCKET/load.sql" --database="$DB" --quiet

echo "  ✓ dados carregados no Cloud SQL ($DB)"
