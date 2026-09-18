#!/usr/bin/env bash
# Deploy do IncorpoData no Cloud Run + Cloud SQL (Postgres/PostGIS).
# Idempotente: pode rodar de novo (cria só o que falta). Carrega dados via load_data.sh.
#
# Uso:
#   PROJECT=meu-projeto DBPASS='senha-forte' JWT_SECRET='segredo' bash deploy/deploy.sh
set -euo pipefail

PROJECT="${PROJECT:?defina PROJECT (id do projeto GCP)}"
REGION="${REGION:-southamerica-east1}"          # São Paulo (mais perto da PB)
INSTANCE="${INSTANCE:-incorpodata-pg}"
DB="${DB:-terraiq}"
DBUSER="${DBUSER:-terraiq}"
DBPASS="${DBPASS:?defina DBPASS (senha do Postgres no Cloud SQL)}"
SERVICE="${SERVICE:-incorpodata}"
TIER="${TIER:-db-custom-1-3840}"                # 1 vCPU / 3.75GB; troque p/ db-f1-micro p/ baratear
JWT_SECRET="${JWT_SECRET:?defina JWT_SECRET}"

echo "→ projeto $PROJECT | região $REGION | instância $INSTANCE | serviço $SERVICE"
gcloud config set project "$PROJECT" >/dev/null

echo "→ habilitando APIs…"
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com >/dev/null

echo "→ Cloud SQL (cria se não existir; ~minutos na 1ª vez)…"
if ! gcloud sql instances describe "$INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$INSTANCE" \
    --database-version=POSTGRES_16 --tier="$TIER" --region="$REGION" \
    --storage-size=10GB --storage-auto-increase
fi

echo "→ usuário e banco…"
gcloud sql users set-password "$DBUSER" --instance="$INSTANCE" --password="$DBPASS" >/dev/null 2>&1 \
  || gcloud sql users create "$DBUSER" --instance="$INSTANCE" --password="$DBPASS"
gcloud sql databases create "$DB" --instance="$INSTANCE" >/dev/null 2>&1 || true

CONN=$(gcloud sql instances describe "$INSTANCE" --format='value(connectionName)')
echo "→ connectionName: $CONN"

echo "→ carregando dados (PostGIS + schemas + 186k lotes/28k comps)…"
CONN="$CONN" DB="$DB" DBUSER="$DBUSER" DBPASS="$DBPASS" bash deploy/load_data.sh

echo "→ deploy no Cloud Run (build da imagem a partir do Dockerfile)…"
DBURL="postgresql+psycopg2://${DBUSER}:${DBPASS}@/${DB}?host=/cloudsql/${CONN}"
gcloud run deploy "$SERVICE" \
  --source . --region "$REGION" --allow-unauthenticated \
  --add-cloudsql-instances "$CONN" \
  --set-env-vars "DATABASE_URL=${DBURL},JWT_SECRET=${JWT_SECRET}" \
  --memory 512Mi --cpu 1 --port 8080 --timeout 60

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "✓ deployado: $URL"
echo "  health: $URL/api/health"
