#!/usr/bin/env bash
# -*- coding: utf-8 -*-

set -euo pipefail

require_value() {
    local name="$1"
    local value="${2:-}"
    if [[ -z "$value" || "$value" == "(unset)" ]]; then
        echo "ERRO: defina $name antes de executar."
        exit 1
    fi
}

set_gcp_secret() {
    local project_id="$1"
    local name="$2"
    local value="$3"
    local tmp_file

    require_value "$name" "$value"

    tmp_file="$(mktemp)"
    trap 'rm -f "$tmp_file"' RETURN
    printf "%s" "$value" > "$tmp_file"

    if ! gcloud secrets describe "$name" --project "$project_id" >/dev/null 2>&1; then
        gcloud secrets create "$name" \
            --project "$project_id" \
            --data-file="$tmp_file" \
            --replication-policy="automatic" >/dev/null
        echo "Secret criado: $name"
    else
        gcloud secrets versions add "$name" \
            --project "$project_id" \
            --data-file="$tmp_file" >/dev/null
        echo "Nova versao adicionada ao secret: $name"
    fi

    rm -f "$tmp_file"
    trap - RETURN
}

urlencode() {
    python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${GCP_REGION:-southamerica-east1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-castro-crm}"
SQL_INSTANCE_NAME="${SQL_INSTANCE_NAME:-castro-crm-db}"
DB_NAME="${DB_NAME:-castro_crm}"
DB_USER="${DB_USER:-castro_app}"
MEDIA_BUCKET="${GCS_MEDIA_BUCKET:-${PROJECT_ID}-castro-crm-media}"
GCS_MEDIA_PREFIX="${GCS_MEDIA_PREFIX:-media}"
DB_PASSWORD="${DB_PASSWORD:-}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
WHATSAPP_TOKEN="${WHATSAPP_TOKEN:-}"
WHATSAPP_VERIFY_TOKEN="${WHATSAPP_VERIFY_TOKEN:-}"
WHATSAPP_APP_SECRET="${WHATSAPP_APP_SECRET:-}"
WHATSAPP_PHONE_NUMBER_ID="${WHATSAPP_PHONE_NUMBER_ID:-}"
WHATSAPP_WABA_ID="${WHATSAPP_WABA_ID:-}"
BOOTSTRAP_ADMIN_USERNAME="${BOOTSTRAP_ADMIN_USERNAME:-admin}"
BOOTSTRAP_ADMIN_DISPLAY_NAME="${BOOTSTRAP_ADMIN_DISPLAY_NAME:-Administrador}"
BOOTSTRAP_ADMIN_DEPARTMENT="${BOOTSTRAP_ADMIN_DEPARTMENT:-Geral}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-}"
JWT_EXPIRATION_MINUTES="${JWT_EXPIRATION_MINUTES:-480}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

require_value "GCP_PROJECT_ID" "$PROJECT_ID"
require_value "DB_PASSWORD" "$DB_PASSWORD"
require_value "WHATSAPP_TOKEN" "$WHATSAPP_TOKEN"
require_value "WHATSAPP_VERIFY_TOKEN" "$WHATSAPP_VERIFY_TOKEN"
require_value "WHATSAPP_APP_SECRET" "$WHATSAPP_APP_SECRET"
require_value "WHATSAPP_PHONE_NUMBER_ID" "$WHATSAPP_PHONE_NUMBER_ID"
require_value "BOOTSTRAP_ADMIN_PASSWORD" "$BOOTSTRAP_ADMIN_PASSWORD"

echo "Projeto:  $PROJECT_ID"
echo "Regiao:   $REGION"
echo "Servico:  $SERVICE_NAME"
echo "Instancia $SQL_INSTANCE_NAME"
echo ""

gcloud config set project "$PROJECT_ID" >/dev/null

gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    --project "$PROJECT_ID" \
    --quiet >/dev/null

INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE_NAME" --project "$PROJECT_ID" --format="value(connectionName)")"
require_value "SQL_INSTANCE_NAME" "$INSTANCE_CONNECTION_NAME"

DB_USER_ENCODED="$(urlencode "$DB_USER")"
DB_PASSWORD_ENCODED="$(urlencode "$DB_PASSWORD")"
DATABASE_URL="postgresql+pg8000://${DB_USER_ENCODED}:${DB_PASSWORD_ENCODED}@/${DB_NAME}?unix_sock=/cloudsql/${INSTANCE_CONNECTION_NAME}/.s.PGSQL.5432"

SERVICE_ACCOUNT_EMAIL="${SERVICE_NAME}-run@${PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${SERVICE_NAME}-run" \
        --project "$PROJECT_ID" \
        --display-name "${SERVICE_NAME} runtime" >/dev/null
fi

if ! gcloud storage buckets describe "gs://${MEDIA_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${MEDIA_BUCKET}" \
        --project "$PROJECT_ID" \
        --location "$REGION" \
        --uniform-bucket-level-access \
        --public-access-prevention >/dev/null
fi

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role "roles/cloudsql.client" \
    --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role "roles/secretmanager.secretAccessor" \
    --quiet >/dev/null

gcloud storage buckets add-iam-policy-binding "gs://${MEDIA_BUCKET}" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role "roles/storage.objectAdmin" >/dev/null

DB_SECRET_NAME="${SERVICE_NAME}-database-url"
APP_SECRET_NAME="${SERVICE_NAME}-secret-key"
WA_TOKEN_SECRET_NAME="${SERVICE_NAME}-whatsapp-token"
WA_VERIFY_SECRET_NAME="${SERVICE_NAME}-whatsapp-verify-token"
WA_APP_SECRET_NAME="${SERVICE_NAME}-whatsapp-app-secret"
BOOTSTRAP_PASSWORD_SECRET_NAME="${SERVICE_NAME}-bootstrap-admin-password"

set_gcp_secret "$PROJECT_ID" "$DB_SECRET_NAME" "$DATABASE_URL"
set_gcp_secret "$PROJECT_ID" "$APP_SECRET_NAME" "$SECRET_KEY"
set_gcp_secret "$PROJECT_ID" "$WA_TOKEN_SECRET_NAME" "$WHATSAPP_TOKEN"
set_gcp_secret "$PROJECT_ID" "$WA_VERIFY_SECRET_NAME" "$WHATSAPP_VERIFY_TOKEN"
set_gcp_secret "$PROJECT_ID" "$WA_APP_SECRET_NAME" "$WHATSAPP_APP_SECRET"
set_gcp_secret "$PROJECT_ID" "$BOOTSTRAP_PASSWORD_SECRET_NAME" "$BOOTSTRAP_ADMIN_PASSWORD"

echo ""
echo "Iniciando deploy no Cloud Run..."

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --service-account "$SERVICE_ACCOUNT_EMAIL" \
    --add-cloudsql-instances "$INSTANCE_CONNECTION_NAME" \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 1 \
    --timeout 300 \
    --set-env-vars "LOG_LEVEL=${LOG_LEVEL},LOG_TO_FILE=false,MEDIA_STORAGE_BACKEND=gcs,GCS_MEDIA_BUCKET=${MEDIA_BUCKET},GCS_MEDIA_PREFIX=${GCS_MEDIA_PREFIX},JWT_EXPIRATION_MINUTES=${JWT_EXPIRATION_MINUTES},WHATSAPP_PHONE_NUMBER_ID=${WHATSAPP_PHONE_NUMBER_ID},WHATSAPP_WABA_ID=${WHATSAPP_WABA_ID},BOOTSTRAP_ADMIN_USERNAME=${BOOTSTRAP_ADMIN_USERNAME},BOOTSTRAP_ADMIN_DISPLAY_NAME=${BOOTSTRAP_ADMIN_DISPLAY_NAME},BOOTSTRAP_ADMIN_DEPARTMENT=${BOOTSTRAP_ADMIN_DEPARTMENT}" \
    --set-secrets "DATABASE_URL=${DB_SECRET_NAME}:latest,SECRET_KEY=${APP_SECRET_NAME}:latest,WHATSAPP_TOKEN=${WA_TOKEN_SECRET_NAME}:latest,WHATSAPP_VERIFY_TOKEN=${WA_VERIFY_SECRET_NAME}:latest,WHATSAPP_APP_SECRET=${WA_APP_SECRET_NAME}:latest,BOOTSTRAP_ADMIN_PASSWORD=${BOOTSTRAP_PASSWORD_SECRET_NAME}:latest"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format="value(status.url)")"

echo ""
echo "Deploy concluido."
echo "URL do servico: $SERVICE_URL"
echo "Webhook:         ${SERVICE_URL}/webhook"
echo "Bucket de media: gs://${MEDIA_BUCKET}"
echo ""
echo "A midia agora fica persistida no Cloud Storage."
