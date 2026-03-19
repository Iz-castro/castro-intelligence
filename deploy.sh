#!/bin/bash
# -*- coding: utf-8 -*-
# Deploy do CRM Castro Intelligence no Google Cloud Run
#
# Pre-requisitos:
#   1. Google Cloud SDK instalado (https://cloud.google.com/sdk/docs/install)
#   2. Projeto GCP criado e billing ativado
#   3. gcloud auth login (executar uma vez)
#
# Uso:
#   chmod +x deploy.sh
#   ./deploy.sh

set -e

# ── Configuracao ──────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-seu-projeto-gcp}"
REGION="southamerica-east1"
SERVICE_NAME="castro-crm"

# Variaveis de ambiente do WABA (preencher antes de rodar)
WA_TOKEN="${WHATSAPP_TOKEN:-}"
WA_PHONE_ID="${WHATSAPP_PHONE_NUMBER_ID:-}"
WA_WABA_ID="${WHATSAPP_WABA_ID:-}"
WA_VERIFY="${WHATSAPP_VERIFY_TOKEN:-}"
WA_APP_SECRET="${WHATSAPP_APP_SECRET:-}"
APP_SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

# ── Validacao ─────────────────────────────────────────────
if [ "$PROJECT_ID" = "seu-projeto-gcp" ]; then
    echo "ERRO: Defina GCP_PROJECT_ID antes de rodar."
    echo "  export GCP_PROJECT_ID=meu-projeto-123"
    exit 1
fi

if [ -z "$WA_VERIFY" ]; then
    echo "ERRO: Defina WHATSAPP_VERIFY_TOKEN antes de rodar."
    echo "  export WHATSAPP_VERIFY_TOKEN=seu_token_verificacao_webhook"
    exit 1
fi

echo "Projeto GCP: $PROJECT_ID"
echo "Regiao:      $REGION"
echo "Servico:     $SERVICE_NAME"
echo ""

# ── Garantir que esta no projeto certo ────────────────────
gcloud config set project "$PROJECT_ID"

# ── Ativar APIs necessarias ───────────────────────────────
echo "Ativando APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    2>/dev/null || true

# ── Build e deploy ────────────────────────────────────────
echo ""
echo "Iniciando build e deploy..."

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 2 \
    --timeout 300 \
    --set-env-vars "\
SECRET_KEY=$APP_SECRET_KEY,\
WHATSAPP_TOKEN=$WA_TOKEN,\
WHATSAPP_PHONE_NUMBER_ID=$WA_PHONE_ID,\
WHATSAPP_WABA_ID=$WA_WABA_ID,\
WHATSAPP_VERIFY_TOKEN=$WA_VERIFY,\
WHATSAPP_APP_SECRET=$WA_APP_SECRET,\
LOG_LEVEL=INFO"

# ── Exibir URL ────────────────────────────────────────────
echo ""
echo "=========================================="
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")
echo "  Deploy concluido."
echo ""
echo "  URL do servico:"
echo "  $SERVICE_URL"
echo ""
echo "  URL do webhook (copiar para o painel da Meta):"
echo "  ${SERVICE_URL}/webhook"
echo ""
echo "  Verify Token configurado via ambiente."
echo "=========================================="
