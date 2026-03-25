#!/usr/bin/env bash
# -*- coding: utf-8 -*-

set -euo pipefail

import_dotenv() {
    local path="$1"
    [[ -f "$path" ]] || return 0

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
        [[ "$line" != *=* ]] && continue

        local name="${line%%=*}"
        local value="${line#*=}"
        name="${name%"${name##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"

        if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]] || [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
            value="${value:1:${#value}-2}"
        fi

        if [[ -n "$name" && -z "${!name+x}" ]]; then
            export "$name=$value"
        fi
    done < "$path"
}

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
        if gcloud secrets create "$name" \
            --project "$project_id" \
            --data-file="$tmp_file" \
            --replication-policy="automatic" >/dev/null; then
            echo "Secret criado: $name"
        else
            gcloud secrets versions add "$name" \
                --project "$project_id" \
                --data-file="$tmp_file" >/dev/null
            echo "Nova versao adicionada ao secret: $name"
        fi
    else
        gcloud secrets versions add "$name" \
            --project "$project_id" \
            --data-file="$tmp_file" >/dev/null
        echo "Nova versao adicionada ao secret: $name"
    fi

    rm -f "$tmp_file"
    trap - RETURN
}

new_cloud_run_env_file() {
    local tmp_file
    tmp_file="$(mktemp)"
    trap 'rm -f "$tmp_file"' RETURN

    for entry in "$@"; do
        local name="${entry%%=*}"
        local value="${entry#*=}"
        value="${value//\'/\'\'}"
        printf "%s: '%s'\n" "$name" "$value" >> "$tmp_file"
    done

    echo "$tmp_file"
    trap - RETURN
}

urlencode() {
    python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
import_dotenv "${SCRIPT_DIR}/.env"

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
REGION="${GCP_REGION:-southamerica-east1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-castro-crm}"
DATA_BACKEND="${DATA_BACKEND:-firestore}"
AUTH_MODE="${AUTH_MODE:-firebase}"
SQL_INSTANCE_NAME="${SQL_INSTANCE_NAME:-castro-crm-db}"
DB_NAME="${DB_NAME:-castro_crm}"
DB_USER="${DB_USER:-castro_app}"
DB_PASSWORD="${DB_PASSWORD:-}"
MEDIA_BUCKET="${FIREBASE_STORAGE_BUCKET:-${GCS_MEDIA_BUCKET:-${PROJECT_ID}-castro-crm-media}}"
GCS_MEDIA_PREFIX="${GCS_MEDIA_PREFIX:-media}"
FIRESTORE_COLLECTION_PREFIX="${FIRESTORE_COLLECTION_PREFIX:-castro_crm}"
ALLOWED_FIREBASE_EMAIL_DOMAIN="${ALLOWED_FIREBASE_EMAIL_DOMAIN:-}"
ALLOWED_FIREBASE_EMAILS="${ALLOWED_FIREBASE_EMAILS:-}"
AUTO_PROVISION_FIREBASE_USERS="${AUTO_PROVISION_FIREBASE_USERS:-true}"
FIREBASE_WEB_API_KEY="${FIREBASE_WEB_API_KEY:-}"
FIREBASE_WEB_AUTH_DOMAIN="${FIREBASE_WEB_AUTH_DOMAIN:-${PROJECT_ID}.firebaseapp.com}"
FIREBASE_WEB_APP_ID="${FIREBASE_WEB_APP_ID:-}"
FIREBASE_WEB_MESSAGING_SENDER_ID="${FIREBASE_WEB_MESSAGING_SENDER_ID:-}"
FIREBASE_WEB_MEASUREMENT_ID="${FIREBASE_WEB_MEASUREMENT_ID:-}"
FEATURE_AUDIO_TRANSCRIPTION="${FEATURE_AUDIO_TRANSCRIPTION:-false}"
STT_LANGUAGE_CODE="${STT_LANGUAGE_CODE:-pt-BR}"
STT_TIMEOUT_SECONDS="${STT_TIMEOUT_SECONDS:-30.0}"
STT_FALLBACK_TEXT="${STT_FALLBACK_TEXT:-}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
WHATSAPP_TOKEN="${WHATSAPP_TOKEN:-}"
WHATSAPP_VERIFY_TOKEN="${WHATSAPP_VERIFY_TOKEN:-}"
WHATSAPP_APP_SECRET="${WHATSAPP_APP_SECRET:-}"
WHATSAPP_PHONE_NUMBER_ID="${WHATSAPP_PHONE_NUMBER_ID:-}"
WHATSAPP_WABA_ID="${WHATSAPP_WABA_ID:-}"
BOOTSTRAP_ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-}"
BOOTSTRAP_ADMIN_USERNAME="${BOOTSTRAP_ADMIN_USERNAME:-admin}"
BOOTSTRAP_ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-}"
BOOTSTRAP_ADMIN_DISPLAY_NAME="${BOOTSTRAP_ADMIN_DISPLAY_NAME:-Administrador}"
BOOTSTRAP_ADMIN_DEPARTMENT="${BOOTSTRAP_ADMIN_DEPARTMENT:-Geral}"
JWT_EXPIRATION_MINUTES="${JWT_EXPIRATION_MINUTES:-480}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
CORS_ORIGINS="${CORS_ORIGINS:-}"
REQUIRE_WEBHOOK_SIGNATURE="${REQUIRE_WEBHOOK_SIGNATURE:-true}"
CHAT_DELIVERY_MODE="${CHAT_DELIVERY_MODE:-snapshot}"
POLLING_INTERVAL_MS="${POLLING_INTERVAL_MS:-5000}"
ENABLE_AUDIO_TRANSCRIPTION=false
case "${FEATURE_AUDIO_TRANSCRIPTION,,}" in
  1|true|yes|on) ENABLE_AUDIO_TRANSCRIPTION=true ;;
esac

require_value "GCP_PROJECT_ID" "$PROJECT_ID"
require_value "WHATSAPP_TOKEN" "$WHATSAPP_TOKEN"
require_value "WHATSAPP_VERIFY_TOKEN" "$WHATSAPP_VERIFY_TOKEN"
require_value "WHATSAPP_APP_SECRET" "$WHATSAPP_APP_SECRET"
require_value "WHATSAPP_PHONE_NUMBER_ID" "$WHATSAPP_PHONE_NUMBER_ID"

if [[ "$DATA_BACKEND" == "sql" ]]; then
    require_value "DB_PASSWORD" "$DB_PASSWORD"
fi

if [[ "$AUTH_MODE" == "legacy" ]]; then
    require_value "BOOTSTRAP_ADMIN_PASSWORD" "$BOOTSTRAP_ADMIN_PASSWORD"
fi

echo "Projeto:  $PROJECT_ID"
echo "Regiao:   $REGION"
echo "Servico:  $SERVICE_NAME"
echo "Backend:  $DATA_BACKEND"
echo "Auth:     $AUTH_MODE"
echo ""

gcloud config set project "$PROJECT_ID" >/dev/null

SERVICES=(
  run.googleapis.com
  cloudbuild.googleapis.com
  artifactregistry.googleapis.com
  secretmanager.googleapis.com
  storage.googleapis.com
  firestore.googleapis.com
)

if [[ "$DATA_BACKEND" == "sql" ]]; then
  SERVICES+=(sqladmin.googleapis.com)
fi

if [[ "$ENABLE_AUDIO_TRANSCRIPTION" == "true" ]]; then
  SERVICES+=(speech.googleapis.com)
fi

gcloud services enable "${SERVICES[@]}" --project "$PROJECT_ID" --quiet >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")"
COMPUTE_SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

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
    --role "roles/secretmanager.secretAccessor" \
    --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${COMPUTE_SERVICE_ACCOUNT}" \
    --role "roles/storage.objectViewer" \
    --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${COMPUTE_SERVICE_ACCOUNT}" \
    --role "roles/artifactregistry.writer" \
    --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${COMPUTE_SERVICE_ACCOUNT}" \
    --role "roles/logging.logWriter" \
    --quiet >/dev/null

gcloud storage buckets add-iam-policy-binding "gs://${MEDIA_BUCKET}" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role "roles/storage.objectAdmin" >/dev/null

if [[ "$DATA_BACKEND" == "sql" ]]; then
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role "roles/cloudsql.client" \
        --quiet >/dev/null
else
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role "roles/datastore.user" \
        --quiet >/dev/null
fi

if [[ "$ENABLE_AUDIO_TRANSCRIPTION" == "true" ]]; then
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
        --role "roles/speech.client" \
        --quiet >/dev/null
fi

APP_SECRET_NAME="${SERVICE_NAME}-secret-key"
WA_TOKEN_SECRET_NAME="${SERVICE_NAME}-whatsapp-token"
WA_VERIFY_SECRET_NAME="${SERVICE_NAME}-whatsapp-verify-token"
WA_APP_SECRET_NAME="${SERVICE_NAME}-whatsapp-app-secret"
SECRETS=(
  "SECRET_KEY=${APP_SECRET_NAME}:latest"
  "WHATSAPP_TOKEN=${WA_TOKEN_SECRET_NAME}:latest"
  "WHATSAPP_VERIFY_TOKEN=${WA_VERIFY_SECRET_NAME}:latest"
  "WHATSAPP_APP_SECRET=${WA_APP_SECRET_NAME}:latest"
)

set_gcp_secret "$PROJECT_ID" "$APP_SECRET_NAME" "$SECRET_KEY"
set_gcp_secret "$PROJECT_ID" "$WA_TOKEN_SECRET_NAME" "$WHATSAPP_TOKEN"
set_gcp_secret "$PROJECT_ID" "$WA_VERIFY_SECRET_NAME" "$WHATSAPP_VERIFY_TOKEN"
set_gcp_secret "$PROJECT_ID" "$WA_APP_SECRET_NAME" "$WHATSAPP_APP_SECRET"

EXTRA_ARGS=()

if [[ "$DATA_BACKEND" == "sql" ]]; then
    INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE_NAME" --project "$PROJECT_ID" --format="value(connectionName)")"
    require_value "SQL_INSTANCE_NAME" "$INSTANCE_CONNECTION_NAME"
    DB_USER_ENCODED="$(urlencode "$DB_USER")"
    DB_PASSWORD_ENCODED="$(urlencode "$DB_PASSWORD")"
    DATABASE_URL="postgresql+pg8000://${DB_USER_ENCODED}:${DB_PASSWORD_ENCODED}@/${DB_NAME}?unix_sock=/cloudsql/${INSTANCE_CONNECTION_NAME}/.s.PGSQL.5432"
    DB_SECRET_NAME="${SERVICE_NAME}-database-url"
    set_gcp_secret "$PROJECT_ID" "$DB_SECRET_NAME" "$DATABASE_URL"
    SECRETS+=("DATABASE_URL=${DB_SECRET_NAME}:latest")
    EXTRA_ARGS+=(--add-cloudsql-instances "$INSTANCE_CONNECTION_NAME")
fi

if [[ "$AUTH_MODE" == "legacy" ]]; then
    BOOTSTRAP_PASSWORD_SECRET_NAME="${SERVICE_NAME}-bootstrap-admin-password"
    set_gcp_secret "$PROJECT_ID" "$BOOTSTRAP_PASSWORD_SECRET_NAME" "$BOOTSTRAP_ADMIN_PASSWORD"
    SECRETS+=("BOOTSTRAP_ADMIN_PASSWORD=${BOOTSTRAP_PASSWORD_SECRET_NAME}:latest")
fi

ENV_VARS=(
  "DATA_BACKEND=${DATA_BACKEND}"
  "AUTH_MODE=${AUTH_MODE}"
  "FIRESTORE_PROJECT_ID=${PROJECT_ID}"
  "FIRESTORE_COLLECTION_PREFIX=${FIRESTORE_COLLECTION_PREFIX}"
  "MEDIA_STORAGE_BACKEND=gcs"
  "FIREBASE_STORAGE_BUCKET=${MEDIA_BUCKET}"
  "GCS_MEDIA_BUCKET=${MEDIA_BUCKET}"
  "GCS_MEDIA_PREFIX=${GCS_MEDIA_PREFIX}"
  "JWT_EXPIRATION_MINUTES=${JWT_EXPIRATION_MINUTES}"
  "WHATSAPP_PHONE_NUMBER_ID=${WHATSAPP_PHONE_NUMBER_ID}"
  "WHATSAPP_WABA_ID=${WHATSAPP_WABA_ID}"
  "BOOTSTRAP_ADMIN_DISPLAY_NAME=${BOOTSTRAP_ADMIN_DISPLAY_NAME}"
  "BOOTSTRAP_ADMIN_DEPARTMENT=${BOOTSTRAP_ADMIN_DEPARTMENT}"
  "CORS_ORIGINS=${CORS_ORIGINS}"
  "REQUIRE_WEBHOOK_SIGNATURE=${REQUIRE_WEBHOOK_SIGNATURE}"
  "LOG_LEVEL=${LOG_LEVEL}"
  "LOG_TO_FILE=false"
  "CHAT_DELIVERY_MODE=${CHAT_DELIVERY_MODE}"
  "POLLING_INTERVAL_MS=${POLLING_INTERVAL_MS}"
  "ALLOWED_FIREBASE_EMAIL_DOMAIN=${ALLOWED_FIREBASE_EMAIL_DOMAIN}"
  "ALLOWED_FIREBASE_EMAILS=${ALLOWED_FIREBASE_EMAILS}"
  "AUTO_PROVISION_FIREBASE_USERS=${AUTO_PROVISION_FIREBASE_USERS}"
  "FIREBASE_WEB_API_KEY=${FIREBASE_WEB_API_KEY}"
  "FIREBASE_WEB_AUTH_DOMAIN=${FIREBASE_WEB_AUTH_DOMAIN}"
  "FIREBASE_WEB_APP_ID=${FIREBASE_WEB_APP_ID}"
  "FIREBASE_WEB_MESSAGING_SENDER_ID=${FIREBASE_WEB_MESSAGING_SENDER_ID}"
  "FIREBASE_WEB_MEASUREMENT_ID=${FIREBASE_WEB_MEASUREMENT_ID}"
  "FEATURE_AUDIO_TRANSCRIPTION=${FEATURE_AUDIO_TRANSCRIPTION}"
  "STT_LANGUAGE_CODE=${STT_LANGUAGE_CODE}"
  "STT_TIMEOUT_SECONDS=${STT_TIMEOUT_SECONDS}"
  "STT_FALLBACK_TEXT=${STT_FALLBACK_TEXT}"
)

if [[ "$AUTH_MODE" == "firebase" ]]; then
  ENV_VARS+=("BOOTSTRAP_ADMIN_EMAIL=${BOOTSTRAP_ADMIN_EMAIL}")
else
  ENV_VARS+=("BOOTSTRAP_ADMIN_USERNAME=${BOOTSTRAP_ADMIN_USERNAME}")
fi

echo ""
echo "Iniciando deploy no Cloud Run..."

ENV_FILE="$(new_cloud_run_env_file "${ENV_VARS[@]}")"
trap 'rm -f "$ENV_FILE"' EXIT

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --service-account "$SERVICE_ACCOUNT_EMAIL" \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --concurrency 40 \
    --timeout 300 \
    --env-vars-file "$ENV_FILE" \
    --set-secrets "$(IFS=,; echo "${SECRETS[*]}")" \
    "${EXTRA_ARGS[@]}"

rm -f "$ENV_FILE"
trap - EXIT

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" --project "$PROJECT_ID" --region "$REGION" --format="value(status.url)")"

echo ""
echo "Deploy concluido."
echo "URL do servico: $SERVICE_URL"
echo "Webhook:         ${SERVICE_URL}/webhook"
echo "Bucket de media: gs://${MEDIA_BUCKET}"
echo ""
