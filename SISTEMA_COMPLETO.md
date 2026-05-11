# Hubloc / Castro Intelligence — Sistema Completo

Codigo-fonte completo do projeto (backend Python + frontend React/TS + configs).
Exclui: `docs/`, `node_modules/`, `.venv/`, `frontend_dist/`, `__pycache__/`, `.env`, `package-lock.json`, `CLAUDE.md`.

Gerado por `scripts/build_sistema_completo.py`. Nao editar a mao.

---

## Sumario

- [.env.example](#envexample)
- [Dockerfile](#dockerfile)
- [docker-compose.yml](#docker-composeyml)
- [requirements.txt](#requirementstxt)
- [firebase.json](#firebasejson)
- [firestore.indexes.json](#firestoreindexesjson)
- [firestore.rules](#firestorerules)
- [storage.rules](#storagerules)
- [deploy.ps1](#deployps1)
- [deploy.sh](#deploysh)
- [start.example.ps1](#startexampleps1)
- [auth.py](#authpy)
- [bootstrap_data.py](#bootstrap_datapy)
- [bot_service.py](#bot_servicepy)
- [channel_service.py](#channel_servicepy)
- [check_whatsapp_coexistence.py](#check_whatsapp_coexistencepy)
- [config.py](#configpy)
- [database.py](#databasepy)
- [database_firestore.py](#database_firestorepy)
- [firebase_admin_client.py](#firebase_admin_clientpy)
- [firestore_common.py](#firestore_commonpy)
- [google_chat.py](#google_chatpy)
- [init_db.py](#init_dbpy)
- [main.py](#mainpy)
- [media.py](#mediapy)
- [pending_events.py](#pending_eventspy)
- [pii_redaction.py](#pii_redactionpy)
- [seed_gchat.py](#seed_gchatpy)
- [tenant_service.py](#tenant_servicepy)
- [test_meta_app_review.py](#test_meta_app_reviewpy)
- [transcription_service.py](#transcription_servicepy)
- [webhook.py](#webhookpy)
- [webhook_google_chat.py](#webhook_google_chatpy)
- [frontend/package.json](#frontendpackagejson)
- [frontend/tsconfig.app.json](#frontendtsconfigappjson)
- [frontend/tsconfig.json](#frontendtsconfigjson)
- [frontend/tsconfig.node.json](#frontendtsconfignodejson)
- [frontend/vite.config.ts](#frontendviteconfigts)
- [frontend/index.html](#frontendindexhtml)
- [frontend/src/styles.css](#frontendsrcstylescss)
- [frontend/src/api.ts](#frontendsrcapits)
- [frontend/src/firebase.ts](#frontendsrcfirebasets)
- [frontend/src/types.ts](#frontendsrctypests)
- [frontend/src/vite-env.d.ts](#frontendsrcvite-envdts)
- [frontend/src/hooks/useClickOutside.ts](#frontendsrchooksuseclickoutsidets)
- [frontend/src/utils/errors.ts](#frontendsrcutilserrorsts)
- [frontend/src/utils/firebase-helpers.ts](#frontendsrcutilsfirebase-helpersts)
- [frontend/src/utils/formatting.ts](#frontendsrcutilsformattingts)
- [frontend/src/utils/media.ts](#frontendsrcutilsmediats)
- [frontend/src/utils/normalization.ts](#frontendsrcutilsnormalizationts)
- [frontend/src/utils/storage.ts](#frontendsrcutilsstoragets)
- [frontend/src/App.tsx](#frontendsrcapptsx)
- [frontend/src/main.tsx](#frontendsrcmaintsx)
- [frontend/src/context/CrmContext.tsx](#frontendsrccontextcrmcontexttsx)
- [frontend/src/components/gchat/InternalChatPanel.tsx](#frontendsrccomponentsgchatinternalchatpaneltsx)
- [frontend/src/components/icons/index.tsx](#frontendsrccomponentsiconsindextsx)
- [scripts/_check_meta_full_status.py](#scripts_check_meta_full_statuspy)
- [scripts/_check_meta_subscription.py](#scripts_check_meta_subscriptionpy)
- [scripts/_delete_orphan_conversations.py](#scripts_delete_orphan_conversationspy)
- [scripts/_diag_channels_prod.py](#scripts_diag_channels_prodpy)
- [scripts/_diag_send_state.py](#scripts_diag_send_statepy)
- [scripts/build_sistema_completo.py](#scriptsbuild_sistema_completopy)
- [scripts/create_test_users.py](#scriptscreate_test_userspy)
- [scripts/delete_channel.py](#scriptsdelete_channelpy)
- [scripts/e2e_test_staging.py](#scriptse2e_test_stagingpy)
- [scripts/wipe_all_collections.py](#scriptswipe_all_collectionspy)

---

## .env.example

```bash
# ============================================================================
# Castro Intelligence CRM - Variaveis de Ambiente
# ============================================================================
# Copie este arquivo para .env e ajuste os valores reais.
#
# Arquitetura alvo:
#   - Firestore como banco principal
#   - Cloud Storage / Firebase Storage para midia
#   - Firebase Auth (Google) para o CRM
#   - snapshot como modo principal do front
# ============================================================================

# -- Secrets --
SECRET_KEY=gerar_com_openssl_rand_hex_32
WHATSAPP_TOKEN=seu_token_permanente_aqui
WHATSAPP_VERIFY_TOKEN=seu_token_verificacao_webhook
WHATSAPP_APP_SECRET=sua_chave_secreta_meta

# -- Banco de dados --
# Mantido por compatibilidade operacional dos scripts, mas o runtime esta fixo
# em Firestore + Firebase Auth.
DATA_BACKEND=firestore
AUTH_MODE=firebase
FIRESTORE_PROJECT_ID=seu_project_id
FIRESTORE_COLLECTION_PREFIX=castro_crm
ALLOWED_FIREBASE_EMAIL_DOMAIN=empresa.com.br
ALLOWED_FIREBASE_EMAILS=
AUTO_PROVISION_FIREBASE_USERS=true
FIREBASE_WEB_API_KEY=sua_firebase_web_api_key
FIREBASE_WEB_AUTH_DOMAIN=seu_project_id.firebaseapp.com
FIREBASE_WEB_APP_ID=1:1234567890:web:abcdef123456
FIREBASE_WEB_MESSAGING_SENDER_ID=1234567890
# FIREBASE_WEB_MEASUREMENT_ID=G-XXXXXXXXXX
# GOOGLE_APPLICATION_CREDENTIALS=/caminho/para/service-account.json

# -- Env vars normais --
# `WHATSAPP_PHONE_NUMBER_ID` e o id numerico do numero conectado a Cloud API.
# `WHATSAPP_WABA_ID` e o id da conta do WhatsApp Business no Meta.
# Em coexistence, normalmente voce vai precisar dos dois identificadores.
WHATSAPP_PHONE_NUMBER_ID=000000000000000
WHATSAPP_WABA_ID=000000000000000
CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
LOG_LEVEL=INFO
LOG_TO_FILE=true
LOG_FILE=./logs/castro_crm.log
MEDIA_DIR=./media
MEDIA_STORAGE_BACKEND=gcs
FIREBASE_STORAGE_BUCKET=seu_project_id.firebasestorage.app
GCS_MEDIA_BUCKET=seu_project_id.firebasestorage.app
GCS_MEDIA_PREFIX=media
JWT_EXPIRATION_MINUTES=480
REQUIRE_WEBHOOK_SIGNATURE=true

# -- Embedded Signup (Coexistence) --
# META_APP_ID e o ID do app no developers.facebook.com (ex: Castro Intelligence CRM)
# META_APP_SECRET e o segredo do app (Configuracoes > Basico > Chave Secreta do Aplicativo)
# EMBEDDED_SIGNUP_CONFIG_ID e o ID da configuracao criada em "Configurador de cadastro incorporado"
META_APP_ID=seu_app_id_aqui
META_APP_SECRET=seu_app_secret_aqui
EMBEDDED_SIGNUP_CONFIG_ID=
CHAT_DELIVERY_MODE=snapshot
POLLING_INTERVAL_MS=5000
FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB=256
FIRESTORE_MEDIA_MAX_MB=8
FIRESTORE_MEDIA_CHUNK_KB=768

# -- Transcricao de audio --
FEATURE_AUDIO_TRANSCRIPTION=false
STT_LANGUAGE_CODE=pt-BR
STT_TIMEOUT_SECONDS=30.0
STT_FALLBACK_TEXT=
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

# -- Google Chat (comunicacao interna) --
FEATURE_GOOGLE_CHAT=false
GOOGLE_CHAT_PROJECT_NUMBER=seu_project_number
GOOGLE_CHAT_SERVICE_ACCOUNT_FILE=
# Se vazio, usa Application Default Credentials (recomendado no Cloud Run)

# -- Bootstrap inicial opcional --
BOOTSTRAP_ADMIN_EMAIL=admin@empresa.com.br
BOOTSTRAP_ADMIN_DISPLAY_NAME=Administrador
BOOTSTRAP_ADMIN_DEPARTMENT=Geral
```

## Dockerfile

```dockerfile
FROM node:22-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /frontend_dist ./frontend_dist

RUN mkdir -p /app/media/images /app/media/audio /app/media/video \
    /app/media/documents /app/media/stickers /app/media/avatars /app/logs

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

## docker-compose.yml

```yaml
services:
  crm:
    build:
      context: .
    container_name: castro-intelligence-crm
    restart: unless-stopped
    ports:
      - "8080:8080"
    env_file:
      - .env
    environment:
      MEDIA_DIR: /data/media
      LOG_FILE: /data/logs/castro_crm.log
      LOG_TO_FILE: "true"
    volumes:
      - castro_crm_data:/data

volumes:
  castro_crm_data:
```

## requirements.txt

```text
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
bcrypt==4.2.0
PyJWT==2.9.0
pyngrok==7.2.2
python-multipart==0.0.9
google-cloud-firestore==2.19.0
google-cloud-storage==2.18.2
firebase-admin==6.7.0
google-api-python-client==2.100.0
google-auth==2.29.0
cryptography==42.0.0
faster-whisper==1.2.1
```

## firebase.json

```json
{
  "firestore": {
    "rules": "firestore.rules",
    "indexes": "firestore.indexes.json"
  }
}
```

## firestore.indexes.json

```json
{
  "indexes": [
    {
      "collectionGroup": "wa_conversations",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "contact_id", "order": "ASCENDING" },
        { "fieldPath": "last_message_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_conversations",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "assigned_to_uid", "order": "ASCENDING" },
        { "fieldPath": "status", "order": "ASCENDING" },
        { "fieldPath": "last_message_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_messages",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "conversation_id", "order": "ASCENDING" },
        { "fieldPath": "timestamp_wa", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_messages",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "contact_id", "order": "ASCENDING" },
        { "fieldPath": "timestamp_wa", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_messages",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "contact_id", "order": "ASCENDING" },
        { "fieldPath": "direction", "order": "ASCENDING" },
        { "fieldPath": "status", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_contacts",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "is_archived", "order": "ASCENDING" },
        { "fieldPath": "last_message_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_contacts",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "assigned_to_uid", "order": "ASCENDING" },
        { "fieldPath": "is_archived", "order": "ASCENDING" },
        { "fieldPath": "last_message_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_contacts",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "department_id", "order": "ASCENDING" },
        { "fieldPath": "is_archived", "order": "ASCENDING" },
        { "fieldPath": "last_message_at", "order": "DESCENDING" }
      ]
    },
    {
      "collectionGroup": "wa_transfer_log",
      "queryScope": "COLLECTION_GROUP",
      "fields": [
        { "fieldPath": "contact_id", "order": "ASCENDING" },
        { "fieldPath": "created_at", "order": "DESCENDING" }
      ]
    }
  ],
  "fieldOverrides": []
}
```

## firestore.rules

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Estas rules precisam usar o mesmo prefixo definido em FIRESTORE_COLLECTION_PREFIX.
    // No ambiente atual, as collections reais sao "castro_crm_*".
    // Regra temporaria de teste:
    // libera somente o email abaixo. Depois troque para o dominio oficial da empresa.
    function signedIn() {
      return request.auth != null && request.auth.token.email != null;
    }

    function emailAllowed() {
      return signedIn() && (
        request.auth.token.email == 'rafaluisc@outlook.com' ||
        request.auth.token.email == 'izaeldecastro@gmail.com' ||
        request.auth.token.email.matches('.*@centralloc\\.com\\.br')
      );
    }

    function myProfileExists() {
      return signedIn() &&
        exists(/databases/$(database)/documents/castro_crm_operator_profiles/$(request.auth.uid));
    }

    function myProfile() {
      return get(/databases/$(database)/documents/castro_crm_operator_profiles/$(request.auth.uid));
    }

    function operatorActive() {
      return emailAllowed() &&
        myProfileExists() &&
        myProfile().data.is_active == 1;
    }

    function isPrivileged() {
      return operatorActive() &&
        (myProfile().data.role == 'admin' || myProfile().data.role == 'supervisor');
    }

    function canSeeConversation(assignedUid, departmentId) {
      return operatorActive() && (
        isPrivileged() ||
        assignedUid == request.auth.uid ||
        assignedUid == '' ||
        departmentId == null ||
        departmentId == myProfile().data.department_id
      );
    }

    match /castro_crm_operator_profiles/{uid} {
      allow read: if emailAllowed() && (uid == request.auth.uid || operatorActive());
      allow write: if false;
    }

    match /castro_crm_departments/{departmentId} {
      allow read: if operatorActive();
      allow write: if false;
    }

    match /castro_crm_wa_contacts/{contactId} {
      // Privilegiados (admin/supervisor) veem todos.
      // Operadores veem: atribuidos a si, sem atribuicao, ou do mesmo departamento.
      allow read: if operatorActive() && (
        isPrivileged() ||
        resource.data.assigned_to_uid == request.auth.uid ||
        resource.data.assigned_to_uid == '' ||
        resource.data.assigned_to_uid == null ||
        resource.data.department_id == myProfile().data.department_id
      );
      allow write: if false;
    }

    match /castro_crm_wa_messages/{messageId} {
      allow read: if operatorActive();
      allow write: if false;
    }

    match /castro_crm_wa_transfer_log/{transferId} {
      allow read: if emailAllowed();
      allow write: if false;
    }

    match /castro_crm_gc_conversations/{convId} {
      allow read: if emailAllowed();
      allow write: if false;
    }

    match /castro_crm_gc_messages/{msgId} {
      allow read: if emailAllowed();
      allow write: if false;
    }

    match /castro_crm_messages/{messageId} {
      allow read: if operatorActive() && (
        resource.data.sender_id == myProfile().data.user_id ||
        resource.data.receiver_id == myProfile().data.user_id
      );
      allow write: if false;
    }

    match /castro_crm_internal_unread/{docId} {
      allow read: if operatorActive() &&
        resource.data.receiver_id == myProfile().data.user_id;
      allow write: if false;
    }

    match /castro_crm_users/{userId} {
      allow read, write: if false;
    }

    match /castro_crm_audit_log/{docId} {
      allow read, write: if false;
    }

    match /castro_crm_wa_message_status/{docId} {
      allow read, write: if false;
    }

    match /castro_crm__meta/{docId} {
      allow read, write: if false;
    }

    // ====================================================================
    // PROD — subcolecoes tenant-scoped (Fase 2C cutover).
    // Backend retorna em /api/session paths como
    // castro_crm_tenants/{tid}/wa_contacts, wa_conversations,
    // wa_messages, etc. Frontend faz onSnapshot direto nesses paths.
    // Rules permissivas espelhando staging (qualquer email autorizado
    // pode ler/escrever). Sera substituido por rules tenant-based
    // estritas com claim no JWT em sessao futura — ver
    // docs/internal/firestore-rules-staging-strict.wip.
    // ====================================================================

    match /castro_crm_tenants/{tenantId} {
      allow read, write: if emailAllowed();

      match /{subcol=**} {
        allow read, write: if emailAllowed();
      }
    }

    // ====================================================================
    // STAGING (FIRESTORE_COLLECTION_PREFIX=castro_crm_staging)
    // Rules permissivas: qualquer email autorizado pode ler/escrever.
    // Sera substituido por regras tenant-based na Fase 2 (subcolecao
    // tenants/{tenant_id}/* com claim no JWT).
    // ====================================================================

    match /castro_crm_staging_operator_profiles/{uid} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_users/{userId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_departments/{deptId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_channels/{channelId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_wa_contacts/{contactId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_wa_conversations/{convId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_wa_messages/{messageId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_wa_message_status/{docId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_wa_transfer_log/{transferId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_bot_states/{convId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_system_settings/{docId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_user_settings/{userId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_audit_log/{docId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_audit_metrics/{docId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_operator_assume_counters/{userId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_media_assets/{assetId} {
      allow read, write: if emailAllowed();
      match /chunks/{chunkId} {
        allow read, write: if emailAllowed();
      }
    }

    match /castro_crm_staging_gc_conversations/{convId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_gc_messages/{msgId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_messages/{messageId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging_internal_unread/{docId} {
      allow read, write: if emailAllowed();
    }

    match /castro_crm_staging__meta/{docId} {
      allow read, write: if emailAllowed();
    }

    // Doc do tenant em si (lista de tenants ainda flat, indice global).
    match /castro_crm_staging_tenants/{tenantId} {
      allow read, write: if emailAllowed();

      // Subcolecoes de cada tenant — em staging libera tudo para
      // qualquer email autorizado (modelo simplificado de teste).
      // Sera substituido por rules tenant-based estritas com claim no
      // JWT quando o frontend renovar tokens (sub-fase futura).
      match /{subcol=**} {
        allow read, write: if emailAllowed();
      }
    }
  }
}
```

## storage.rules

```
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    // Regra temporaria de teste:
    // libera somente o email abaixo. Depois troque para o dominio oficial da empresa.
    function signedIn() {
      return request.auth != null && request.auth.token.email != null;
    }

    function emailAllowed() {
      return signedIn() && (
        request.auth.token.email == 'rafaluisc@outlook.com' ||
        request.auth.token.email == 'izaeldecastro@gmail.com' ||
        request.auth.token.email.matches('.*@centralloc\\.com\\.br')
      );
    }

    match /media/{allPaths=**} {
      allow read: if emailAllowed();
      allow write: if false;
    }

    match /{allPaths=**} {
      allow read, write: if false;
    }
  }
}
```

## deploy.ps1

```powershell
$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            return
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if (-not [string]::IsNullOrWhiteSpace($name) -and -not (Test-Path "Env:$name")) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

function Require-Value {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -eq "(unset)") {
        throw "Defina a variavel de ambiente $Name antes de executar."
    }
}

function New-HexSecret {
    param([int]$Bytes = 32)

    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return ($buffer | ForEach-Object { $_.ToString("x2") }) -join ""
}

function Test-GcloudCall {
    param([string[]]$Args)

    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $script:GCLOUD_BIN @Args 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Set-GcpSecret {
    param(
        [string]$ProjectId,
        [string]$Name,
        [string]$Value
    )

    Require-Value -Name $Name -Value $Value

    $tmpFile = Join-Path $env:TEMP "$Name-$([guid]::NewGuid().ToString('N')).txt"
    try {
        [System.IO.File]::WriteAllText($tmpFile, $Value)
        if (-not (Test-GcloudCall -Args @("secrets", "describe", $Name, "--project", $ProjectId))) {
            gcloud secrets create $Name `
                --project $ProjectId `
                --data-file=$tmpFile `
                --replication-policy=automatic | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Secret criado: $Name"
            }
            else {
                gcloud secrets versions add $Name `
                    --project $ProjectId `
                    --data-file=$tmpFile | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "Falha ao criar ou atualizar o secret $Name."
                }
                Write-Host "Nova versao adicionada ao secret: $Name"
            }
        }
        else {
            gcloud secrets versions add $Name `
                --project $ProjectId `
                --data-file=$tmpFile | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Falha ao atualizar o secret $Name."
            }
            Write-Host "Nova versao adicionada ao secret: $Name"
        }
    }
    finally {
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
}

function New-CloudRunEnvFile {
    param([System.Collections.Generic.List[string]]$Entries)

    $path = Join-Path $env:TEMP "cloudrun-env-$([guid]::NewGuid().ToString('N')).yaml"
    try {
        $lines = foreach ($entry in $Entries) {
            $parts = $entry.Split("=", 2)
            $name = $parts[0]
            $value = if ($parts.Count -gt 1) { $parts[1] } else { "" }
            $escaped = $value.Replace("'", "''")
            "$name : '$escaped'"
        }
        [System.IO.File]::WriteAllLines($path, $lines)
        return $path
    }
    catch {
        Remove-Item $path -ErrorAction SilentlyContinue
        throw
    }
}

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-DotEnv -Path (Join-Path $SCRIPT_DIR ".env")

$script:GCLOUD_BIN = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (-not $script:GCLOUD_BIN) {
    $script:GCLOUD_BIN = (Get-Command gcloud -ErrorAction Stop).Source
}

function gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & $script:GCLOUD_BIN @Args
}

$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { (& gcloud config get-value project 2>$null) }
$PROJECT_ID = "$PROJECT_ID".Trim()
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "southamerica-east1" }
$SERVICE_NAME = if ($env:CLOUD_RUN_SERVICE) { $env:CLOUD_RUN_SERVICE } else { "castro-crm" }
# O runtime foi consolidado em Firestore + Firebase Auth.
$DATA_BACKEND = "firestore"
$AUTH_MODE = "firebase"
$MEDIA_BUCKET = if ($env:FIREBASE_STORAGE_BUCKET) {
    $env:FIREBASE_STORAGE_BUCKET
}
elseif ($env:GCS_MEDIA_BUCKET) {
    $env:GCS_MEDIA_BUCKET
}
else {
    "$PROJECT_ID-castro-crm-media"
}
$GCS_MEDIA_PREFIX = if ($env:GCS_MEDIA_PREFIX) { $env:GCS_MEDIA_PREFIX } else { "media" }
$FIRESTORE_COLLECTION_PREFIX = if ($env:FIRESTORE_COLLECTION_PREFIX) { $env:FIRESTORE_COLLECTION_PREFIX } else { "castro_crm" }
$ALLOWED_FIREBASE_EMAIL_DOMAIN = if ($env:ALLOWED_FIREBASE_EMAIL_DOMAIN) { $env:ALLOWED_FIREBASE_EMAIL_DOMAIN } else { "" }
$ALLOWED_FIREBASE_EMAILS = if ($env:ALLOWED_FIREBASE_EMAILS) { $env:ALLOWED_FIREBASE_EMAILS } else { "" }
$AUTO_PROVISION_FIREBASE_USERS = if ($env:AUTO_PROVISION_FIREBASE_USERS) { $env:AUTO_PROVISION_FIREBASE_USERS } else { "true" }
$FIREBASE_WEB_API_KEY = if ($env:FIREBASE_WEB_API_KEY) { $env:FIREBASE_WEB_API_KEY } else { "" }
$FIREBASE_WEB_AUTH_DOMAIN = if ($env:FIREBASE_WEB_AUTH_DOMAIN) { $env:FIREBASE_WEB_AUTH_DOMAIN } else { "$PROJECT_ID.firebaseapp.com" }
$FIREBASE_WEB_APP_ID = if ($env:FIREBASE_WEB_APP_ID) { $env:FIREBASE_WEB_APP_ID } else { "" }
$FIREBASE_WEB_MESSAGING_SENDER_ID = if ($env:FIREBASE_WEB_MESSAGING_SENDER_ID) { $env:FIREBASE_WEB_MESSAGING_SENDER_ID } else { "" }
$FIREBASE_WEB_MEASUREMENT_ID = if ($env:FIREBASE_WEB_MEASUREMENT_ID) { $env:FIREBASE_WEB_MEASUREMENT_ID } else { "" }
$FEATURE_AUDIO_TRANSCRIPTION = if ($env:FEATURE_AUDIO_TRANSCRIPTION) { $env:FEATURE_AUDIO_TRANSCRIPTION } else { "false" }
$STT_LANGUAGE_CODE = if ($env:STT_LANGUAGE_CODE) { $env:STT_LANGUAGE_CODE } else { "pt-BR" }
$STT_TIMEOUT_SECONDS = if ($env:STT_TIMEOUT_SECONDS) { $env:STT_TIMEOUT_SECONDS } else { "30.0" }
$STT_FALLBACK_TEXT = if ($env:STT_FALLBACK_TEXT) { $env:STT_FALLBACK_TEXT } else { "" }
$WHISPER_MODEL_SIZE = if ($env:WHISPER_MODEL_SIZE) { $env:WHISPER_MODEL_SIZE } else { "base" }
$WHISPER_DEVICE = if ($env:WHISPER_DEVICE) { $env:WHISPER_DEVICE } else { "cpu" }
$WHISPER_COMPUTE_TYPE = if ($env:WHISPER_COMPUTE_TYPE) { $env:WHISPER_COMPUTE_TYPE } else { "int8" }
$SECRET_KEY = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { New-HexSecret }
$WHATSAPP_TOKEN = $env:WHATSAPP_TOKEN
$WHATSAPP_VERIFY_TOKEN = $env:WHATSAPP_VERIFY_TOKEN
$WHATSAPP_APP_SECRET = $env:WHATSAPP_APP_SECRET
$WHATSAPP_PHONE_NUMBER_ID = $env:WHATSAPP_PHONE_NUMBER_ID
$WHATSAPP_WABA_ID = $env:WHATSAPP_WABA_ID
$BOOTSTRAP_ADMIN_EMAIL = if ($env:BOOTSTRAP_ADMIN_EMAIL) { $env:BOOTSTRAP_ADMIN_EMAIL } else { "" }
$BOOTSTRAP_ADMIN_DISPLAY_NAME = if ($env:BOOTSTRAP_ADMIN_DISPLAY_NAME) { $env:BOOTSTRAP_ADMIN_DISPLAY_NAME } else { "Administrador" }
$BOOTSTRAP_ADMIN_DEPARTMENT = if ($env:BOOTSTRAP_ADMIN_DEPARTMENT) { $env:BOOTSTRAP_ADMIN_DEPARTMENT } else { "Geral" }
$JWT_EXPIRATION_MINUTES = if ($env:JWT_EXPIRATION_MINUTES) { $env:JWT_EXPIRATION_MINUTES } else { "480" }
$LOG_LEVEL = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { "INFO" }
$CORS_ORIGINS = if ($env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { "" }
$REQUIRE_WEBHOOK_SIGNATURE = if ($env:REQUIRE_WEBHOOK_SIGNATURE) { $env:REQUIRE_WEBHOOK_SIGNATURE } else { "true" }
$CHAT_DELIVERY_MODE = if ($env:CHAT_DELIVERY_MODE) { $env:CHAT_DELIVERY_MODE.Trim().ToLowerInvariant() } else { "snapshot" }
$POLLING_INTERVAL_MS = if ($env:POLLING_INTERVAL_MS) { $env:POLLING_INTERVAL_MS } else { "5000" }

if ($CHAT_DELIVERY_MODE -notin @("snapshot", "polling")) {
    throw "CHAT_DELIVERY_MODE deve ser 'snapshot' ou 'polling'."
}

Require-Value -Name "GCP_PROJECT_ID" -Value $PROJECT_ID
Require-Value -Name "WHATSAPP_TOKEN" -Value $WHATSAPP_TOKEN
Require-Value -Name "WHATSAPP_VERIFY_TOKEN" -Value $WHATSAPP_VERIFY_TOKEN
Require-Value -Name "WHATSAPP_APP_SECRET" -Value $WHATSAPP_APP_SECRET
Require-Value -Name "WHATSAPP_PHONE_NUMBER_ID" -Value $WHATSAPP_PHONE_NUMBER_ID

Write-Host ""
Write-Host "Projeto:  $PROJECT_ID"
Write-Host "Regiao:   $REGION"
Write-Host "Servico:  $SERVICE_NAME"
Write-Host "Backend:  $DATA_BACKEND"
Write-Host "Auth:     $AUTH_MODE"
Write-Host ""

gcloud config set project $PROJECT_ID | Out-Null

$services = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "firestore.googleapis.com"
)

$serviceEnableArgs = @("services", "enable")
$serviceEnableArgs += $services
$serviceEnableArgs += @("--project", $PROJECT_ID, "--quiet")
& gcloud @serviceEnableArgs | Out-Null

$PROJECT_NUMBER = (& gcloud projects describe $PROJECT_ID --format="value(projectNumber)").Trim()
$COMPUTE_SERVICE_ACCOUNT = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

$SERVICE_ACCOUNT_EMAIL = "$SERVICE_NAME-run@$PROJECT_ID.iam.gserviceaccount.com"
if (-not (Test-GcloudCall -Args @("iam", "service-accounts", "describe", $SERVICE_ACCOUNT_EMAIL, "--project", $PROJECT_ID))) {
    gcloud iam service-accounts create "$SERVICE_NAME-run" `
        --project $PROJECT_ID `
        --display-name "$SERVICE_NAME runtime" | Out-Null
}

if (-not (Test-GcloudCall -Args @("storage", "buckets", "describe", "gs://$MEDIA_BUCKET", "--project", $PROJECT_ID))) {
    gcloud storage buckets create "gs://$MEDIA_BUCKET" `
        --project $PROJECT_ID `
        --location $REGION `
        --uniform-bucket-level-access `
        --public-access-prevention | Out-Null
}

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role "roles/secretmanager.secretAccessor" `
    --quiet | Out-Null

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$COMPUTE_SERVICE_ACCOUNT" `
    --role "roles/storage.objectViewer" `
    --quiet | Out-Null

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$COMPUTE_SERVICE_ACCOUNT" `
    --role "roles/artifactregistry.writer" `
    --quiet | Out-Null

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$COMPUTE_SERVICE_ACCOUNT" `
    --role "roles/logging.logWriter" `
    --quiet | Out-Null

gcloud storage buckets add-iam-policy-binding "gs://$MEDIA_BUCKET" `
    --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role "roles/storage.objectAdmin" | Out-Null

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role "roles/datastore.user" `
    --quiet | Out-Null

$APP_SECRET_NAME = "$SERVICE_NAME-secret-key"
$WA_TOKEN_SECRET_NAME = "$SERVICE_NAME-whatsapp-token"
$WA_VERIFY_SECRET_NAME = "$SERVICE_NAME-whatsapp-verify-token"
$WA_APP_SECRET_NAME = "$SERVICE_NAME-whatsapp-app-secret"

$secretMappings = New-Object System.Collections.Generic.List[string]
$secretMappings.Add("SECRET_KEY=${APP_SECRET_NAME}:latest")
$secretMappings.Add("WHATSAPP_TOKEN=${WA_TOKEN_SECRET_NAME}:latest")
$secretMappings.Add("WHATSAPP_VERIFY_TOKEN=${WA_VERIFY_SECRET_NAME}:latest")
$secretMappings.Add("WHATSAPP_APP_SECRET=${WA_APP_SECRET_NAME}:latest")

Set-GcpSecret -ProjectId $PROJECT_ID -Name $APP_SECRET_NAME -Value $SECRET_KEY
Set-GcpSecret -ProjectId $PROJECT_ID -Name $WA_TOKEN_SECRET_NAME -Value $WHATSAPP_TOKEN
Set-GcpSecret -ProjectId $PROJECT_ID -Name $WA_VERIFY_SECRET_NAME -Value $WHATSAPP_VERIFY_TOKEN
Set-GcpSecret -ProjectId $PROJECT_ID -Name $WA_APP_SECRET_NAME -Value $WHATSAPP_APP_SECRET

$deployArgs = New-Object System.Collections.Generic.List[string]

$envVars = New-Object System.Collections.Generic.List[string]
$envVars.Add("DATA_BACKEND=$DATA_BACKEND")
$envVars.Add("AUTH_MODE=$AUTH_MODE")
$envVars.Add("FIRESTORE_PROJECT_ID=$PROJECT_ID")
$envVars.Add("FIRESTORE_COLLECTION_PREFIX=$FIRESTORE_COLLECTION_PREFIX")
$envVars.Add("MEDIA_STORAGE_BACKEND=gcs")
$envVars.Add("FIREBASE_STORAGE_BUCKET=$MEDIA_BUCKET")
$envVars.Add("GCS_MEDIA_BUCKET=$MEDIA_BUCKET")
$envVars.Add("GCS_MEDIA_PREFIX=$GCS_MEDIA_PREFIX")
$envVars.Add("JWT_EXPIRATION_MINUTES=$JWT_EXPIRATION_MINUTES")
$envVars.Add("WHATSAPP_PHONE_NUMBER_ID=$WHATSAPP_PHONE_NUMBER_ID")
$envVars.Add("WHATSAPP_WABA_ID=$WHATSAPP_WABA_ID")
$envVars.Add("BOOTSTRAP_ADMIN_DISPLAY_NAME=$BOOTSTRAP_ADMIN_DISPLAY_NAME")
$envVars.Add("BOOTSTRAP_ADMIN_DEPARTMENT=$BOOTSTRAP_ADMIN_DEPARTMENT")
$envVars.Add("CORS_ORIGINS=$CORS_ORIGINS")
$envVars.Add("REQUIRE_WEBHOOK_SIGNATURE=$REQUIRE_WEBHOOK_SIGNATURE")
$envVars.Add("LOG_LEVEL=$LOG_LEVEL")
$envVars.Add("LOG_TO_FILE=false")
$envVars.Add("CHAT_DELIVERY_MODE=$CHAT_DELIVERY_MODE")
$envVars.Add("POLLING_INTERVAL_MS=$POLLING_INTERVAL_MS")
$envVars.Add("ALLOWED_FIREBASE_EMAIL_DOMAIN=$ALLOWED_FIREBASE_EMAIL_DOMAIN")
$envVars.Add("ALLOWED_FIREBASE_EMAILS=$ALLOWED_FIREBASE_EMAILS")
$envVars.Add("AUTO_PROVISION_FIREBASE_USERS=$AUTO_PROVISION_FIREBASE_USERS")
$envVars.Add("FIREBASE_WEB_API_KEY=$FIREBASE_WEB_API_KEY")
$envVars.Add("FIREBASE_WEB_AUTH_DOMAIN=$FIREBASE_WEB_AUTH_DOMAIN")
$envVars.Add("FIREBASE_WEB_APP_ID=$FIREBASE_WEB_APP_ID")
$envVars.Add("FIREBASE_WEB_MESSAGING_SENDER_ID=$FIREBASE_WEB_MESSAGING_SENDER_ID")
$envVars.Add("FIREBASE_WEB_MEASUREMENT_ID=$FIREBASE_WEB_MEASUREMENT_ID")
$envVars.Add("FEATURE_AUDIO_TRANSCRIPTION=$FEATURE_AUDIO_TRANSCRIPTION")
$envVars.Add("STT_LANGUAGE_CODE=$STT_LANGUAGE_CODE")
$envVars.Add("STT_TIMEOUT_SECONDS=$STT_TIMEOUT_SECONDS")
$envVars.Add("STT_FALLBACK_TEXT=$STT_FALLBACK_TEXT")
$envVars.Add("WHISPER_MODEL_SIZE=$WHISPER_MODEL_SIZE")
$envVars.Add("WHISPER_DEVICE=$WHISPER_DEVICE")
$envVars.Add("WHISPER_COMPUTE_TYPE=$WHISPER_COMPUTE_TYPE")
$envVars.Add("BOOTSTRAP_ADMIN_EMAIL=$BOOTSTRAP_ADMIN_EMAIL")

Write-Host ""
Write-Host "Iniciando deploy no Cloud Run..."

$envFile = New-CloudRunEnvFile -Entries $envVars
try {
    $gcloudArgs = @(
        "run", "deploy", $SERVICE_NAME,
        "--source", ".",
        "--project", $PROJECT_ID,
        "--region", $REGION,
        "--platform", "managed",
        "--allow-unauthenticated",
        "--service-account", $SERVICE_ACCOUNT_EMAIL,
        "--port", "8080",
        "--memory", "1Gi",
        "--cpu", "1",
        "--min-instances", "0",
        "--max-instances", "3",
        "--concurrency", "1",
        "--timeout", "300",
        "--env-vars-file", $envFile,
        "--set-secrets", ($secretMappings -join ",")
    )

    if ($deployArgs.Count -gt 0) {
        $gcloudArgs += $deployArgs
    }

    & gcloud @gcloudArgs
}
finally {
    Remove-Item $envFile -ErrorAction SilentlyContinue
}

$SERVICE_URL = (& gcloud run services describe $SERVICE_NAME --project $PROJECT_ID --region $REGION --format="value(status.url)").Trim()

Write-Host ""
Write-Host "Deploy concluido."
Write-Host "URL do servico: $SERVICE_URL"
Write-Host "Webhook:         $SERVICE_URL/webhook"
Write-Host "Bucket de media: gs://$MEDIA_BUCKET"
Write-Host ""
```

## deploy.sh

```bash
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
# O runtime foi consolidado em Firestore + Firebase Auth.
DATA_BACKEND="firestore"
AUTH_MODE="firebase"
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
WHISPER_MODEL_SIZE="${WHISPER_MODEL_SIZE:-base}"
WHISPER_DEVICE="${WHISPER_DEVICE:-cpu}"
WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-int8}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"
WHATSAPP_TOKEN="${WHATSAPP_TOKEN:-}"
WHATSAPP_VERIFY_TOKEN="${WHATSAPP_VERIFY_TOKEN:-}"
WHATSAPP_APP_SECRET="${WHATSAPP_APP_SECRET:-}"
WHATSAPP_PHONE_NUMBER_ID="${WHATSAPP_PHONE_NUMBER_ID:-}"
WHATSAPP_WABA_ID="${WHATSAPP_WABA_ID:-}"
BOOTSTRAP_ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-}"
BOOTSTRAP_ADMIN_DISPLAY_NAME="${BOOTSTRAP_ADMIN_DISPLAY_NAME:-Administrador}"
BOOTSTRAP_ADMIN_DEPARTMENT="${BOOTSTRAP_ADMIN_DEPARTMENT:-Geral}"
JWT_EXPIRATION_MINUTES="${JWT_EXPIRATION_MINUTES:-480}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
CORS_ORIGINS="${CORS_ORIGINS:-}"
REQUIRE_WEBHOOK_SIGNATURE="${REQUIRE_WEBHOOK_SIGNATURE:-true}"
CHAT_DELIVERY_MODE="${CHAT_DELIVERY_MODE:-snapshot}"
POLLING_INTERVAL_MS="${POLLING_INTERVAL_MS:-5000}"
require_value "GCP_PROJECT_ID" "$PROJECT_ID"
require_value "WHATSAPP_TOKEN" "$WHATSAPP_TOKEN"
require_value "WHATSAPP_VERIFY_TOKEN" "$WHATSAPP_VERIFY_TOKEN"
require_value "WHATSAPP_APP_SECRET" "$WHATSAPP_APP_SECRET"
require_value "WHATSAPP_PHONE_NUMBER_ID" "$WHATSAPP_PHONE_NUMBER_ID"

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

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member "serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role "roles/datastore.user" \
    --quiet >/dev/null

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
  "WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE}"
  "WHISPER_DEVICE=${WHISPER_DEVICE}"
  "WHISPER_COMPUTE_TYPE=${WHISPER_COMPUTE_TYPE}"
  "BOOTSTRAP_ADMIN_EMAIL=${BOOTSTRAP_ADMIN_EMAIL}"
)

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
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --concurrency 1 \
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
```

## start.example.ps1

```powershell
$env:SECRET_KEY="troque_por_uma_chave_hex_aleatoria"
$env:DATA_BACKEND="firestore"
$env:AUTH_MODE="firebase"
$env:FIRESTORE_PROJECT_ID="seu_project_id"
$env:FIRESTORE_COLLECTION_PREFIX="castro_crm"
$env:ALLOWED_FIREBASE_EMAIL_DOMAIN="empresa.com.br"
$env:AUTO_PROVISION_FIREBASE_USERS="true"
$env:FIREBASE_WEB_API_KEY="sua_firebase_web_api_key"
$env:FIREBASE_WEB_AUTH_DOMAIN="seu_project_id.firebaseapp.com"
$env:FIREBASE_WEB_APP_ID="1:1234567890:web:abcdef123456"
$env:FIREBASE_WEB_MESSAGING_SENDER_ID="1234567890"
$env:GOOGLE_APPLICATION_CREDENTIALS="$PWD\service-account.json"
$env:WHATSAPP_TOKEN="troque_pelo_token_da_meta"
$env:WHATSAPP_PHONE_NUMBER_ID="000000000000000"
$env:WHATSAPP_WABA_ID="000000000000000"
$env:WHATSAPP_VERIFY_TOKEN="troque_pelo_token_de_verificacao"
$env:WHATSAPP_APP_SECRET="troque_pelo_app_secret_da_meta"
$env:BOOTSTRAP_ADMIN_EMAIL="admin@empresa.com.br"
$env:BOOTSTRAP_ADMIN_DISPLAY_NAME="Administrador"
$env:BOOTSTRAP_ADMIN_DEPARTMENT="Geral"
$env:REQUIRE_WEBHOOK_SIGNATURE="true"
$env:MEDIA_STORAGE_BACKEND="gcs"
$env:FIREBASE_STORAGE_BUCKET="seu_project_id.firebasestorage.app"
$env:GCS_MEDIA_BUCKET="seu_project_id.firebasestorage.app"
$env:GCS_MEDIA_PREFIX="media"
$env:MEDIA_DIR="$PWD\media"
$env:LOG_TO_FILE="true"
$env:LOG_FILE="$PWD\logs\castro_crm.log"
$env:CHAT_DELIVERY_MODE="snapshot"
$env:POLLING_INTERVAL_MS="5000"
$env:FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB="256"
$env:FIRESTORE_MEDIA_MAX_MB="8"
$env:FIRESTORE_MEDIA_CHUNK_KB="768"
$env:FEATURE_AUDIO_TRANSCRIPTION="true"
$env:STT_LANGUAGE_CODE="pt-BR"
$env:STT_TIMEOUT_SECONDS="30.0"
$env:STT_FALLBACK_TEXT=""
$env:WHISPER_MODEL_SIZE="base"
$env:WHISPER_DEVICE="cpu"
$env:WHISPER_COMPUTE_TYPE="int8"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Castro Intelligence CRM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Modo MVP local no Windows:"
Write-Host "    1. Firestore como banco principal"
Write-Host "    2. Midia em Cloud Storage / Firebase Storage"
Write-Host "    3. FastAPI na porta 8080"
Write-Host "    4. ngrok opcional para webhook"
Write-Host ""

# Copie este arquivo para start.ps1 e preencha os valores reais antes de rodar.

# Terminal 1: Servidor
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; .\.venv\Scripts\activate; python init_db.py; python main.py"

# Esperar servidor subir
Start-Sleep -Seconds 4

# Terminal 2: ngrok com IPv4 explicito
Start-Process powershell -ArgumentList "-NoExit", "-Command", "ngrok http 127.0.0.1:8080"

Write-Host "  Servidor e ngrok iniciados." -ForegroundColor Green
Write-Host ""
Write-Host "  Acesso local: http://127.0.0.1:8080" -ForegroundColor Yellow
Write-Host "  Firestore project: $env:FIRESTORE_PROJECT_ID" -ForegroundColor Yellow
Write-Host "  Storage bucket: $env:GCS_MEDIA_BUCKET" -ForegroundColor Yellow
Write-Host "  Entrega do chat: $env:CHAT_DELIVERY_MODE" -ForegroundColor Yellow
Write-Host "  Firebase Auth domain: $env:FIREBASE_WEB_AUTH_DOMAIN" -ForegroundColor Yellow
Write-Host "  Copie a URL HTTPS do ngrok e atualize no painel da Meta se necessario."
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
```

## auth.py

```python
# -*- coding: utf-8 -*-

import logging

from config import (
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
    ALLOWED_FIREBASE_EMAILS,
    AUTO_PROVISION_FIREBASE_USERS,
)
from database import (
    get_user_by_email,
    get_user_by_firebase_uid,
    get_user_by_id,
    log_audit,
    sync_user_identity,
    update_last_login,
    upsert_firebase_user,
)
from firebase_admin_client import set_tenant_claims, verify_firebase_id_token
from firestore_common import set_tenant_context

logger = logging.getLogger("castro_crm.auth")

# Tenant default usado durante a transicao multi-tenant — todos os usuarios
# pre-existentes do CRM Hubloc operam neste tenant ate que o custom_claim
# correspondente seja propagado.
_DEFAULT_TENANT = "hubloc"


def _resolve_tenant_id(decoded_token, user):
    """Resolve tenant_id do usuario autenticado.

    Ordem de busca:
      1. custom_claims do token (preferencia — set por set_tenant_claims)
      2. user.tenant_id (campo do doc do CRM — raro, redundante com path)
      3. tenant_context atual (foi setado em authenticate_firebase_token
         como claim_tenant or _DEFAULT_TENANT). Caso comum hoje — usuario
         que logou via SSO sem claim nunca teve seu JWT sincronizado.
      4. None (sistema single-tenant ainda — backend trata como legado).

    Quando claim e ausente mas algum fallback retorna tenant, ressincroniza
    custom_claims em background. Cliente precisa renovar token na
    proxima request (getIdToken(true) ou logout/login) para o claim
    aparecer no JWT — Firestore rules tenant-scoped dependem disso.
    """
    claim_tenant = (decoded_token or {}).get("tenant_id")
    if claim_tenant:
        return str(claim_tenant)

    db_tenant = (user or {}).get("tenant_id") if user else None
    if not db_tenant:
        # Fallback: tenant context atual (setado upstream em
        # authenticate_firebase_token a partir do claim ou _DEFAULT_TENANT).
        from firestore_common import get_tenant_context as _get_ctx
        db_tenant = _get_ctx()

    if db_tenant:
        firebase_uid = (user or {}).get("firebase_uid", "") or (decoded_token or {}).get("uid", "")
        if firebase_uid:
            try:
                set_tenant_claims(firebase_uid, str(db_tenant), role=(user or {}).get("role") or "operador")
                logger.info(
                    "tenant_id sincronizado em custom_claims | user_id=%s tenant_id=%s "
                    "(usuario precisa renovar ID token para refletir)",
                    (user or {}).get("id"), db_tenant,
                )
            except Exception as exc:
                logger.warning("Falha ao sincronizar custom_claims: %s", exc)
        return str(db_tenant)

    return None


def _firebase_email_allowed(email):
    email = (email or "").strip().lower()
    if ALLOWED_FIREBASE_EMAILS and email in ALLOWED_FIREBASE_EMAILS:
        return True
    if ALLOWED_FIREBASE_EMAIL_DOMAIN:
        return bool(email) and "@" in email and email.split("@", 1)[1].lower() == ALLOWED_FIREBASE_EMAIL_DOMAIN
    return not ALLOWED_FIREBASE_EMAILS


def authenticate_firebase_token(id_token, ip_address=""):
    try:
        decoded = verify_firebase_id_token(id_token)
    except Exception as exc:
        logger.warning("Falha ao validar Firebase ID token: %s", exc)
        return {"success": False, "status_code": 401, "error": "Token Firebase invalido"}

    firebase_uid = decoded.get("uid") or decoded.get("sub")
    email = (decoded.get("email") or "").strip().lower()
    display_name = (decoded.get("name") or email.split("@", 1)[0] or firebase_uid or "").strip()

    if not firebase_uid:
        return {"success": False, "status_code": 401, "error": "Token Firebase sem uid"}

    if not _firebase_email_allowed(email):
        return {"success": False, "status_code": 403, "error": "Acesso restrito ao email ou dominio autorizado"}

    # Seta tenant_context EARLY para que todos os lookups abaixo
    # (get_user_by_firebase_uid, get_user_by_email etc.) operem na
    # subcolecao correta do tenant. Usa claim do JWT ou fallback para
    # _DEFAULT_TENANT durante a migration. Nao reseta — o contextvar
    # vive ate o fim da request via FastAPI dependency lifecycle.
    claim_tenant = decoded.get("tenant_id") or _DEFAULT_TENANT
    set_tenant_context(claim_tenant)

    user = get_user_by_firebase_uid(firebase_uid) or get_user_by_email(email)
    if user:
        sync_user_identity(
            user["id"],
            email=email,
            firebase_uid=firebase_uid,
            auth_provider="firebase",
            display_name=display_name or user.get("display_name", ""),
        )
        user = get_user_by_id(user["id"])
    elif AUTO_PROVISION_FIREBASE_USERS and email:
        user = upsert_firebase_user(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name or email,
        )

    if not user:
        return {"success": False, "status_code": 403, "error": "Usuario nao provisionado no CRM"}

    if not user.get("is_active", 1):
        return {"success": False, "status_code": 403, "error": "Usuario desativado"}

    update_last_login(user["id"])
    log_audit(user["id"], "LOGIN_SUCCESS_FIREBASE", email or firebase_uid, ip_address)

    # Resolve e anexa tenant_id ao user retornado.
    # No estado atual (pre Fase 2.B/C), tenant_id pode ser None — backend
    # legado ignora. Apos Fase 2.B/C, todas as queries usam.
    tenant_id = _resolve_tenant_id(decoded, user)
    if tenant_id:
        user = dict(user)
        user["tenant_id"] = tenant_id

    return {
        "success": True,
        "decoded_token": decoded,
        "user": user,
    }
```

## bootstrap_data.py

```python
# -*- coding: utf-8 -*-

DEFAULT_DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral", "bot_key": None},
    {"name": "Vendas", "description": "Equipe comercial", "bot_key": "comercial"},
    {"name": "Suporte", "description": "Suporte tecnico", "bot_key": "sac"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos", "bot_key": "financeiro"},
]


def ensure_default_departments(create_department_fn, emit=None):
    dept_map = {}
    for department in DEFAULT_DEPARTMENTS:
        department_id = create_department_fn(
            department["name"],
            department["description"],
            bot_key=department.get("bot_key"),
        )
        dept_map[department["name"]] = department_id
        if emit:
            emit(department, department_id)
    return dept_map
```

## bot_service.py

```python
# -*- coding: utf-8 -*-

"""
Servico de bot para atendimento automatico via WhatsApp.
Baseado no modelo de fluxo conversacional com coleta de nome, equipamento e setor.
Opera como state machine: cada mensagem do cliente avanca o estado.
"""

import re
import logging
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional

from firestore_common import document, utcnow, get_firestore_client
from database import (
    get_wa_contact, get_system_settings, get_all_departments,
    assign_wa_contact, save_wa_message, log_audit,
    get_user_by_id,
)

logger = logging.getLogger("castro_crm.bot")

# =========================================================================
# Timezone e expediente
# =========================================================================

EMPRESA_TZ = timezone(timedelta(hours=-3))
HORA_INICIO = 7
HORA_FIM = 17

# =========================================================================
# Vocabularios
# =========================================================================

CONECTORES_NOME = {"de", "da", "do", "dos", "das", "e"}

TERMOS_PULAR = {
    "pular", "nao quero informar", "não quero informar",
    "nao informar", "não informar", "sem nome",
    "prefiro nao informar", "prefiro não informar",
    "nao sei", "não sei",
}

TERMOS_PEDIDO = {
    "quero", "preciso", "gostaria", "necessito", "alugar", "locar",
    "locacao", "locação", "cotar", "orcamento", "orçamento",
    "valor", "preco", "preço", "quanto", "reservar",
}

TERMOS_EQUIPAMENTO = {
    "betoneira", "martelete", "martelo", "martelo demolidor",
    "rompedor", "compactador", "compactador de solo",
    "placa vibratoria", "placa vibratória", "andaime", "andaimes",
    "escora", "escoras", "furadeira", "serra", "serra circular",
    "serra marmore", "serra mármore", "lavadora", "compressor",
    "gerador", "enceradeira", "vibrador de concreto", "lixadeira",
    "cortadora", "cortadora de piso", "perfurador", "parafusadeira",
    "guincho", "container", "caçamba", "cacamba",
}

TERMOS_INVALIDOS_COMO_NOME = {
    "oi", "ola", "olá", "bom", "boa", "dia", "tarde", "noite",
    "meu", "nome", "cliente", "falar", "quero", "preciso",
    "valor", "preco", "preço", "quanto", "custa", "gostaria",
    "administrativo", "financeiro", "comercial", "sac",
}

PALAVRAS_COMERCIAL = {
    "comercial", "vendas", "locacao", "locação", "aluguel",
    "alugar", "locar", "orcamento", "orçamento", "cotacao",
    "cotação", "preco", "preço", "valor", "equipamento",
}

PALAVRAS_FINANCEIRO = {
    "financeiro", "boleto", "boletos", "nota", "nota fiscal",
    "pagamento", "pagamentos", "cobranca", "cobrança",
    "fatura", "faturas", "segunda via", "pix", "deposito", "depósito",
}

PALAVRAS_ADMINISTRATIVO = {
    "administrativo", "adm", "cadastro", "documento", "documentos",
    "contrato", "contratos", "fornecedor", "fornecedores", "rh",
}

PALAVRAS_SAC = {
    "sac", "suporte", "atendimento", "reclamacao", "reclamação",
    "problema", "defeito", "quebrado", "manutencao", "manutenção",
    "avaria", "atraso", "troca", "cancelamento",
}

# =========================================================================
# Utilidades de texto
# =========================================================================

def _norm(texto: str) -> str:
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)


def _limpar_nome(texto: str) -> str:
    for padrao in [r"^\s*meu nome e\s+", r"^\s*meu nome é\s+", r"^\s*me chamo\s+",
                   r"^\s*sou o\s+", r"^\s*sou a\s+", r"^\s*sou\s+"]:
        texto = re.sub(padrao, "", texto, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", texto).strip()


def _formatar_nome(texto: str) -> str:
    texto = re.sub(r"[^A-Za-zÀ-ÿ'\-\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    partes = []
    for token in texto.split():
        if _norm(token) in CONECTORES_NOME:
            partes.append(token.lower())
        else:
            partes.append(token.capitalize())
    return " ".join(partes)


def _contem(texto_norm: str, expressao: str) -> bool:
    expressao = _norm(expressao)
    return re.search(r"(?<!\w)" + re.escape(expressao) + r"(?!\w)", texto_norm) is not None


def _detectar_equipamento(texto: str) -> Optional[str]:
    texto_norm = _norm(texto)
    if any(_contem(texto_norm, t) for t in TERMOS_EQUIPAMENTO):
        return texto.strip()
    if any(_contem(texto_norm, t) for t in TERMOS_PEDIDO):
        if re.search(r"\b\d+\s?(kg|cv|hp|mm|cm|m|pol|polegada|polegadas)\b", texto_norm):
            return texto.strip()
    return None


def _parece_nome(texto: str) -> bool:
    candidato = _limpar_nome(texto)
    candidato_norm = _norm(candidato)
    if not candidato_norm:
        return False
    if candidato_norm in {_norm(x) for x in TERMOS_PULAR}:
        return False
    if any(ch.isdigit() for ch in candidato):
        return False
    if _detectar_equipamento(candidato):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ÿ'\-]+", candidato)
    if not tokens or len(tokens) > 4:
        return False
    for t in tokens:
        tn = _norm(t)
        if tn in CONECTORES_NOME:
            continue
        if tn in TERMOS_INVALIDOS_COMO_NOME or tn in {_norm(x) for x in TERMOS_EQUIPAMENTO} or len(tn) < 2:
            return False
    return True


def _classificar_setor(texto: str) -> Optional[int]:
    texto_norm = _norm(texto.strip())
    direto = {"1": 1, "2": 2, "3": 3, "4": 4}
    if texto_norm in direto:
        return direto[texto_norm]
    if any(_contem(texto_norm, p) for p in PALAVRAS_FINANCEIRO):
        return 2
    if any(_contem(texto_norm, p) for p in PALAVRAS_ADMINISTRATIVO):
        return 3
    if any(_contem(texto_norm, p) for p in PALAVRAS_SAC):
        return 4
    if any(_contem(texto_norm, p) for p in PALAVRAS_COMERCIAL):
        return 1
    if _detectar_equipamento(texto):
        return 1
    return None


# =========================================================================
# Mapeamento setor -> departamento do CRM
# =========================================================================

_SETOR_NOMES = {1: "Comercial", 2: "Financeiro", 3: "Administrativo", 4: "SAC"}
_BOT_KEY_BY_SETOR = {1: "comercial", 2: "financeiro", 3: "administrativo", 4: "sac"}

_dept_cache = None


def _get_dept_map() -> dict:
    """Mapeia setor do bot -> department_id do CRM.

    Preferencia: campo `bot_key` do departamento (estavel, nao quebra com rename).
    Fallback: substring match com _SETOR_NOMES quando bot_key nao esta definido.
    """
    global _dept_cache
    if _dept_cache is not None:
        return _dept_cache
    depts = get_all_departments()
    mapping = {}

    # Pass 1: bot_key explicito (prioridade)
    by_bot_key = {}
    for dept in depts:
        bk = (dept.get("bot_key") or "").strip().lower()
        if bk:
            by_bot_key[bk] = dept.get("id")
    for setor_id, bot_key in _BOT_KEY_BY_SETOR.items():
        if bot_key in by_bot_key:
            mapping[setor_id] = by_bot_key[bot_key]

    # Pass 2: substring match para setores que ainda nao tem mapeamento
    for dept in depts:
        name_norm = _norm(dept.get("name", ""))
        for setor_id, setor_nome in _SETOR_NOMES.items():
            if setor_id in mapping:
                continue
            if _norm(setor_nome) in name_norm or name_norm in _norm(setor_nome):
                mapping[setor_id] = dept.get("id")

    _dept_cache = mapping
    return mapping


def invalidate_dept_cache():
    global _dept_cache
    _dept_cache = None


# =========================================================================
# Bot state machine
# =========================================================================

# Estados: greeting -> ask_name -> ask_equipment -> ask_sector -> done
# O estado e dados ficam em Firestore: bot_states/{contact_id}

def _get_bot_state(contact_id: int) -> dict:
    ref = document("bot_states", contact_id)
    snap = ref.get()
    if snap.exists:
        return snap.to_dict() or {}
    return {}


def _set_bot_state(contact_id: int, state: dict):
    document("bot_states", contact_id).set(state, merge=True)


def _clear_bot_state(contact_id: int):
    document("bot_states", contact_id).delete()


def _saudacao() -> str:
    agora = datetime.now(timezone.utc).astimezone(EMPRESA_TZ)
    if 5 <= agora.hour < 12:
        sauda = "Bom dia"
    elif 12 <= agora.hour < 18:
        sauda = "Boa tarde"
    else:
        sauda = "Boa noite"
    aberto = agora.weekday() < 5 and HORA_INICIO <= agora.hour < HORA_FIM
    if aberto:
        return f"{sauda}! Bem-vindo a Hub Loc.\nPor favor, informe seu nome para iniciarmos o atendimento.\n(Caso não queira informar, digite PULAR)"
    else:
        return (
            f"{sauda}! Bem-vindo a Hub Loc.\n"
            "Nosso expediente funciona de segunda a sexta, das 7h as 17h.\n"
            "Sua mensagem sera registrada e o retorno ocorrera no proximo horario util.\n\n"
            "Por favor, informe seu nome para iniciarmos.\n(Caso não queira informar, digite PULAR)"
        )


MENU_SETORES = (
    "Informe o numero da opcao desejada:\n\n"
    "1 - Comercial\n"
    "2 - Financeiro\n"
    "3 - Administrativo\n"
    "4 - SAC"
)


def is_bot_enabled() -> bool:
    settings = get_system_settings()
    return bool(settings.get("bot_enabled", False))


def process_bot_message(contact_id: int, text: str, contact_name: str = "") -> Optional[str]:
    """
    Processa uma mensagem do cliente pelo bot.
    Retorna a resposta do bot (str) ou None se o bot nao deve responder.
    Se o fluxo terminar, atribui o contato ao departamento correto e retorna None.
    """
    if not is_bot_enabled():
        return None

    contact = get_wa_contact(contact_id)
    if not contact:
        return None

    # Se ja tem operador atribuido, bot nao interfere
    if contact.get("assigned_to"):
        return None

    state = _get_bot_state(contact_id)
    step = state.get("step", "")

    # Primeira mensagem — enviar saudacao e pedir nome
    if not step:
        _set_bot_state(contact_id, {
            "step": "ask_name",
            "nome": None,
            "equipamento": None,
            "setor_sugerido": None,
            "started_at": utcnow().isoformat(),
        })
        return _saudacao()

    text_stripped = text.strip()
    text_norm = _norm(text_stripped)

    # -- Etapa: coletar nome --
    if step == "ask_name":
        # Verificar se pulou
        if text_norm in {_norm(x) for x in TERMOS_PULAR}:
            _set_bot_state(contact_id, {**state, "step": "ask_equipment", "nome": None})
            return "Sem problemas! Qual equipamento deseja locar?\nSe nao for locacao, descreva o assunto ou digite PULAR."

        # Verificar se digitou setor direto
        setor = _classificar_setor(text_stripped)
        if setor and (text_norm in {"1", "2", "3", "4"} or any(_contem(text_norm, p) for p in
                PALAVRAS_COMERCIAL | PALAVRAS_FINANCEIRO | PALAVRAS_ADMINISTRATIVO | PALAVRAS_SAC)):
            _set_bot_state(contact_id, {**state, "step": "ask_name_after_sector", "setor_sugerido": setor})
            return f"Entendi que voce quer falar com o setor: {_SETOR_NOMES[setor]}.\nAgora informe seu nome.\n(Caso nao queira informar, digite PULAR)"

        # Verificar se digitou equipamento
        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {**state, "step": "ask_name_after_equip", "equipamento": equipamento, "setor_sugerido": 1})
            return f'Entendi que voce se interessa por: "{equipamento}".\nAgora informe seu nome.\n(Caso nao queira informar, digite PULAR)'

        # Verificar se e nome valido
        if _parece_nome(text_stripped):
            nome = _formatar_nome(_limpar_nome(text_stripped))
            _set_bot_state(contact_id, {**state, "step": "ask_equipment", "nome": nome})
            # Atualizar display_name do contato
            document("wa_contacts", contact_id).set({"display_name": nome}, merge=True)
            return f"Obrigado, {nome}! Qual equipamento deseja locar?\nSe nao for locacao, descreva o assunto ou digite PULAR."

        return "Nao consegui identificar um nome valido.\nDigite apenas seu nome.\n(Caso nao queira informar, digite PULAR)"

    # -- Etapa: nome apos ter dado setor/equipamento primeiro --
    if step in ("ask_name_after_sector", "ask_name_after_equip"):
        if text_norm in {_norm(x) for x in TERMOS_PULAR}:
            nome = None
        elif _parece_nome(text_stripped):
            nome = _formatar_nome(_limpar_nome(text_stripped))
            document("wa_contacts", contact_id).set({"display_name": nome}, merge=True)
        else:
            return "Nao consegui identificar um nome valido.\nDigite apenas seu nome ou PULAR."

        _set_bot_state(contact_id, {**state, "step": "ask_sector", "nome": nome})

        equip = state.get("equipamento")
        setor_sug = state.get("setor_sugerido")
        msg = MENU_SETORES
        if equip:
            msg += f'\n\nEquipamento informado: "{equip}"\nSugestao: 1 - Comercial'
        elif setor_sug:
            msg += f"\n\nSugestao: {setor_sug} - {_SETOR_NOMES.get(setor_sug, '?')}"
        return msg

    # -- Etapa: coletar equipamento --
    if step == "ask_equipment":
        if text_norm in {_norm(x) for x in TERMOS_PULAR}:
            _set_bot_state(contact_id, {**state, "step": "ask_sector"})
            return MENU_SETORES

        equipamento = _detectar_equipamento(text_stripped)
        if equipamento:
            _set_bot_state(contact_id, {**state, "step": "ask_sector", "equipamento": equipamento, "setor_sugerido": 1})
            msg = MENU_SETORES + f'\n\nEquipamento informado: "{equipamento}"\nSugestao: 1 - Comercial'
            return msg

        setor = _classificar_setor(text_stripped)
        if setor:
            _set_bot_state(contact_id, {**state, "step": "ask_sector", "setor_sugerido": setor})
            msg = MENU_SETORES + f"\n\nSugestao: {setor} - {_SETOR_NOMES.get(setor, '?')}"
            return msg

        return "Nao consegui identificar o equipamento ou assunto.\nExemplos: Betoneira, Segunda via de boleto, PULAR"

    # -- Etapa: coletar setor --
    if step == "ask_sector":
        setor = _classificar_setor(text_stripped)
        setor_sug = state.get("setor_sugerido")

        if setor is None:
            if not text_norm and setor_sug:
                setor = setor_sug
            else:
                return "Opcao invalida. Digite 1, 2, 3 ou 4.\n" + MENU_SETORES

        # Fluxo concluido — atribuir ao departamento
        _finalize_bot(contact_id, state, setor)
        return None

    # Estado desconhecido — resetar
    _clear_bot_state(contact_id)
    return None


def _finalize_bot(contact_id: int, state: dict, setor: int):
    """Finaliza o bot: atribui o contato ao departamento correto."""
    dept_map = _get_dept_map()
    dept_id = dept_map.get(setor)
    setor_nome = _SETOR_NOMES.get(setor, "Desconhecido")

    # Gravar resumo no contato
    nome = state.get("nome") or "Nao informado"
    equipamento = state.get("equipamento") or ""
    notes = f"Bot: Nome={nome}"
    if equipamento:
        notes += f" | Equipamento={equipamento}"
    notes += f" | Setor={setor_nome}"

    updates = {
        "bot_completed": True,
        "bot_setor": setor,
        "bot_setor_nome": setor_nome,
        "bot_notes": notes,
    }
    if dept_id:
        updates["department_id"] = dept_id

    document("wa_contacts", contact_id).set(updates, merge=True)

    # Inserir mensagem de sistema
    sys_content = f"Bot finalizado | {notes} | Encaminhado para {setor_nome}"
    save_wa_message(
        wa_message_id="",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=sys_content,
        status="",
        timestamp_wa=utcnow().isoformat(),
    )

    _clear_bot_state(contact_id)
    logger.info("[BOT] Fluxo finalizado | contato=%d | setor=%s | dept_id=%s", contact_id, setor_nome, dept_id)
```

## channel_service.py

```python
# -*- coding: utf-8 -*-
"""
Servico de canais WhatsApp.

Substitui as referencias hardcoded a WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID
por um registry que suporta multiplos canais (standard + coexistence).

Uso:
    from channel_service import (
        get_channel, get_channel_by_phone_id, get_default_channel,
        get_channels_for_user, get_send_credentials, refresh_channels,
    )
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from firestore_common import (
    _flat_collection as collection,
    _flat_document as document,
    next_sequence,
    utcnow,
    normalize_record,
)

# NOTA: channel_service usa explicitamente _flat_collection/_flat_document
# para que canais permanecam em colecao flat (compartilhada entre tenants)
# enquanto a migracao de canais para tenants/{id}/channels nao for feita.
# Isso evita que o webhook, que opera dentro de tenant_context, leia
# canais da subcolecao errada (vazia) e nao consiga rotear mensagens.

logger = logging.getLogger("castro_crm.channels")

CHANNEL_TYPE_STANDARD = "standard"
CHANNEL_TYPE_COEXISTENCE = "coexistence"

# ---------------------------------------------------------------------------
# In-memory cache (thread-safe via lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_channels_by_id: dict[int, dict] = {}
_channels_by_phone_id: dict[str, dict] = {}
_default_channel_id: int | None = None
_last_refresh: float = 0
_CACHE_TTL_SECONDS = 60


def _needs_refresh() -> bool:
    return time.monotonic() - _last_refresh > _CACHE_TTL_SECONDS


def refresh_channels() -> None:
    """Recarrega todos os canais ativos do Firestore para o cache."""
    global _last_refresh, _default_channel_id

    rows = []
    for snap in collection("channels").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            try:
                data["id"] = int(snap.id)
            except ValueError:
                data["id"] = snap.id
        if data.get("is_active"):
            rows.append(data)

    by_id: dict[int, dict] = {}
    by_phone: dict[str, dict] = {}
    default_id: int | None = None

    for row in rows:
        cid = row["id"]
        by_id[cid] = row
        phone_id = str(row.get("phone_number_id", "")).strip()
        if phone_id:
            by_phone[phone_id] = row
        if row.get("channel_type") == CHANNEL_TYPE_STANDARD and default_id is None:
            default_id = cid

    with _lock:
        _channels_by_id.clear()
        _channels_by_id.update(by_id)
        _channels_by_phone_id.clear()
        _channels_by_phone_id.update(by_phone)
        _default_channel_id = default_id
        _last_refresh = time.monotonic()

    logger.info("Channel cache refreshed: %d active channels", len(by_id))


def _ensure_cache() -> None:
    if _needs_refresh():
        refresh_channels()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def get_channel(channel_id: int) -> dict | None:
    """Retorna um canal pelo ID."""
    _ensure_cache()
    with _lock:
        return _channels_by_id.get(channel_id)


def get_channel_by_phone_id(phone_number_id: str) -> dict | None:
    """Retorna um canal pelo phone_number_id da Meta."""
    if not phone_number_id:
        return None
    _ensure_cache()
    with _lock:
        return _channels_by_phone_id.get(str(phone_number_id).strip())


def get_default_channel() -> dict | None:
    """Retorna o canal standard (bot) padrao."""
    _ensure_cache()
    with _lock:
        if _default_channel_id is not None:
            return _channels_by_id.get(_default_channel_id)
    return None


def get_all_active_channels() -> list[dict]:
    """Retorna todos os canais ativos."""
    _ensure_cache()
    with _lock:
        return [normalize_record(ch) for ch in _channels_by_id.values()]


def get_channels_for_user(user_id: int) -> list[dict]:
    """Retorna canais que o usuario pode acessar.

    - Canal standard (bot): acessivel por todos
    - Canal coexistence: acessivel apenas pelo owner + admin/supervisor
    """
    _ensure_cache()
    with _lock:
        result = []
        for ch in _channels_by_id.values():
            if ch.get("channel_type") == CHANNEL_TYPE_STANDARD:
                result.append(ch)
            elif ch.get("owner_user_id") == user_id:
                result.append(ch)
        return [normalize_record(ch) for ch in result]


def get_send_credentials(channel_id: int | None) -> tuple[str, str, str]:
    """Retorna (access_token, phone_number_id, graph_api_base) para envio.

    Se channel_id for None, usa o canal default.
    Quando channel_id e explicito mas nao encontrado no cache, faz UM
    refresh sincrono e tenta de novo — protege contra cache stale entre
    instancias do Cloud Run apos create_channel recente. Se ainda assim
    nao for encontrado, falha em vez de cair em outro canal (caso
    contrario o envio iria pelo canal default com creds erradas).
    Raises ValueError se o canal nao for encontrado.
    """
    from config import GRAPH_API_BASE, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN

    channel = None
    if channel_id is not None:
        channel = get_channel(channel_id)
        if channel is None:
            # Cache stale entre instancias — recarrega do Firestore e
            # tenta de novo antes de aceitar o miss.
            refresh_channels()
            channel = get_channel(channel_id)
        if channel is None:
            raise ValueError(
                f"Canal {channel_id} solicitado nao existe (mesmo apos refresh). "
                "Recusa-se a cair em canal default para evitar enviar pelo canal errado."
            )
    if channel is None:
        channel = get_default_channel()
    if channel is None:
        raise ValueError("Nenhum canal WhatsApp configurado.")

    # Para o canal standard, o segredo do Cloud Run e a fonte de verdade.
    # Isso evita que o registry Firestore fique preso em um token antigo
    # depois de uma rotacao do secret.
    if channel.get("channel_type") == CHANNEL_TYPE_STANDARD:
        env_token = str(WHATSAPP_TOKEN or "").strip()
        env_phone_id = str(WHATSAPP_PHONE_NUMBER_ID or "").strip()
        if env_token and env_phone_id:
            return env_token, env_phone_id, GRAPH_API_BASE

    token = str(channel.get("access_token", "")).strip()
    phone_id = str(channel.get("phone_number_id", "")).strip()

    if not token or not phone_id:
        raise ValueError(f"Canal {channel.get('id')} sem token ou phone_number_id.")

    return token, phone_id, GRAPH_API_BASE


# ---------------------------------------------------------------------------
# Escrita (CRUD)
# ---------------------------------------------------------------------------

def create_channel(
    channel_type: str,
    label: str,
    waba_id: str,
    phone_number_id: str,
    display_phone_number: str,
    access_token: str,
    owner_user_id: int | None = None,
    owner_firebase_uid: str = "",
    default_department_id: int | None = None,
    is_bot_enabled: bool = False,
    token_expires_at: str | None = None,
    platform_type: str = "",
    is_official_business_account: bool | None = None,
    code_verification_status: str = "",
    messaging_limit_tier: str = "",
    verified_name: str = "",
    quality_rating: str = "",
    webhook_subscribed: bool = False,
    tenant_id: str | None = None,
) -> int:
    """Cria um novo canal e retorna o ID.

    Tambem popula o indice global `phone_routing/{phone_number_id}` quando
    `phone_number_id` esta disponivel — permite ao webhook resolver
    tenant em O(1) sem varrer canais por tenant.
    """
    channel_id = next_sequence("channels")
    now = utcnow()
    phone_id_norm = str(phone_number_id).strip()
    # Resolve tenant: prioridade explicito > contexto atual > 'hubloc'.
    if not tenant_id:
        from firestore_common import get_tenant_context
        tenant_id = get_tenant_context() or "hubloc"
    document("channels", channel_id).set({
        "id": channel_id,
        "channel_type": channel_type,
        "label": label,
        "waba_id": str(waba_id).strip(),
        "phone_number_id": phone_id_norm,
        "display_phone_number": display_phone_number,
        "access_token": access_token,
        "token_expires_at": token_expires_at,
        "owner_user_id": owner_user_id,
        "owner_firebase_uid": owner_firebase_uid,
        "default_department_id": default_department_id,
        "is_bot_enabled": is_bot_enabled,
        "is_active": True,
        "webhook_subscribed": webhook_subscribed,
        "platform_type": platform_type,
        "is_official_business_account": is_official_business_account,
        "code_verification_status": code_verification_status,
        "messaging_limit_tier": messaging_limit_tier,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
        "tenant_id": str(tenant_id),
        "created_at": now,
        "updated_at": now,
    })
    if phone_id_norm:
        try:
            from tenant_service import upsert_phone_routing
            upsert_phone_routing(phone_id_norm, str(tenant_id), channel_id)
        except Exception as exc:
            logger.warning(
                "Falha ao popular phone_routing | channel=%s phone=%s tenant=%s err=%s",
                channel_id, phone_id_norm, tenant_id, exc,
            )
    refresh_channels()
    logger.info("Channel created: id=%d type=%s label=%s phone=%s tenant=%s",
                channel_id, channel_type, label, phone_id_norm, tenant_id)
    return channel_id


def update_channel(channel_id: int, **fields: Any) -> bool:
    """Atualiza campos de um canal existente."""
    allowed = {
        "label", "access_token", "token_expires_at", "owner_user_id", "owner_firebase_uid",
        "default_department_id", "is_bot_enabled", "is_active",
        "webhook_subscribed", "display_phone_number", "phone_number_id", "waba_id",
        "platform_type", "is_official_business_account", "code_verification_status",
        "messaging_limit_tier", "verified_name", "quality_rating",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = utcnow()
    document("channels", channel_id).set(updates, merge=True)
    refresh_channels()
    return True


def refresh_coexistence_token(channel_id: int) -> bool:
    """Tenta estender o token de um canal coexistence via fb_exchange_token.

    Retorna True se renovou com sucesso, False caso contrario.
    Loga warning quando falha (sinaliza necessidade de re-onboarding).
    """
    from datetime import datetime, timedelta, timezone

    import httpx

    from config import GRAPH_API_BASE, META_APP_ID, META_APP_SECRET

    if not META_APP_ID or not META_APP_SECRET:
        logger.warning("refresh_coexistence_token: META_APP_ID/SECRET ausente")
        return False

    channel = get_channel(channel_id)
    if not channel:
        logger.warning("refresh_coexistence_token: canal %s nao encontrado", channel_id)
        return False
    if channel.get("channel_type") != CHANNEL_TYPE_COEXISTENCE:
        return False

    current_token = str(channel.get("access_token", "")).strip()
    if not current_token:
        logger.warning("refresh_coexistence_token: canal %s sem token armazenado", channel_id)
        return False

    url = f"{GRAPH_API_BASE}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "fb_exchange_token": current_token,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
        if resp.status_code >= 400:
            # NAO logar resp.text cru — pode conter token em sucesso parcial
            # ou outros campos sensiveis. Extrai apenas a mensagem de erro
            # estruturada do JSON da Graph API.
            err_msg = ""
            try:
                err_msg = ((resp.json() or {}).get("error") or {}).get("message", "")
            except Exception:
                err_msg = "<unparseable>"
            logger.warning(
                "refresh_coexistence_token: canal %s falhou status=%s erro=%s",
                channel_id, resp.status_code, err_msg,
            )
            return False
        data = resp.json()
    except Exception as exc:
        logger.warning("refresh_coexistence_token: canal %s exception=%s", channel_id, exc)
        return False

    new_token = data.get("access_token")
    if not new_token:
        # Loga apenas as chaves do response (sem valores) — o que importa
        # pra debug e qual campo veio (ex.: 'error' vs 'access_token').
        logger.warning(
            "refresh_coexistence_token: canal %s resposta sem access_token (campos=%s)",
            channel_id, sorted((data or {}).keys()),
        )
        return False

    expires_in = data.get("expires_in")
    expires_at_iso: str | None = None
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        expires_at_iso = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()

    update_channel(channel_id, access_token=new_token, token_expires_at=expires_at_iso)
    logger.info("refresh_coexistence_token: canal %s renovado (expira em %s)", channel_id, expires_at_iso)
    return True


def deactivate_channel(channel_id: int) -> bool:
    """Desativa um canal e remove o indice phone_routing correspondente."""
    channel = get_channel(channel_id)
    phone_id = str((channel or {}).get("phone_number_id", "")).strip()
    ok = update_channel(channel_id, is_active=False)
    if phone_id:
        try:
            from tenant_service import remove_phone_routing
            remove_phone_routing(phone_id)
        except Exception as exc:
            logger.warning(
                "Falha ao remover phone_routing | channel=%s phone=%s err=%s",
                channel_id, phone_id, exc,
            )
    return ok


def get_channel_by_id_from_db(channel_id: int) -> dict | None:
    """Leitura direta do Firestore (sem cache)."""
    snap = document("channels", channel_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = channel_id
    return normalize_record(data)


# ---------------------------------------------------------------------------
# Bootstrap: cria canal default a partir das env vars legadas
# ---------------------------------------------------------------------------

def bootstrap_default_channel() -> int | None:
    """Cria o canal standard default se nao existir, usando env vars.

    Chamado no startup do app. Retorna o channel_id ou None se nao ha
    credenciais configuradas.
    """
    from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID

    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.info("Bootstrap channel: sem WHATSAPP_TOKEN/PHONE_NUMBER_ID, pulando")
        return None

    # Verifica se ja existe um canal standard
    refresh_channels()
    existing = get_default_channel()
    if existing:
        updates: dict[str, Any] = {}
        if str(existing.get("access_token", "")).strip() != str(WHATSAPP_TOKEN).strip():
            updates["access_token"] = WHATSAPP_TOKEN
        if str(existing.get("phone_number_id", "")).strip() != str(WHATSAPP_PHONE_NUMBER_ID).strip():
            updates["phone_number_id"] = WHATSAPP_PHONE_NUMBER_ID
        if str(existing.get("waba_id", "")).strip() != str(WHATSAPP_WABA_ID).strip():
            updates["waba_id"] = WHATSAPP_WABA_ID
        if updates:
            update_channel(existing["id"], **updates)
            logger.info(
                "Bootstrap channel: canal default sincronizado com env (id=%s fields=%s)",
                existing["id"],
                ",".join(sorted(updates.keys())),
            )
        else:
            logger.info("Bootstrap channel: canal default ja existe (id=%s)", existing["id"])
        # Garante que phone_routing aponta para o canal default ate quando
        # ele foi criado antes da Fase 2C (sem indice).
        eff_phone_id = str(updates.get("phone_number_id") or existing.get("phone_number_id") or "").strip()
        if eff_phone_id:
            try:
                from firestore_common import get_tenant_context
                from tenant_service import upsert_phone_routing
                tenant_id = existing.get("tenant_id") or get_tenant_context() or "hubloc"
                upsert_phone_routing(eff_phone_id, str(tenant_id), existing["id"])
            except Exception as exc:
                logger.warning("Bootstrap channel: falha ao backfill phone_routing: %s", exc)
        return existing["id"]

    channel_id = create_channel(
        channel_type=CHANNEL_TYPE_STANDARD,
        label="Canal Principal",
        waba_id=WHATSAPP_WABA_ID,
        phone_number_id=WHATSAPP_PHONE_NUMBER_ID,
        display_phone_number="",
        access_token=WHATSAPP_TOKEN,
        owner_user_id=None,
        is_bot_enabled=True,
    )
    logger.info("Bootstrap channel: canal default criado (id=%d)", channel_id)
    return channel_id
```

## check_whatsapp_coexistence.py

```python
# -*- coding: utf-8 -*-
"""
Diagnostico rapido do provisionamento WhatsApp / Meta em cenarios de coexistence.

Uso comum:
  python check_whatsapp_coexistence.py
  python check_whatsapp_coexistence.py --token-source gcloud-secret --gcloud-project <project-id>
  python check_whatsapp_coexistence.py --token-source both --gcloud-project <project-id>
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent


def load_local_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(BASE_DIR / ".env")

from config import (
    FIRESTORE_PROJECT_ID,
    GRAPH_API_BASE,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_WABA_ID,
)

STATUS_FIELDS = (
    "id,display_phone_number,verified_name,quality_rating,"
    "code_verification_status,name_status,status,platform_type"
)
DEFAULT_SECRET_NAME = "castro-crm-whatsapp-token"


@dataclass
class TokenResolution:
    label: str
    token: str
    details: str
    phone_id: str
    waba_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida token, WABA e numero configurados para a integracao WhatsApp/Meta."
    )
    parser.add_argument(
        "--token-source",
        choices=("env", "gcloud-secret", "both"),
        default="env",
        help="Origem do token de acesso da Meta.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Token explicito. Quando informado, substitui o token vindo do ambiente.",
    )
    parser.add_argument(
        "--token-secret",
        default=DEFAULT_SECRET_NAME,
        help="Nome do secret no Secret Manager quando --token-source=gcloud-secret.",
    )
    parser.add_argument(
        "--gcloud-project",
        default=FIRESTORE_PROJECT_ID,
        help="Project ID usado para ler o Secret Manager.",
    )
    parser.add_argument(
        "--phone-id",
        default="",
        help="Phone Number ID da Meta. Quando omitido, o script tenta descobrir a origem correta.",
    )
    parser.add_argument(
        "--waba-id",
        default="",
        help="WhatsApp Business Account ID. Quando omitido, o script tenta descobrir a origem correta.",
    )
    parser.add_argument(
        "--graph-api-base",
        default=GRAPH_API_BASE,
        help="Base da Graph API. Ex.: https://graph.facebook.com/v22.0",
    )
    parser.add_argument(
        "--cloud-run-service",
        default="castro-crm",
        help="Servico Cloud Run usado para descobrir os IDs de producao.",
    )
    parser.add_argument(
        "--cloud-run-region",
        default="southamerica-east1",
        help="Regiao do servico Cloud Run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime o resultado em JSON.",
    )
    return parser.parse_args()


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def get_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message", "erro sem mensagem")
            return f"code={code} message={message}"
    if payload is None:
        return "erro desconhecido"
    return str(payload)


def fetch_graph(path: str, token: str, base_url: str, fields: str | None = None) -> dict[str, Any]:
    query = {"access_token": token}
    if fields:
        query["fields"] = fields

    url = f"{normalize_base_url(base_url)}/{path.lstrip('/')}?{urlencode(query)}"
    request = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "status": response.status, "body": body}
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = raw_body
        return {"ok": False, "status": exc.code, "body": body}
    except Exception as exc:  # pragma: no cover - depende do ambiente
        return {"ok": False, "error": str(exc)}


def resolve_env_token(
    explicit_token: str,
    phone_id_override: str = "",
    waba_id_override: str = "",
) -> TokenResolution:
    token = (explicit_token or WHATSAPP_TOKEN).strip()
    if not token:
        raise RuntimeError("WHATSAPP_TOKEN nao esta definido no ambiente atual.")
    phone_id = (phone_id_override or WHATSAPP_PHONE_NUMBER_ID).strip()
    waba_id = (waba_id_override or WHATSAPP_WABA_ID).strip()
    if not phone_id or not waba_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID e WHATSAPP_WABA_ID nao estao definidos no ambiente atual.")
    if explicit_token:
        return TokenResolution(
            label="token-explicito",
            token=token,
            details="via argumento --token",
            phone_id=phone_id,
            waba_id=waba_id,
        )
    return TokenResolution(
        label="env",
        token=token,
        details="via ambiente atual /.env",
        phone_id=phone_id,
        waba_id=waba_id,
    )


def _run_gcloud_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _run_gcloud_text(args: list[str]) -> str:
    attempts: list[list[str]] = []
    direct = shutil.which("gcloud")
    if direct:
        attempts.append([direct, *args])

    joined = " ".join(args)
    if os.name == "nt":
        attempts.append(["cmd.exe", "/d", "/c", f"gcloud {joined}"])
        attempts.append(["powershell", "-NoProfile", "-Command", f"gcloud {joined}"])
    else:
        attempts.append(["sh", "-lc", f"gcloud {joined}"])

    last_error = "gcloud nao encontrado"
    for command in attempts:
        try:
            result = _run_gcloud_command(command)
        except FileNotFoundError:
            continue

        if result.returncode == 0:
            return (result.stdout or "").strip()

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        last_error = stderr or stdout or f"gcloud saiu com codigo {result.returncode}"

    raise RuntimeError(last_error)


def read_cloud_run_env(project_id: str, service_name: str, region: str) -> dict[str, str]:
    if not project_id:
        raise RuntimeError("Informe --gcloud-project para consultar o Cloud Run.")

    raw = _run_gcloud_text(
        [
            "run",
            "services",
            "describe",
            service_name,
            f"--region={region}",
            f"--project={project_id}",
            "--format=json",
        ]
    )
    payload = json.loads(raw)
    env_list = (
        payload.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [{}])[0]
        .get("env", [])
    )
    env_map: dict[str, str] = {}
    for item in env_list:
        name = str(item.get("name", "")).strip()
        value = str(item.get("value", "")).strip()
        if name:
            env_map[name] = value
    return env_map


def resolve_gcloud_secret(
    secret_name: str,
    project_id: str,
    service_name: str,
    region: str,
    phone_id_override: str = "",
    waba_id_override: str = "",
) -> TokenResolution:
    if not project_id:
        raise RuntimeError("Informe --gcloud-project para ler o Secret Manager.")
    token = _run_gcloud_text(
        [
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_name}",
            f"--project={project_id}",
        ]
    )
    if not token:
        raise RuntimeError("Secret Manager retornou token vazio")

    env_map = read_cloud_run_env(project_id, service_name, region)
    phone_id = (phone_id_override or env_map.get("WHATSAPP_PHONE_NUMBER_ID", "")).strip()
    waba_id = (waba_id_override or env_map.get("WHATSAPP_WABA_ID", "")).strip()
    if not phone_id or not waba_id:
        raise RuntimeError("Nao foi possivel descobrir WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_WABA_ID via Cloud Run.")

    return TokenResolution(
        label="gcloud-secret",
        token=token,
        details=(
            f"via Secret Manager ({secret_name}) no projeto {project_id} "
            f"+ ids do Cloud Run {service_name}/{region}"
        ),
        phone_id=phone_id,
        waba_id=waba_id,
    )


def resolve_tokens(args: argparse.Namespace) -> list[TokenResolution]:
    if args.token_source == "env":
        return [
            resolve_env_token(
                args.token,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        ]
    if args.token_source == "gcloud-secret":
        return [
            resolve_gcloud_secret(
                args.token_secret,
                args.gcloud_project,
                args.cloud_run_service,
                args.cloud_run_region,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        ]

    resolutions: list[TokenResolution] = []
    env_error: str | None = None
    try:
        resolutions.append(
            resolve_env_token(
                args.token,
                phone_id_override=args.phone_id.strip(),
                waba_id_override=args.waba_id.strip(),
            )
        )
    except RuntimeError as exc:
        env_error = str(exc)

    resolutions.append(
        resolve_gcloud_secret(
            args.token_secret,
            args.gcloud_project,
            args.cloud_run_service,
            args.cloud_run_region,
            phone_id_override=args.phone_id.strip(),
            waba_id_override=args.waba_id.strip(),
        )
    )

    if env_error:
        resolutions.append(
            TokenResolution(
                label="env-error",
                token="",
                details=env_error,
                phone_id=args.phone_id.strip(),
                waba_id=args.waba_id.strip(),
            )
        )

    return resolutions


def diagnose(phone_result: dict[str, Any], waba_result: dict[str, Any], phone_id: str) -> list[str]:
    notes: list[str] = []

    if not phone_result.get("ok"):
        notes.append(f"falha ao consultar o numero: {get_error_message(phone_result.get('body'))}")
        message = get_error_message(phone_result.get("body")).lower()
        if "application has been deleted" in message:
            notes.append("o token atual parece vinculado a uma app Meta removida")
        if "code=190" in message:
            notes.append("o token da Meta esta invalido, expirado ou associado a uma app incorreta")
        return notes

    phone_body = phone_result.get("body", {})
    status = str(phone_body.get("status", "")).upper()
    platform_type = str(phone_body.get("platform_type", "")).upper()
    verification = str(phone_body.get("code_verification_status", "")).upper()

    if status == "DISCONNECTED":
        notes.append("o numero ainda nao esta conectado para envio pela Cloud API")
    if verification == "NOT_VERIFIED":
        notes.append("a verificacao do numero ainda nao foi concluida no lado da Meta")
    if platform_type == "ON_PREMISE":
        notes.append("o numero ainda aparece como ON_PREMISE; a coexistence nao terminou de provisionar o canal cloud")
    if status == "CONNECTED":
        notes.append("o numero ja aparece como CONNECTED")

    if waba_result.get("ok"):
        data = waba_result.get("body", {}).get("data", [])
        if isinstance(data, list) and not any(str(item.get("id")) == phone_id for item in data if isinstance(item, dict)):
            notes.append("a WABA consultada nao retornou o phone_id esperado")
    else:
        notes.append(f"falha ao consultar a WABA: {get_error_message(waba_result.get('body'))}")

    return notes


def run_single_check(
    resolution: TokenResolution,
    base_url: str,
) -> dict[str, Any]:
    if not resolution.token:
        return {
            "token_source": resolution.label,
            "token_details": resolution.details,
            "phone_id": resolution.phone_id,
            "waba_id": resolution.waba_id,
            "ok": False,
            "error": resolution.details,
        }

    phone_result = fetch_graph(resolution.phone_id, resolution.token, base_url, STATUS_FIELDS)
    waba_result = fetch_graph(f"{resolution.waba_id}/phone_numbers", resolution.token, base_url, STATUS_FIELDS)
    diagnosis = diagnose(phone_result, waba_result, resolution.phone_id)

    return {
        "token_source": resolution.label,
        "token_details": resolution.details,
        "phone_id": resolution.phone_id,
        "waba_id": resolution.waba_id,
        "graph_api_base": normalize_base_url(base_url),
        "phone_lookup": phone_result,
        "waba_phone_numbers": waba_result,
        "diagnosis": diagnosis,
    }


def print_human(results: list[dict[str, Any]]) -> None:
    for index, result in enumerate(results, start=1):
        if index > 1:
            print()
            print("-" * 72)
            print()

        print(f"[{index}] token_source={result['token_source']}")
        print(f"token_details: {result['token_details']}")

        if not result.get("ok", True):
            print(f"erro: {result.get('error', 'falha ao resolver token')}")
            continue

        phone_body = result["phone_lookup"].get("body", {}) if result["phone_lookup"].get("ok") else {}
        print(f"phone_id: {result['phone_id']}")
        print(f"waba_id:  {result['waba_id']}")
        print(
            "phone: status={status} platform_type={platform} code_verification_status={verification}".format(
                status=phone_body.get("status", "n/a"),
                platform=phone_body.get("platform_type", "n/a"),
                verification=phone_body.get("code_verification_status", "n/a"),
            )
        )
        print(
            "phone: display={display} verified_name={name} quality={quality}".format(
                display=phone_body.get("display_phone_number", "n/a"),
                name=phone_body.get("verified_name", "n/a"),
                quality=phone_body.get("quality_rating", "n/a"),
            )
        )

        if result["phone_lookup"].get("ok"):
            print("phone_lookup: ok")
        else:
            print(f"phone_lookup: {get_error_message(result['phone_lookup'].get('body'))}")

        if result["waba_phone_numbers"].get("ok"):
            data = result["waba_phone_numbers"].get("body", {}).get("data", [])
            print(f"waba_phone_numbers: ok ({len(data)} numero(s) retornado(s))")
        else:
            print(f"waba_phone_numbers: {get_error_message(result['waba_phone_numbers'].get('body'))}")

        print("diagnosis:")
        if result["diagnosis"]:
            for note in result["diagnosis"]:
                print(f"- {note}")
        else:
            print("- sem alertas adicionais")


def main() -> int:
    args = parse_args()

    try:
        resolutions = resolve_tokens(args)
        results = [
            run_single_check(
                resolution=resolution,
                base_url=args.graph_api_base,
            )
            for resolution in resolutions
        ]
    except RuntimeError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print_human(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## config.py

```python
# -*- coding: utf-8 -*-

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - uvicorn[standard] instala python-dotenv
    load_dotenv = None

if load_dotenv:
    load_dotenv(BASE_DIR / ".env", override=False)

IS_CLOUD_RUN = bool(os.getenv("K_SERVICE"))


def _as_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_int(value, default):
    if value is None or str(value).strip() == "":
        return default
    return int(value)


DATA_BACKEND = "firestore"
IS_FIRESTORE_BACKEND = True

# O CRM React depende de Firebase Auth e o runtime do backend nao expõe
# mais caminhos legados de autenticacao.
AUTH_MODE = "firebase"

FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "").strip()
FIRESTORE_COLLECTION_PREFIX = os.getenv("FIRESTORE_COLLECTION_PREFIX", "castro_crm").strip().strip("_")
FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB = _as_int(os.getenv("FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB"), 256)
FIRESTORE_MEDIA_MAX_MB = _as_int(os.getenv("FIRESTORE_MEDIA_MAX_MB"), 8)
FIRESTORE_MEDIA_CHUNK_KB = _as_int(os.getenv("FIRESTORE_MEDIA_CHUNK_KB"), 768)
ALLOWED_FIREBASE_EMAIL_DOMAIN = os.getenv("ALLOWED_FIREBASE_EMAIL_DOMAIN", "").strip().lower()
ALLOWED_FIREBASE_EMAILS = [item.lower() for item in _split_csv(os.getenv("ALLOWED_FIREBASE_EMAILS", ""))]
AUTO_PROVISION_FIREBASE_USERS = _as_bool(os.getenv("AUTO_PROVISION_FIREBASE_USERS"), default=True)
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "").strip()
FIREBASE_WEB_AUTH_DOMAIN = os.getenv(
    "FIREBASE_WEB_AUTH_DOMAIN",
    f"{FIRESTORE_PROJECT_ID}.firebaseapp.com" if FIRESTORE_PROJECT_ID else "",
).strip()
FIREBASE_WEB_APP_ID = os.getenv("FIREBASE_WEB_APP_ID", "").strip()
FIREBASE_WEB_MESSAGING_SENDER_ID = os.getenv("FIREBASE_WEB_MESSAGING_SENDER_ID", "").strip()
FIREBASE_WEB_MEASUREMENT_ID = os.getenv("FIREBASE_WEB_MEASUREMENT_ID", "").strip()

CHAT_DELIVERY_MODE = os.getenv("CHAT_DELIVERY_MODE", "snapshot").strip().lower()
POLLING_INTERVAL_MS = _as_int(os.getenv("POLLING_INTERVAL_MS"), 15000)



# -- Seguranca --
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "480"))

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
MAX_MESSAGE_LENGTH = 4000

# -- Servidor --
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# -- WhatsApp Business API (Meta Cloud API) --
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
REQUIRE_WEBHOOK_SIGNATURE = _as_bool(
    os.getenv("REQUIRE_WEBHOOK_SIGNATURE"),
    default=IS_CLOUD_RUN,
)

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# -- Embedded Signup (Coexistence) --
META_APP_ID = os.getenv("META_APP_ID", "").strip()
META_APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
EMBEDDED_SIGNUP_CONFIG_ID = os.getenv("EMBEDDED_SIGNUP_CONFIG_ID", "").strip()

# -- Media --
DEFAULT_MEDIA_DIR = Path("/tmp/castro_crm_media") if IS_CLOUD_RUN else BASE_DIR / "media"
MEDIA_DIR = os.getenv("MEDIA_DIR", str(DEFAULT_MEDIA_DIR))
GCS_MEDIA_BUCKET = os.getenv("GCS_MEDIA_BUCKET", FIREBASE_STORAGE_BUCKET).strip()
GCS_MEDIA_PREFIX = os.getenv("GCS_MEDIA_PREFIX", "media").strip().strip("/")
MEDIA_STORAGE_BACKEND = os.getenv(
    "MEDIA_STORAGE_BACKEND",
    "gcs" if GCS_MEDIA_BUCKET else ("local" if not IS_FIRESTORE_BACKEND else "firestore"),
).strip().lower()
MAX_MEDIA_SIZE_MB = 16

# -- Avatar / Foto de perfil --
AVATAR_DIR = os.path.join(MEDIA_DIR, "avatars")
AVATAR_MAX_SIZE_KB = 512
AVATAR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# -- Audio gravado --
AUDIO_MAX_DURATION_SEC = 120
AUDIO_ALLOWED_MIME = {"audio/ogg", "audio/webm", "audio/mp4", "audio/mpeg"}

# -- Transcricao de audio (Faster Whisper) --
def _bool_env(key, default="false"):
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes")

FEATURE_MESSAGE_STATUS = _bool_env("FEATURE_MESSAGE_STATUS", "true")
FEATURE_AUDIO_TRANSCRIPTION = _bool_env("FEATURE_AUDIO_TRANSCRIPTION", "false")
STT_LANGUAGE_CODE = os.getenv("STT_LANGUAGE_CODE", "pt-BR").strip()
STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "30.0"))
STT_FALLBACK_TEXT = os.getenv("STT_FALLBACK_TEXT", "").strip()

# -- Qualificacao de contatos --
QUALIFICATION_OPTIONS = [
    "novo",
    "em_atendimento",
    "qualificado",
    "nao_qualificado",
    "convertido",
]

# -- Cargos / funcoes --
ROLE_OPTIONS = [
    "admin",
    "supervisor",
    "operador",
]

# -- Bootstrap inicial --
BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
BOOTSTRAP_ADMIN_DISPLAY_NAME = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrador")
BOOTSTRAP_ADMIN_DEPARTMENT = os.getenv("BOOTSTRAP_ADMIN_DEPARTMENT", "Geral")

# -- Logging --
DEFAULT_LOG_FILE = Path("/tmp/logs/castro_crm.log") if IS_CLOUD_RUN else BASE_DIR / "logs" / "castro_crm.log"
LOG_FILE = os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = _as_bool(os.getenv("LOG_TO_FILE"), default=not IS_CLOUD_RUN)

# -- Google Chat Integration --
FEATURE_GOOGLE_CHAT = _bool_env("FEATURE_GOOGLE_CHAT", "false")
GOOGLE_CHAT_PROJECT_NUMBER = os.getenv("GOOGLE_CHAT_PROJECT_NUMBER", "").strip()
GOOGLE_CHAT_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CHAT_SERVICE_ACCOUNT_FILE", "").strip()

# -- CORS --
DEFAULT_CORS_ORIGINS = "http://localhost:8080,http://127.0.0.1:8080"
CORS_ORIGINS = _split_csv(os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
```

## database.py

```python
# -*- coding: utf-8 -*-

from database_firestore import *  # noqa: F401,F403
```

## database_firestore.py

```python
# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from google.cloud import firestore

from firestore_common import (
    collection,
    document,
    get_firestore_client,
    next_sequence,
    normalize_record,
    utcnow,
)

logger = logging.getLogger("castro_crm.database")


def _coerce_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def _raw_doc(snapshot):
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if "id" not in data:
        try:
            data["id"] = int(snapshot.id)
        except ValueError:
            data["id"] = snapshot.id
    return data


def _all_docs(name):
    return [_raw_doc(snapshot) for snapshot in collection(name).stream()]


def _get_doc(name, doc_id):
    return _raw_doc(document(name, doc_id).get())


def _get_first_by_field(name, field_name, value):
    query = collection(name).where(field_name, "==", value).limit(1)
    for snapshot in query.stream():
        return _raw_doc(snapshot)
    return None


def _sort_records(records, field_name, reverse=False):
    return sorted(
        records,
        key=lambda item: item.get(field_name) or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=reverse,
    )


_user_cache = {}
_department_cache = {}


def _user_map(user_ids):
    unique_ids = {uid for uid in user_ids if uid}
    missing = unique_ids - _user_cache.keys()
    for user_id in missing:
        user = _get_doc("users", user_id)
        if user:
            _user_cache[user_id] = user
    return {uid: _user_cache[uid] for uid in unique_ids if uid in _user_cache}


def _department_map(department_ids):
    unique_ids = {did for did in department_ids if did}
    missing = unique_ids - _department_cache.keys()
    for department_id in missing:
        department = _get_doc("departments", department_id)
        if department:
            _department_cache[department_id] = department
    return {did: _department_cache[did] for did in unique_ids if did in _department_cache}


def invalidate_caches():
    _user_cache.clear()
    _department_cache.clear()


def _prefer_wa_msg_type(existing_type, new_type):
    existing = (existing_type or "").strip().lower()
    incoming = (new_type or "").strip().lower()
    weak = {"", "unknown", "unsupported"}
    if incoming == "gif" and existing == "video":
        return incoming
    if incoming not in weak and existing in weak:
        return incoming
    if incoming in weak:
        return existing or incoming
    return existing or incoming


def _prefer_wa_content(existing_content, new_content):
    existing = (existing_content or "").strip()
    incoming = (new_content or "").strip()
    placeholders = {"[unknown]", "[unsupported]"}
    if not incoming:
        return existing
    if existing.lower() in placeholders and incoming.lower() not in placeholders:
        return incoming
    if incoming.lower() in placeholders and existing:
        return existing
    return incoming or existing


def _operator_profile_ref(firebase_uid):
    return document("operator_profiles", firebase_uid)


def _operator_profile_doc(firebase_uid):
    if not firebase_uid:
        return None
    return _raw_doc(_operator_profile_ref(firebase_uid).get())


def _sync_operator_profile_from_user(user):
    firebase_uid = (user or {}).get("firebase_uid")
    if not firebase_uid:
        return
    _operator_profile_ref(firebase_uid).set({
        "uid": firebase_uid,
        "user_id": user["id"],
        "email": user.get("email", ""),
        "display_name": user.get("display_name", ""),
        "role": user.get("role", "operador"),
        "department_id": user.get("department_id"),
        "is_active": user.get("is_active", 1),
        "updated_at": utcnow(),
    }, merge=True)


def _normalize_many(records):
    return [normalize_record(record) for record in records]


def _internal_unread_doc_id(receiver_id, sender_id):
    return f"{receiver_id}_{sender_id}"


def get_connection():
    return get_firestore_client()


@contextmanager
def db_session():
    yield None


def init_database():
    document("_meta", "counters").set({}, merge=True)
    logger.info("Firestore inicializado")


VALID_BOT_KEYS = {"comercial", "financeiro", "administrativo", "sac"}
_SENTINEL = object()


def _normalize_bot_key(value):
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v not in VALID_BOT_KEYS:
        return None
    return v


def create_department(name, description="", bot_key=None):
    existing = _get_first_by_field("departments", "name", name)
    if existing:
        return existing["id"]

    department_id = next_sequence("departments")
    document("departments", department_id).set({
        "id": department_id,
        "name": name,
        "description": description or "",
        "bot_key": _normalize_bot_key(bot_key),
        "is_active": 1,
        "created_at": utcnow(),
    })
    return department_id


def get_all_departments(include_inactive=False):
    if include_inactive:
        rows = [row for row in _all_docs("departments") if row]
    else:
        rows = [row for row in _all_docs("departments") if row and row.get("is_active", 1)]
    rows.sort(key=lambda row: (row.get("sort_order", 0), row.get("name", "").lower()))
    return _normalize_many(rows)


def get_department_by_id(department_id):
    return normalize_record(_get_doc("departments", department_id))


def update_department(department_id, name=None, description=None, is_active=None, sort_order=None, bot_key=_SENTINEL):
    fields = {}
    if name is not None:
        # Verifica duplicata de nome (excluindo o proprio)
        existing = _get_first_by_field("departments", "name", name)
        if existing and existing["id"] != department_id:
            return False, "Ja existe um departamento com este nome"
        fields["name"] = name
    if description is not None:
        fields["description"] = description
    if is_active is not None:
        fields["is_active"] = 1 if is_active else 0
    if sort_order is not None:
        fields["sort_order"] = sort_order
    if bot_key is not _SENTINEL:
        fields["bot_key"] = _normalize_bot_key(bot_key)
    if not fields:
        return False, "Nenhum campo para atualizar"
    fields["updated_at"] = utcnow()
    document("departments", department_id).set(fields, merge=True)
    _department_cache.pop(department_id, None)
    return True, None


def deactivate_department(department_id):
    document("departments", department_id).set({
        "is_active": 0,
        "updated_at": utcnow(),
    }, merge=True)
    _department_cache.pop(department_id, None)
    return True


def get_user_by_username(username):
    row = _get_first_by_field("users", "username", username)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_email(email):
    if not email:
        return None
    row = _get_first_by_field("users", "email", email.strip().lower())
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_firebase_uid(firebase_uid):
    if not firebase_uid:
        return None
    row = _get_first_by_field("users", "firebase_uid", firebase_uid)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_operator_profile_by_uid(firebase_uid):
    row = _operator_profile_doc(firebase_uid)
    if not row or not row.get("is_active", 1):
        return None
    return normalize_record(row)


def get_user_by_id(user_id):
    row = _get_doc("users", user_id)
    if not row or not row.get("is_active", 1):
        return None
    department_id = row.get("department_id")
    department_name = ""
    if department_id:
        department = _get_doc("departments", department_id)
        if department:
            department_name = department.get("name", "")
    return normalize_record({
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "department_id": department_id,
        "department_name": department_name,
        "role": row.get("role", "operador"),
        "is_active": row.get("is_active", 1),
        "email": row.get("email", ""),
        "firebase_uid": row.get("firebase_uid", ""),
        "auth_provider": row.get("auth_provider", "firebase"),
        "created_at": row.get("created_at"),
        "last_login": row.get("last_login"),
        "avatar_path": row.get("avatar_path", ""),
    })


def get_all_users():
    rows = [row for row in _all_docs("users") if row]
    dept_map = _department_map([row.get("department_id") for row in rows])
    rows.sort(key=lambda row: row.get("display_name", "").lower())
    normalized = []
    for row in rows:
        enriched = dict(row)
        department = dept_map.get(row.get("department_id"))
        enriched["department_name"] = department.get("name", "") if department else ""
        normalized.append(enriched)
    return _normalize_many(normalized)


def create_user(username, display_name, password_hash, department_id=None, role="operador"):
    existing = _get_first_by_field("users", "username", username)
    if existing:
        return None

    user_id = next_sequence("users")
    document("users", user_id).set({
        "id": user_id,
        "username": username,
        "display_name": display_name,
        "password_hash": password_hash,
        "department_id": department_id,
        "role": role,
        "email": "",
        "firebase_uid": "",
        "auth_provider": "firebase",
        "avatar_path": "",
        "is_active": 1,
        "created_at": utcnow(),
        "last_login": None,
        "failed_attempts": 0,
        "locked_until": None,
    })
    return user_id


def update_user(user_id, display_name=None, department_id=None, role=None):
    fields = {}
    if display_name is not None:
        fields["display_name"] = display_name
    if department_id is not None:
        fields["department_id"] = department_id if department_id else None
    if role is not None:
        fields["role"] = role
    if not fields:
        return False
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return True


def deactivate_user(user_id):
    document("users", user_id).set({"is_active": 0}, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)


def update_last_login(user_id):
    document("users", user_id).set({
        "last_login": utcnow(),
        "failed_attempts": 0,
        "locked_until": None,
    }, merge=True)


def sync_user_identity(user_id, email=None, firebase_uid=None, auth_provider="firebase", display_name=None):
    fields = {
        "auth_provider": auth_provider or "firebase",
    }
    if email is not None:
        fields["email"] = email.strip().lower()
    if firebase_uid is not None:
        fields["firebase_uid"] = firebase_uid
    if display_name:
        fields["display_name"] = display_name
    document("users", user_id).set(fields, merge=True)
    updated = _get_doc("users", user_id)
    if updated:
        _sync_operator_profile_from_user(updated)
    return normalize_record(updated) if updated else None


def upsert_firebase_user(firebase_uid, email, display_name="", role=None, department_id=None):
    email = (email or "").strip().lower()
    existing = get_user_by_firebase_uid(firebase_uid) or get_user_by_email(email)
    if existing:
        sync_user_identity(
            existing["id"],
            email=email,
            firebase_uid=firebase_uid,
            auth_provider="firebase",
            display_name=display_name or existing.get("display_name", ""),
        )
        if department_id is not None or role is not None:
            update_user(existing["id"], display_name=display_name or existing.get("display_name", ""), department_id=department_id, role=role)
        return get_user_by_id(existing["id"])

    base_username = email or firebase_uid or f"user_{next_sequence('usernames')}"
    username = base_username[:50]
    suffix = 1
    while _get_first_by_field("users", "username", username):
        suffix += 1
        username = f"{base_username[: max(1, 47 - len(str(suffix)))]}_{suffix}"[:50]

    user_id = create_user(username, display_name or username, "", department_id, role or "operador")
    if not user_id:
        return None
    sync_user_identity(user_id, email=email, firebase_uid=firebase_uid, auth_provider="firebase", display_name=display_name or username)
    return get_user_by_id(user_id)


def increment_failed_attempts(username, lockout_until=None):
    row = _get_first_by_field("users", "username", username)
    if not row:
        return
    updates = {"failed_attempts": int(row.get("failed_attempts", 0)) + 1}
    if lockout_until is not None:
        updates["locked_until"] = _coerce_timestamp(lockout_until)
    document("users", row["id"]).set(updates, merge=True)


def update_user_avatar(user_id, avatar_path):
    document("users", user_id).set({"avatar_path": avatar_path}, merge=True)


def get_user_avatar(user_id):
    row = _get_doc("users", user_id)
    if row and row.get("is_active", 1):
        return row.get("avatar_path", "") or ""
    return ""


def _conversation_key(user_a, user_b):
    a = int(user_a)
    b = int(user_b)
    return f"{min(a, b)}:{max(a, b)}"


def save_internal_message(sender_id, receiver_id, content, msg_type="text"):
    message_id = next_sequence("messages")
    created_at = utcnow()
    document("messages", message_id).set({
        "id": message_id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "conversation_key": _conversation_key(sender_id, receiver_id),
        "content": content,
        "msg_type": msg_type,
        "is_read": 0,
        "created_at": created_at,
    })
    unread_ref = document("internal_unread", _internal_unread_doc_id(receiver_id, sender_id))
    existing = _raw_doc(unread_ref.get()) or {}
    unread_ref.set({
        "receiver_id": receiver_id,
        "sender_id": sender_id,
        "count": int(existing.get("count", 0)) + 1,
        "last_message_at": created_at,
    })
    return message_id


def get_internal_conversation(user_a, user_b, limit=100, offset=0):
    rows = []
    for snapshot in collection("messages").where("conversation_key", "==", _conversation_key(user_a, user_b)).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    rows = _sort_records(rows, "created_at")
    if offset:
        rows = rows[offset:]
    if limit:
        rows = rows[:limit]
    users = _user_map([row.get("sender_id") for row in rows])
    enriched = []
    for row in rows:
        item = dict(row)
        sender = users.get(row.get("sender_id"))
        item["sender_name"] = sender.get("display_name", "") if sender else ""
        enriched.append(item)
    return _normalize_many(enriched)


def mark_messages_as_read(reader_id, sender_id):
    conversation = get_internal_conversation(reader_id, sender_id, limit=10000, offset=0)
    for message in conversation:
        if message.get("receiver_id") == reader_id and message.get("sender_id") == sender_id and not message.get("is_read"):
            document("messages", message["id"]).set({"is_read": 1}, merge=True)
    document("internal_unread", _internal_unread_doc_id(reader_id, sender_id)).set({
        "receiver_id": reader_id,
        "sender_id": sender_id,
        "count": 0,
        "last_message_at": utcnow(),
    }, merge=True)


def get_unread_count(user_id):
    rows = []
    for snapshot in collection("internal_unread").where("receiver_id", "==", user_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    return {int(row["sender_id"]): int(row.get("count", 0)) for row in rows if int(row.get("count", 0)) > 0}


def _resolve_display_name(declared_name, whatsapp_profile_name, phone_formatted):
    """Resolve o nome efetivo para exibicao: declared > whatsapp > phone."""
    return declared_name or whatsapp_profile_name or phone_formatted or ""


# ---------------------------------------------------------------------------
# wa_conversations — sub-threads por canal (Fase 2)
# ---------------------------------------------------------------------------
#
# Para suportar o cenario "mesmo wa_id em mais de um canal", as mensagens
# pertencem a uma `conversation` (par canal+telefone) em vez de ao
# contato direto. O contato continua sendo unico por wa_id (preserva
# nome, notas, qualificacao do cliente), mas thread, assigned_to,
# unread_count etc. ficam na conversation.
#
# conversation_id e deterministico: "{channel_id}__{wa_id}". Garante
# que webhook nunca duplique conversation pro mesmo par.
#
# Esta camada e ADITIVA: as funcoes legadas (upsert_wa_contact,
# save_wa_message, get_wa_conversation) continuam funcionando — apenas
# passam tambem a manter a coleção wa_conversations atualizada e
# denormalizam conversation_id em wa_messages. O frontend ainda
# consome a API por contact_id; quando a Fase 3 do plano for entregue,
# o frontend passa a listar conversations e mostrar badges de canal.

class ConversationIdError(ValueError):
    """Raise quando channel_id ou wa_id nao podem gerar conversation_id
    deterministico. Webhook handlers devem capturar e enfileirar em
    pending_webhook_events em vez de salvar mensagem com id sintetico
    (default__) que nao casa com selectedThreadId do frontend."""


def _make_conversation_id(channel_id, wa_id):
    """Gera id deterministico de conversation '{channel_id}__{wa_id}'.

    Falha-loud com ConversationIdError se channel_id ou wa_id estiverem
    ausentes. O fallback antigo ('default__{wa_id}') gerava ids que o
    frontend nunca encontrava (selectedThreadId usa channel_id real),
    deixando mensagens orfas invisiveis ao operador.

    Normaliza wa_id (nono digito BR) defesa-em-profundidade — callers
    como save_wa_message reusam contact.wa_id de docs antigos que
    podem estar em forma 12-dig sem 9. Sem normalizar aqui, mensagem
    nova sai com conversation_id divergente do que o frontend espera.
    """
    if channel_id is None or channel_id == "":
        raise ConversationIdError(
            f"_make_conversation_id requer channel_id (wa_id={wa_id!r})"
        )
    if not wa_id:
        raise ConversationIdError(
            f"_make_conversation_id requer wa_id (channel_id={channel_id!r})"
        )
    return f"{channel_id}__{normalize_br_phone(wa_id)}"


def upsert_wa_conversation(
    contact_id,
    wa_id,
    channel_id=None,
    source_channel_type="",
    phone_number_id="",
    auto_assign_user_id=None,
    direction_for_unread=None,
):
    """Cria ou atualiza a conversation correspondente a (channel_id, wa_id).

    Retorna conversation_id (string deterministica). Se a conversation
    ja existe, atualiza last_message_at e demais timestamps, alem de
    auto-assign quando aplicavel.

    direction_for_unread: 'inbound' incrementa unread_count, outras
    direcoes nao mexem. None nao mexe (uso pelo upsert_wa_contact).

    Normaliza o nono digito BR antes de calcular o conversation_id —
    determinismo de id depende de wa_id canonico para nao criar
    threads duplicadas pra mesmo cliente.
    """
    if wa_id is None or wa_id == "":
        raise ValueError("wa_id obrigatorio para upsert_wa_conversation")
    wa_id = normalize_br_phone(wa_id)
    conversation_id = _make_conversation_id(channel_id, wa_id)
    now = utcnow()
    ref = document("wa_conversations", conversation_id)
    snap = ref.get()
    existing = snap.to_dict() if snap.exists else None

    if existing:
        updates = {
            "last_message_at": now,
        }
        if direction_for_unread == "inbound":
            updates["last_inbound_at"] = now
            updates["unread_count"] = int(existing.get("unread_count", 0)) + 1
        elif direction_for_unread == "outbound":
            updates["last_outbound_at"] = now
        # Auto-assign se nao atribuido (coexistence)
        if auto_assign_user_id and not existing.get("assigned_to"):
            user = _get_doc("users", auto_assign_user_id)
            if user:
                updates["assigned_to"] = auto_assign_user_id
                updates["assigned_to_uid"] = user.get("firebase_uid", "")
                if not existing.get("department_id") and user.get("department_id"):
                    updates["department_id"] = user["department_id"]
        ref.set(updates, merge=True)
        return conversation_id

    # Nova conversation
    new_conv = {
        "id": conversation_id,
        "contact_id": contact_id,
        "wa_id": wa_id,
        "channel_id": channel_id,
        "phone_number_id": phone_number_id or "",
        "source_channel_type": source_channel_type or "",
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "unread_count": 1 if direction_for_unread == "inbound" else 0,
        "status": "open",
        "created_at": now,
        "last_message_at": now,
        "last_inbound_at": now if direction_for_unread == "inbound" else None,
        "last_outbound_at": now if direction_for_unread == "outbound" else None,
    }
    if auto_assign_user_id:
        user = _get_doc("users", auto_assign_user_id)
        if user:
            new_conv["assigned_to"] = auto_assign_user_id
            new_conv["assigned_to_uid"] = user.get("firebase_uid", "")
            if user.get("department_id"):
                new_conv["department_id"] = user["department_id"]
    ref.set(new_conv)
    return conversation_id


def get_wa_conversation_by_id(conversation_id):
    """Retorna a conversation pelo id deterministico."""
    snap = document("wa_conversations", conversation_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = conversation_id
    return normalize_record(data)


def get_conversations_by_contact(contact_id):
    """Retorna todas as conversations de um contato (todos os canais)."""
    rows = []
    for snap in collection("wa_conversations").where("contact_id", "==", contact_id).stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        rows.append(data)
    rows.sort(key=lambda r: r.get("last_message_at") or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return _normalize_many(rows)


def assign_wa_conversation(conversation_id, to_user_id, to_department_id, transferred_by, reason="", summary=""):
    """Transfere uma conversation (thread). Atualiza apenas a conversation
    e contact (assigned_to compartilhado por enquanto). Loga transferencia
    com referencia a conversation_id E contact_id.

    Retorna {from_user_id, to_user_id, contact_id} ou None se nao achar.
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        return None
    contact_id = conv.get("contact_id")
    from_user = conv.get("assigned_to")
    from_dept = conv.get("department_id")
    to_user = _get_doc("users", to_user_id) if to_user_id else None

    document("wa_conversations", conversation_id).set({
        "assigned_to": to_user_id,
        "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
        "department_id": to_department_id,
    }, merge=True)
    # Espelho no contato pra views legadas que ainda leem dali
    if contact_id is not None:
        document("wa_contacts", contact_id).set({
            "assigned_to": to_user_id,
            "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
            "department_id": to_department_id,
        }, merge=True)

    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id) if contact_id is not None else "",
        "from_user_id": from_user,
        "to_user_id": to_user_id,
        "to_user_uid": (to_user or {}).get("firebase_uid", ""),
        "from_department_id": from_dept,
        "to_department_id": to_department_id,
        "department_id": to_department_id,
        "reason": reason or "",
        "summary": summary or "",
        "transferred_by": transferred_by,
        "created_at": utcnow(),
    })
    return {"from_user_id": from_user, "to_user_id": to_user_id, "contact_id": contact_id}


def mark_wa_conversation_read_by_id(conversation_id):
    """Marca como lidas as mensagens inbound de uma conversation especifica.
    Usa filtro por conversation_id (Fase 2C) — nao colide entre threads do
    mesmo contato em canais diferentes."""
    q = (
        collection("wa_messages")
        .where("conversation_id", "==", conversation_id)
        .where("direction", "==", "inbound")
        .where("status", "==", "received")
    )
    batch = get_firestore_client().batch()
    count = 0
    total_updated = 0
    for snapshot in q.stream():
        batch.set(snapshot.reference, {"status": "read"}, merge=True)
        count += 1
        total_updated += 1
        if count >= 400:
            batch.commit()
            batch = get_firestore_client().batch()
            count = 0
    if count > 0:
        batch.commit()
    document("wa_conversations", conversation_id).set({"unread_count": 0}, merge=True)
    return total_updated


def upsert_wa_contact(wa_id, display_name="", channel_id=None,
                      phone_number_id="", source_channel_type="",
                      auto_assign_user_id=None,
                      from_message_event=True):
    """Cria ou atualiza um contato WhatsApp.

    Para canais coexistence, auto_assign_user_id atribui automaticamente
    ao operador dono do numero.

    Normaliza o nono digito BR e busca tambem variantes (com/sem '9')
    como defesa em profundidade contra callers que esquecam de
    normalizar.

    `from_message_event=True` (default): caller veio de evento real de
    mensagem (_process_messages, _process_smb_message_echoes,
    _process_history). Atualiza `last_message_at`/`last_inbound_at` e
    cria/atualiza a `wa_conversation` correspondente.

    `from_message_event=False`: caller e o `_process_smb_app_state_sync`
    (sincronizacao da agenda telefonica do dono). Nao popula timestamps
    de mensagem nem cria conversation — contato fica disponivel pra
    busca/seleção, mas só vira thread quando houver mensagem real.
    """
    wa_id = normalize_br_phone(wa_id)
    now = utcnow()
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        updates = {}
        if from_message_event:
            updates["last_message_at"] = now
            updates["last_inbound_at"] = now
        # Canonizar wa_id do contato pra forma com 9 (Brasil pos-2012).
        # Se o contato foi achado via variante (ex: 12-dig sem 9 mas o
        # webhook chegou com 13-dig), o doc fica preso na forma antiga e
        # todas as conversations geradas a partir de contact.wa_id ficam
        # com conversation_id divergente do selectedThreadId do frontend.
        # Migra agora pra evitar threads orfas.
        existing_wa = str(existing.get("wa_id", ""))
        if existing_wa and existing_wa != wa_id:
            updates["wa_id"] = wa_id
            updates["phone_formatted"] = format_phone_br(wa_id)
            logger.info(
                "Contato %s migrado wa_id %s -> %s (nono digito BR)",
                existing["id"], existing_wa, wa_id,
            )
        # Atualizar whatsapp_profile_name do webhook sem sobrescrever declared_name
        if display_name:
            updates["whatsapp_profile_name"] = display_name
            # Recalcular display_name efetivo
            declared = existing.get("declared_name", "")
            updates["display_name"] = _resolve_display_name(
                declared, display_name, updates.get("phone_formatted") or existing.get("phone_formatted", ""),
            )
        # Atualizar canal se ainda nao definido ou se mudou
        if channel_id is not None and not existing.get("channel_id"):
            updates["channel_id"] = channel_id
            updates["phone_number_id"] = phone_number_id
            updates["source_channel_type"] = source_channel_type
        # Auto-atribuir para coexistence se nao atribuido
        if auto_assign_user_id and not existing.get("assigned_to"):
            user = _get_doc("users", auto_assign_user_id)
            if user:
                updates["assigned_to"] = auto_assign_user_id
                updates["assigned_to_uid"] = user.get("firebase_uid", "")
                if not existing.get("department_id") and user.get("department_id"):
                    updates["department_id"] = user["department_id"]
                if existing.get("qualification") == "novo":
                    updates["qualification"] = "em_atendimento"
        document("wa_contacts", existing["id"]).set(updates, merge=True)
        # Reflete wa_id canonizado no dict local pra _maybe_upsert_conversation
        # propagar a forma certa pra wa_conversations.
        if updates.get("wa_id"):
            existing = dict(existing)
            existing["wa_id"] = updates["wa_id"]
        # Garante que a conversation deste (channel, wa_id) tambem existe.
        # Pulado em state_sync — contato existe sem thread ate ter mensagem.
        if from_message_event:
            _maybe_upsert_conversation_for_existing_contact(
                existing, channel_id, source_channel_type, phone_number_id, auto_assign_user_id,
            )
        return existing["id"]

    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name("", display_name, phone_formatted),
        "declared_name": "",
        "whatsapp_profile_name": display_name or "",
        "created_source": "webhook" if from_message_event else "state_sync",
        "created_by_user_id": None,
        "phone_formatted": phone_formatted,
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "novo",
        "notes": "",
        "assigned_to": None,
        "assigned_to_uid": "",
        "department_id": None,
        "channel_id": channel_id,
        "phone_number_id": phone_number_id,
        "source_channel_type": source_channel_type,
        "original_operator_id": None,
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        # Timestamps de mensagem so populados quando vem de evento real.
        # state_sync (agenda telefonica) deixa null pra contato nao aparecer
        # no orderBy("last_message_at") da sidebar.
        "last_message_at": now if from_message_event else None,
        "last_inbound_at": now if from_message_event else None,
    }
    # Auto-atribuir para coexistence
    if auto_assign_user_id:
        user = _get_doc("users", auto_assign_user_id)
        if user:
            new_contact["assigned_to"] = auto_assign_user_id
            new_contact["assigned_to_uid"] = user.get("firebase_uid", "")
            new_contact["qualification"] = "em_atendimento"
            if user.get("department_id"):
                new_contact["department_id"] = user["department_id"]
    document("wa_contacts", contact_id).set(new_contact)
    # Upsert conversation correspondente (Fase 2 — sub-threads por canal).
    # Pulado em state_sync: thread so nasce com mensagem real, pra nao
    # poluir sidebar com 165 contatos da agenda telefonica.
    if from_message_event:
        upsert_wa_conversation(
            contact_id=contact_id,
            wa_id=wa_id,
            channel_id=channel_id,
            source_channel_type=source_channel_type,
            phone_number_id=phone_number_id,
            auto_assign_user_id=auto_assign_user_id,
        )
    return contact_id


def _maybe_upsert_conversation_for_existing_contact(existing_contact, channel_id, source_channel_type, phone_number_id, auto_assign_user_id):
    """Helper: ao atualizar contato existente, garante que a conversation
    correspondente (channel + wa_id) tambem exista/seja atualizada."""
    upsert_wa_conversation(
        contact_id=existing_contact["id"],
        wa_id=existing_contact["wa_id"],
        channel_id=channel_id,
        source_channel_type=source_channel_type or existing_contact.get("source_channel_type", ""),
        phone_number_id=phone_number_id or existing_contact.get("phone_number_id", ""),
        auto_assign_user_id=auto_assign_user_id,
    )


def create_manual_wa_contact(declared_name, wa_id, channel_id, user_id, allow_admin_override=False):
    """Cria contato manualmente pelo operador.

    Retorna (contact_id, error_message).

    Regras quando o wa_id ja existe:
      - Se o contato esta atribuido a OUTRO operador (assigned_to != user_id)
        e nao foi arquivado, retorna erro pedindo transferencia.
        allow_admin_override=True permite ignorar essa trava (admin/supervisor).
      - Se o contato pertence ao proprio user_id, ou esta sem dono
        (assigned_to vazio), ou esta arquivado, reabre/assume e retorna
        o id existente.
    """
    existing = _find_contact_by_wa_id_any_variant(wa_id)
    if existing:
        user = _get_doc("users", user_id)
        if not user:
            return None, "Operador nao encontrado"

        existing_assigned = existing.get("assigned_to")
        is_archived = bool(existing.get("is_archived"))
        has_other_owner = bool(existing_assigned) and existing_assigned != user_id and not is_archived

        if has_other_owner and not allow_admin_override:
            owner = _get_doc("users", existing_assigned)
            owner_name = (owner or {}).get("display_name") if owner else ""
            owner_label = owner_name or f"operador #{existing_assigned}"
            return None, (
                f"Este numero ja esta em atendimento por {owner_label}. "
                "Solicite uma transferencia ao inves de criar um novo contato."
            )

        # Admin/supervisor usando override: apenas abre o contato existente
        # sem mexer em assigned_to/department/qualification do dono original.
        # Apenas completa declared_name se estiver vazio (melhoria cosmetica).
        if has_other_owner and allow_admin_override:
            updates: dict = {}
            if declared_name and not existing.get("declared_name"):
                updates["declared_name"] = declared_name
                updates["display_name"] = _resolve_display_name(
                    declared_name,
                    existing.get("whatsapp_profile_name", ""),
                    existing.get("phone_formatted", ""),
                )
            if updates:
                document("wa_contacts", existing["id"]).set(updates, merge=True)
            return existing["id"], None

        # Contato do proprio user, sem dono ou arquivado: reabre/assume.
        updates = {
            "assigned_to": user_id,
            "assigned_to_uid": user.get("firebase_uid", ""),
            "qualification": "em_atendimento",
            "is_archived": 0,
        }
        if declared_name and not existing.get("declared_name"):
            updates["declared_name"] = declared_name
            updates["display_name"] = _resolve_display_name(
                declared_name,
                existing.get("whatsapp_profile_name", ""),
                existing.get("phone_formatted", ""),
            )
        if not existing.get("department_id") and user.get("department_id"):
            updates["department_id"] = user["department_id"]
        document("wa_contacts", existing["id"]).set(updates, merge=True)
        return existing["id"], None

    now = utcnow()
    user = _get_doc("users", user_id)
    if not user:
        return None, "Operador nao encontrado"

    phone_formatted = format_phone_br(wa_id)
    contact_id = next_sequence("wa_contacts")
    new_contact = {
        "id": contact_id,
        "wa_id": wa_id,
        "display_name": _resolve_display_name(declared_name, "", phone_formatted),
        "declared_name": declared_name or "",
        "whatsapp_profile_name": "",
        "created_source": "manual",
        "created_by_user_id": user_id,
        "phone_formatted": phone_formatted,
        "profile_picture_url": "",
        "contact_avatar_path": "",
        "qualification": "em_atendimento",
        "notes": "",
        "assigned_to": user_id,
        "assigned_to_uid": user.get("firebase_uid", ""),
        "department_id": user.get("department_id"),
        "channel_id": channel_id,
        "phone_number_id": "",
        "source_channel_type": "standard",
        "original_operator_id": None,
        "converted_by_user_id": None,
        "rating": None,
        "rating_requested_at": None,
        "is_archived": 0,
        "unread_count": 0,
        "first_seen_at": now,
        "last_message_at": None,
        "last_inbound_at": None,
    }
    document("wa_contacts", contact_id).set(new_contact)
    # Fase 3: cria conversation associada para o contato manual aparecer
    # imediatamente na sidebar (que agora itera por threads, nao contatos).
    try:
        upsert_wa_conversation(
            contact_id=contact_id,
            wa_id=wa_id,
            channel_id=channel_id,
            source_channel_type=new_contact.get("source_channel_type", "standard"),
            phone_number_id="",
            auto_assign_user_id=user_id,
            direction_for_unread=None,
        )
    except Exception as exc:
        logger.warning("Falha ao criar conversation para contato manual %s: %s", contact_id, exc)
    return contact_id, None


def update_wa_contact_declared_name(contact_id, declared_name):
    """Atualiza o nome declarado pelo operador."""
    existing = _get_doc("wa_contacts", contact_id)
    if not existing:
        return False
    phone_formatted = existing.get("phone_formatted", "")
    whatsapp_name = existing.get("whatsapp_profile_name", "")
    document("wa_contacts", contact_id).set({
        "declared_name": declared_name,
        "display_name": _resolve_display_name(declared_name, whatsapp_name, phone_formatted),
    }, merge=True)
    return True


def _enrich_contact(row):
    if not row:
        return None
    users = _user_map([row.get("assigned_to")])
    departments = _department_map([row.get("department_id")])
    enriched = dict(row)
    user = users.get(row.get("assigned_to"))
    department = departments.get(row.get("department_id"))
    enriched["assigned_name"] = user.get("display_name", "") if user else ""
    enriched["assigned_role"] = user.get("role", "") if user else ""
    enriched["assigned_to_uid"] = row.get("assigned_to_uid", "") or (user.get("firebase_uid", "") if user else "")
    enriched["department_name"] = department.get("name", "") if department else ""
    return normalize_record(enriched)


def get_wa_contact(contact_id):
    return _enrich_contact(_get_doc("wa_contacts", contact_id))


def get_all_wa_contacts(include_archived=False):
    rows = [row for row in _all_docs("wa_contacts") if row]
    if not include_archived:
        rows = [row for row in rows if not row.get("is_archived")]
    rows = _sort_records(rows, "last_message_at", reverse=True)

    # Batch: coletar todos IDs unicos antes de enriquecer (evita N+1)
    all_user_ids = [row.get("assigned_to") for row in rows]
    all_dept_ids = [row.get("department_id") for row in rows]
    users = _user_map(all_user_ids)
    departments = _department_map(all_dept_ids)

    enriched = []
    for row in rows:
        item = dict(row)
        user = users.get(row.get("assigned_to"))
        department = departments.get(row.get("department_id"))
        item["assigned_name"] = user.get("display_name", "") if user else ""
        item["assigned_role"] = user.get("role", "") if user else ""
        item["assigned_to_uid"] = row.get("assigned_to_uid", "") or (user.get("firebase_uid", "") if user else "")
        item["department_name"] = department.get("name", "") if department else ""
        enriched.append(normalize_record(item))
    return enriched


def update_wa_contact_qualification(contact_id, qualification, notes=""):
    fields = {"qualification": qualification}
    if notes is not None:
        fields["notes"] = notes
    document("wa_contacts", contact_id).set(fields, merge=True)


def set_attendance_protocol(contact_id, protocol, started_at):
    document("wa_contacts", contact_id).set({
        "attendance_protocol": protocol,
        "attendance_started_at": started_at,
    }, merge=True)


def archive_wa_contact(contact_id):
    document("wa_contacts", contact_id).set({"is_archived": 1}, merge=True)


def restore_wa_contact(contact_id):
    document("wa_contacts", contact_id).set({"is_archived": 0}, merge=True)


def update_contact_avatar(contact_id, avatar_path):
    document("wa_contacts", contact_id).set({"contact_avatar_path": avatar_path}, merge=True)


def assign_wa_contact(contact_id, to_user_id, to_department_id, transferred_by, reason="", summary=""):
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None

    from_user = current.get("assigned_to")
    from_dept = current.get("department_id")
    to_user = _get_doc("users", to_user_id) if to_user_id else None
    document("wa_contacts", contact_id).set({
        "assigned_to": to_user_id,
        "assigned_to_uid": (to_user or {}).get("firebase_uid", ""),
        "department_id": to_department_id,
    }, merge=True)

    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "from_user_id": from_user,
        "to_user_id": to_user_id,
        "to_user_uid": (to_user or {}).get("firebase_uid", ""),
        "from_department_id": from_dept,
        "to_department_id": to_department_id,
        "department_id": to_department_id,
        "reason": reason or "",
        "summary": summary or "",
        "transferred_by": transferred_by,
        "created_at": utcnow(),
    })
    return {"from_user_id": from_user, "to_user_id": to_user_id}


def return_contact_to_bot(contact_id, returned_by_user_id):
    """Devolve o contato para a fila do bot (remove atribuicao)."""
    current = _get_doc("wa_contacts", contact_id)
    if not current:
        return None
    from_user = current.get("assigned_to")
    from_dept = current.get("department_id")
    document("wa_contacts", contact_id).set({
        "assigned_to": None,
        "assigned_to_uid": "",
        "qualification": "novo",
        "bot_completed": False,
        "attendance_protocol": "",
        "attendance_started_at": "",
    }, merge=True)
    # Log na transfer_log
    transfer_id = next_sequence("wa_transfer_log")
    document("wa_transfer_log", transfer_id).set({
        "id": transfer_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "from_user_id": from_user,
        "to_user_id": None,
        "to_user_uid": "",
        "from_department_id": from_dept,
        "to_department_id": None,
        "department_id": None,
        "reason": "Devolvido ao bot",
        "summary": "Contato devolvido para a fila do bot",
        "transferred_by": returned_by_user_id,
        "created_at": utcnow(),
    })
    return True


def get_contacts_by_assigned_user(user_id):
    """Retorna todos os contatos atribuidos a um usuario."""
    rows = []
    for snapshot in collection("wa_contacts").where("assigned_to", "==", user_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    return _normalize_many(rows)


def insert_transfer_system_message(contact_id, content, operator_id=None,
                                   conversation_id=None, channel_id=None):
    return save_wa_message(
        wa_message_id=f"sys_{utcnow().isoformat()}_{contact_id}",
        contact_id=contact_id,
        direction="system",
        msg_type="system",
        content=content,
        status="delivered",
        timestamp_wa=utcnow().isoformat(),
        operator_id=operator_id,
        sender_user_id=operator_id,
        conversation_id=conversation_id,
        channel_id=channel_id,
    )


def get_transfer_history(contact_id, limit=50):
    rows = []
    for snapshot in collection("wa_transfer_log").where("contact_id", "==", contact_id).stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)
    rows = _sort_records(rows, "created_at", reverse=True)[:limit]
    user_ids = []
    department_ids = []
    for row in rows:
        user_ids.extend([row.get("from_user_id"), row.get("to_user_id"), row.get("transferred_by")])
        department_ids.extend([row.get("from_department_id"), row.get("to_department_id")])
    users = _user_map(user_ids)
    departments = _department_map(department_ids)
    enriched = []
    for row in rows:
        item = dict(row)
        item["from_user_name"] = users.get(row.get("from_user_id"), {}).get("display_name", "")
        item["to_user_name"] = users.get(row.get("to_user_id"), {}).get("display_name", "")
        item["transferred_by_name"] = users.get(row.get("transferred_by"), {}).get("display_name", "")
        item["from_dept_name"] = departments.get(row.get("from_department_id"), {}).get("name", "")
        item["to_dept_name"] = departments.get(row.get("to_department_id"), {}).get("name", "")
        enriched.append(item)
    return _normalize_many(enriched)


def save_wa_message(wa_message_id, contact_id, direction, msg_type, content="",
                    media_path="", media_mime="", media_id="",
                    latitude=None, longitude=None, filename="",
                    status="received", timestamp_wa="", operator_id=None,
                    reply_to_message_id=None, reply_to_preview="", reply_to_sender_name="",
                    channel_id=None, phone_number_id="",
                    is_rating_message=False, visibility="all",
                    conversation_id=None,
                    channel_owner_user_id=None, sender_user_id=None,
                    template_category=None, media_size_bytes=0):
    """Persiste mensagem WhatsApp.

    Auditoria coexistence (Fase 2C):
      - `channel_owner_user_id`: dono fisico do numero (ex.: operador X que
        conectou o WhatsApp pessoal dele via coexistence). Vem de
        `channel.owner_user_id` no momento do envio/recebimento.
      - `sender_user_id`: operador que efetivamente digitou/enviou (em
        outbound). None em inbound. Permite distinguir, em transferencias
        coexistence, quem digitou vs quem e o dono do numero.

    `conversation_id` pode ser passado explicitamente (caller ja resolveu
    a thread). Caso contrario, e derivado de (channel_id, contact.wa_id).

    Visibilidade de uso (Fase 2.10.4):
      - `template_category`: 'marketing'/'utility'/'authentication' quando
        msg_type='template'; demais values mapeados pra 'unknown'.
      - `media_size_bytes`: tamanho em bytes do payload de midia outbound.
        Usado pra agregacao mensal em audit_metrics/usage_{YYYY_MM}.
    """
    if wa_message_id:
        existing = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
        if existing:
            document("wa_messages", existing["id"]).set({
                "msg_type": _prefer_wa_msg_type(existing.get("msg_type"), msg_type),
                "content": _prefer_wa_content(existing.get("content"), content),
                "media_path": media_path or existing.get("media_path", ""),
                "media_mime": media_mime or existing.get("media_mime", ""),
                "media_id": media_id or existing.get("media_id", ""),
                "latitude": latitude if latitude is not None else existing.get("latitude"),
                "longitude": longitude if longitude is not None else existing.get("longitude"),
                "filename": filename or existing.get("filename", ""),
                "status": status or existing.get("status", "received"),
                "operator_id": operator_id if operator_id is not None else existing.get("operator_id"),
                "timestamp_wa": _coerce_timestamp(timestamp_wa) or existing.get("timestamp_wa"),
                "reply_to_message_id": reply_to_message_id if reply_to_message_id is not None else existing.get("reply_to_message_id"),
                "reply_to_preview": reply_to_preview or existing.get("reply_to_preview", ""),
                "reply_to_sender_name": reply_to_sender_name or existing.get("reply_to_sender_name", ""),
            }, merge=True)
            return existing["id"]

    message_id = next_sequence("wa_messages")
    created_at = utcnow()
    effective_wa_message_id = wa_message_id or f"local_{message_id}"
    contact = _get_doc("wa_contacts", contact_id)
    # Resolve channel/wa_id efetivos pra calcular conversation_id
    eff_channel_id = channel_id if channel_id is not None else (contact or {}).get("channel_id")
    eff_wa_id = (contact or {}).get("wa_id", "")
    eff_phone_number_id = phone_number_id or (contact or {}).get("phone_number_id", "")
    if conversation_id:
        eff_conversation_id = conversation_id
    else:
        try:
            eff_conversation_id = _make_conversation_id(eff_channel_id, eff_wa_id)
        except ConversationIdError as exc:
            # Mensagem que nao pode ter conversation_id deterministico
            # ficaria invisivel pro frontend (filtra por selectedThreadId).
            # Quem nos chama (webhook) deve enfileirar em
            # pending_webhook_events. Mensagens system internas (transfer,
            # etc.) podem pular o filtro com direction='system'.
            if direction != "system":
                logger.error(
                    "save_wa_message abortado: %s | contact=%s direction=%s",
                    exc, contact_id, direction,
                )
                raise
            eff_conversation_id = None
    document("wa_messages", message_id).set({
        "id": message_id,
        "wa_message_id": effective_wa_message_id,
        "contact_id": contact_id,
        "contact_doc_id": str(contact_id),
        "conversation_id": eff_conversation_id,
        "direction": direction,
        "msg_type": msg_type,
        "content": content or "",
        "media_path": media_path or "",
        "media_mime": media_mime or "",
        "media_id": media_id or "",
        "latitude": latitude,
        "longitude": longitude,
        "filename": filename or "",
        "status": status or "received",
        "operator_id": operator_id,
        "sender_user_id": sender_user_id,
        "channel_owner_user_id": channel_owner_user_id,
        "assigned_to": (contact or {}).get("assigned_to"),
        "assigned_to_uid": (contact or {}).get("assigned_to_uid", ""),
        "department_id": (contact or {}).get("department_id"),
        "channel_id": eff_channel_id,
        "phone_number_id": eff_phone_number_id,
        "is_rating_message": is_rating_message,
        "visibility": visibility,
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": created_at,
        "reply_to_message_id": reply_to_message_id,
        "reply_to_preview": reply_to_preview or "",
        "reply_to_sender_name": reply_to_sender_name or "",
    })

    if contact:
        updates = {"last_message_at": created_at}
        if direction == "inbound" and status == "received":
            updates["unread_count"] = int(contact.get("unread_count", 0)) + 1
        document("wa_contacts", contact_id).set(updates, merge=True)

        # Atualiza conversation correspondente (Fase 2 — sub-threads).
        # Se ainda nao existe (mensagem de contato legado pre-Fase 2),
        # cria automaticamente.
        if eff_wa_id:
            try:
                upsert_wa_conversation(
                    contact_id=contact_id,
                    wa_id=eff_wa_id,
                    channel_id=eff_channel_id,
                    source_channel_type=(contact or {}).get("source_channel_type", ""),
                    phone_number_id=eff_phone_number_id,
                    direction_for_unread="inbound" if direction == "inbound" and status == "received" else ("outbound" if direction == "outbound" else None),
                )
            except Exception as exc:
                logger.warning("Falha ao upsert conversation para msg %s: %s", message_id, exc)

    # Atualizar metricas de auditoria (fire-and-forget)
    increment_audit_metrics(
        direction=direction,
        operator_id=operator_id or (contact or {}).get("assigned_to"),
    )
    # Visibilidade de uso mensal (Fase 2.10.4 — usage_{YYYY_MM} per-tenant)
    increment_usage_metrics(
        direction=direction,
        msg_type=msg_type,
        template_category=template_category,
        media_size_bytes=media_size_bytes,
    )
    return message_id


def get_wa_conversation(contact_id, limit=50, offset=0, conversation_id=None):
    """Retorna mensagens do contato em ordem cronologica real.

    Ordena por `timestamp_wa` (quando a mensagem realmente aconteceu),
    nao `created_at` (quando foi salva). Critico pro history sync —
    mensagens antigas chegam horas/dias depois mas devem aparecer no
    fundo da timeline, nao no topo.

    Se conversation_id for passado, filtra apenas a thread (canal+wa_id)
    correspondente — preserva isolamento entre canais (coexistence vs
    standard) que o filtro legado por contact_id misturava.
    """
    q = collection("wa_messages").where("contact_id", "==", contact_id)
    if conversation_id:
        q = q.where("conversation_id", "==", conversation_id)
    q = q.order_by("timestamp_wa", direction="DESCENDING")
    if limit:
        q = q.limit(limit + offset)

    rows = []
    for snapshot in q.stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)

    if offset:
        rows = rows[offset:]
    # Reverter para ordem cronologica (mais antigo primeiro)
    rows.reverse()

    contact = _get_doc("wa_contacts", contact_id)
    operators = _user_map([row.get("operator_id") for row in rows])
    enriched = []
    for row in rows:
        item = dict(row)
        item["contact_name"] = contact.get("display_name", "") if contact else ""
        item["wa_id"] = contact.get("wa_id", "") if contact else ""
        item["phone_formatted"] = contact.get("phone_formatted", "") if contact else ""
        item["contact_avatar_path"] = contact.get("contact_avatar_path", "") if contact else ""
        item["operator_name"] = operators.get(row.get("operator_id"), {}).get("display_name", "")
        enriched.append(item)
    return _normalize_many(enriched)


def get_wa_message_by_id(message_id: int):
    for snap in collection("wa_messages").where("id", "==", message_id).limit(1).stream():
        return _raw_doc(snap)
    return None


def get_wa_message_by_wa_message_id(wa_message_id):
    if not wa_message_id:
        return None
    for snap in collection("wa_messages").where("wa_message_id", "==", wa_message_id).limit(1).stream():
        return _raw_doc(snap)
    return None


def mark_message_corrected(message_id: int, corrected_by_message_id: int):
    """Marca uma mensagem como corrigida por outra mensagem."""
    msg = get_wa_message_by_id(message_id)
    if not msg:
        return False
    document("wa_messages", message_id).set({
        "is_corrected": True,
        "corrected_by_message_id": corrected_by_message_id,
    }, merge=True)
    return True


def update_wa_message_transcription(db_id: int, transcription: str):
    document("wa_messages", db_id).set({"transcription": transcription}, merge=True)


def update_wa_message_status(wa_message_id, status, timestamp_wa=""):
    target = _get_first_by_field("wa_messages", "wa_message_id", wa_message_id)
    if target:
        document("wa_messages", target["id"]).set({"status": status}, merge=True)

    status_id = next_sequence("wa_message_status")
    document("wa_message_status", status_id).set({
        "id": status_id,
        "wa_message_id": wa_message_id,
        "status": status,
        "timestamp_wa": _coerce_timestamp(timestamp_wa),
        "created_at": utcnow(),
    })


def get_wa_unread_count():
    """Retorna mapa {contact_id: unread_count}.

    Nota: get_all_wa_contacts() ja inclui unread_count nos contatos.
    Esta funcao existe apenas para chamadas avulsas; o endpoint
    /api/wa/contacts NAO precisa mais chamar esta funcao separadamente.
    """
    result = {}
    for snapshot in collection("wa_contacts").where("unread_count", ">", 0).stream():
        row = _raw_doc(snapshot)
        if row:
            result[int(row["id"])] = int(row.get("unread_count", 0))
    return result


def mark_wa_conversation_read(contact_id):
    """Marca mensagens inbound como lidas. Usa query filtrada para ler apenas
    as mensagens que realmente precisam ser atualizadas (em vez de todas)."""
    q = (
        collection("wa_messages")
        .where("contact_id", "==", contact_id)
        .where("direction", "==", "inbound")
        .where("status", "==", "received")
    )
    batch = get_firestore_client().batch()
    count = 0
    total_updated = 0
    for snapshot in q.stream():
        batch.set(snapshot.reference, {"status": "read"}, merge=True)
        count += 1
        total_updated += 1
        if count >= 400:  # Firestore batch limit = 500
            batch.commit()
            batch = get_firestore_client().batch()
            count = 0
    if count > 0:
        batch.commit()
    document("wa_contacts", contact_id).set({"unread_count": 0}, merge=True)
    return total_updated


# ---------------------------------------------------------------------------
# Audit metrics (pre-aggregated daily counters)
# ---------------------------------------------------------------------------

def _audit_metric_doc_id(date_str, user_id=None):
    return f"{date_str}_{user_id}" if user_id else date_str


def increment_audit_metrics(direction, operator_id=None, is_new_lead=False, is_assumed=False):
    """Incrementa metricas diarias. Chamada a cada save_wa_message."""
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    half_hour = f"{now.strftime('%H')}:{('00' if now.minute < 30 else '30')}"

    def _increment(doc_id):
        ref = document("audit_metrics", doc_id)
        snap = ref.get()
        data = snap.to_dict() if snap.exists else {}

        updates = {
            "date": date_str,
            "updated_at": now,
        }

        if direction == "inbound":
            updates["total_messages_inbound"] = int(data.get("total_messages_inbound", 0)) + 1
        elif direction == "outbound":
            updates["total_messages_outbound"] = int(data.get("total_messages_outbound", 0)) + 1

        if is_new_lead:
            updates["total_leads_received"] = int(data.get("total_leads_received", 0)) + 1
        if is_assumed:
            updates["total_leads_assumed"] = int(data.get("total_leads_assumed", 0)) + 1

        # Messages by half hour
        by_half = data.get("messages_by_half_hour", {})
        by_half[half_hour] = int(by_half.get(half_hour, 0)) + 1
        updates["messages_by_half_hour"] = by_half

        # Activity tracking
        if not data.get("first_activity_at"):
            updates["first_activity_at"] = now
        updates["last_activity_at"] = now

        ref.set(updates, merge=True)

    try:
        # Global aggregate
        _increment(_audit_metric_doc_id(date_str))
        # Per-operator aggregate
        if operator_id:
            _increment(_audit_metric_doc_id(date_str, operator_id))
    except Exception as exc:
        logger.warning("Falha ao atualizar audit_metrics: %s", exc)


def get_audit_metrics(date_from, date_to):
    """Retorna metricas agregadas (daily/per-operator) para o periodo.

    Pula docs com prefix `usage_` (agregacao mensal — get_monthly_usage).
    """
    rows = []
    for snap in collection("audit_metrics").stream():
        if snap.id.startswith("usage_"):
            continue
        data = snap.to_dict() or {}
        date_str = data.get("date", "")
        if date_from <= date_str <= date_to:
            data["doc_id"] = snap.id
            rows.append(normalize_record(data))
    return rows


# ---------------------------------------------------------------------------
# Usage metrics mensal per-tenant (Fase 2.10.4)
# ---------------------------------------------------------------------------
#
# Doc id: `usage_{YYYY-MM}` em tenants/{tid}/audit_metrics/.
# Tenant scoping vem do ContextVar (collection() roteia automaticamente).
# Increment atomico via firestore.Increment evita perda em concorrencia.

def _usage_metrics_doc_id(year_month=None):
    if not year_month:
        year_month = utcnow().strftime("%Y-%m")
    return f"usage_{year_month}"


_VALID_TEMPLATE_CATEGORIES = ("marketing", "utility", "authentication")


def increment_usage_metrics(direction, msg_type="", template_category=None, media_size_bytes=0):
    """Incrementa usage_{YYYY_MM} do tenant atual com Increment atomico.

    Campos atualizados conforme direction/msg_type:
      - inbound  -> inbound_received++
      - outbound + msg_type='template' -> templates_sent.{cat}++ (cat
        normalizada pra marketing/utility/authentication ou 'unknown')
      - outbound + outros msg_type -> free_form_sent++
      - media_size_bytes>0 -> media_uploaded_bytes += bytes
    """
    now = utcnow()
    year_month = now.strftime("%Y-%m")
    doc_id = _usage_metrics_doc_id(year_month)

    updates = {
        "month": year_month,
        "updated_at": now,
    }

    if direction == "inbound":
        updates["inbound_received"] = firestore.Increment(1)
    elif direction == "outbound":
        if msg_type == "template":
            cat = (template_category or "").strip().lower() or "unknown"
            if cat not in _VALID_TEMPLATE_CATEGORIES:
                cat = "unknown"
            updates["templates_sent"] = {cat: firestore.Increment(1)}
        else:
            updates["free_form_sent"] = firestore.Increment(1)

    if media_size_bytes and int(media_size_bytes) > 0:
        updates["media_uploaded_bytes"] = firestore.Increment(int(media_size_bytes))

    try:
        document("audit_metrics", doc_id).set(updates, merge=True)
    except Exception as exc:
        logger.warning("Falha ao atualizar usage_metrics: %s", exc)


def get_monthly_usage(year_month=None):
    """Retorna usage_{YYYY_MM} do tenant atual.

    year_month default = mes corrente (UTC). Retorna esqueleto zerado se
    o doc ainda nao existe (mes sem trafego).
    """
    if not year_month:
        year_month = utcnow().strftime("%Y-%m")
    doc_id = _usage_metrics_doc_id(year_month)
    snap = document("audit_metrics", doc_id).get()
    if not snap.exists:
        return {
            "month": year_month,
            "templates_sent": {},
            "free_form_sent": 0,
            "inbound_received": 0,
            "media_uploaded_bytes": 0,
        }
    data = snap.to_dict() or {}
    data.setdefault("month", year_month)
    data.setdefault("templates_sent", {})
    data.setdefault("free_form_sent", 0)
    data.setdefault("inbound_received", 0)
    data.setdefault("media_uploaded_bytes", 0)
    return normalize_record(data)


def get_usage_history(months=3):
    """Retorna ultimos N meses de usage do tenant atual (mes corrente primeiro).

    months e clampeado em [1, 24].
    """
    months = max(1, min(int(months or 3), 24))
    now = utcnow()
    rows = []
    for offset in range(months):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        ym = f"{year:04d}-{month:02d}"
        rows.append(get_monthly_usage(ym))
    return rows


def get_all_ratings(date_from=None, date_to=None):
    """Retorna contatos convertidos com rating."""
    rows = []
    for snap in collection("wa_contacts").where("qualification", "==", "convertido").stream():
        data = _raw_doc(snap)
        if not data or data.get("rating") is None:
            continue
        if date_from or date_to:
            rated_at = str(data.get("rating_received_at", ""))[:10]
            if date_from and rated_at < date_from:
                continue
            if date_to and rated_at > date_to:
                continue
        rows.append(normalize_record(data))
    return rows


def log_audit(user_id, action, detail="", ip_address=""):
    audit_id = next_sequence("audit_log")
    document("audit_log", audit_id).set({
        "id": audit_id,
        "user_id": user_id,
        "action": action,
        "detail": detail or "",
        "ip_address": ip_address or "",
        "created_at": utcnow(),
    })


def format_phone_br(wa_id):
    s = str(wa_id)
    if len(s) == 13 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:9]}-{s[9:]}"
    if len(s) == 12 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:8]}-{s[8:]}"
    return f"+{s}" if not s.startswith("+") else s


def normalize_br_phone(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55"):
        ddd = s[2:4]
        local = s[4:]
        if local and local[0] in ("6", "7", "8", "9"):
            return f"55{ddd}9{local}"
    return s


def wa_id_variants(wa_id):
    """Gera todas as variantes equivalentes de um wa_id brasileiro.

    Celulares BR tem o '9' na frente desde 2012, mas numeros cadastrados
    antes (ou recebidos via webhook de clientes antigos) podem chegar sem.
    Retorna lista com o wa_id original e a variante com/sem 9 para
    cruzamento ao buscar contato existente.
    """
    s = str(wa_id).strip()
    if not s:
        return []
    variants = [s]
    # Celular BR com 9 (13 digitos, ex: 5531982779779) -> adiciona variante sem 9
    if len(s) == 13 and s.startswith("55") and len(s) > 4 and s[4] == "9":
        variants.append(s[:4] + s[5:])
    # Celular BR sem 9 (12 digitos, ex: 553182779779) -> adiciona variante com 9
    elif len(s) == 12 and s.startswith("55") and len(s) > 4 and s[4] in ("6", "7", "8", "9"):
        variants.append(s[:4] + "9" + s[4:])
    return variants


def _find_contact_by_wa_id_any_variant(wa_id):
    """Busca contato por wa_id testando tambem a variante com/sem 9.

    Retorna o primeiro match encontrado ou None.
    """
    for variant in wa_id_variants(wa_id):
        found = _get_first_by_field("wa_contacts", "wa_id", variant)
        if found:
            return found
    return None


# ---------------------------------------------------------------------------
# Configuracoes do sistema e do usuario
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_SETTINGS = {
    "chat_prefix_enabled": False,
    "chat_prefix_roles": ["admin", "supervisor", "operador"],
    "quick_message_max": 20,
    "quick_messages_global": [],
    "notification_sound_enabled": True,
    "alarm_enabled": True,
    "alarm_threshold_minutes": 5,
    "alarm_department_ids": [],
    "alarm_sound_path": "",
    "notification_sound_path": "",
    "bot_enabled": False,
}


def get_system_settings():
    doc = _get_doc("system_settings", "chat")
    if not doc:
        return dict(_DEFAULT_SYSTEM_SETTINGS)
    result = dict(_DEFAULT_SYSTEM_SETTINGS)
    result.update({k: v for k, v in doc.items() if k in _DEFAULT_SYSTEM_SETTINGS})
    return result


def save_system_settings(settings: dict):
    allowed = set(_DEFAULT_SYSTEM_SETTINGS.keys())
    filtered = {k: v for k, v in settings.items() if k in allowed}
    filtered["updated_at"] = utcnow()
    document("system_settings", "chat").set(filtered, merge=True)
    return get_system_settings()


def get_user_settings(user_id: int):
    doc = _get_doc("user_settings", user_id)
    defaults = {
        "chat_prefix_enabled": False,
        "chat_prefix_name": "",
        "quick_messages": [],
    }
    if not doc:
        return defaults
    result = dict(defaults)
    result.update({k: v for k, v in doc.items() if k in defaults})
    return result


def save_user_settings(user_id: int, settings: dict):
    allowed = {"chat_prefix_enabled", "chat_prefix_name", "quick_messages"}
    filtered = {k: v for k, v in settings.items() if k in allowed}
    filtered["updated_at"] = utcnow()
    document("user_settings", user_id).set(filtered, merge=True)
    return get_user_settings(user_id)


# ---------------------------------------------------------------------------
# Google Chat - Comunicacao interna
# ---------------------------------------------------------------------------

def _active_gc_participants():
    participants = {
        str((row or {}).get("email") or "").strip().lower()
        for row in _all_docs("users")
        if row and row.get("is_active", 1)
    }
    participants.discard("")
    return sorted(participants)


def _gc_unread_recipients(conversation):
    recipients = set(_active_gc_participants())
    recipients.update(
        str(participant or "").strip().lower()
        for participant in (conversation or {}).get("participants", [])
        if str(participant or "").strip()
    )
    recipients.update(
        str(identifier or "").strip().lower()
        for identifier in ((conversation or {}).get("unread_count", {}) or {}).keys()
        if str(identifier or "").strip()
    )
    recipients.discard("")
    return sorted(recipients)


def upsert_gc_conversation(space_id, space_name=""):
    """Cria ou atualiza conversa do Google Chat. Retorna conversation_id."""
    now = utcnow()
    existing = _get_first_by_field("gc_conversations", "space_id", space_id)
    participants = _active_gc_participants()
    if existing:
        updates = {"last_message_at": now, "participants": participants}
        if space_name:
            updates["space_name"] = space_name
        document("gc_conversations", existing["id"]).set(updates, merge=True)
        return existing["id"]

    conversation_id = next_sequence("gc_conversations")
    document("gc_conversations", conversation_id).set({
        "id": conversation_id,
        "space_id": space_id,
        "space_name": space_name or space_id,
        "participants": participants,
        "last_message": "",
        "last_message_at": now,
        "unread_count": {},
        "created_at": now,
    })
    return conversation_id


def get_gc_conversation(conversation_id):
    """Retorna uma conversa pelo ID."""
    return normalize_record(_get_doc("gc_conversations", conversation_id))


def get_gc_conversation_by_space(space_id):
    """Retorna conversa pelo space_id do Google Chat."""
    row = _get_first_by_field("gc_conversations", "space_id", space_id)
    return normalize_record(row) if row else None


def get_all_gc_conversations():
    """Lista todas as conversas do Google Chat."""
    rows = [row for row in _all_docs("gc_conversations") if row]
    rows = _sort_records(rows, "last_message_at", reverse=True)
    return _normalize_many(rows)


def save_gc_message(conversation_id, gchat_message_id, sender_email, sender_name,
                    msg_type="text", content="", media_path="", media_mime="",
                    source="google_chat", create_time=""):
    """Salva mensagem do Google Chat no Firestore."""
    existing = _get_first_by_field("gc_messages", "gchat_message_id", gchat_message_id)
    if existing:
        return existing["id"]

    message_id = next_sequence("gc_messages")
    now = utcnow()
    document("gc_messages", message_id).set({
        "id": message_id,
        "conversation_id": conversation_id,
        "gchat_message_id": gchat_message_id,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "msg_type": msg_type,
        "content": content or "",
        "media_path": media_path or "",
        "media_mime": media_mime or "",
        "source": source,
        "create_time": _coerce_timestamp(create_time),
        "created_at": now,
    })

    # Atualizar preview e timestamp na conversa
    conversation = _get_doc("gc_conversations", conversation_id)
    if conversation:
        participants = _gc_unread_recipients(conversation)
        sender_key = str(sender_email or "").strip().lower()
        preview = content[:100] if content else f"[{msg_type}]"
        updates = {
            "last_message": preview,
            "last_message_at": now,
            "participants": participants,
        }
        unread = conversation.get("unread_count", {}) or {}
        for participant_id in participants:
            unread.setdefault(participant_id, 0)
            if participant_id != sender_key:
                unread[participant_id] = int(unread.get(participant_id, 0)) + 1
        updates["unread_count"] = unread
        document("gc_conversations", conversation_id).set(updates, merge=True)

    return message_id


def get_gc_messages(conversation_id, limit=50, offset=0):
    """Retorna mensagens de uma conversa do Google Chat."""
    q = (
        collection("gc_messages")
        .where("conversation_id", "==", conversation_id)
        .order_by("created_at", direction="DESCENDING")
    )
    if limit:
        q = q.limit(limit + offset)

    rows = []
    for snapshot in q.stream():
        row = _raw_doc(snapshot)
        if row:
            rows.append(row)

    if offset:
        rows = rows[offset:]
    rows.reverse()
    return _normalize_many(rows)


def mark_gc_conversation_read(conversation_id, user_identifier):
    """Reseta o contador de nao-lidas para um usuario em uma conversa."""
    conversation = _get_doc("gc_conversations", conversation_id)
    if not conversation:
        return
    unread = conversation.get("unread_count", {}) or {}
    uid = str(user_identifier or "").strip().lower()
    if not uid:
        return
    unread[uid] = 0
    document("gc_conversations", conversation_id).set({"unread_count": unread}, merge=True)


# ---------------------------------------------------------------------------
# Contador de assumidas sem resposta (operador)
# ---------------------------------------------------------------------------

_ASSUME_COUNTER_MIN = -2
_ASSUME_COUNTER_MAX = 0


def get_assume_counter(user_id: int) -> int:
    """Retorna o contador de assumidas sem resposta do operador (entre -2 e 0)."""
    doc = _get_doc("operator_assume_counters", user_id)
    if not doc:
        return 0
    return max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, doc.get("counter", 0)))


@firestore.transactional
def _transactional_decrement(transaction, ref, user_id):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {} if snapshot.exists else {}
    current = max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, data.get("counter", 0)))
    new_val = max(_ASSUME_COUNTER_MIN, current - 1)
    transaction.set(ref, {"user_id": user_id, "counter": new_val, "updated_at": utcnow()}, merge=True)
    return new_val


def decrement_assume_counter(user_id: int) -> int:
    """Decrementa o contador ao assumir sem ter respondido. Usa transacao atomica."""
    ref = document("operator_assume_counters", user_id)
    client = get_firestore_client()
    return _transactional_decrement(client.transaction(), ref, user_id)


@firestore.transactional
def _transactional_increment(transaction, ref, user_id):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {} if snapshot.exists else {}
    current = max(_ASSUME_COUNTER_MIN, min(_ASSUME_COUNTER_MAX, data.get("counter", 0)))
    new_val = min(_ASSUME_COUNTER_MAX, current + 1)
    transaction.set(ref, {"user_id": user_id, "counter": new_val, "updated_at": utcnow()}, merge=True)
    return new_val


def increment_assume_counter(user_id: int) -> int:
    """Incrementa o contador ao responder uma conversa assumida. Usa transacao atomica."""
    ref = document("operator_assume_counters", user_id)
    client = get_firestore_client()
    return _transactional_increment(client.transaction(), ref, user_id)


def mark_contact_pending_response(contact_id: int):
    """Marca o contato como pendente de resposta do operador apos assumir."""
    document("wa_contacts", contact_id).set({
        "assume_pending_response": True,
    }, merge=True)


def clear_contact_pending_response(contact_id: int):
    """Remove a flag de pendente de resposta apos o operador responder."""
    document("wa_contacts", contact_id).set({
        "assume_pending_response": False,
    }, merge=True)


def reset_assume_counter(user_id: int):
    """Reseta o contador de assumidas sem resposta para 0."""
    document("operator_assume_counters", user_id).set({
        "user_id": user_id,
        "counter": 0,
        "updated_at": utcnow(),
    }, merge=True)
```

## firebase_admin_client.py

```python
# -*- coding: utf-8 -*-

import logging

import firebase_admin
from firebase_admin import auth

from config import FIREBASE_STORAGE_BUCKET, FIRESTORE_PROJECT_ID

logger = logging.getLogger("castro_crm.firebase_admin")


def get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        options = {}
        if FIRESTORE_PROJECT_ID:
            options["projectId"] = FIRESTORE_PROJECT_ID
        if FIREBASE_STORAGE_BUCKET:
            options["storageBucket"] = FIREBASE_STORAGE_BUCKET
        return firebase_admin.initialize_app(options=options or None)


def verify_firebase_id_token(id_token):
    app = get_firebase_app()
    return auth.verify_id_token(id_token, app=app, check_revoked=False)


def set_tenant_claims(firebase_uid, tenant_id, role=None):
    """Define custom claims tenant_id (e role opcional) no usuario Firebase.

    O JWT do usuario passa a carregar essas claims, lidas pelo backend em
    get_current_user. O cliente precisa renovar o ID token (forceRefresh)
    para o claim aparecer na proxima chamada — o frontend deve chamar
    user.getIdToken(true) apos qualquer set_tenant_claims.
    """
    if not firebase_uid:
        raise ValueError("firebase_uid obrigatorio")
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    app = get_firebase_app()
    try:
        existing = auth.get_user(firebase_uid, app=app)
        current_claims = dict(existing.custom_claims or {})
    except Exception as exc:
        logger.warning("set_tenant_claims: get_user falhou para %s: %s", firebase_uid, exc)
        current_claims = {}
    current_claims["tenant_id"] = str(tenant_id)
    if role:
        current_claims["role"] = str(role)
    try:
        auth.set_custom_user_claims(firebase_uid, current_claims, app=app)
        logger.info(
            "Custom claims atualizados | uid=%s tenant_id=%s role=%s",
            firebase_uid, tenant_id, role or "(unchanged)",
        )
        return True
    except Exception as exc:
        logger.error("set_tenant_claims: falha ao setar claims | uid=%s exc=%s", firebase_uid, exc)
        return False


def get_user_claims(firebase_uid):
    """Retorna o dict de custom claims do usuario Firebase, ou {} se none."""
    if not firebase_uid:
        return {}
    app = get_firebase_app()
    try:
        return dict((auth.get_user(firebase_uid, app=app).custom_claims or {}))
    except Exception as exc:
        logger.warning("get_user_claims: falha para %s: %s", firebase_uid, exc)
        return {}
```

## firestore_common.py

```python
# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from functools import lru_cache

from google.cloud import firestore

from config import FIRESTORE_COLLECTION_PREFIX, FIRESTORE_PROJECT_ID

logger = logging.getLogger("castro_crm.firestore")

# ---------------------------------------------------------------------------
# Tenant context (Fase 2 multi-tenant)
# ---------------------------------------------------------------------------
#
# Estrategia de implementacao:
#
#   ContextVar `_current_tenant_id` carrega o tenant ativo para a request
#   ou tarefa atual. Toda funcao que usa `collection(name)` / `document(name)`
#   automaticamente roteia para `tenants/{tenant_id}/<name>` quando o
#   contextvar esta setado, ou cai em coletas flat quando ausente
#   (compatibilidade pre-migration).
#
#   Coletas listadas em _GLOBAL_COLLECTIONS NUNCA sao roteadas para
#   subcolecao do tenant — sao genuinamente globais (counters, indice
#   phone_routing, e a propria root tenants/).
#
#   Uso:
#     - FastAPI middleware ou get_current_user seta o contextvar via
#       set_tenant_context(tid) por request.
#     - Webhook seta antes de processar payload da Meta.
#     - Operacoes super-admin cross-tenant podem usar
#       `with tenant_context(None): ...` para ler/escrever no flat global.

_current_tenant_id: ContextVar[str | None] = ContextVar("castro_crm_tenant", default=None)

# Colecoes que permanecem globais mesmo com tenant context ativo.
_GLOBAL_COLLECTIONS = frozenset({"_meta", "tenants", "phone_routing"})


def set_tenant_context(tenant_id):
    """Seta o tenant ativo para o contexto atual. Retorna token p/ reset."""
    return _current_tenant_id.set(tenant_id if tenant_id else None)


def reset_tenant_context(token):
    _current_tenant_id.reset(token)


def get_tenant_context():
    """Retorna o tenant_id ativo no contexto atual, ou None se nao setado."""
    return _current_tenant_id.get()


@contextmanager
def tenant_context(tenant_id):
    """Context manager para escopo limitado de tenant.

    Exemplo (super-admin pulando para outro tenant):
        with tenant_context("clinica-vida"):
            data = get_all_wa_contacts()
    """
    token = set_tenant_context(tenant_id)
    try:
        yield
    finally:
        reset_tenant_context(token)


@lru_cache(maxsize=1)
def get_firestore_client():
    if FIRESTORE_PROJECT_ID:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)
    return firestore.Client()


def collection_name(name):
    prefix = FIRESTORE_COLLECTION_PREFIX.strip("_")
    return f"{prefix}_{name}" if prefix else name


def _flat_collection(name):
    """Coleção flat sem aplicar tenant context. Uso interno e GLOBAL_COLLECTIONS."""
    return get_firestore_client().collection(collection_name(name))


def _flat_document(name, doc_id):
    return _flat_collection(name).document(str(doc_id))


def collection(name):
    """Retorna referencia a colecao, aplicando tenant context se ativo.

    - Se name esta em _GLOBAL_COLLECTIONS: sempre flat (counters,
      phone_routing, tenants root).
    - Se tenant context setado: roteia para tenants/{tid}/<name>.
    - Se tenant context vazio: flat (compatibilidade pre-migration).
    """
    if name in _GLOBAL_COLLECTIONS:
        return _flat_collection(name)
    tid = _current_tenant_id.get()
    if tid:
        return _tenant_subcollection_raw(tid, name)
    return _flat_collection(name)


def document(name, doc_id):
    """Retorna referencia a documento. Mesma logica de collection()."""
    if name in _GLOBAL_COLLECTIONS:
        return _flat_document(name, doc_id)
    tid = _current_tenant_id.get()
    if tid:
        return _tenant_subcollection_raw(tid, name).document(str(doc_id))
    return _flat_document(name, doc_id)


def _tenant_subcollection_raw(tenant_id, name):
    """Helper interno: subcolecao do tenant sem checar contextvar (evita recursao)."""
    return (
        get_firestore_client()
        .collection(collection_name("tenants"))
        .document(str(tenant_id))
        .collection(name)
    )


# ---------------------------------------------------------------------------
# Multi-tenant helpers (Fase 2)
# ---------------------------------------------------------------------------
#
# Estrutura:
#   <prefix>_tenants/{tenant_id}                       <- doc do tenant
#   <prefix>_tenants/{tenant_id}/<sub_name>/{doc_id}    <- subcolecoes
#
# Onde <prefix> e o FIRESTORE_COLLECTION_PREFIX (castro_crm em prod,
# castro_crm_staging em staging). Garante isolamento entre ambientes
# dentro do mesmo projeto Firebase.
#
# As funcoes existentes collection()/document() continuam atendendo
# colecoes globais (fora de tenants/), como _meta, phone_routing e a
# propria coleção root 'tenants'.

def tenant_collection(tenant_id, name):
    """Retorna referencia a uma subcolecao dentro de tenants/{tenant_id}/.

    Exemplo: tenant_collection('hubloc', 'wa_contacts')
    -> <prefix>_tenants/hubloc/wa_contacts
    """
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    client = get_firestore_client()
    return (
        client.collection(collection_name("tenants"))
        .document(str(tenant_id))
        .collection(name)
    )


def tenant_document(tenant_id, name, doc_id):
    """Retorna referencia a um documento dentro de uma subcolecao do tenant.

    Exemplo: tenant_document('hubloc', 'wa_contacts', 42)
    -> <prefix>_tenants/hubloc/wa_contacts/42
    """
    return tenant_collection(tenant_id, name).document(str(doc_id))


def tenant_doc_ref(tenant_id):
    """Retorna referencia ao DOC do proprio tenant (nao subcolecao).

    Exemplo: tenant_doc_ref('hubloc')
    -> <prefix>_tenants/hubloc
    """
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    return get_firestore_client().collection(collection_name("tenants")).document(str(tenant_id))


def global_collection(name):
    """Colecao FLAT, sempre fora de tenants/ — ignora tenant context.

    Usado explicitamente para colecoes nao escopadas a um tenant
    (phone_routing, _meta, tenants root listing). Aplica o prefix do
    ambiente mas NUNCA a subcolecao do tenant.
    """
    return _flat_collection(name)


def global_document(name, doc_id):
    return _flat_document(name, doc_id)


def utcnow():
    return datetime.now(timezone.utc)


def normalize_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalize_record(record):
    if not record:
        return None
    return {key: normalize_value(value) for key, value in dict(record).items()}


@firestore.transactional
def _next_sequence_transaction(transaction, counters_ref, counter_name):
    snapshot = counters_ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    next_value = int(data.get(counter_name, 0)) + 1
    transaction.set(counters_ref, {counter_name: next_value}, merge=True)
    return next_value


def next_sequence(counter_name, tenant_id=None):
    """Atomico auto-increment.

    Resolucao do tenant:
      1. Se tenant_id explicito for passado, usa ele.
      2. Se nao, le do contextvar atual (set_tenant_context).
      3. Se ambos vazios, cai em counters globais flat (compat pre-migration).

    Counters per-tenant ficam em tenants/{tid}/_meta/counters; globais em
    <prefix>__meta/counters.
    """
    client = get_firestore_client()
    if tenant_id is None:
        tenant_id = _current_tenant_id.get()
    if tenant_id:
        counters_ref = _tenant_subcollection_raw(tenant_id, "_meta").document("counters")
    else:
        counters_ref = _flat_document("_meta", "counters")
    return _next_sequence_transaction(client.transaction(), counters_ref, counter_name)
```

## google_chat.py

```python
# -*- coding: utf-8 -*-

"""
Servico de integracao com Google Chat API.
Gerencia autenticacao via service account, envio de mensagens e download de midia.
"""

import logging
from functools import lru_cache

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import GOOGLE_CHAT_SERVICE_ACCOUNT_FILE, FEATURE_GOOGLE_CHAT

logger = logging.getLogger("castro_crm.google_chat")

SCOPES = [
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/chat.memberships.readonly",
]


@lru_cache(maxsize=1)
def _get_credentials():
    """Cria credenciais da service account. No Cloud Run usa ADC se arquivo nao configurado."""
    if GOOGLE_CHAT_SERVICE_ACCOUNT_FILE:
        return service_account.Credentials.from_service_account_file(
            GOOGLE_CHAT_SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )
    import google.auth
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


@lru_cache(maxsize=1)
def get_chat_service():
    """Retorna cliente autenticado da Google Chat API."""
    if not FEATURE_GOOGLE_CHAT:
        return None
    try:
        creds = _get_credentials()
        return build("chat", "v1", credentials=creds)
    except Exception as exc:
        logger.error("Falha ao inicializar Google Chat API: %s", exc, exc_info=True)
        return None


def list_spaces():
    """Lista spaces (salas) que o Chat App participa."""
    service = get_chat_service()
    if not service:
        return []
    try:
        result = service.spaces().list().execute()
        spaces = result.get("spaces", [])
        return [
            {
                "space_id": s["name"],
                "display_name": s.get("displayName", s["name"]),
                "type": s.get("spaceType", ""),
                "single_user_bot_dm": s.get("singleUserBotDm", False),
            }
            for s in spaces
        ]
    except Exception as exc:
        logger.error("Erro ao listar spaces: %s", exc, exc_info=True)
        return []


def get_space_members(space_id):
    """Lista membros de um space."""
    service = get_chat_service()
    if not service:
        return []
    try:
        result = service.spaces().members().list(parent=space_id).execute()
        members = result.get("memberships", [])
        return [
            {
                "name": m["name"],
                "member_type": m.get("member", {}).get("type", ""),
                "display_name": m.get("member", {}).get("displayName", ""),
                "email": m.get("member", {}).get("domainId", ""),
            }
            for m in members
        ]
    except Exception as exc:
        logger.error("Erro ao listar membros do space %s: %s", space_id, exc, exc_info=True)
        return []


def send_text_message(space_id, text):
    """Envia mensagem de texto para um space."""
    service = get_chat_service()
    if not service:
        return None
    try:
        result = service.spaces().messages().create(
            parent=space_id,
            body={"text": text},
        ).execute()
        logger.info("[GC OUT] Mensagem enviada para %s | id=%s", space_id, result.get("name", ""))
        return {
            "gchat_message_id": result.get("name", ""),
            "text": result.get("text", ""),
            "sender": result.get("sender", {}).get("displayName", ""),
            "create_time": result.get("createTime", ""),
        }
    except Exception as exc:
        logger.error("Erro ao enviar mensagem para %s: %s", space_id, exc, exc_info=True)
        return None


def download_attachment(resource_name):
    """Baixa anexo (audio, imagem, etc) do Google Chat usando resourceName.

    O Google Chat nao envia o binario direto no webhook — envia um resourceName
    que deve ser usado com media.download para obter o conteudo.
    """
    service = get_chat_service()
    if not service:
        return None
    try:
        result = service.media().download(resourceName=resource_name).execute()
        return result
    except Exception as exc:
        logger.error("Erro ao baixar anexo %s: %s", resource_name, exc, exc_info=True)
        return None


def get_message(message_name):
    """Busca uma mensagem especifica pelo name (spaces/X/messages/Y)."""
    service = get_chat_service()
    if not service:
        return None
    try:
        return service.spaces().messages().get(name=message_name).execute()
    except Exception as exc:
        logger.error("Erro ao buscar mensagem %s: %s", message_name, exc, exc_info=True)
        return None
```

## init_db.py

```python
# -*- coding: utf-8 -*-

from bootstrap_data import DEFAULT_DEPARTMENTS, ensure_default_departments
from config import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_DISPLAY_NAME,
    BOOTSTRAP_ADMIN_DEPARTMENT,
)
from database import (
    create_department,
    get_user_by_email,
    init_database,
    upsert_firebase_user,
)

def seed_departments():
    return ensure_default_departments(
        create_department,
        emit=lambda department, department_id: print(f"  Setor '{department['name']}' (id={department_id})"),
    )


def seed_bootstrap_admin(dept_map):
    department_name = BOOTSTRAP_ADMIN_DEPARTMENT or "Geral"
    department_id = dept_map.get(department_name)
    if department_id is None:
        department_id = create_department(
            department_name,
            "Setor criado automaticamente pelo bootstrap",
        )
        dept_map[department_name] = department_id
        print(f"  Setor '{department_name}' criado automaticamente (id={department_id})")

    display_name = BOOTSTRAP_ADMIN_DISPLAY_NAME or "Administrador"
    email = BOOTSTRAP_ADMIN_EMAIL.strip().lower()
    if not email:
        print(
            "\nBootstrap admin Firebase nao configurado. "
            "Defina BOOTSTRAP_ADMIN_EMAIL para provisionar o primeiro admin."
        )
        return

    existing = get_user_by_email(email)
    user = upsert_firebase_user("", email, display_name, "admin", department_id)
    if user and existing:
        print(f"  '{email}' ja existe. Perfil bootstrap Firebase sincronizado como admin.")
    elif user:
        print(f"  '{email}' provisionado para login com Google (cargo: admin)")


def seed():
    init_database()
    dept_map = seed_departments()
    seed_bootstrap_admin(dept_map)
    print("\nSetores: " + ", ".join(department["name"] for department in DEFAULT_DEPARTMENTS))


if __name__ == "__main__":
    seed()
```

## main.py

```python
# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import (
    FastAPI, Request,
    HTTPException, Depends, Query, UploadFile, File, Form,
)
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from bootstrap_data import ensure_default_departments
from config import (
    HOST, PORT, MAX_MESSAGE_LENGTH, BASE_DIR, LOG_FILE, LOG_LEVEL, LOG_TO_FILE,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS, FEATURE_GOOGLE_CHAT,
    WHATSAPP_VERIFY_TOKEN, WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID, GRAPH_API_BASE, GRAPH_API_VERSION,
    AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS,
    BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_DISPLAY_NAME, BOOTSTRAP_ADMIN_DEPARTMENT,
    CORS_ORIGINS, GCS_MEDIA_BUCKET, IS_CLOUD_RUN,
    MEDIA_STORAGE_BACKEND, REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    CHAT_DELIVERY_MODE, POLLING_INTERVAL_MS, AUTH_MODE,
    FIRESTORE_PROJECT_ID, FIREBASE_STORAGE_BUCKET,
    FIREBASE_WEB_API_KEY, FIREBASE_WEB_AUTH_DOMAIN, FIREBASE_WEB_APP_ID,
    FIREBASE_WEB_MESSAGING_SENDER_ID, FIREBASE_WEB_MEASUREMENT_ID,
    ALLOWED_FIREBASE_EMAIL_DOMAIN,
    STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS,
    META_APP_ID, META_APP_SECRET, EMBEDDED_SIGNUP_CONFIG_ID,
)
from database import (
    init_database, get_user_by_id, get_all_users,
    get_all_wa_contacts, get_wa_conversation,
    mark_wa_conversation_read, mark_wa_conversation_read_by_id,
    save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    get_department_by_id, update_department, deactivate_department,
    assign_wa_contact, assign_wa_conversation, get_transfer_history,
    return_contact_to_bot, get_contacts_by_assigned_user,
    update_user_avatar, get_user_avatar,
    update_user, deactivate_user,
    upsert_firebase_user, get_user_by_email,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message, set_attendance_protocol,
    get_wa_message_by_id, update_wa_message_transcription,
    create_manual_wa_contact, update_wa_contact_declared_name,
    mark_message_corrected,
    get_wa_conversation_by_id, upsert_wa_conversation,
    get_system_settings, save_system_settings,
    get_user_settings, save_user_settings,
    get_all_gc_conversations, get_gc_messages, save_gc_message,
    mark_gc_conversation_read, upsert_gc_conversation,
    get_audit_metrics, get_all_ratings,
    get_monthly_usage, get_usage_history,
    get_assume_counter, decrement_assume_counter, increment_assume_counter,
    mark_contact_pending_response, clear_contact_pending_response,
    reset_assume_counter,
)
from channel_service import (
    get_all_active_channels, get_channels_for_user,
    create_channel, update_channel, deactivate_channel,
    get_channel_by_id_from_db,
    CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE,
)
from auth import authenticate_firebase_token
from firestore_common import (
    collection_name, document as fs_document, utcnow as fs_utcnow,
    set_tenant_context, tenant_context, get_tenant_context,
)
from pii_redaction import redact_phone, redact_name
from tenant_service import (
    create_tenant, get_tenant, tenant_exists, lookup_phone_routing,
)
from webhook import process_webhook_payload, validate_signature
from webhook_google_chat import validate_google_chat_token, process_google_chat_event
from media import (
    ensure_media_dir, upload_media_to_whatsapp, send_media_message,
    save_upload_media, convert_audio_to_ogg_opus,
    save_avatar_media, delete_media, get_media_asset,
    _write_media_bytes,
)

# -- Logging --

log_handlers = [logging.StreamHandler()]
if LOG_TO_FILE and LOG_FILE:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log_handlers.insert(0, logging.FileHandler(LOG_FILE, encoding="utf-8"))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=log_handlers,
)
logger = logging.getLogger("castro_crm.main")

# -- App --

FRONTEND_DIST_DIR = os.path.join(BASE_DIR, "frontend_dist")
FRONTEND_ASSETS_DIR = os.path.join(FRONTEND_DIST_DIR, "assets")
FRONTEND_INDEX_FILE = os.path.join(FRONTEND_DIST_DIR, "index.html")

app = FastAPI(
    title="Castro Intelligence CRM",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# Middleware HTTP que extrai tenant_id do JWT ANTES do endpoint e seta o
# contextvar no asyncio task correto. Necessario porque get_current_user
# eh sync (def) e roda em threadpool — set_tenant_context dentro dele nao
# persiste pro endpoint async no main thread.
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    from firestore_common import set_tenant_context, reset_tenant_context
    from firebase_admin_client import verify_firebase_id_token

    auth_header = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    tid = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            decoded = verify_firebase_id_token(token)
            tid = decoded.get("tenant_id")
            # Cache decoded no request.state pro get_current_user reutilizar
            request.state.firebase_decoded = decoded
        except Exception:
            # Auth real acontece em get_current_user; aqui so detecta
            # tenant pra setar context cedo.
            pass
    # Fallback: usuarios pre-Fase 2 sem custom_claim ainda — assume tenant default.
    if not tid and auth_header:
        tid = "hubloc"

    if tid:
        ctx_token = set_tenant_context(tid)
        try:
            return await call_next(request)
        finally:
            reset_tenant_context(ctx_token)
    return await call_next(request)


if os.path.isdir(FRONTEND_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_DIR), name="frontend-assets")

class WaSendRequest(BaseModel):
    # Fase 2C: conversation_id e o canonico (identifica thread channel+wa_id).
    # contact_id continua aceito enquanto o frontend nao migrou todas as views
    # — backend resolve para (conversation, contact) via _resolve_send_target.
    conversation_id: str | None = None
    contact_id: int | None = None
    content: str
    reply_to_message_id: int | None = None
    reply_to_preview: str = ""
    reply_to_sender_name: str = ""

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v

    @field_validator("reply_to_preview", "reply_to_sender_name")
    @classmethod
    def trim_reply_fields(cls, v):
        return v.strip()


class WaSendLocationRequest(BaseModel):
    conversation_id: str | None = None
    contact_id: int | None = None
    latitude: float
    longitude: float
    name: str = ""
    address: str = ""
    reply_to_message_id: int | None = None
    reply_to_preview: str = ""
    reply_to_sender_name: str = ""

    @field_validator("reply_to_preview", "reply_to_sender_name")
    @classmethod
    def trim_reply_fields(cls, v):
        return v.strip()


# -- Dependencias --

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
    ip = request.client.host if request.client else "unknown"
    result = authenticate_firebase_token(token, ip)
    if not result["success"]:
        raise HTTPException(status_code=result.get("status_code", 401), detail=result["error"])
    return result["user"]


# -- Validacao de imagem --

AVATAR_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",
}


def _wa_target(wa_id):
    # Para respostas, use exatamente o identificador telefonico recebido/salvo no contato.
    # Inserir digitos extras aqui faz a Meta rejeitar o envio com HTTP 400.
    return "".join(ch for ch in str(wa_id or "").strip() if ch.isdigit())


def _fallback_reply_preview(message: dict) -> str:
    content = str(message.get("content") or "").strip()
    if content:
        return content

    transcription = str(message.get("transcription") or "").strip()
    if transcription:
        return transcription

    filename = str(message.get("filename") or "").strip()
    msg_type = str(message.get("msg_type") or "").strip().lower()
    labels = {
        "audio": "Audio",
        "document": "Documento",
        "gif": "Video",
        "image": "Imagem",
        "location": "Localizacao",
        "sticker": "Figurinha",
        "template": "Template",
        "video": "Video",
    }
    if filename and msg_type in labels:
        return f"{labels[msg_type]}: {filename}"
    return labels.get(msg_type, "Mensagem")


def _fallback_reply_sender(message: dict) -> str:
    direction = str(message.get("direction") or "").strip().lower()
    if direction == "inbound":
        return "Cliente"
    if direction == "system":
        return "Sistema"
    operator_id = message.get("operator_id")
    operator = get_user_by_id(operator_id) if operator_id else None
    return str((operator or {}).get("display_name") or "Equipe")


def _build_reply_fields(contact_id: int, reply_to_message_id: int | None, reply_to_preview: str = "", reply_to_sender_name: str = "") -> dict:
    if reply_to_message_id is None:
        return {}

    reply_message = get_wa_message_by_id(reply_to_message_id)
    if not reply_message or int(reply_message.get("contact_id") or 0) != int(contact_id):
        raise HTTPException(status_code=400, detail="Mensagem de resposta invalida para este contato")

    preview = (reply_to_preview or _fallback_reply_preview(reply_message)).strip()
    sender_name = (reply_to_sender_name or _fallback_reply_sender(reply_message)).strip()
    return {
        "reply_to_message_id": int(reply_message.get("id") or reply_to_message_id),
        "reply_to_preview": preview[:280],
        "reply_to_sender_name": sender_name[:80],
    }


def _build_reply_context(contact_id: int, reply_to_message_id: int | None) -> dict:
    if reply_to_message_id is None:
        return {}
    reply_message = get_wa_message_by_id(reply_to_message_id)
    if not reply_message or int(reply_message.get("contact_id") or 0) != int(contact_id):
        raise HTTPException(status_code=400, detail="Mensagem de resposta invalida para este contato")
    wa_message_id = str(reply_message.get("wa_message_id") or "").strip()
    if not wa_message_id:
        return {}
    return {"context": {"message_id": wa_message_id}}


def _validate_image_bytes(content):
    for magic, mime in AVATAR_MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            return mime
    return None


def _save_avatar(content, prefix, entity_id):
    real_mime = _validate_image_bytes(content)
    if not real_mime or real_mime not in AVATAR_ALLOWED_MIME:
        return None
    return save_avatar_media(content, prefix, entity_id, real_mime)


def _remove_old_avatar(old_path):
    delete_media(old_path)


def _frontend_build_available():
    return os.path.isfile(FRONTEND_INDEX_FILE)


def _serve_frontend_app():
    if not os.path.isfile(FRONTEND_INDEX_FILE):
        return HTMLResponse(
            content="<h1>Frontend React nao compilado. Execute: cd frontend && npm run build</h1>",
            status_code=503,
        )
    return FileResponse(FRONTEND_INDEX_FILE)


def bootstrap_admin_user():
    if not BOOTSTRAP_ADMIN_EMAIL:
        logger.info("Bootstrap admin Firebase nao configurado")
        return

    department_id = create_department(
        BOOTSTRAP_ADMIN_DEPARTMENT,
        "Setor criado automaticamente no primeiro deploy",
    )
    user = upsert_firebase_user(
        firebase_uid="",
        email=BOOTSTRAP_ADMIN_EMAIL,
        display_name=BOOTSTRAP_ADMIN_DISPLAY_NAME,
        role="admin",
        department_id=department_id,
    )
    if user:
        # Sincroniza custom_claim tenant_id no usuario Firebase para a
        # proxima sessao. O usuario precisa renovar o ID token (logout/login
        # ou getIdToken(true)) para o claim aparecer.
        firebase_uid = user.get("firebase_uid", "")
        tenant_id = get_tenant_context() or "hubloc"
        if firebase_uid:
            try:
                from firebase_admin_client import set_tenant_claims
                set_tenant_claims(firebase_uid, tenant_id, role="admin")
            except Exception as exc:
                logger.warning("Falha ao setar custom_claim tenant_id no admin: %s", exc)
        logger.info(
            "Bootstrap admin Firebase sincronizado | email=%s tenant_id=%s",
            redact_name(BOOTSTRAP_ADMIN_EMAIL), tenant_id,
        )
    else:
        logger.warning(
            "Falha ao sincronizar bootstrap admin Firebase | email=%s",
            redact_name(BOOTSTRAP_ADMIN_EMAIL),
        )


def bootstrap_departments():
    dept_map = ensure_default_departments(create_department)
    logger.info("Departamentos padrao sincronizados | total=%d", len(dept_map))


def bootstrap_default_tenant():
    """Cria o tenant 'hubloc' (default single-tenant) se ainda nao existir.

    Esse tenant e usado durante a transicao multi-tenant: todos os
    usuarios e dados que nao tem tenant_id explicito sao roteados para
    ele. Quando UI super-admin de criacao de tenants estiver pronta
    (Roadmap pos-Fase 2), tenants adicionais sao criados via interface.
    """
    if tenant_exists("hubloc"):
        logger.info("Tenant default 'hubloc' ja existe")
        return
    create_tenant(
        tenant_id="hubloc",
        name="Hubloc Imobiliaria",
        plan="professional",
        cnpj="",
    )
    logger.info("Tenant default 'hubloc' criado")


def validate_runtime_config():
    if not IS_CLOUD_RUN:
        return

    if MEDIA_STORAGE_BACKEND == "gcs":
        if not GCS_MEDIA_BUCKET:
            raise RuntimeError("Cloud Run com GCS requer GCS_MEDIA_BUCKET configurado")
    elif MEDIA_STORAGE_BACKEND != "firestore":
        raise RuntimeError("Cloud Run requer MEDIA_STORAGE_BACKEND=gcs ou firestore")

    if REQUIRE_WEBHOOK_SIGNATURE and not WHATSAPP_APP_SECRET:
        raise RuntimeError("Cloud Run requer WHATSAPP_APP_SECRET quando REQUIRE_WEBHOOK_SIGNATURE=true")

    if not WHATSAPP_VERIFY_TOKEN:
        raise RuntimeError("Cloud Run requer WHATSAPP_VERIFY_TOKEN configurado")


# -- Startup --

@app.on_event("startup")
async def startup():
    validate_runtime_config()
    init_database()
    # Cria o tenant default antes de qualquer bootstrap escopado.
    bootstrap_default_tenant()
    # Departamentos e admin do tenant default rodam DENTRO do contexto
    # do tenant — assim ficam em tenants/hubloc/{departments,users,...}.
    with tenant_context("hubloc"):
        bootstrap_departments()
        bootstrap_admin_user()
    ensure_media_dir()
    # Channel ainda fica em colecao flat (compartilhado por enquanto).
    # Migrar para tenants/{tid}/channels e parte da Fase 2 (sub-fase
    # futura). Por enquanto, todos os tenants compartilham os canais
    # ativos no Cloud Run — o webhook resolve o tenant via tenant_id
    # do channel ou via phone_routing global.
    from channel_service import bootstrap_default_channel
    bootstrap_default_channel()
    if FEATURE_AUDIO_TRANSCRIPTION:
        from transcription_service import init_speech_client
        if init_speech_client():
            logger.info("Transcricao de audio habilitada (Faster Whisper)")
        else:
            logger.warning("Transcricao de audio desabilitada (Faster Whisper falhou)")
    logger.info("CRM iniciado | host=%s port=%d", HOST, PORT)
    if WHATSAPP_TOKEN:
        if WHATSAPP_WABA_ID:
            logger.info(
                "WABA configurado | waba_id=%s phone_id=%s",
                WHATSAPP_WABA_ID,
                WHATSAPP_PHONE_NUMBER_ID,
            )
        else:
            logger.info("WABA configurado | phone_id=%s", WHATSAPP_PHONE_NUMBER_ID)
    else:
        logger.warning("WHATSAPP_TOKEN nao definido - webhook ativo mas envio desabilitado")


# -- Paginas HTML --

@app.get("/", response_class=HTMLResponse)
async def index():
    return _serve_frontend_app()


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return _serve_frontend_app()


@app.get("/app", response_class=HTMLResponse)
async def app_shell():
    if not _frontend_build_available():
        raise HTTPException(status_code=503, detail="Frontend React nao buildado")
    return FileResponse(FRONTEND_INDEX_FILE)


# -- Servir midia --

@app.get("/media/{subdir}/{filename}")
async def serve_media(subdir: str, filename: str):
    safe_subdir = os.path.basename(subdir)
    safe_filename = os.path.basename(filename)
    asset = get_media_asset(f"/media/{safe_subdir}/{safe_filename}")
    if not asset:
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    if asset.get("file_path"):
        return FileResponse(asset["file_path"], media_type=asset.get("mime_type"))
    return Response(content=asset["content"], media_type=asset.get("mime_type"))


# -- Webhook WABA --

@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso")
        return PlainTextResponse(hub_challenge)
    # NAO logar o token recebido (LGPD/secret leakage). Indica apenas o
    # comprimento pra diferenciar "token vazio" de "token errado".
    logger.warning(
        "Falha na verificacao do webhook | mode=%s token_len=%s",
        hub_mode, len(hub_verify_token or ""),
    )
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_signature(body, signature):
        logger.warning("Assinatura invalida no webhook")
        return JSONResponse(status_code=403, content={"error": "Assinatura invalida"})
    payload = await request.json()
    await process_webhook_payload(payload, ws_notify_callback=broadcast_to_operators)
    return {"status": "ok"}


# -- API: Autenticacao --

@app.post("/api/login")
async def login_removed():
    raise HTTPException(
        status_code=410,
        detail="Login legado removido. Use Firebase Auth no frontend e envie o ID token nas chamadas da API.",
    )


@app.get("/api/session")
async def session_info(current_user: dict = Depends(get_current_user)):
    """Retorna dados da sessao do usuario autenticado.

    Inclui paths das colecoes Firestore SCOPADAS ao tenant atual — o
    frontend sobrescreve config.firestore.collections com esses paths
    para que snapshots em modo realtime leiam diretamente da subcolecao
    do tenant (tenants/{tenant_id}/<colecao>).
    """
    tenant_id = current_user.get("tenant_id") or "hubloc"
    tenants_root = collection_name("tenants")
    tenant_collections = {
        "departments": f"{tenants_root}/{tenant_id}/departments",
        "operator_profiles": f"{tenants_root}/{tenant_id}/operator_profiles",
        "wa_contacts": f"{tenants_root}/{tenant_id}/wa_contacts",
        "wa_messages": f"{tenants_root}/{tenant_id}/wa_messages",
        "wa_conversations": f"{tenants_root}/{tenant_id}/wa_conversations",
        "wa_transfer_log": f"{tenants_root}/{tenant_id}/wa_transfer_log",
        "gc_conversations": f"{tenants_root}/{tenant_id}/gc_conversations",
        "gc_messages": f"{tenants_root}/{tenant_id}/gc_messages",
    }
    return {
        "user": current_user,
        "auth_mode": AUTH_MODE,
        "tenant_id": tenant_id,
        "firestore_collections": tenant_collections,
    }


@app.get("/api/client-config")
async def client_config():
    return {
        "auth_mode": AUTH_MODE,
        "chat_delivery_mode": CHAT_DELIVERY_MODE,
        "polling_interval_ms": POLLING_INTERVAL_MS,
        "data_backend": "firestore",
        "media_storage_backend": MEDIA_STORAGE_BACKEND,
        "allowed_email_domain": ALLOWED_FIREBASE_EMAIL_DOMAIN,
        "firebase_web_config": {
            "apiKey": FIREBASE_WEB_API_KEY,
            "authDomain": FIREBASE_WEB_AUTH_DOMAIN,
            "projectId": FIRESTORE_PROJECT_ID,
            "storageBucket": FIREBASE_STORAGE_BUCKET,
            "appId": FIREBASE_WEB_APP_ID,
            "messagingSenderId": FIREBASE_WEB_MESSAGING_SENDER_ID,
            "measurementId": FIREBASE_WEB_MEASUREMENT_ID,
        },
        "feature_message_status": FEATURE_MESSAGE_STATUS,
        "feature_google_chat": FEATURE_GOOGLE_CHAT,
        "firestore": {
            "collections": {
                "departments": collection_name("departments"),
                "operator_profiles": collection_name("operator_profiles"),
                "wa_contacts": collection_name("wa_contacts"),
                "wa_messages": collection_name("wa_messages"),
                "wa_transfer_log": collection_name("wa_transfer_log"),
                "gc_conversations": collection_name("gc_conversations"),
                "gc_messages": collection_name("gc_messages"),
            },
            "snapshot_enabled": True,
        },
    }


# -- API: Avatar do operador --

@app.post("/api/profile/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    user_id = current_user["id"]
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido. Use JPEG, PNG ou WebP.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(get_user_avatar(user_id))
    path = _save_avatar(content, "avatar", user_id)
    if not path:
        raise HTTPException(status_code=400, detail="Conteudo do arquivo nao corresponde a uma imagem valida.")
    update_user_avatar(user_id, path)
    log_audit(user_id, "AVATAR_UPLOAD", f"Arquivo: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


@app.delete("/api/profile/avatar")
async def remove_avatar(current_user: dict = Depends(get_current_user)):
    _remove_old_avatar(get_user_avatar(current_user["id"]))
    update_user_avatar(current_user["id"], "")
    log_audit(current_user["id"], "AVATAR_REMOVE", "")
    return {"status": "ok"}


# -- API: Avatar do contato WhatsApp --

@app.post("/api/wa/contact/{contact_id}/avatar")
async def upload_contact_avatar(contact_id: int, request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(contact.get("contact_avatar_path", ""))
    path = _save_avatar(content, "contact", contact_id)
    if not path:
        raise HTTPException(status_code=400, detail="Arquivo invalido.")
    update_contact_avatar(contact_id, path)
    log_audit(current_user["id"], "CONTACT_AVATAR", f"Contato {contact_id}: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


# -- API: Admin - Gerenciar usuarios --

@app.post("/api/admin/users")
async def admin_create_user(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    body = await request.json()
    email = (body.get("email", "")).strip().lower()
    display_name = (body.get("display_name", "")).strip()
    department_id = body.get("department_id")
    role = body.get("role", "operador")
    if not email or not display_name:
        raise HTTPException(status_code=400, detail="Campos obrigatorios: email, display_name")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalido")
    if len(display_name) > 100:
        raise HTTPException(status_code=400, detail="Display name excede limite de caracteres")
    if role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    existing = get_user_by_email(email)
    if existing:
        raise HTTPException(status_code=409, detail="Usuario ja existe")
    user = upsert_firebase_user(
        firebase_uid="",
        email=email,
        display_name=display_name,
        role=role,
        department_id=department_id,
    )
    if not user:
        raise HTTPException(status_code=500, detail="Falha ao provisionar usuario Firebase")
    log_audit(current_user["id"], "USER_CREATE", f"{email} ({role})")
    return {"status": "ok", "user_id": user["id"]}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    body = await request.json()
    display_name = body.get("display_name")
    department_id = body.get("department_id")
    role = body.get("role")
    if role and role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    update_user(user_id, display_name=display_name, department_id=department_id, role=role)
    log_audit(current_user["id"], "USER_UPDATE", f"id={user_id}")
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def admin_deactivate_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Apenas admin pode desativar usuarios")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Nao pode desativar a si mesmo")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    deactivate_user(user_id)
    log_audit(current_user["id"], "USER_DEACTIVATE", f"id={user_id} ({target['display_name']})")
    return {"status": "ok"}


@app.get("/api/admin/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    return {"roles": ROLE_OPTIONS}


# -- API: Configuracoes do sistema --

@app.get("/api/settings/system")
async def get_settings_system(current_user: dict = Depends(get_current_user)):
    return get_system_settings()


@app.put("/api/settings/system")
async def update_settings_system(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode alterar configuracoes do sistema")
    body = await request.json()
    result = save_system_settings(body)
    log_audit(current_user["id"], "SYSTEM_SETTINGS_UPDATE", str(body))
    return result


@app.get("/api/settings/user")
async def get_settings_user(current_user: dict = Depends(get_current_user)):
    return get_user_settings(current_user["id"])


@app.put("/api/settings/user")
async def update_settings_user(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = save_user_settings(current_user["id"], body)
    log_audit(current_user["id"], "USER_SETTINGS_UPDATE", str(body))
    return result


ALARM_ALLOWED_MIME = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/webm", "audio/mp3"}
ALARM_MAX_SIZE_KB = 500


@app.post("/api/admin/upload-alarm-sound")
async def upload_alarm_sound(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("alarm"),
    current_user: dict = Depends(get_current_user),
):
    """Upload de som personalizado para notificacao ou alarme. Apenas admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    content = await file.read()
    if len(content) > ALARM_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo excede {ALARM_MAX_SIZE_KB}KB")
    mime = file.content_type or "audio/mpeg"
    if mime not in ALARM_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Tipo nao permitido: {mime}. Use MP3, WAV ou OGG.")
    filename = file.filename or "alarm.mp3"
    ext = os.path.splitext(filename)[1] or ".mp3"
    safe_kind = "alarm" if kind == "alarm" else "notification"
    dest_name = f"{safe_kind}_custom{ext}"
    path = _write_media_bytes(content, "sounds", dest_name, mime)
    settings = get_system_settings()
    field = "alarm_sound_path" if safe_kind == "alarm" else "notification_sound_path"
    settings[field] = path
    save_system_settings(settings)
    log_audit(current_user["id"], "UPLOAD_ALARM_SOUND", f"{safe_kind}: {filename}")
    return {"status": "ok", "path": path, "kind": safe_kind}


# -- API: WhatsApp --

@app.get("/api/wa/contacts")
async def wa_contacts(current_user: dict = Depends(get_current_user)):
    contacts = get_all_wa_contacts()
    for c in contacts:
        c["unread"] = int(c.get("unread_count", 0))
    return {"contacts": contacts}


@app.get("/api/wa/contacts/all")
async def wa_contacts_all(
    q: str | None = Query(default=None, description="Busca por nome ou telefone"),
    limit: int = Query(default=500, ge=1, le=2000),
    current_user: dict = Depends(get_current_user),
):
    """Lista TODOS os contatos do tenant — usado pelo modal de selecao
    (botao + da sidebar) que mostra tambem contatos da agenda telefonica
    sincronizada via smb_app_state_sync, nao so quem tem conversa ativa.

    Diferente de /api/wa/contacts (que usa orderBy('last_message_at')
    e exclui contatos sem mensagem), aqui retornamos ordenados
    alfabeticamente por display_name. Aceita filtro 'q' pra busca
    parcial em display_name, declared_name, whatsapp_profile_name e
    wa_id.
    """
    from firestore_common import collection as fs_coll
    rows = []
    for snap in fs_coll("wa_contacts").stream():
        d = snap.to_dict() or {}
        if int(d.get("is_archived", 0) or 0) != 0:
            continue
        rows.append(d)

    if q:
        needle = q.strip().lower()
        if needle:
            def _match(c):
                return any(
                    needle in str(c.get(field, "") or "").lower()
                    for field in ("display_name", "declared_name", "whatsapp_profile_name", "wa_id", "phone_formatted")
                )
            rows = [c for c in rows if _match(c)]

    rows.sort(key=lambda c: str(c.get("display_name", "") or "").lower())
    total = len(rows)
    rows = rows[:limit]
    return {"contacts": rows, "total": total, "returned": len(rows)}


@app.post("/api/wa/conversation/open")
async def wa_conversation_open(request: Request, current_user: dict = Depends(get_current_user)):
    """Abre (ou cria) a conversation pra um contato + canal especifico.

    Usado quando o operador clica num contato da agenda telefonica que
    ainda nao tem thread no CRM — precisamos materializar a conversation
    pra ela aparecer na sidebar e o operador conseguir mandar template
    ou esperar mensagem do cliente.

    Body: { contact_id: int, channel_id?: int }
    Retorna o conversation_id determinístico.
    """
    body = await request.json()
    contact_id = body.get("contact_id")
    if contact_id is None:
        raise HTTPException(status_code=400, detail="contact_id obrigatorio")
    contact = get_wa_contact(int(contact_id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    channel_id = body.get("channel_id") or contact.get("channel_id")
    if channel_id is None:
        raise HTTPException(
            status_code=400,
            detail="channel_id obrigatorio (contato sem canal associado)",
        )
    from database import upsert_wa_conversation
    wa_id = str(contact.get("wa_id") or "")
    if not wa_id:
        raise HTTPException(status_code=400, detail="Contato sem wa_id")
    conversation_id = upsert_wa_conversation(
        contact_id=int(contact_id),
        wa_id=wa_id,
        channel_id=int(channel_id),
        source_channel_type=str(contact.get("source_channel_type", "") or ""),
        phone_number_id=str(contact.get("phone_number_id", "") or ""),
        auto_assign_user_id=current_user["id"],
        direction_for_unread=None,
    )
    log_audit(
        current_user["id"],
        "WA_CONVERSATION_OPEN",
        f"contact_id={contact_id} channel_id={channel_id} conv_id={conversation_id}",
    )
    return {"conversation_id": conversation_id, "contact_id": int(contact_id), "channel_id": int(channel_id)}


@app.get("/api/wa/conversations")
async def wa_conversations(current_user: dict = Depends(get_current_user)):
    """Retorna lista de conversations enriquecidas (Fase 3 multi-canal).

    Cada conversation representa uma thread (channel_id + wa_id).
    O mesmo wa_id em mais de um canal aparece como entradas distintas,
    cada uma com seu proprio assigned_to/unread/last_message_at.
    Dados do cliente (nome, telefone formatado, notas, qualificacao,
    rating) sao mesclados via join in-memory com wa_contacts.
    """
    from firestore_common import collection as fs_coll
    from channel_service import get_channel
    convs_raw = []
    for snap in fs_coll("wa_conversations").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        convs_raw.append(data)

    # Cache de contatos por id (evita N queries)
    contacts_by_id = {}
    for c in get_all_wa_contacts():
        contacts_by_id[c["id"]] = c

    enriched = []
    for conv in convs_raw:
        contact = contacts_by_id.get(conv.get("contact_id"))
        if not contact:
            continue
        channel = get_channel(conv.get("channel_id")) if conv.get("channel_id") else None
        item = {
            **conv,
            "wa_id": contact.get("wa_id"),
            "display_name": contact.get("display_name"),
            "declared_name": contact.get("declared_name"),
            "phone_formatted": contact.get("phone_formatted"),
            "qualification": contact.get("qualification"),
            "notes": contact.get("notes"),
            "rating": contact.get("rating"),
            "is_archived": contact.get("is_archived", 0),
            "contact_avatar_path": contact.get("contact_avatar_path"),
            "attendance_protocol": contact.get("attendance_protocol"),
            "attendance_started_at": contact.get("attendance_started_at"),
            "channel_label": channel.get("label", "") if channel else "",
            "channel_type": channel.get("channel_type", "") if channel else "",
            "channel_phone_number": channel.get("display_phone_number", "") if channel else "",
            "unread": int(conv.get("unread_count", 0)),
        }
        enriched.append(item)

    # Ordena por last_message_at desc (similar a get_all_wa_contacts)
    def _ts(c):
        v = c.get("last_message_at")
        if not v:
            return ""
        return v if isinstance(v, str) else v.isoformat()
    enriched.sort(key=_ts, reverse=True)

    return {"conversations": enriched}


@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(
    contact_id: int,
    limit: int = Query(default=10, ge=1, le=200),
    conversation_id: str | None = Query(default=None, description="Filtra por thread especifica (canal+wa_id)"),
    current_user: dict = Depends(get_current_user),
):
    """Retorna mensagens de um contato.

    Comportamento Fase 2:
    - Se conversation_id e fornecido: filtra por aquela thread (canal+wa_id).
    - Se nao: retorna timeline cross-channel do contato (legado).
    """
    messages = get_wa_conversation(contact_id, limit=limit, conversation_id=conversation_id)
    return {"messages": messages}


@app.post("/api/wa/messages/{message_id}/transcribe")
async def wa_transcribe_message(message_id: int, current_user: dict = Depends(get_current_user)):
    from transcription_service import get_speech_client, transcribe_audio_bytes
    from media import get_media_asset

    speech_client = get_speech_client()
    if not speech_client:
        if FEATURE_AUDIO_TRANSCRIPTION:
            from transcription_service import init_speech_client
            speech_client = init_speech_client() and get_speech_client()
        if not speech_client:
            raise HTTPException(status_code=503, detail="Servico de transcricao nao disponivel. Verifique FEATURE_AUDIO_TRANSCRIPTION, dependencias e configuracao WHISPER_*.")

    msg = get_wa_message_by_id(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Mensagem nao encontrada")
    if msg.get("msg_type") != "audio":
        raise HTTPException(status_code=400, detail="Mensagem nao e do tipo audio")

    media_path = msg.get("media_path", "")
    if not media_path:
        raise HTTPException(status_code=400, detail="Mensagem sem arquivo de audio")

    asset = get_media_asset(media_path)
    if not asset:
        raise HTTPException(status_code=404, detail="Arquivo de audio nao encontrado no storage")

    if "content" in asset:
        audio_bytes = asset["content"]
    elif "file_path" in asset:
        with open(asset["file_path"], "rb") as fh:
            audio_bytes = fh.read()
    else:
        raise HTTPException(status_code=500, detail="Nao foi possivel ler os bytes do audio")

    mime = asset.get("mime_type") or msg.get("media_mime") or "audio/ogg"
    transcript = transcribe_audio_bytes(
        audio_bytes,
        media_mime=mime,
        language_code=STT_LANGUAGE_CODE,
        timeout_s=STT_TIMEOUT_SECONDS,
    )

    if not transcript:
        raise HTTPException(status_code=422, detail="Nao foi possivel transcrever o audio. Verifique qualidade ou idioma.")

    update_wa_message_transcription(message_id, transcript)
    log_audit(current_user["id"], "WA_TRANSCRIBE", f"msg_id={message_id}")
    return {"transcription": transcript}


# -- Helper: janela de 24h do WhatsApp --

_24H = timedelta(hours=24)


def _check_send_permission(contact: dict, current_user: dict):
    """LEGADO. Substituido por _check_conv_send_permission (atua na conversation).
    Mantido apenas como fallback caso algum codigo legado interno chame.
    """
    assigned = contact.get("assigned_to")
    if assigned and assigned != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    if not assigned and current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Assuma o atendimento antes de enviar mensagem")


def _check_24h_window(contact: dict):
    """Raises 403 if last inbound message is older than 24h (Meta free-form window)."""
    last_inbound = contact.get("last_inbound_at")
    if not last_inbound:
        raise HTTPException(
            status_code=403,
            detail="Janela de 24h expirada. O cliente nunca enviou mensagem. Use um template.",
        )
    if isinstance(last_inbound, str):
        last_inbound = datetime.fromisoformat(last_inbound.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if now - last_inbound > _24H:
        raise HTTPException(
            status_code=403,
            detail="Janela de 24h expirada. Use um template para reabrir a conversa.",
        )


def _maybe_refresh_coex_token(channel: dict | None) -> None:
    """Renova proativamente token coexistence se faltar <5min."""
    if not channel:
        return
    from channel_service import CHANNEL_TYPE_COEXISTENCE, refresh_coexistence_token

    if channel.get("channel_type") != CHANNEL_TYPE_COEXISTENCE:
        return
    expires_at_raw = channel.get("token_expires_at")
    if not expires_at_raw:
        return
    try:
        expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
            refresh_coexistence_token(int(channel["id"]))
    except (ValueError, TypeError):
        logger.warning(
            "Canal coexistence %s com token_expires_at invalido: %s",
            channel.get("id"), expires_at_raw,
        )


def _resolve_channel_creds_by_id(channel_id: int | None) -> tuple[str, str, str]:
    """Resolve credenciais (token, phone_id, base) a partir de um channel_id.
    Refresh proativo do token coexistence quando aplicavel."""
    from channel_service import get_channel, get_send_credentials

    if channel_id is not None:
        _maybe_refresh_coex_token(get_channel(channel_id))

    try:
        return get_send_credentials(channel_id)
    except ValueError:
        # Fallback para env vars legadas
        if WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
            return WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE
        raise HTTPException(status_code=503, detail="Nenhum canal WhatsApp configurado")


def _resolve_send_target(
    conversation_id: str | None,
    contact_id: int | None,
) -> tuple[dict, dict, dict | None]:
    """Resolve (conversation, contact, channel) para um endpoint de envio.

    Estrategia Fase 2C:
      - Se conversation_id: thread e canonica. Carrega conversation, contato
        derivado dela, canal pelo conversation.channel_id.
      - Se so contact_id (legado): carrega contato, deriva
        conversation_id deterministico via (contact.channel_id, contact.wa_id),
        upserta conversation se nao existir.

    Levanta HTTPException 400/404 quando algo estiver inconsistente.
    Channel pode ser None quando canal foi removido (envio cai em fallback).
    """
    from channel_service import get_channel
    from database import (
        get_wa_conversation_by_id, get_wa_contact, upsert_wa_conversation,
    )

    if conversation_id:
        conv = get_wa_conversation_by_id(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation nao encontrada")
        ctc = get_wa_contact(conv.get("contact_id"))
        if not ctc:
            raise HTTPException(status_code=404, detail="Contato da conversation nao encontrado")
        ch = get_channel(conv.get("channel_id")) if conv.get("channel_id") is not None else None
        return conv, ctc, ch

    if contact_id is None:
        raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")

    ctc = get_wa_contact(contact_id)
    if not ctc:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    ch_id = ctc.get("channel_id")
    ch = get_channel(ch_id) if ch_id is not None else None
    # Garante conversation: necessario pra audit + thread frontend
    derived_conv_id = upsert_wa_conversation(
        contact_id=ctc["id"],
        wa_id=ctc.get("wa_id", ""),
        channel_id=ch_id,
        source_channel_type=str(ctc.get("source_channel_type") or ""),
        phone_number_id=str(ctc.get("phone_number_id") or ""),
    )
    conv = get_wa_conversation_by_id(derived_conv_id) or {
        "id": derived_conv_id,
        "contact_id": ctc["id"],
        "wa_id": ctc.get("wa_id", ""),
        "channel_id": ch_id,
        "assigned_to": ctc.get("assigned_to"),
        "department_id": ctc.get("department_id"),
    }
    return conv, ctc, ch


def _check_conv_send_permission(conversation: dict, current_user: dict):
    """Permission check baseado na conversation (Fase 2C).

    Bloqueia envio se a thread esta atribuida a outro operador. Sem
    atribuicao, exige role admin/supervisor (mesma regra anterior, mas
    por thread em vez de por contato — admite que o mesmo cliente em
    canais diferentes seja atendido por gente diferente).
    """
    assigned = conversation.get("assigned_to")
    if assigned and assigned != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")
    if not assigned and current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Assuma o atendimento antes de enviar mensagem")


def _resolve_channel_creds(contact: dict) -> tuple[str, str, str]:
    """LEGADO. Resolve credenciais a partir do contato. Mantido para os
    poucos call-sites que ainda nao migraram para conversation_id (qualify
    rating template e similares onde a thread vem do contato direto).
    Novos endpoints devem usar _resolve_send_target + _resolve_channel_creds_by_id.
    """
    return _resolve_channel_creds_by_id(contact.get("channel_id"))


@app.post("/api/wa/send-location")
async def wa_send_location(body: WaSendLocationRequest, current_user: dict = Depends(get_current_user)):
    conv, contact, channel = _resolve_send_target(body.conversation_id, body.contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], body.reply_to_message_id)

    wa_id = contact["wa_id"]
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    location_obj: dict = {"latitude": body.latitude, "longitude": body.longitude}
    if body.name:
        location_obj["name"] = body.name
    if body.address:
        location_obj["address"] = body.address

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "location",
        "location": location_obj,
        **reply_context,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        content = f"{body.name} {body.address}".strip()
        save_wa_message(
            wa_message_id=wa_msg_id,
            contact_id=contact["id"],
            direction="outbound",
            msg_type="location",
            content=content,
            latitude=body.latitude,
            longitude=body.longitude,
            status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        log_audit(current_user["id"], "WA_SEND_LOCATION", f"Para {wa_id}: {body.latitude},{body.longitude}")
        return {"status": "sent", "wa_message_id": wa_msg_id}

    error_msg = result.get("error", {}).get("message", "Erro desconhecido")
    raise HTTPException(status_code=502, detail=error_msg)


def _maybe_credit_assume_counter(contact: dict, operator_id: int):
    """Incrementa o contador do operador se esta e a primeira resposta apos assumir."""
    if contact.get("assume_pending_response") and contact.get("assigned_to") == operator_id:
        clear_contact_pending_response(contact["id"])
        increment_assume_counter(operator_id)


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    conv, contact, channel = _resolve_send_target(body.conversation_id, body.contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], body.reply_to_message_id, body.reply_to_preview, body.reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], body.reply_to_message_id)

    wa_id = _wa_target(contact["wa_id"])
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": body.content}, **reply_context}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
            msg_type="text", content=body.content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            **reply_fields,
        )
        _maybe_credit_assume_counter(contact, current_user["id"])
        log_audit(current_user["id"], "WA_SEND", f"Para {wa_id}: {body.content[:80]}")
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        logger.warning("Falha ao enviar texto para %s | status=%s | erro=%s", redact_phone(wa_id), resp.status_code, error_msg)
        raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send-media")
async def wa_send_media(
    request: Request,
    conversation_id: str | None = Form(None),
    contact_id: int | None = Form(None),
    caption: str = Form(""), file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    current_user = get_current_user(request)
    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], reply_to_message_id)

    file_content = await file.read()
    if len(file_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede 16MB")

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    try:
        local_result = await save_upload_media(file_content, filename, mime_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    msg_type = local_result["msg_type"]

    media_id = await upload_media_to_whatsapp(file_content, mime_type, filename, token=token, phone_id=phone_id)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload para a Meta")

    send_result = await send_media_message(contact["wa_id"], media_id, msg_type, caption, reply_context.get("context", {}).get("message_id", ""), token=token, phone_id=phone_id)
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type=msg_type, content=caption, media_path=local_result["path"],
        media_mime=mime_type, media_id=media_id, filename=filename,
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        media_size_bytes=len(file_content),
        **reply_fields,
    )
    _maybe_credit_assume_counter(contact, current_user["id"])
    log_audit(current_user["id"], "WA_SEND_MEDIA", f"{msg_type} para {contact['wa_id']}: {filename}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": msg_type, "media_path": local_result["path"]}


@app.post("/api/wa/send-audio")
async def wa_send_audio(
    request: Request,
    conversation_id: str | None = Form(None),
    contact_id: int | None = Form(None),
    file: UploadFile = File(...),
    reply_to_message_id: int | None = Form(None),
    reply_to_preview: str = Form(""),
    reply_to_sender_name: str = Form(""),
):
    """Envia audio gravado pelo microfone para contato WhatsApp.
    Converte WebM/Opus do navegador para OGG/Opus via FFmpeg."""
    current_user = get_current_user(request)

    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_conv_send_permission(conv, current_user)
    _check_24h_window(contact)
    reply_fields = _build_reply_fields(contact["id"], reply_to_message_id, reply_to_preview, reply_to_sender_name)
    reply_context = _build_reply_context(contact["id"], reply_to_message_id)

    raw_content = await file.read()
    if len(raw_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio excede 16MB")

    original_mime = file.content_type or "audio/webm"

    # Converter WebM/Opus -> OGG/Opus (formato exigido pelo WhatsApp)
    converted = convert_audio_to_ogg_opus(raw_content, original_mime)
    if not converted:
        raise HTTPException(status_code=500, detail="Falha na conversao do audio. Verifique se o FFmpeg esta instalado.")

    # Salvar versao convertida localmente
    try:
        local_result = await save_upload_media(converted, "gravacao.ogg", "audio/ogg")
    except RuntimeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    # Upload do OGG convertido para a Meta
    media_id = await upload_media_to_whatsapp(converted, "audio/ogg", "audio.ogg", token=token, phone_id=phone_id)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload de audio para a Meta")

    # Enviar mensagem de audio
    send_result = await send_media_message(contact["wa_id"], media_id, "audio", reply_wa_message_id=reply_context.get("context", {}).get("message_id", ""), token=token, phone_id=phone_id)
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type="audio", content="", media_path=local_result["path"],
        media_mime="audio/ogg", media_id=media_id, filename="gravacao.ogg",
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        media_size_bytes=len(converted),
        **reply_fields,
    )
    _maybe_credit_assume_counter(contact, current_user["id"])
    log_audit(current_user["id"], "WA_SEND_AUDIO", f"Para {contact['wa_id']}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": "audio", "media_path": local_result["path"]}


class WaSendTemplateRequest(BaseModel):
    conversation_id: str | None = None
    contact_id: int | None = None
    template_name: str = "hello_world"
    language: str = "pt_BR"
    components: list[dict] | None = None  # [{type, sub_type?, index?, parameters: [{type:"text", text:"..."}]}]
    # Categoria Meta (marketing/utility/authentication). Best-effort
    # informada pelo frontend que ja conhece via /api/wa/templates.
    # Quando ausente, contabilizada em templates_sent.unknown.
    template_category: str | None = None


@app.post("/api/wa/send-template")
async def wa_send_template(
    body: WaSendTemplateRequest | None = None,
    contact_id: int | None = None,
    template_name: str = "hello_world",
    language: str = "pt_BR",
    current_user: dict = Depends(get_current_user),
):
    # Compat: aceita tanto body JSON quanto query params (legado).
    if body is not None:
        effective_conversation_id = body.conversation_id
        effective_contact_id = body.contact_id
        effective_template_name = body.template_name or template_name
        effective_language = body.language or language
        components = body.components or []
        effective_template_category = body.template_category
    else:
        if contact_id is None:
            raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")
        effective_conversation_id = None
        effective_contact_id = contact_id
        effective_template_name = template_name
        effective_language = language
        components = []
        effective_template_category = None

    conv, contact, channel = _resolve_send_target(effective_conversation_id, effective_contact_id)
    _check_conv_send_permission(conv, current_user)
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    template_payload: dict = {
        "name": effective_template_name,
        "language": {"code": effective_language},
    }
    if components:
        template_payload["components"] = components
    payload = {
        "messaging_product": "whatsapp",
        "to": _wa_target(contact["wa_id"]),
        "type": "template",
        "template": template_payload,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()
    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        # Renderiza preview do corpo para exibir no chat (substitui {{1}}..{{n}}).
        rendered_content = f"[template: {effective_template_name}]"
        try:
            body_params = []
            for comp in components:
                if comp.get("type") == "body":
                    body_params = [p.get("text", "") for p in comp.get("parameters", []) if p.get("type") == "text"]
                    break
            if body_params:
                rendered_content = f"[template: {effective_template_name}] " + " | ".join(body_params)
        except Exception:
            pass
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
            msg_type="template", content=rendered_content,
            status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
            channel_id=channel["id"] if channel else conv.get("channel_id"),
            conversation_id=conv["id"],
            sender_user_id=current_user["id"],
            channel_owner_user_id=(channel or {}).get("owner_user_id"),
            template_category=effective_template_category,
        )
        log_audit(current_user["id"], "WA_SEND_TEMPLATE", f"Para {contact['wa_id']} template={effective_template_name} lang={effective_language}")
        return {"status": "sent", "wa_message_id": wa_msg_id, "template_name": effective_template_name}
    else:
        # Fase 2.10: traduz erros Meta relacionados a billing para HTTP 402
        # com mensagem orientando o admin a configurar metodo de pagamento.
        err = (result or {}).get("error", {}) if isinstance(result, dict) else {}
        err_msg = str(err.get("message") or "Erro desconhecido")
        err_code = err.get("code")
        err_subcode = err.get("error_subcode")
        billing_signals = (
            err_code == 131009
            or err_subcode in (2494051, 2494052)
            or "not subscribed" in err_msg.lower()
            or "payment" in err_msg.lower()
        )
        if billing_signals:
            raise HTTPException(
                status_code=402,
                detail=(
                    "A WhatsApp Business Account ainda nao tem metodo de pagamento "
                    "configurado na Meta. Acesse business.facebook.com/wa/manage/billing/ "
                    "para adicionar e tente novamente em alguns minutos. "
                    f"(Meta: {err_msg} | code={err_code})"
                ),
            )
        raise HTTPException(status_code=502, detail=err_msg)


@app.get("/api/wa/templates")
async def wa_list_templates(
    channel_id: int | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Lista templates aprovados da WABA do canal (ou canal default)."""
    from channel_service import get_channel, get_default_channel, get_send_credentials

    channel = get_channel(channel_id) if channel_id is not None else get_default_channel()
    if channel is None:
        raise HTTPException(status_code=503, detail="Nenhum canal WhatsApp configurado")

    waba_id = str(channel.get("waba_id", "")).strip()
    if not waba_id:
        raise HTTPException(status_code=503, detail=f"Canal {channel.get('id')} sem waba_id")

    try:
        token, _phone_id, api_base = get_send_credentials(channel.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    url = f"{api_base}/{waba_id}/message_templates"
    params = {
        "fields": "name,language,category,status,components,id",
        "limit": 100,
    }
    headers = {"Authorization": f"Bearer {token}"}

    templates: list[dict] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        next_url: str | None = url
        next_params: dict | None = params
        while next_url:
            resp = await client.get(next_url, params=next_params, headers=headers)
            if resp.status_code >= 400:
                try:
                    err = resp.json().get("error", {}).get("message", resp.text[:300])
                except Exception:
                    err = resp.text[:300]
                raise HTTPException(status_code=502, detail=f"Meta retornou erro: {err}")
            data = resp.json()
            templates.extend(data.get("data", []) or [])
            paging = data.get("paging") or {}
            next_url = paging.get("next")
            next_params = None

    approved = [t for t in templates if str(t.get("status", "")).upper() == "APPROVED"]
    approved.sort(key=lambda t: (str(t.get("category", "")), str(t.get("name", ""))))
    return {
        "channel_id": channel.get("id"),
        "waba_id": waba_id,
        "total": len(templates),
        "approved_count": len(approved),
        "templates": approved,
    }


# -- API: Correcao de mensagem (Cenario C) --


class CorrectMessageRequest(BaseModel):
    message_id: int
    new_content: str

    @field_validator("new_content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Conteudo da correcao vazio")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


@app.post("/api/wa/correct-message")
async def correct_message(body: CorrectMessageRequest, current_user: dict = Depends(get_current_user)):
    """Envia uma nova mensagem corrigindo uma mensagem anterior.

    Marca a mensagem original como corrigida e envia a nova mensagem
    como reply da original, prefixada com indicador de correcao.
    """
    original = get_wa_message_by_id(body.message_id)
    if not original:
        raise HTTPException(status_code=404, detail="Mensagem original nao encontrada")
    if original.get("direction") != "outbound":
        raise HTTPException(status_code=400, detail="Apenas mensagens outbound podem ser corrigidas")
    if original.get("msg_type") != "text":
        raise HTTPException(status_code=400, detail="Apenas mensagens de texto podem ser corrigidas")
    if original.get("is_corrected"):
        raise HTTPException(status_code=400, detail="Mensagem ja foi corrigida")

    # Resolve thread original — preferimos conversation_id da mensagem
    # (denormalizado no save_wa_message) para nao confundir threads do
    # mesmo contato em canais distintos.
    conv, contact, channel = _resolve_send_target(
        original.get("conversation_id"),
        original.get("contact_id"),
    )
    token, phone_id, api_base = _resolve_channel_creds_by_id(
        channel["id"] if channel else conv.get("channel_id")
    )
    _check_24h_window(contact)

    # Enviar nova mensagem como reply da original
    wa_id = _wa_target(contact["wa_id"])
    url = f"{api_base}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    reply_context = {}
    orig_wa_id = original.get("wa_message_id", "")
    if orig_wa_id and not orig_wa_id.startswith("local_"):
        reply_context = {"context": {"message_id": orig_wa_id}}
    payload = {
        "messaging_product": "whatsapp", "to": wa_id, "type": "text",
        "text": {"body": body.new_content},
        **reply_context,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code != 200:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        raise HTTPException(status_code=502, detail=error_msg)

    wa_msg_id = result.get("messages", [{}])[0].get("id", "")
    original_preview = (original.get("content") or "")[:80]

    new_msg_id = save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact["id"], direction="outbound",
        msg_type="text", content=body.new_content, status="sent",
        timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
        conversation_id=conv["id"],
        sender_user_id=current_user["id"],
        channel_owner_user_id=(channel or {}).get("owner_user_id"),
        reply_to_message_id=body.message_id,
        reply_to_preview=original_preview,
        reply_to_sender_name=current_user.get("display_name", "Operador"),
    )

    # Marcar original como corrigida
    mark_message_corrected(body.message_id, new_msg_id)

    log_audit(current_user["id"], "WA_MESSAGE_CORRECT", f"Msg {body.message_id} corrigida por {new_msg_id}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "new_message_id": new_msg_id, "corrected_message_id": body.message_id}


# -- API: Contatos - Criacao manual e nome declarado --


class ManualContactRequest(BaseModel):
    declared_name: str
    phone: str
    channel_id: int | None = None

    @field_validator("declared_name")
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Nome e obrigatorio")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        v = "".join(ch for ch in v.strip() if ch.isdigit())
        if len(v) < 10:
            raise ValueError("Telefone invalido")
        return v


class DeclaredNameRequest(BaseModel):
    declared_name: str = ""

    @field_validator("declared_name")
    @classmethod
    def validate_name(cls, v):
        return v.strip()


@app.post("/api/wa/contact/manual")
async def create_contact_manual(body: ManualContactRequest, current_user: dict = Depends(get_current_user)):
    """Cria contato manualmente para iniciar conversa outbound via template."""
    wa_id = normalize_br_phone(body.phone)
    if not wa_id.startswith("55"):
        wa_id = f"55{wa_id}"

    # Resolver canal
    channel_id = body.channel_id
    if not channel_id:
        from channel_service import get_default_channel
        default_ch = get_default_channel()
        if not default_ch:
            raise HTTPException(status_code=400, detail="Nenhum canal WhatsApp disponivel")
        channel_id = default_ch["id"]

    allow_override = current_user.get("role") in ("admin", "supervisor")
    contact_id, error = create_manual_wa_contact(
        declared_name=body.declared_name,
        wa_id=wa_id,
        channel_id=channel_id,
        user_id=current_user["id"],
        allow_admin_override=allow_override,
    )
    if error:
        raise HTTPException(status_code=409, detail=error)

    contact = get_wa_contact(contact_id)
    # Conversation determinística criada por upsert_wa_conversation (Fase 3).
    conversation_id = f"{channel_id}__{wa_id}"
    log_audit(current_user["id"], "CONTACT_MANUAL_CREATE", f"Contato {contact_id}: {body.declared_name} ({wa_id})")
    return {"contact": contact, "conversation_id": conversation_id}


@app.put("/api/wa/contact/{contact_id}/declared-name")
async def update_declared_name(contact_id: int, body: DeclaredNameRequest, current_user: dict = Depends(get_current_user)):
    """Atualiza o nome declarado pelo operador."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    update_wa_contact_declared_name(contact_id, body.declared_name)
    log_audit(current_user["id"], "CONTACT_DECLARED_NAME", f"Contato {contact_id}: {body.declared_name}")
    updated = get_wa_contact(contact_id)
    return {"contact": updated}


# -- API: Contatos - Qualificacao e gerenciamento --

@app.put("/api/wa/contact/{contact_id}/qualify")
async def qualify_contact(contact_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    qualification = body.get("qualification", "")
    notes = body.get("notes")
    if qualification and qualification not in QUALIFICATION_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Qualificacao invalida. Opcoes: {', '.join(QUALIFICATION_OPTIONS)}")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    update_wa_contact_qualification(contact_id, qualification, notes)
    log_audit(current_user["id"], "CONTACT_QUALIFY", f"Contato {contact_id}: {qualification}")

    result = {"status": "ok"}

    # Ao marcar como convertido: gravar quem converteu e enviar template de avaliacao
    if qualification == "convertido":

        fs_document("wa_contacts", contact_id).set({
            "converted_by_user_id": current_user["id"],
            "rating_requested_at": fs_utcnow().isoformat(),
        }, merge=True)

        # Enviar template de avaliacao (mensagem visivel apenas para admin)
        try:
            token, phone_id, api_base = _resolve_channel_creds(contact)
            wa_id = _wa_target(contact["wa_id"])
            rating_url = f"{api_base}/{phone_id}/messages"
            rating_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            rating_payload = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "template",
                "template": {
                    "name": "rating_request",
                    "language": {"code": "pt_BR"},
                },
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(rating_url, json=rating_payload, headers=rating_headers)
                resp_data = resp.json()

            if resp.status_code == 200:
                wa_msg_id = resp_data.get("messages", [{}])[0].get("id", "")
                from channel_service import get_channel as _get_ch
                _rating_channel = _get_ch(contact.get("channel_id")) if contact.get("channel_id") is not None else None
                save_wa_message(
                    wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
                    msg_type="template", content="[avaliacao: responda de 1 a 10]",
                    status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
                    operator_id=current_user["id"],
                    sender_user_id=current_user["id"],
                    channel_id=contact.get("channel_id"),
                    channel_owner_user_id=(_rating_channel or {}).get("owner_user_id"),
                    is_rating_message=True, visibility="admin_only",
                )
                result["rating_sent"] = True
                logger.info("Rating template enviado para contato %d", contact_id)
            else:
                # Template pode nao existir ainda — nao bloqueia a conversao
                error_msg = resp_data.get("error", {}).get("message", "")
                logger.warning("Falha ao enviar rating template: %s", error_msg)
                result["rating_sent"] = False
                result["rating_error"] = error_msg
        except Exception as exc:
            logger.warning("Erro ao enviar rating template: %s", exc)
            result["rating_sent"] = False

    return result


@app.post("/api/wa/contact/{contact_id}/read")
async def mark_contact_read(contact_id: int, current_user: dict = Depends(get_current_user)):
    """LEGADO: marca todas as mensagens inbound do contato como lidas
    (cross-channel). Frontend novo deve usar
    POST /api/wa/conversation/{conversation_id}/read pra zerar unread
    apenas da thread aberta."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if int(contact.get("unread_count", 0) or 0) <= 0:
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read(contact_id)
    return {"status": "ok", "updated_count": updated_count}


@app.post("/api/wa/conversation/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """Zera unread_count da conversation e marca mensagens inbound da
    thread como lidas. Diferente do endpoint legado por contato, nao
    afeta unread de outras threads do mesmo cliente em canais distintos.
    """
    conv = get_wa_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")
    if int(conv.get("unread_count", 0) or 0) <= 0:
        return {"status": "ok", "updated_count": 0}
    updated_count = mark_wa_conversation_read_by_id(conversation_id)
    return {"status": "ok", "updated_count": updated_count}


@app.delete("/api/wa/contact/{contact_id}")
async def delete_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    archive_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_ARCHIVE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.post("/api/wa/contact/{contact_id}/restore")
async def restore_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    restore_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_RESTORE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.get("/api/wa/qualifications")
async def list_qualifications(current_user: dict = Depends(get_current_user)):
    return {"qualifications": QUALIFICATION_OPTIONS}


# -- API: Departamentos e Transferencia --

@app.get("/api/departments")
async def list_departments(current_user: dict = Depends(get_current_user)):
    return {"departments": get_all_departments()}


@app.post("/api/admin/departments")
async def create_department_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome obrigatorio")
    department_id = create_department(name, body.get("description", ""), bot_key=body.get("bot_key"))
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_CREATE", f"name={name} id={department_id}")
    return {"id": department_id, "name": name}


@app.put("/api/admin/departments/{department_id}")
async def update_department_endpoint(department_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    existing = get_department_by_id(department_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    body = await request.json()
    update_kwargs = dict(
        name=body.get("name"),
        description=body.get("description"),
        is_active=body.get("is_active"),
        sort_order=body.get("sort_order"),
    )
    if "bot_key" in body:
        update_kwargs["bot_key"] = body.get("bot_key")
    ok, error = update_department(department_id, **update_kwargs)
    if not ok:
        raise HTTPException(status_code=400, detail=error)
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_UPDATE", f"id={department_id} fields={list(body.keys())}")
    return {"ok": True}


@app.delete("/api/admin/departments/{department_id}")
async def delete_department_endpoint(department_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    existing = get_department_by_id(department_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Departamento nao encontrado")
    deactivate_department(department_id)
    from bot_service import invalidate_dept_cache
    invalidate_dept_cache()
    log_audit(current_user["id"], "DEPARTMENT_DELETE", f"id={department_id} name={existing.get('name')}")
    return {"ok": True}


# -- API: Canais WhatsApp --

@app.get("/api/admin/channels")
async def list_channels(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") in ("admin", "supervisor"):
        channels = get_all_active_channels()
    else:
        channels = get_channels_for_user(current_user["id"])
    # Nao expor access_token na resposta
    safe = []
    for ch in channels:
        c = dict(ch)
        c.pop("access_token", None)
        safe.append(c)
    return {"channels": safe}


@app.post("/api/admin/channels")
async def create_channel_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    channel_type = body.get("channel_type", CHANNEL_TYPE_COEXISTENCE)
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label obrigatorio")
    phone_number_id = (body.get("phone_number_id") or "").strip()
    if not phone_number_id:
        raise HTTPException(status_code=400, detail="phone_number_id obrigatorio")
    channel_id = create_channel(
        channel_type=channel_type,
        label=label,
        waba_id=body.get("waba_id", ""),
        phone_number_id=phone_number_id,
        display_phone_number=body.get("display_phone_number", ""),
        access_token=body.get("access_token", ""),
        owner_user_id=body.get("owner_user_id"),
        owner_firebase_uid=body.get("owner_firebase_uid", ""),
        default_department_id=body.get("default_department_id"),
        is_bot_enabled=body.get("is_bot_enabled", False),
    )
    log_audit(current_user["id"], "CHANNEL_CREATE", f"id={channel_id} type={channel_type} label={label}")
    return {"id": channel_id, "channel_type": channel_type, "label": label}


@app.put("/api/admin/channels/{channel_id}")
async def update_channel_endpoint(channel_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    existing = get_channel_by_id_from_db(channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    body = await request.json()
    ok = update_channel(channel_id, **body)
    if not ok:
        raise HTTPException(status_code=400, detail="Nenhum campo valido para atualizar")
    log_audit(current_user["id"], "CHANNEL_UPDATE", f"id={channel_id} fields={list(body.keys())}")
    return {"ok": True}


@app.delete("/api/admin/channels/{channel_id}")
async def delete_channel_endpoint(channel_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    existing = get_channel_by_id_from_db(channel_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    deactivate_channel(channel_id)
    log_audit(current_user["id"], "CHANNEL_DELETE", f"id={channel_id} label={existing.get('label')}")
    return {"ok": True}


@app.post("/api/admin/channels/{channel_id}/trigger-coex-sync")
async def trigger_coex_sync(
    channel_id: int,
    sync_type: str = Query(default="both", description="smb_app_state_sync|history|both"),
    current_user: dict = Depends(get_current_user),
):
    """Dispara sync de contatos e/ou history para canal coexistence.

    Doc Meta: POST /{phone_id}/smb_app_data com sync_type. Cada sync
    so pode ser disparado UMA VEZ por signup. Se ja foi disparado
    antes, Meta retorna erro. Janela de 24h apos signup — passou disso
    precisa desligar canal e refazer signup.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if sync_type not in ("smb_app_state_sync", "history", "both"):
        raise HTTPException(status_code=400, detail="sync_type deve ser smb_app_state_sync, history, ou both")
    channel = get_channel_by_id_from_db(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    if str(channel.get("channel_type", "")) != CHANNEL_TYPE_COEXISTENCE:
        raise HTTPException(status_code=400, detail="Apenas canais coexistence")
    phone_id = str(channel.get("phone_number_id", "")).strip()
    token = str(channel.get("access_token", "")).strip()
    if not phone_id or not token:
        raise HTTPException(status_code=400, detail="Canal sem phone_number_id ou access_token")

    types_to_sync = ["smb_app_state_sync", "history"] if sync_type == "both" else [sync_type]
    results: dict[str, dict] = {}
    smb_data_url = f"{GRAPH_API_BASE}/{phone_id}/smb_app_data"

    async with httpx.AsyncClient(timeout=30.0) as client:
        for stype in types_to_sync:
            try:
                resp = await client.post(
                    smb_data_url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"messaging_product": "whatsapp", "sync_type": stype},
                )
                if resp.status_code >= 400:
                    detail = _meta_error_detail(resp)
                    results[stype] = {"ok": False, "error": detail}
                    logger.error("trigger-coex-sync %s falhou: %s", stype, detail)
                else:
                    body = resp.json()
                    results[stype] = {"ok": True, "request_id": body.get("request_id", "")}
                    logger.info("trigger-coex-sync %s OK | request_id=%s", stype, body.get("request_id", ""))
            except httpx.RequestError as exc:
                results[stype] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                logger.warning("trigger-coex-sync %s erro de rede: %s", stype, exc)

    log_audit(
        current_user["id"],
        "TRIGGER_COEX_SYNC",
        f"channel_id={channel_id} types={types_to_sync} results={results}",
    )
    return {"channel_id": channel_id, "results": results}


# -- API: Pending webhook events (eventos da Meta sem canal resolvido) --

@app.get("/api/admin/pending-webhook-events")
async def list_pending_webhook_events(
    status: str | None = Query(default=None, description="pending|resolved|failed"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Lista eventos da Meta que nao puderam ser processados imediatamente
    (canal nao indexado ainda durante onboarding, phone_id sem canal,
    excecao no processamento). Garantia de zero perda — operador retenta
    apos o canal estar disponivel."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    from pending_events import list_pending_events
    events = list_pending_events(status=status, limit=limit)
    return {"events": events, "count": len(events)}


@app.post("/api/admin/pending-webhook-events/{event_id}/retry")
async def retry_pending_webhook_event(event_id: int, current_user: dict = Depends(get_current_user)):
    """Re-roda process_webhook_payload com o payload original. Idempotente
    via wa_message_id (save_wa_message detecta duplicata)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    from pending_events import get_pending_event, mark_event_attempt
    event = get_pending_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    if event.get("status") == "resolved":
        return {"status": "already_resolved", "id": event_id}
    payload = event.get("payload") or {}
    if not payload:
        raise HTTPException(status_code=400, detail="Evento sem payload")
    try:
        await process_webhook_payload(payload, ws_notify_callback=broadcast_to_operators)
        mark_event_attempt(event_id, success=True)
        log_audit(current_user["id"], "PENDING_EVENT_RETRY", f"id={event_id} ok")
        return {"status": "ok", "id": event_id}
    except Exception as exc:
        mark_event_attempt(event_id, success=False, error=f"{type(exc).__name__}: {exc}")
        log_audit(current_user["id"], "PENDING_EVENT_RETRY", f"id={event_id} err={type(exc).__name__}")
        raise HTTPException(status_code=502, detail=f"Falha ao reprocessar: {exc}")


@app.post("/api/admin/pending-webhook-events/{event_id}/dismiss")
async def dismiss_pending_webhook_event(event_id: int, current_user: dict = Depends(get_current_user)):
    """Marca evento como definitivamente falho (nao retentar). Usar quando
    intervencao confirma que o evento nao tem como ser recuperado."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    from pending_events import mark_event_failed, get_pending_event
    if not get_pending_event(event_id):
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    mark_event_failed(event_id, error="dismissed_by_admin")
    log_audit(current_user["id"], "PENDING_EVENT_DISMISS", f"id={event_id}")
    return {"status": "dismissed", "id": event_id}


@app.delete("/api/admin/pending-webhook-events/{event_id}")
async def delete_pending_webhook_event_endpoint(event_id: int, current_user: dict = Depends(get_current_user)):
    """Remove evento da fila. Use apos retry confirmado ou eventos sem
    valor de retencao."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin")
    from pending_events import delete_pending_event
    if not delete_pending_event(event_id):
        raise HTTPException(status_code=404, detail="Evento nao encontrado")
    log_audit(current_user["id"], "PENDING_EVENT_DELETE", f"id={event_id}")
    return {"status": "deleted", "id": event_id}


async def _fetch_channel_billing_status(channel_id: int) -> dict:
    """Helper reusavel: consulta Meta Graph API e retorna estado de billing
    de um canal. Usado pelo endpoint admin (channel_billing_status) e pelo
    cron de health-check (Fase 2.10.3).

    Em vez de raise, retorna dict com `ok=False` e `error` na falha.
    """
    from channel_service import get_channel, get_send_credentials

    channel = get_channel(channel_id)
    if not channel:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "channel_not_found",
            "has_payment_method": False,
        }

    waba_id = str(channel.get("waba_id") or "").strip()
    if not waba_id:
        return {
            "channel_id": channel_id,
            "ok": False,
            "error": "missing_waba_id",
            "has_payment_method": False,
        }

    try:
        token, _phone_id, api_base = get_send_credentials(channel_id)
    except ValueError as exc:
        return {
            "channel_id": channel_id,
            "waba_id": waba_id,
            "ok": False,
            "error": str(exc),
            "has_payment_method": False,
        }

    url = f"{api_base}/{waba_id}"
    params = {"fields": "primary_funding_id,account_review_status,health_status,owner_business_info"}
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code >= 400:
            return {
                "channel_id": channel_id,
                "waba_id": waba_id,
                "ok": False,
                "error": _meta_error_detail(resp),
                "has_payment_method": False,
            }
        data = resp.json()
    except Exception as exc:
        return {
            "channel_id": channel_id,
            "waba_id": waba_id,
            "ok": False,
            "error": str(exc),
            "has_payment_method": False,
        }

    primary_funding_id = data.get("primary_funding_id") or ""
    return {
        "channel_id": channel_id,
        "waba_id": waba_id,
        "ok": True,
        "has_payment_method": bool(primary_funding_id),
        "primary_funding_id": primary_funding_id,
        "account_review_status": data.get("account_review_status"),
        "health_status": data.get("health_status"),
        "owner_business_info": data.get("owner_business_info"),
        "checked_at": fs_utcnow().isoformat(),
    }


@app.get("/api/wa/channel/{channel_id}/billing-status")
async def channel_billing_status(channel_id: int, current_user: dict = Depends(get_current_user)):
    """Health-check do canal na Meta (Fase 2.10).

    Consulta GET /<WABA_ID>?fields=primary_funding_id,account_review_status
    para descobrir se o cliente ja configurou metodo de pagamento. Sem
    isso, templates de marketing/utility falham com erro #131009 ao
    tentar enviar.
    """
    from channel_service import get_channel

    channel = get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal nao encontrado")
    waba_id = str(channel.get("waba_id") or "").strip()
    if not waba_id:
        raise HTTPException(status_code=400, detail="Canal sem WABA_ID associado")

    res = await _fetch_channel_billing_status(channel_id)
    if not res.get("ok") and res.get("error") in ("channel_not_found", "missing_waba_id"):
        # Caminho rejeitado antes do helper — manter HTTPException pro endpoint admin
        raise HTTPException(
            status_code=404 if res["error"] == "channel_not_found" else 400,
            detail=res["error"],
        )
    return res


# ---------------------------------------------------------------------------
# Cron health-check (Fase 2.10.3) — Cloud Scheduler chama diariamente.
# Computa estado consolidado por tenant em tenants/{tid}/health_status/current
# e atualiza payment_method_status no doc flat de cada canal.
# ---------------------------------------------------------------------------

def _classify_payment_status(billing: dict, channel: dict) -> tuple[str, bool, bool]:
    """Decide payment_method_status (ok|pending|error|expired) e flags
    de token_expired/token_expiring_soon (so coexistence)."""
    if not billing.get("ok"):
        status = "error"
    elif billing.get("has_payment_method"):
        status = "ok"
    else:
        status = "pending"

    token_expired = False
    token_expiring = False
    if channel.get("channel_type") == "coexistence":
        expires_at_raw = channel.get("token_expires_at")
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(
                    str(expires_at_raw).replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                if expires_at <= now:
                    token_expired = True
                    status = "expired"
                elif expires_at - now <= timedelta(days=7):
                    token_expiring = True
            except (ValueError, TypeError):
                pass
    return status, token_expired, token_expiring


async def _compute_tenant_health() -> dict:
    """Executa dentro de tenant_context. Para cada canal ativo: chama
    _fetch_channel_billing_status, classifica, persiste payment_method_status
    no doc flat do canal. Retorna dict pronto pra gravar em
    tenants/{tid}/health_status/current.
    """
    import asyncio
    from channel_service import get_all_active_channels
    from firestore_common import global_document

    channels = get_all_active_channels()
    if not channels:
        return {
            "checked_at": fs_utcnow().isoformat(),
            "channels_total": 0,
            "channels_pending_payment": 0,
            "tokens_expiring_soon": 0,
            "templates_recent_failures": 0,
            "per_channel": [],
        }

    billing_results = await asyncio.gather(
        *[_fetch_channel_billing_status(ch["id"]) for ch in channels],
        return_exceptions=True,
    )

    channels_pending_payment = 0
    tokens_expiring_soon = 0
    per_channel: list[dict] = []
    for ch, billing in zip(channels, billing_results):
        if isinstance(billing, Exception):
            billing = {
                "channel_id": ch["id"],
                "ok": False,
                "error": str(billing),
                "has_payment_method": False,
            }
        status, token_expired, token_expiring = _classify_payment_status(billing, ch)
        if status == "pending":
            channels_pending_payment += 1
        if token_expiring:
            tokens_expiring_soon += 1

        try:
            global_document("channels", ch["id"]).set({
                "payment_method_status": status,
                "payment_method_checked_at": fs_utcnow(),
            }, merge=True)
        except Exception as exc:
            logger.warning(
                "cron health: falha ao atualizar payment_method_status canal %s: %s",
                ch["id"], exc,
            )

        per_channel.append({
            "channel_id": ch["id"],
            "label": ch.get("label", ""),
            "channel_type": ch.get("channel_type"),
            "payment_method_status": status,
            "has_payment_method": billing.get("has_payment_method", False),
            "account_review_status": billing.get("account_review_status"),
            "token_expiring_soon": token_expiring,
            "token_expired": token_expired,
            "error": billing.get("error") if not billing.get("ok") else None,
        })

    return {
        "checked_at": fs_utcnow().isoformat(),
        "channels_total": len(channels),
        "channels_pending_payment": channels_pending_payment,
        "tokens_expiring_soon": tokens_expiring_soon,
        "templates_recent_failures": 0,  # placeholder pra futura agregacao
        "per_channel": per_channel,
    }


def _verify_oidc_token(token: str) -> None:
    """Valida OIDC token Bearer (Cloud Scheduler nativo).

    Cloud Scheduler com `--oidc-service-account-email=<sa>` e
    `--oidc-token-audience=<url>` envia Authorization: Bearer <jwt>
    onde o JWT eh assinado pelo Google e tem:
      - iss = https://accounts.google.com
      - aud = audience configurado no job
      - email = SA do scheduler

    Env vars (configuradas no Cloud Run):
      CRON_OIDC_AUDIENCE          (obrigatorio, ex: a propria URL do endpoint)
      CRON_OIDC_SERVICE_ACCOUNT   (opcional, email do SA esperado — strict)
    """
    audience = os.environ.get("CRON_OIDC_AUDIENCE", "").strip()
    if not audience:
        raise HTTPException(
            status_code=503,
            detail="CRON_OIDC_AUDIENCE nao configurado",
        )
    expected_sa = os.environ.get("CRON_OIDC_SERVICE_ACCOUNT", "").strip()

    from google.oauth2 import id_token as _id_token
    from google.auth.transport import requests as _ga_requests

    try:
        payload = _id_token.verify_oauth2_token(
            token, _ga_requests.Request(), audience=audience
        )
    except ValueError as exc:
        # Token invalido / mal-assinado / aud errada / iss errada / expirado
        raise HTTPException(
            status_code=401,
            detail=f"OIDC token invalido: {exc}",
        )

    if expected_sa and payload.get("email") != expected_sa:
        # Strict mode: rejeita se SA nao bate com o esperado
        raise HTTPException(
            status_code=401,
            detail="OIDC SA mismatch",
        )


def _verify_cron_auth(request: Request) -> None:
    """Aceita OIDC Bearer (Cloud Scheduler) OU header X-Cron-Secret.

    Tenta primeiro o que estiver presente:
      1. Authorization: Bearer ...  -> OIDC verify
      2. X-Cron-Secret: ...         -> shared secret hmac compare
      3. Nenhum                     -> 401

    Cada metodo eh independente — falha de um nao cai no outro.
    Em prod, mover pra OIDC e remover INTERNAL_CRON_SECRET (CRON_OIDC_*
    sao suficientes); em staging/dev/CI, X-Cron-Secret continua util.
    """
    import hmac as _hmac

    auth_header = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        _verify_oidc_token(auth_header[7:].strip())
        return

    secret_header = request.headers.get("X-Cron-Secret", "")
    if secret_header:
        expected = os.environ.get("INTERNAL_CRON_SECRET", "").strip()
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="INTERNAL_CRON_SECRET nao configurado",
            )
        if not _hmac.compare_digest(secret_header.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(status_code=401, detail="X-Cron-Secret invalido")
        return

    raise HTTPException(
        status_code=401,
        detail="auth ausente: envie Authorization: Bearer <oidc> ou X-Cron-Secret",
    )


@app.post("/api/internal/cron/health-check")
async def cron_health_check(request: Request):
    """Cloud Scheduler chama diariamente. Itera tenants ativos, computa
    estado consolidado e grava em tenants/{tid}/health_status/current.

    Auth (qualquer um valida):
      - Authorization: Bearer <OIDC token>  (Cloud Scheduler com
        --oidc-service-account-email + --oidc-token-audience)
      - X-Cron-Secret: <secret>             (header customizado, fallback
        pra dev/staging onde OIDC nao tem SA configurado)
    """
    _verify_cron_auth(request)

    from tenant_service import list_tenants
    from firestore_common import set_tenant_context, reset_tenant_context, document as fs_doc

    summary: list[dict] = []
    for tenant in list_tenants(active_only=True):
        tid = str(tenant.get("id") or "")
        if not tid:
            continue
        token = set_tenant_context(tid)
        try:
            health = await _compute_tenant_health()
            fs_doc("health_status", "current").set(health, merge=False)
            summary.append({
                "tenant_id": tid,
                "channels_total": health["channels_total"],
                "channels_pending_payment": health["channels_pending_payment"],
                "tokens_expiring_soon": health["tokens_expiring_soon"],
            })
        except Exception as exc:
            logger.warning("cron_health_check: tenant %s falhou: %s", tid, exc)
            summary.append({"tenant_id": tid, "error": str(exc)})
        finally:
            reset_tenant_context(token)

    return {
        "checked_at": fs_utcnow().isoformat(),
        "tenants_processed": len(summary),
        "summary": summary,
    }


@app.get("/api/wa/contact/{contact_id}")
async def wa_contact_detail(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return {"contact": contact}


@app.post("/api/wa/transfer")
async def wa_transfer(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    conversation_id = body.get("conversation_id")
    contact_id = body.get("contact_id")
    to_user_id = body.get("to_user_id")
    to_department_id = body.get("to_department_id")
    reason = body.get("reason", "")
    summary = body.get("summary", "")
    if not conversation_id and not contact_id:
        raise HTTPException(status_code=400, detail="conversation_id ou contact_id obrigatorio")
    if not to_user_id:
        raise HTTPException(status_code=400, detail="Selecione o operador destino")
    if not summary:
        raise HTTPException(status_code=400, detail="Resumo do atendimento e obrigatorio")

    conv, contact, channel = _resolve_send_target(conversation_id, contact_id)

    # Fase 2C: transferencia atua na conversation. Quando vier so contact_id
    # (legado), assign_wa_contact espelha em todas as conversations do contato
    # — mas no fluxo novo so transferimos a thread aberta, deixando outras
    # threads coexistence intactas.
    if conversation_id:
        result = assign_wa_conversation(conv["id"], to_user_id, to_department_id, current_user["id"], reason, summary)
    else:
        result = assign_wa_contact(contact["id"], to_user_id, to_department_id, current_user["id"], reason, summary)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation nao encontrada")

    to_user = get_user_by_id(to_user_id) if to_user_id else None
    to_name = to_user["display_name"] if to_user else "Nenhum"

    sys_content = (
        f"Transferido de {current_user['display_name']} para {to_name}"
        + (f" | Motivo: {reason}" if reason else "")
        + (f" | Resumo: {summary}" if summary else "")
    )
    insert_transfer_system_message(
        contact["id"], sys_content, current_user["id"],
        conversation_id=conv["id"],
        channel_id=channel["id"] if channel else conv.get("channel_id"),
    )
    log_audit(current_user["id"], "WA_TRANSFER", f"Conv {conv['id']} -> {to_name} (dept={to_department_id}): {reason}")

    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {
            "conversation_id": conv["id"],
            "contact_id": contact["id"],
            "assigned_to": to_user_id,
            "assigned_name": to_name,
        },
    })
    return {"status": "transferred", "to_user": to_name}


@app.post("/api/wa/assume/{contact_id}")
async def wa_assume_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Operador assume o atendimento de um contato nao atribuido."""
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    try:
        existing_id = int(contact.get("assigned_to") or 0) or None
        current_id = int(current_user["id"])
    except (TypeError, ValueError):
        existing_id = None
        current_id = None
    if existing_id is not None and existing_id != current_id:
        raise HTTPException(status_code=409, detail="Atendimento ja assumido por outro operador")
    # -- Regra do contador de assumidas sem resposta --
    assume_counter = get_assume_counter(current_user["id"])
    if assume_counter <= -2:
        raise HTTPException(
            status_code=403,
            detail="Voce atingiu o limite de atendimentos assumidos sem resposta. Responda as conversas pendentes antes de assumir novas.",
        )
    result = assign_wa_contact(contact_id, current_user["id"], contact.get("department_id"), current_user["id"], reason="Assumido pelo operador", summary="Assumido pelo operador")
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    # Decrementar contador e marcar contato como pendente de resposta
    decrement_assume_counter(current_user["id"])
    mark_contact_pending_response(contact_id)
    # Gravar original_operator_id se ainda nao definido (para roteamento de lead retornante)
    if not contact.get("original_operator_id"):

        fs_document("wa_contacts", contact_id).set({"original_operator_id": current_user["id"]}, merge=True)
    now = datetime.now(timezone.utc)
    protocol = f"ATD-{now.strftime('%Y%m%d%H%M%S')}-{contact_id:05d}"
    set_attendance_protocol(contact_id, protocol, now.isoformat())
    sys_content = f"Atendimento assumido por {current_user['display_name']} | Protocolo: {protocol}"
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_ASSUME", f"Contato {contact_id} | Protocolo {protocol}")
    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": current_user["id"], "assigned_name": current_user["display_name"]},
    })
    return {"status": "assumed", "assigned_to": current_user["id"], "assigned_name": current_user["display_name"], "protocol": protocol}


@app.post("/api/admin/operator/{user_id}/reset-assume-counter")
async def admin_reset_assume_counter(user_id: int, current_user: dict = Depends(get_current_user)):
    """Reseta o contador de assumidas sem resposta de um operador. Apenas admin/supervisor."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Operador nao encontrado")
    reset_assume_counter(user_id)
    log_audit(current_user["id"], "RESET_ASSUME_COUNTER", f"Operador {target.get('display_name', user_id)} (id={user_id})")
    return {"status": "reset", "user_id": user_id, "counter": 0}


@app.get("/api/wa/transfer-history/{contact_id}")
async def wa_transfer_hist(contact_id: int, current_user: dict = Depends(get_current_user)):
    return {"history": get_transfer_history(contact_id)}


@app.post("/api/wa/contact/{contact_id}/return-to-bot")
async def wa_return_to_bot(contact_id: int, current_user: dict = Depends(get_current_user)):
    """Devolve o contato para a fila do bot. Apenas admin/supervisor."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    result = return_contact_to_bot(contact_id, current_user["id"])
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    sys_content = f"Devolvido ao bot por {current_user['display_name']}"
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_RETURN_TO_BOT", f"Contato {contact_id}")
    return {"status": "returned_to_bot"}


@app.post("/api/admin/bulk-reassign")
async def admin_bulk_reassign(request: Request, current_user: dict = Depends(get_current_user)):
    """Reatribuicao em lote de contatos de um operador.

    Body: { from_user_id, action: "return_to_bot" | "transfer", to_user_id? }

    Exclui automaticamente contatos cujo canal e coexistence proprio do
    operador X (i.e. `channel.owner_user_id == from_user_id`). Esses
    contatos pertencem ao WhatsApp pessoal dele e nao podem ser
    transferidos sem perder acesso ao numero — o operador continua dono.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    body = await request.json()
    from_user_id = body.get("from_user_id")
    action = body.get("action", "return_to_bot")
    to_user_id = body.get("to_user_id")

    if not from_user_id:
        raise HTTPException(status_code=400, detail="from_user_id obrigatorio")

    contacts = get_contacts_by_assigned_user(from_user_id)
    if not contacts:
        return {"status": "ok", "count": 0}

    from channel_service import CHANNEL_TYPE_COEXISTENCE, get_channel

    count = 0
    skipped_coex = 0
    for contact in contacts:
        cid = contact["id"]
        # Filtro coexistence: se canal e coexistence cujo dono e exatamente
        # o operador que estamos esvaziando, manter o vinculo.
        ch_id = contact.get("channel_id")
        if ch_id is not None:
            ch = get_channel(ch_id)
            if (
                ch
                and ch.get("channel_type") == CHANNEL_TYPE_COEXISTENCE
                and int(ch.get("owner_user_id") or 0) == int(from_user_id)
            ):
                skipped_coex += 1
                continue
        if action == "return_to_bot":
            return_contact_to_bot(cid, current_user["id"])
            insert_transfer_system_message(cid, f"Devolvido ao bot (reatribuicao em lote) por {current_user['display_name']}", current_user["id"])
        elif action == "transfer" and to_user_id:
            to_user = get_user_by_id(to_user_id)
            assign_wa_contact(cid, to_user_id, (to_user or {}).get("department_id"), current_user["id"], reason="Reatribuicao em lote", summary=f"Reatribuido de operador {from_user_id}")
            insert_transfer_system_message(cid, f"Reatribuido para {(to_user or {}).get('display_name', '?')} por {current_user['display_name']} (lote)", current_user["id"])
        count += 1

    log_audit(current_user["id"], "BULK_REASSIGN", f"from={from_user_id} action={action} to={to_user_id} count={count} skipped_coex={skipped_coex}")
    return {"status": "ok", "count": count, "skipped_coex": skipped_coex}


@app.get("/api/operators")
async def list_operators(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "username": u.get("username", ""), "display_name": u["display_name"],
            "department_name": u.get("department_name", ""),
            "department_id": u.get("department_id"),
            "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"),
            "email": u.get("email", ""),
            "firebase_uid": u.get("firebase_uid", ""),
        }
        for u in users if u.get("is_active")
    ]


async def broadcast_to_operators(message: dict):
    # Mantido como no-op porque o fluxo legado de notificacao via WebSocket
    # foi removido. O webhook ainda pode chamar este callback sem efeito colateral.
    return None


# -- API: Google Chat (comunicacao interna) --


class GcSendRequest(BaseModel):
    conversation_id: int
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


@app.get("/api/gc/conversations")
async def gc_list_conversations(current_user: dict = Depends(get_current_user)):
    """Lista todas as conversas do Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    conversations = get_all_gc_conversations()
    return {"conversations": conversations}


@app.get("/api/gc/messages/{conversation_id}")
async def gc_get_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Retorna mensagens de uma conversa."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    messages = get_gc_messages(conversation_id, limit=limit, offset=offset)
    return {"messages": messages}


@app.post("/api/gc/send")
async def gc_send_message(body: GcSendRequest, current_user: dict = Depends(get_current_user)):
    """Envia mensagem do CRM para o Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")

    from database import get_gc_conversation
    conversation = get_gc_conversation(body.conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa nao encontrada")

    space_id = conversation.get("space_id")
    if not space_id:
        raise HTTPException(status_code=400, detail="Space ID nao configurado")

    # Enviar via Google Chat API
    from google_chat import send_text_message
    result = send_text_message(space_id, body.content)
    if not result:
        raise HTTPException(status_code=502, detail="Falha ao enviar para Google Chat")

    # Salvar no Firestore
    sender_email = current_user.get("email", "")
    sender_name = current_user.get("display_name", "")
    message_id = save_gc_message(
        conversation_id=body.conversation_id,
        gchat_message_id=result.get("gchat_message_id", ""),
        sender_email=sender_email,
        sender_name=sender_name,
        msg_type="text",
        content=body.content,
        source="crm",
        create_time=result.get("create_time", ""),
    )

    log_audit(current_user["id"], "gc_send_message", f"conv={body.conversation_id} msg_id={message_id}")
    return {"message_id": message_id, "gchat_message_id": result.get("gchat_message_id", "")}


@app.post("/api/gc/mark-read/{conversation_id}")
async def gc_mark_read(conversation_id: int, current_user: dict = Depends(get_current_user)):
    """Marca conversa como lida para o usuario atual."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    user_identifier = current_user.get("email", str(current_user["id"]))
    mark_gc_conversation_read(conversation_id, user_identifier)
    return {"status": "ok"}


@app.get("/api/gc/spaces")
async def gc_list_spaces(current_user: dict = Depends(get_current_user)):
    """Lista spaces disponiveis no Google Chat."""
    if not FEATURE_GOOGLE_CHAT:
        raise HTTPException(status_code=404, detail="Google Chat desabilitado")
    from google_chat import list_spaces
    spaces = list_spaces()
    return {"spaces": spaces}


@app.post("/webhooks/google-chat")
async def webhook_google_chat(request: Request):
    """Recebe eventos do Google Chat (mensagens, bot adicionado/removido)."""
    if not FEATURE_GOOGLE_CHAT:
        return JSONResponse(status_code=404, content={"error": "Google Chat desabilitado"})

    auth_header = request.headers.get("Authorization", "")
    is_valid = await validate_google_chat_token(auth_header)
    if not is_valid:
        logger.warning("Webhook Google Chat: token invalido")
        return JSONResponse(status_code=403, content={"error": "Token invalido"})

    event = await request.json()
    response = await process_google_chat_event(event)
    return response or {}


# -- API: Dashboard de Auditoria --


@app.get("/api/admin/dashboard/summary")
async def dashboard_summary(
    date_from: str = Query(""),
    date_to: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    """Retorna metricas agregadas para o periodo."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if not date_from:
        date_from = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    metrics = get_audit_metrics(date_from, date_to)

    # Separar global vs per-operator
    global_metrics = [m for m in metrics if "_" not in str(m.get("doc_id", ""))[11:]]
    operator_metrics = [m for m in metrics if "_" in str(m.get("doc_id", ""))[11:]]

    # Agregar global
    total_inbound = sum(int(m.get("total_messages_inbound") or 0) for m in global_metrics)
    total_outbound = sum(int(m.get("total_messages_outbound") or 0) for m in global_metrics)
    total_leads = sum(int(m.get("total_leads_received") or 0) for m in global_metrics)
    total_assumed = sum(int(m.get("total_leads_assumed") or 0) for m in global_metrics)

    # Agregar por operador
    operators_agg: dict[str, dict] = {}
    for m in operator_metrics:
        doc_id = str(m.get("doc_id", ""))
        parts = doc_id.split("_", 1)
        if len(parts) < 2:
            continue
        uid = parts[1]
        if uid not in operators_agg:
            operators_agg[uid] = {"user_id": int(uid) if uid.isdigit() else uid, "inbound": 0, "outbound": 0, "leads_assumed": 0, "first_activity": None, "last_activity": None}
        agg = operators_agg[uid]
        agg["inbound"] += int(m.get("total_messages_inbound") or 0)
        agg["outbound"] += int(m.get("total_messages_outbound") or 0)
        agg["leads_assumed"] += int(m.get("total_leads_assumed") or 0)
        fa = m.get("first_activity_at")
        la = m.get("last_activity_at")
        if fa and (not agg["first_activity"] or fa < agg["first_activity"]):
            agg["first_activity"] = fa
        if la and (not agg["last_activity"] or la > agg["last_activity"]):
            agg["last_activity"] = la

    # Peak chart: agregar messages_by_half_hour
    peak: dict[str, int] = {}
    for m in global_metrics:
        half_hours = m.get("messages_by_half_hour") or {}
        if isinstance(half_hours, dict):
            for slot, count in half_hours.items():
                peak[slot] = peak.get(slot, 0) + int(count or 0)

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_messages_inbound": total_inbound,
        "total_messages_outbound": total_outbound,
        "total_messages": total_inbound + total_outbound,
        "total_leads_received": total_leads,
        "total_leads_assumed": total_assumed,
        "operators": list(operators_agg.values()),
        "peak_chart": peak,
    }


@app.get("/api/admin/dashboard/ratings")
async def dashboard_ratings(
    date_from: str = Query(""),
    date_to: str = Query(""),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    ratings = get_all_ratings(date_from or None, date_to or None)
    return {"ratings": ratings}


# -- API: Usage mensal per-tenant (Fase 2.10.4) --


@app.get("/api/wa/usage/current-month")
async def wa_usage_current_month(current_user: dict = Depends(get_current_user)):
    """Retorna usage do mes corrente pro tenant atual (informativo).

    Estrutura: { month, templates_sent: {marketing,utility,authentication,unknown},
    free_form_sent, inbound_received, media_uploaded_bytes }.
    Acessivel a admin/supervisor — visibilidade pra cruzar com fatura Meta.
    """
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    return get_monthly_usage()


@app.get("/api/wa/usage/history")
async def wa_usage_history(
    months: int = Query(3, ge=1, le=24),
    current_user: dict = Depends(get_current_user),
):
    """Retorna ultimos N meses de usage do tenant atual (mes corrente primeiro)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    return {"months": get_usage_history(months)}


@app.get("/api/wa/usage/{year_month}")
async def wa_usage_specific_month(
    year_month: str,
    current_user: dict = Depends(get_current_user),
):
    """Retorna usage de um mes especifico (formato YYYY-MM)."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")
    if len(year_month) != 7 or year_month[4] != "-":
        raise HTTPException(status_code=400, detail="Formato esperado: YYYY-MM")
    try:
        y, m = year_month.split("-")
        if not (1 <= int(m) <= 12) or not (2020 <= int(y) <= 2099):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato esperado: YYYY-MM")
    return get_monthly_usage(year_month)


# -- API: Export --


@app.get("/api/admin/export")
async def export_data(
    date_from: str = Query(""),
    date_to: str = Query(""),
    format: str = Query("json"),
    current_user: dict = Depends(get_current_user),
):
    """Exporta conversas e contatos em JSON ou CSV."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor")

    contacts = get_all_wa_contacts(include_archived=True)
    # Filtrar por data se especificado
    if date_from:
        contacts = [c for c in contacts if str(c.get("first_seen_at", ""))[:10] >= date_from]
    if date_to:
        contacts = [c for c in contacts if str(c.get("first_seen_at", ""))[:10] <= date_to]

    if format == "csv":
        import csv
        import io
        output = io.StringIO()
        if contacts:
            fields = ["id", "wa_id", "display_name", "phone_formatted", "qualification",
                       "assigned_to", "assigned_name", "department_name", "channel_id",
                       "source_channel_type", "rating", "first_seen_at", "last_message_at",
                       "notes"]
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for c in contacts:
                writer.writerow(c)
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=export_{date_from}_{date_to}.csv"},
        )
    else:
        return {"contacts": contacts, "count": len(contacts), "date_from": date_from, "date_to": date_to}


# -- API: Embedded Signup (Coexistence) --


@app.get("/api/admin/embedded-signup/config")
async def embedded_signup_config(current_user: dict = Depends(get_current_user)):
    """Retorna configuracao necessaria para o frontend iniciar o Embedded Signup."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor podem acessar o signup")
    missing: list[str] = []
    if not META_APP_ID:
        missing.append("META_APP_ID")
    if not META_APP_SECRET:
        missing.append("META_APP_SECRET")
    if not EMBEDDED_SIGNUP_CONFIG_ID:
        missing.append("EMBEDDED_SIGNUP_CONFIG_ID")
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Configuracao de Embedded Signup incompleta: {', '.join(missing)}",
        )
    return {
        "app_id": META_APP_ID,
        "config_id": EMBEDDED_SIGNUP_CONFIG_ID,
        "graph_api_version": GRAPH_API_VERSION,
    }


class EmbeddedSignupExchange(BaseModel):
    code: str
    channel_type: str = "coexistence"
    owner_user_id: int | None = None
    label: str = ""
    default_department_id: int | None = None


def _meta_error_detail(resp: httpx.Response) -> str:
    """Extrai mensagem de erro estruturada de uma resposta da Graph API."""
    try:
        data = resp.json()
    except Exception:
        return resp.text[:500] or f"HTTP {resp.status_code}"
    err = data.get("error") or {}
    msg = err.get("message") or err.get("error_user_msg") or ""
    code = err.get("code")
    subcode = err.get("error_subcode")
    trace = err.get("fbtrace_id")
    parts = []
    if msg:
        parts.append(msg)
    if code is not None:
        parts.append(f"code={code}")
    if subcode is not None:
        parts.append(f"subcode={subcode}")
    if trace:
        parts.append(f"trace={trace}")
    return " | ".join(parts) or resp.text[:500] or f"HTTP {resp.status_code}"


@app.post("/api/admin/embedded-signup/exchange")
async def embedded_signup_exchange(
    body: EmbeddedSignupExchange,
    current_user: dict = Depends(get_current_user),
):
    """Troca o code do Embedded Signup por token e descobre WABA/Phone IDs."""
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Apenas admin/supervisor podem realizar signup")
    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(status_code=503, detail="META_APP_ID e META_APP_SECRET sao obrigatorios")

    # 1. Trocar code por access token
    token_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        f"?client_id={META_APP_ID}"
        f"&client_secret={META_APP_SECRET}"
        f"&code={body.code}"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.get(token_url)

    if token_resp.status_code >= 400:
        detail = _meta_error_detail(token_resp)
        logger.error("Embedded Signup token exchange falhou: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro na troca do code: {detail}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        detail = _meta_error_detail(token_resp)
        logger.error("Embedded Signup token exchange sem access_token: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro na troca do code: {detail}")

    expires_in_raw = token_data.get("expires_in")
    token_expires_at_iso: str | None = None
    if isinstance(expires_in_raw, (int, float)) and expires_in_raw > 0:
        token_expires_at_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_raw))
        ).isoformat()
    logger.info(
        "Embedded Signup: token obtido (expires_in=%s)",
        expires_in_raw if expires_in_raw is not None else "n/a",
    )

    # 2. debug_token: descobre WABAs autorizados e valida escopo coexistence
    debug_url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token"
        f"?input_token={access_token}&access_token={META_APP_ID}|{META_APP_SECRET}"
    )
    async with httpx.AsyncClient(timeout=20.0) as client:
        debug_resp = await client.get(debug_url)

    if debug_resp.status_code >= 400:
        detail = _meta_error_detail(debug_resp)
        logger.error("Embedded Signup debug_token falhou: %s", detail)
        raise HTTPException(status_code=502, detail=f"Erro ao validar token: {detail}")

    debug_data = debug_resp.json()
    granular_scopes = debug_data.get("data", {}).get("granular_scopes", [])

    waba_ids: list[str] = []
    coexistence_scope_present = False
    granted_scope_names: list[str] = []
    for scope in granular_scopes:
        scope_name = scope.get("scope") or ""
        granted_scope_names.append(scope_name)
        if scope_name == "whatsapp_business_management":
            for tid in scope.get("target_ids") or []:
                if tid and tid not in waba_ids:
                    waba_ids.append(str(tid))
        if scope_name == "whatsapp_business_app_onboarding":
            coexistence_scope_present = True

    if not waba_ids:
        logger.warning(
            "Embedded Signup: nenhum WABA nos scopes (granted=%s)",
            ",".join(granted_scope_names) or "<vazio>",
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Nenhuma conta WhatsApp Business retornada pelo signup. "
                "Confirme que o usuario concedeu acesso a uma WABA."
            ),
        )

    if body.channel_type == "coexistence" and not coexistence_scope_present:
        logger.warning(
            "Embedded Signup: pediu coexistence mas escopo whatsapp_business_app_onboarding ausente (granted=%s)",
            ",".join(granted_scope_names) or "<vazio>",
        )
        # Nao bloqueia (Meta as vezes nao retorna esse scope no debug),
        # mas registra para diagnostico futuro.

    waba_id = waba_ids[0]
    logger.info(
        "Embedded Signup: WABA ID = %s (total descobertos: %d)",
        waba_id, len(waba_ids),
    )

    # 3. Buscar todos os Phone Numbers do WABA, com paginacao
    phone_numbers: list[dict] = []
    next_url: str | None = f"{GRAPH_API_BASE}/{waba_id}/phone_numbers"
    next_params: dict | None = {"limit": 100}
    async with httpx.AsyncClient(timeout=20.0) as client:
        while next_url:
            phones_resp = await client.get(
                next_url,
                params=next_params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if phones_resp.status_code >= 400:
                detail = _meta_error_detail(phones_resp)
                logger.error("Embedded Signup phone_numbers falhou: %s", detail)
                raise HTTPException(status_code=502, detail=f"Erro ao buscar numeros: {detail}")
            phones_data = phones_resp.json()
            phone_numbers.extend(phones_data.get("data", []) or [])
            paging = phones_data.get("paging") or {}
            next_url = paging.get("next")
            next_params = None  # paging.next ja inclui cursor

    if not phone_numbers:
        logger.warning("Embedded Signup: nenhum numero encontrado no WABA %s", waba_id)
        raise HTTPException(status_code=400, detail="Nenhum numero de telefone encontrado na conta")

    phone_info = phone_numbers[0]
    phone_number_id = phone_info.get("id", "")
    display_phone = phone_info.get("display_phone_number", "")
    verified_name = phone_info.get("verified_name", "")
    quality_rating = phone_info.get("quality_rating", "")
    platform_type = phone_info.get("platform_type", "")
    status = phone_info.get("status", "")
    code_verification_status = phone_info.get("code_verification_status", "")
    messaging_limit_tier = phone_info.get("messaging_limit_tier", "")
    is_official = phone_info.get("is_official_business_account")

    logger.info(
        "Embedded Signup concluido | waba=%s phone_id=%s display=%s status=%s platform=%s tier=%s",
        waba_id, phone_number_id, redact_phone(display_phone), status, platform_type, messaging_limit_tier,
    )

    # 4. Determinar tipo do canal antes de assinar webhook (campos diferem)
    is_coexistence = body.channel_type == "coexistence"
    channel_type = CHANNEL_TYPE_COEXISTENCE if is_coexistence else CHANNEL_TYPE_STANDARD
    owner_id = (body.owner_user_id or current_user["id"]) if is_coexistence else None

    # 5. Registrar webhook do app no WABA com os fields apropriados
    if is_coexistence:
        subscribed_fields = [
            "messages",
            "message_template_status_update",
            "message_template_quality_update",
            "history",
            "smb_message_echoes",
            "smb_app_state_sync",
            "account_update",
        ]
    else:
        subscribed_fields = [
            "messages",
            "message_template_status_update",
            "message_template_quality_update",
            "account_update",
        ]

    subscribe_url = f"{GRAPH_API_BASE}/{waba_id}/subscribed_apps"
    sub_resp = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            sub_resp = await client.post(
                subscribe_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"subscribed_fields": subscribed_fields},
            )
    except httpx.RequestError as exc:
        # ReadTimeout / ConnectError / etc na Meta sao transitorios e nao
        # devem aborter o signup — o canal eh criado e o admin reinscreve
        # o webhook depois (botao na UI ou rerun do signup).
        logger.warning(
            "Embedded Signup subscribed_apps falhou por erro de rede (%s: %s) "
            "— canal segue criado, admin reassina webhook depois",
            type(exc).__name__, exc,
        )

    webhook_subscribed = False
    if sub_resp is None:
        # Falha de rede — log ja emitido acima, continua com webhook=False
        pass
    elif sub_resp.status_code >= 400:
        sub_detail = _meta_error_detail(sub_resp)
        logger.error("Embedded Signup subscribed_apps falhou: %s", sub_detail)
        # Nao aborta: canal pode ser criado mesmo sem webhook (admin reassina depois)
    else:
        sub_data = sub_resp.json()
        webhook_subscribed = bool(sub_data.get("success", False))
        logger.info(
            "Embedded Signup: webhook subscription = %s | fields=%s",
            webhook_subscribed, ",".join(subscribed_fields),
        )

    # 6. Criar canal no registry
    owner_user = get_user_by_id(owner_id) if owner_id else None
    channel_label = body.label or (
        f"{(owner_user or {}).get('display_name', 'Operador')} - {display_phone}"
        if is_coexistence
        else f"Canal {display_phone}"
    )

    new_channel_id = create_channel(
        channel_type=channel_type,
        label=channel_label,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
        display_phone_number=display_phone,
        access_token=access_token,
        token_expires_at=token_expires_at_iso,
        owner_user_id=owner_id,
        owner_firebase_uid=(owner_user or {}).get("firebase_uid", ""),
        default_department_id=body.default_department_id,
        is_bot_enabled=not is_coexistence,
        platform_type=platform_type,
        is_official_business_account=is_official,
        code_verification_status=code_verification_status,
        messaging_limit_tier=messaging_limit_tier,
        verified_name=verified_name,
        quality_rating=quality_rating,
        webhook_subscribed=webhook_subscribed,
    )

    # 7. Disparar sync de contatos + history (coexistence apenas).
    # Doc Meta: POST /{phone_id}/smb_app_data e necessario pra Meta
    # comecar a entregar webhooks 'smb_app_state_sync' (contatos) e
    # 'history' (mensagens dos ultimos 180 dias). Janela de 24h apos
    # signup, depois disso precisa desligar e refazer signup. Cada sync
    # so pode ser disparado UMA VEZ por signup.
    sync_results: dict[str, dict] = {}
    if is_coexistence:
        smb_data_url = f"{GRAPH_API_BASE}/{phone_number_id}/smb_app_data"
        for sync_type in ("smb_app_state_sync", "history"):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    sync_resp = await client.post(
                        smb_data_url,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"messaging_product": "whatsapp", "sync_type": sync_type},
                    )
                if sync_resp.status_code >= 400:
                    detail = _meta_error_detail(sync_resp)
                    logger.error(
                        "Embedded Signup smb_app_data %s falhou: %s",
                        sync_type, detail,
                    )
                    sync_results[sync_type] = {"ok": False, "error": detail}
                else:
                    body_json = sync_resp.json()
                    sync_results[sync_type] = {
                        "ok": True,
                        "request_id": body_json.get("request_id", ""),
                    }
                    logger.info(
                        "Embedded Signup smb_app_data %s OK | request_id=%s",
                        sync_type, body_json.get("request_id", ""),
                    )
            except httpx.RequestError as exc:
                # Erro de rede nao aborta signup. Admin pode redisparar
                # via POST /api/admin/channels/{id}/trigger-coex-sync
                # dentro da janela de 24h.
                logger.warning(
                    "Embedded Signup smb_app_data %s erro de rede (%s: %s) — "
                    "canal segue criado, admin redispara via endpoint",
                    sync_type, type(exc).__name__, exc,
                )
                sync_results[sync_type] = {"ok": False, "error": str(exc)}

    log_audit(
        current_user["id"],
        "EMBEDDED_SIGNUP",
        f"WABA={waba_id} Phone={phone_number_id} ({display_phone}) status={status} channel_id={new_channel_id} syncs={list(sync_results.keys())}",
    )

    return {
        "status": "ok",
        "channel_id": new_channel_id,
        "channel_type": channel_type,
        "access_token": access_token,
        "token_expires_at": token_expires_at_iso,
        "waba_id": waba_id,
        "all_wabas": waba_ids,
        "phone_number_id": phone_number_id,
        "display_phone_number": display_phone,
        "verified_name": verified_name,
        "quality_rating": quality_rating,
        "platform_type": platform_type,
        "phone_status": status,
        "code_verification_status": code_verification_status,
        "messaging_limit_tier": messaging_limit_tier,
        "is_official_business_account": is_official,
        "webhook_subscribed": webhook_subscribed,
        "subscribed_fields": subscribed_fields,
        "coex_syncs": sync_results,
        "all_phones": [
            {
                "id": p.get("id"),
                "display_phone_number": p.get("display_phone_number"),
                "verified_name": p.get("verified_name"),
                "status": p.get("status"),
                "platform_type": p.get("platform_type"),
            }
            for p in phone_numbers
        ],
    }


# -- Execucao --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")
```

## media.py

```python
# -*- coding: utf-8 -*-

"""
Gerencia download de midia recebida via WhatsApp Cloud API,
conversao de audio e persistencia em disco local, Cloud Storage ou Firestore.
"""

import gzip
import hashlib
import logging
import mimetypes
import os
import subprocess
import tempfile
from datetime import datetime

import httpx

from pii_redaction import redact_phone

from config import (
    WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    GRAPH_API_BASE,
    MEDIA_DIR,
    MAX_MEDIA_SIZE_MB,
    MEDIA_STORAGE_BACKEND,
    GCS_MEDIA_BUCKET,
    GCS_MEDIA_PREFIX,
    FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB,
    FIRESTORE_MEDIA_MAX_MB,
    FIRESTORE_MEDIA_CHUNK_KB,
)
from firestore_common import collection, document, utcnow

logger = logging.getLogger("castro_crm.media")

_storage_client = None
_storage_backend_logged = False


def _normalize_wa_target(wa_id):
    return "".join(ch for ch in str(wa_id or "").strip() if ch.isdigit())


MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/amr": ".amr",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
}


def _using_gcs():
    return MEDIA_STORAGE_BACKEND == "gcs" and bool(GCS_MEDIA_BUCKET)


def _using_firestore():
    return MEDIA_STORAGE_BACKEND == "firestore"


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError("google-cloud-storage nao instalado") from exc
        _storage_client = storage.Client()
    return _storage_client


def _get_bucket():
    return _get_storage_client().bucket(GCS_MEDIA_BUCKET)


def _log_storage_backend_once():
    global _storage_backend_logged
    if _storage_backend_logged:
        return
    if _using_gcs():
        logger.info(
            "Midia configurada para Cloud Storage | bucket=%s prefix=%s",
            GCS_MEDIA_BUCKET,
            GCS_MEDIA_PREFIX or "(raiz)",
        )
    elif _using_firestore():
        logger.info(
            "Midia configurada para Firestore | compress_threshold_kb=%d max_mb=%d chunk_kb=%d",
            FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB,
            FIRESTORE_MEDIA_MAX_MB,
            FIRESTORE_MEDIA_CHUNK_KB,
        )
    else:
        logger.info("Midia configurada para filesystem local | dir=%s", MEDIA_DIR)
    _storage_backend_logged = True


def ensure_media_dir():
    _log_storage_backend_once()
    if _using_gcs() or _using_firestore():
        return
    os.makedirs(MEDIA_DIR, exist_ok=True)
    for subdir in ("images", "audio", "video", "documents", "stickers", "avatars", "sounds"):
        os.makedirs(os.path.join(MEDIA_DIR, subdir), exist_ok=True)


def get_subdir_for_type(msg_type):
    mapping = {
        "image": "images",
        "audio": "audio",
        "video": "video",
        "document": "documents",
        "sticker": "stickers",
    }
    return mapping.get(msg_type, "documents")


def _build_media_path(subdir, filename):
    return f"/media/{subdir}/{filename}"


def _split_media_path(media_path):
    normalized = (media_path or "").strip()
    if not normalized.startswith("/media/"):
        return None, None
    parts = normalized.split("/", 3)
    if len(parts) != 4:
        return None, None
    subdir = os.path.basename(parts[2])
    filename = os.path.basename(parts[3])
    if not subdir or not filename:
        return None, None
    return subdir, filename


def _build_object_name(subdir, filename):
    parts = []
    if GCS_MEDIA_PREFIX:
        parts.append(GCS_MEDIA_PREFIX)
    parts.extend([subdir, filename])
    return "/".join(parts)


def _build_local_path(subdir, filename):
    return os.path.join(MEDIA_DIR, subdir, filename)


def _firestore_asset_id(subdir, filename):
    return f"{subdir}__{filename}"


def _firestore_asset_ref(subdir, filename):
    return document("media_assets", _firestore_asset_id(subdir, filename))


def _default_mime_type(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _resolve_extension(mime_type, filename=""):
    ext = MIME_EXTENSIONS.get(mime_type or "", "")
    if not ext and filename:
        _, ext = os.path.splitext(filename)
    return ext or ".bin"


def _maybe_compress_content(content):
    threshold = max(FIRESTORE_MEDIA_COMPRESS_THRESHOLD_KB, 0) * 1024
    if len(content) < threshold:
        return content, False
    compressed = gzip.compress(content, compresslevel=6)
    if len(compressed) + 64 < len(content):
        return compressed, True
    return content, False


def _store_media_in_firestore(content, subdir, filename, mime_type):
    stored_content, compressed = _maybe_compress_content(content)
    max_bytes = max(FIRESTORE_MEDIA_MAX_MB, 1) * 1024 * 1024
    if len(stored_content) > max_bytes:
        raise RuntimeError(
            f"Arquivo excede limite seguro para Firestore ({FIRESTORE_MEDIA_MAX_MB}MB apos compressao)."
        )

    chunk_size = min(max(FIRESTORE_MEDIA_CHUNK_KB, 64) * 1024, 900 * 1024)
    chunks = [
        stored_content[index:index + chunk_size]
        for index in range(0, len(stored_content), chunk_size)
    ] or [b""]

    asset_ref = _firestore_asset_ref(subdir, filename)
    asset_ref.set({
        "subdir": subdir,
        "filename": filename,
        "mime_type": mime_type,
        "content_encoding": "gzip" if compressed else "",
        "original_size": len(content),
        "stored_size": len(stored_content),
        "chunk_count": len(chunks),
        "created_at": utcnow(),
        "checksum": hashlib.sha256(content).hexdigest(),
    })

    for idx, chunk in enumerate(chunks):
        asset_ref.collection("chunks").document(f"{idx:06d}").set({
            "seq": idx,
            "data": chunk,
        })

    return _build_media_path(subdir, filename)


def _write_media_bytes(content, subdir, filename, mime_type):
    ensure_media_dir()
    if _using_firestore():
        return _store_media_in_firestore(content, subdir, filename, mime_type)
    if _using_gcs():
        blob = _get_bucket().blob(_build_object_name(subdir, filename))
        blob.upload_from_string(content, content_type=mime_type)
        return _build_media_path(subdir, filename)

    filepath = _build_local_path(subdir, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return _build_media_path(subdir, filename)


def save_avatar_media(content, prefix, entity_id, mime_type):
    ext = _resolve_extension(mime_type)
    file_hash = hashlib.sha256(content).hexdigest()[:16]
    filename = f"{prefix}_{entity_id}_{file_hash}{ext}"
    return _write_media_bytes(content, "avatars", filename, mime_type)


def delete_media(media_path):
    if not media_path:
        return

    subdir, filename = _split_media_path(media_path)
    if not subdir or not filename:
        return

    deleted = False
    if _using_firestore():
        try:
            asset_ref = _firestore_asset_ref(subdir, filename)
            chunk_refs = list(asset_ref.collection("chunks").stream())
            for chunk_snapshot in chunk_refs:
                chunk_snapshot.reference.delete()
            asset_ref.delete()
            deleted = True
        except Exception as exc:
            logger.warning("Falha ao remover midia no Firestore (%s): %s", media_path, exc)

    if _using_gcs():
        try:
            blob = _get_bucket().blob(_build_object_name(subdir, filename))
            if blob.exists():
                blob.delete()
                deleted = True
        except Exception as exc:
            logger.warning("Falha ao remover midia no Cloud Storage (%s): %s", media_path, exc)

    filepath = _build_local_path(subdir, filename)
    if os.path.isfile(filepath):
        try:
            os.remove(filepath)
            deleted = True
        except OSError:
            pass

    if deleted:
        logger.info("Midia removida: %s", media_path)


def get_media_asset(media_path):
    subdir, filename = _split_media_path(media_path)
    if not subdir or not filename:
        return None

    if _using_firestore():
        try:
            asset = _firestore_asset_ref(subdir, filename).get()
            if asset.exists:
                data = asset.to_dict() or {}
                chunk_docs = sorted(
                    asset.reference.collection("chunks").stream(),
                    key=lambda snapshot: int((snapshot.to_dict() or {}).get("seq", 0)),
                )
                content = b"".join((snapshot.to_dict() or {}).get("data", b"") for snapshot in chunk_docs)
                if data.get("content_encoding") == "gzip":
                    content = gzip.decompress(content)
                return {
                    "content": content,
                    "mime_type": data.get("mime_type") or _default_mime_type(filename),
                    "filename": filename,
                    "source": "firestore",
                }
        except Exception as exc:
            logger.warning("Falha ao ler midia no Firestore (%s): %s", media_path, exc)

    if _using_gcs():
        try:
            blob = _get_bucket().blob(_build_object_name(subdir, filename))
            if blob.exists():
                return {
                    "content": blob.download_as_bytes(),
                    "mime_type": blob.content_type or _default_mime_type(filename),
                    "filename": filename,
                    "source": "gcs",
                }
        except Exception as exc:
            logger.warning("Falha ao ler midia no Cloud Storage (%s): %s", media_path, exc)

    filepath = _build_local_path(subdir, filename)
    if os.path.isfile(filepath):
        return {
            "file_path": filepath,
            "mime_type": _default_mime_type(filename),
            "filename": filename,
            "source": "local",
        }
    return None


def convert_audio_to_ogg_opus(input_bytes, input_mime="audio/webm"):
    """
    Converte audio gravado pelo navegador (webm/opus) para OGG/Opus
    que e o formato aceito pelo WhatsApp.
    Retorna os bytes do arquivo OGG ou None em caso de falha.
    """
    ext_in = ".webm"
    if "mp4" in input_mime or "m4a" in input_mime:
        ext_in = ".m4a"
    elif "mpeg" in input_mime or "mp3" in input_mime:
        ext_in = ".mp3"
    elif "ogg" in input_mime:
        ext_in = ".ogg"

    tmp_in = None
    tmp_out_path = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=ext_in, delete=False)
        tmp_in.write(input_bytes)
        tmp_in.close()

        tmp_out_path = tmp_in.name.replace(ext_in, "_converted.ogg")
        cmd = [
            "ffmpeg",
            "-i", tmp_in.name,
            "-c:a", "libopus",
            "-b:a", "48k",
            "-ar", "48000",
            "-ac", "1",
            "-application", "voip",
            "-f", "ogg",
            "-y",
            tmp_out_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("FFmpeg falhou (code=%d): %s", result.returncode, stderr_text)
            return None

        with open(tmp_out_path, "rb") as f:
            converted = f.read()

        if len(converted) < 100:
            logger.error("Arquivo convertido muito pequeno (%d bytes)", len(converted))
            return None

        logger.info(
            "Audio convertido: %s -> ogg/opus (%d -> %d bytes)",
            ext_in, len(input_bytes), len(converted)
        )
        return converted

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout na conversao de audio")
        return None
    except Exception as exc:
        logger.error("Erro na conversao de audio: %s", exc)
        return None
    finally:
        if tmp_in and os.path.isfile(tmp_in.name):
            try:
                os.remove(tmp_in.name)
            except OSError:
                pass
        if tmp_out_path and os.path.isfile(tmp_out_path):
            try:
                os.remove(tmp_out_path)
            except OSError:
                pass


async def get_media_url(media_id, token=None):
    token = token or WHATSAPP_TOKEN
    if not token:
        logger.error("WHATSAPP_TOKEN nao configurado")
        return None

    endpoint = f"{GRAPH_API_BASE}/{media_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code != 200:
                # NAO logar resp.text cru — pode ter URL assinada com token.
                # Loga apenas a mensagem de erro estruturada.
                err_msg = ""
                try:
                    err_msg = ((resp.json() or {}).get("error") or {}).get("message", "")
                except Exception:
                    err_msg = "<unparseable>"
                logger.error(
                    "Falha ao obter URL da midia %s | status=%s erro=%s",
                    media_id, resp.status_code, err_msg,
                )
                return None
            data = resp.json()
            return {
                "url": data.get("url", ""),
                "mime_type": data.get("mime_type", ""),
                "file_size": data.get("file_size", 0),
                "sha256": data.get("sha256", ""),
            }
        except Exception as exc:
            logger.error("Erro ao consultar midia %s: %s", media_id, exc)
            return None


async def download_media(media_id, msg_type, original_filename="", token=None):
    ensure_media_dir()

    token = token or WHATSAPP_TOKEN
    media_info = await get_media_url(media_id, token=token)
    if not media_info or not media_info["url"]:
        return None

    file_size = media_info.get("file_size", 0)
    if file_size > MAX_MEDIA_SIZE_MB * 1024 * 1024:
        logger.warning("Midia %s excede limite de %dMB", media_id, MAX_MEDIA_SIZE_MB)
        return None

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.get(media_info["url"], headers=headers)
            if resp.status_code != 200:
                logger.error("Falha no download da midia %s: HTTP %d", media_id, resp.status_code)
                return None

            content = resp.content
            mime = media_info["mime_type"]
            ext = _resolve_extension(mime, original_filename)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_id = hashlib.sha256(media_id.encode()).hexdigest()[:12]
            filename = f"{timestamp}_{safe_id}{ext}"
            subdir = get_subdir_for_type(msg_type)
            relative_path = _write_media_bytes(content, subdir, filename, mime or _default_mime_type(filename))

            logger.info("Midia salva: %s (%s, %d bytes)", relative_path, mime, len(content))
            result = {
                "path": relative_path,
                "mime_type": mime,
                "size": len(content),
                "filename": original_filename or filename,
            }
            # Retorna bytes apenas para audio (usado na transcricao STT)
            if msg_type == "audio":
                result["content"] = content
            return result

        except Exception as exc:
            logger.error("Erro no download da midia %s: %s", media_id, exc)
            return None


def detect_media_type(mime_type):
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    return "document"


async def save_upload_media(file_content, filename, mime_type):
    ensure_media_dir()

    msg_type = detect_media_type(mime_type)
    subdir = get_subdir_for_type(msg_type)
    ext = _resolve_extension(mime_type, filename)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_hash = hashlib.sha256(file_content[:1024]).hexdigest()[:12]
    safe_name = f"{timestamp}_{safe_hash}{ext}"
    relative_path = _write_media_bytes(file_content, subdir, safe_name, mime_type)

    logger.info("Upload salvo: %s (%s, %d bytes)", relative_path, mime_type, len(file_content))
    return {
        "path": relative_path,
        "mime_type": mime_type,
        "size": len(file_content),
        "msg_type": msg_type,
    }


async def save_upload_locally(file_content, filename, mime_type):
    return await save_upload_media(file_content, filename, mime_type)


async def upload_media_to_whatsapp(file_content, mime_type, filename="", token=None, phone_id=None):
    token = token or WHATSAPP_TOKEN
    phone_id = phone_id or WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_id:
        logger.error("WABA nao configurado para upload")
        return None

    url = f"{GRAPH_API_BASE}/{phone_id}/media"
    headers = {"Authorization": f"Bearer {token}"}

    if not filename:
        ext = MIME_EXTENSIONS.get(mime_type, ".bin")
        filename = f"upload{ext}"

    files = {"file": (filename, file_content, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, files=files, data=data)
            result = resp.json()
            if resp.status_code in (200, 201):
                media_id = result.get("id", "")
                logger.info("Upload para Meta OK: media_id=%s", media_id)
                return media_id
            error = result.get("error", {}).get("message", resp.text[:200])
            logger.error("Upload para Meta falhou: %s", error)
            return None
        except Exception as exc:
            logger.error("Erro no upload para Meta: %s", exc)
            return None


async def send_media_message(wa_id, media_id, msg_type, caption="", reply_wa_message_id="", token=None, phone_id=None):
    token = token or WHATSAPP_TOKEN
    phone_id = phone_id or WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_id:
        return None

    wa_id = _normalize_wa_target(wa_id)
    url = f"{GRAPH_API_BASE}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    media_object = {"id": media_id}
    if caption and msg_type in ("image", "video", "document"):
        media_object["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": msg_type,
        msg_type: media_object,
    }
    if reply_wa_message_id:
        payload["context"] = {"message_id": reply_wa_message_id}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            result = resp.json()
            if resp.status_code == 200:
                wa_msg_id = result.get("messages", [{}])[0].get("id", "")
                logger.info("[WA MEDIA OUT] %s -> %s (type=%s)", redact_phone(wa_id), wa_msg_id, msg_type)
                return {"wa_message_id": wa_msg_id, "status": "sent"}
            error = result.get("error", {}).get("message", "Erro desconhecido")
            logger.error("[WA MEDIA FAIL] %s: %s", redact_phone(wa_id), error)
            return {"error": error}
        except Exception as exc:
            logger.error("Erro ao enviar midia para %s: %s", redact_phone(wa_id), exc)
            return {"error": str(exc)}
```

## pending_events.py

```python
# -*- coding: utf-8 -*-

"""
Fila de webhooks pendentes — eventos da Meta que chegaram antes do canal
correspondente estar indexado no Firestore (race entre Embedded Signup
finalizar e o primeiro webhook chegar) ou cujo phone_number_id nao bate
com nenhum canal cadastrado.

Garantia: zero perda. Retornamos 200 imediatamente para a Meta nao
penalizar o endpoint, persistimos o payload bruto + motivo, e expomos
via UI admin pra retry/intervencao humana.

A colecao e GLOBAL (fora de tenants/) porque o tenant_id e desconhecido
ate o canal ser resolvido — esse e exatamente o motivo do evento estar
pendente.

Schema:
    {
        "id": int,
        "received_at": datetime,
        "change_field": str,           # "messages"/"smb_message_echoes"/etc
        "phone_number_id": str,        # do payload, pode estar vazio
        "reason": str,                 # "no_channel"/"no_default_channel"/...
        "status": "pending"|"resolved"|"failed",
        "attempts": int,
        "last_attempt_at": datetime|None,
        "last_error": str,
        "payload": dict,               # payload bruto da Meta
    }
"""

import logging
from datetime import datetime, timezone

from firestore_common import (
    global_collection,
    global_document,
    get_firestore_client,
    next_sequence,
    utcnow,
    normalize_record,
)

logger = logging.getLogger("castro_crm.pending_events")

PENDING_COLLECTION = "pending_webhook_events"

STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"
STATUS_FAILED = "failed"


def enqueue_pending_event(payload: dict, change_field: str,
                          phone_number_id: str, reason: str) -> int:
    """Persiste um evento pendente. Retorna event_id.

    Chamada do webhook quando o canal nao puder ser resolvido pra um
    change especifico. payload e o dict completo do webhook (entry+changes),
    nao apenas o change pendente — facilita retry posterior reusando
    process_webhook_payload.
    """
    event_id = next_sequence("pending_webhook_events")
    doc = {
        "id": event_id,
        "received_at": utcnow(),
        "change_field": str(change_field or ""),
        "phone_number_id": str(phone_number_id or ""),
        "reason": str(reason or ""),
        "status": STATUS_PENDING,
        "attempts": 0,
        "last_attempt_at": None,
        "last_error": "",
        "payload": payload,
    }
    global_document(PENDING_COLLECTION, event_id).set(doc)
    logger.warning(
        "[PENDING] Evento enfileirado | id=%s field=%s phone_id=%s reason=%s",
        event_id, change_field, phone_number_id, reason,
    )
    return event_id


def list_pending_events(status: str | None = None, limit: int = 100) -> list[dict]:
    """Lista eventos pendentes (mais recentes primeiro)."""
    q = global_collection(PENDING_COLLECTION)
    if status:
        q = q.where("status", "==", status)
    rows = []
    for snap in q.stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            try:
                data["id"] = int(snap.id)
            except (TypeError, ValueError):
                data["id"] = snap.id
        rows.append(data)
    rows.sort(
        key=lambda r: r.get("received_at") or datetime.fromtimestamp(0, tz=timezone.utc),
        reverse=True,
    )
    if limit:
        rows = rows[:limit]
    return [normalize_record(r) for r in rows]


def get_pending_event(event_id: int) -> dict | None:
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = event_id
    return normalize_record(data)


def mark_event_attempt(event_id: int, success: bool, error: str = "") -> None:
    """Atualiza contador de tentativas e status final."""
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return
    current = snap.to_dict() or {}
    attempts = int(current.get("attempts", 0)) + 1
    updates = {
        "attempts": attempts,
        "last_attempt_at": utcnow(),
        "last_error": "" if success else (error or "")[:500],
        "status": STATUS_RESOLVED if success else STATUS_PENDING,
    }
    global_document(PENDING_COLLECTION, event_id).set(updates, merge=True)


def mark_event_failed(event_id: int, error: str) -> None:
    """Marca um evento como definitivamente falho (nao retentar)."""
    global_document(PENDING_COLLECTION, event_id).set(
        {
            "status": STATUS_FAILED,
            "last_attempt_at": utcnow(),
            "last_error": (error or "")[:500],
        },
        merge=True,
    )


def delete_pending_event(event_id: int) -> bool:
    snap = global_document(PENDING_COLLECTION, event_id).get()
    if not snap.exists:
        return False
    global_document(PENDING_COLLECTION, event_id).delete()
    return True


def count_pending() -> int:
    """Conta eventos com status='pending'. Usado em badges/health."""
    count = 0
    for _ in global_collection(PENDING_COLLECTION).where("status", "==", STATUS_PENDING).stream():
        count += 1
    return count
```

## pii_redaction.py

```python
# -*- coding: utf-8 -*-
"""
Helpers de redacao para conformidade LGPD em logs.

Diretriz CLAUDE.md secao 2: tokens, secrets e PII jamais em logs cleartext.

Estes helpers permitem manter logs informativos pra debugging sem expor
dados pessoais de clientes (telefone, nome, email) ou credenciais.
"""

from __future__ import annotations


def redact_phone(phone: str | None, keep_last: int = 4) -> str:
    """Mantem apenas os N ultimos digitos visiveis.

    >>> redact_phone("5531999998888")
    '***8888'
    >>> redact_phone("31999998888", keep_last=2)
    '***88'
    >>> redact_phone(None)
    '***'
    >>> redact_phone("")
    '***'
    """
    if not phone:
        return "***"
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) <= keep_last:
        return "***"
    return f"***{digits[-keep_last:]}"


def redact_name(name: str | None) -> str:
    """Retorna primeira letra + comprimento total. Ex.: 'Joao' -> 'J*** (4)'.

    Para nomes vazios/None retorna apenas '***'. Util pra distinguir
    contatos diferentes sem expor identidade.
    """
    if not name:
        return "***"
    s = str(name).strip()
    if not s:
        return "***"
    return f"{s[0]}*** ({len(s)})"


def redact_secret(value: str | None, keep_first: int = 0) -> str:
    """Retorna placeholder ou prefixo curto pra debug.

    Default: nao mostra nada do valor (keep_first=0 -> '<redacted>').
    Com keep_first>0, mostra os N primeiros chars (uso raro, pra
    distinguir versoes de token).
    """
    if not value:
        return "<empty>"
    s = str(value)
    if keep_first <= 0:
        return "<redacted>"
    return f"{s[:keep_first]}***"
```

## seed_gchat.py

```python
# -*- coding: utf-8 -*-

"""
Script de seed para popular o Firestore com dados de teste do Google Chat.
Simula conversas entre operadores e supervisores.

Uso:
  python seed_gchat.py

Requer FIRESTORE_PROJECT_ID configurado no .env ou variavel de ambiente.
"""

from datetime import datetime, timedelta, timezone

from firestore_common import collection, document, next_sequence, utcnow


def seed():
    now = utcnow()

    # --- Conversa 1: Patio de Maquinas ---
    conv1_id = next_sequence("gc_conversations")
    document("gc_conversations", conv1_id).set({
        "id": conv1_id,
        "space_id": "spaces/test_patio_001",
        "space_name": "Patio de Maquinas",
        "participants": ["ana@centralloc.com.br", "beto@centralloc.com.br"],
        "last_message": "Tem 3 betoneiras disponiveis, pode fechar",
        "last_message_at": now - timedelta(minutes=2),
        "unread_count": {},
        "created_at": now - timedelta(days=5),
    })

    messages_patio = [
        ("ana@centralloc.com.br", "Ana Silva", "crm", "Beto, tem betoneira 400L disponivel?", -30),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Deixa eu verificar aqui no patio", -28),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Tem 3 unidades. Todas revisadas semana passada", -25),
        ("ana@centralloc.com.br", "Ana Silva", "crm", "O cliente quer desconto de 10%, posso dar?", -20),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "10% pode sim, ta parada ha 2 semanas", -18),
        ("ana@centralloc.com.br", "Ana Silva", "crm", "Fechado! Vou confirmar com o cliente", -15),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Tem 3 betoneiras disponiveis, pode fechar", -2),
    ]

    for sender_email, sender_name, source, content, minutes_ago in messages_patio:
        msg_id = next_sequence("gc_messages")
        document("gc_messages", msg_id).set({
            "id": msg_id,
            "conversation_id": conv1_id,
            "gchat_message_id": f"spaces/test_patio_001/messages/test_{msg_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "msg_type": "text",
            "content": content,
            "media_path": "",
            "media_mime": "",
            "source": source,
            "create_time": now + timedelta(minutes=minutes_ago),
            "created_at": now + timedelta(minutes=minutes_ago),
        })

    # --- Conversa 2: Logistica ---
    conv2_id = next_sequence("gc_conversations")
    document("gc_conversations", conv2_id).set({
        "id": conv2_id,
        "space_id": "spaces/test_logistica_002",
        "space_name": "Logistica e Entregas",
        "participants": ["carlos@centralloc.com.br", "diana@centralloc.com.br"],
        "last_message": "Caminhao saiu as 14h, chega em 2h",
        "last_message_at": now - timedelta(hours=1),
        "unread_count": {},
        "created_at": now - timedelta(days=3),
    })

    messages_logistica = [
        ("carlos@centralloc.com.br", "Carlos Lima", "crm", "Diana, qual o status da entrega do pedido #4521?", -120),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "Estou carregando o caminhao agora", -115),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "2 escoras + 1 andaime, tudo conferido", -110),
        ("carlos@centralloc.com.br", "Carlos Lima", "crm", "Beleza, o cliente ta perguntando previsao de chegada", -90),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "Caminhao saiu as 14h, chega em 2h", -60),
    ]

    for sender_email, sender_name, source, content, minutes_ago in messages_logistica:
        msg_id = next_sequence("gc_messages")
        document("gc_messages", msg_id).set({
            "id": msg_id,
            "conversation_id": conv2_id,
            "gchat_message_id": f"spaces/test_logistica_002/messages/test_{msg_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "msg_type": "text",
            "content": content,
            "media_path": "",
            "media_mime": "",
            "source": source,
            "create_time": now + timedelta(minutes=minutes_ago),
            "created_at": now + timedelta(minutes=minutes_ago),
        })

    # --- Conversa 3: Manutencao (vazia - so o space) ---
    conv3_id = next_sequence("gc_conversations")
    document("gc_conversations", conv3_id).set({
        "id": conv3_id,
        "space_id": "spaces/test_manutencao_003",
        "space_name": "Manutencao Preventiva",
        "participants": [],
        "last_message": "",
        "last_message_at": now - timedelta(days=1),
        "unread_count": {},
        "created_at": now - timedelta(days=1),
    })

    print(f"Seed concluido!")
    print(f"  - Conversa '{conv1_id}': Patio de Maquinas (7 mensagens)")
    print(f"  - Conversa '{conv2_id}': Logistica e Entregas (5 mensagens)")
    print(f"  - Conversa '{conv3_id}': Manutencao Preventiva (vazia)")


if __name__ == "__main__":
    seed()
```

## tenant_service.py

```python
# -*- coding: utf-8 -*-
"""
Servico de Tenants — Fase 2 multi-tenant.

Cada tenant representa um cliente B2B (imobiliaria, clinica, locadora)
operando dentro do mesmo Castro CRM. A Castro Intelligence (provedor)
gerencia os tenants via super-admin; cada tenant tem seu proprio
conjunto isolado de operadores, canais WhatsApp, contatos e mensagens
em subcolecao Firestore tenants/{tenant_id}/...

Modelo do doc principal:
    <prefix>_tenants/{tenant_id}
        ├── name: str
        ├── slug: str (alias humano, ex: "hubloc", "clinica-vida")
        ├── cnpj: str
        ├── plan: str (starter | professional | enterprise | premium)
        ├── is_active: bool
        ├── settings: dict (logo_url, brand_color, default_locale)
        ├── billing: dict (status, next_due, ...)
        ├── created_at, updated_at: ISO datetime

A coleção root tenants/ e os docs sao acessados via Admin SDK
(backend), nunca diretamente do frontend. Operadores leem apenas o
proprio doc do tenant deles para exibir nome/branding.

Uso:
    from tenant_service import (
        get_tenant, list_tenants, create_tenant,
        update_tenant, deactivate_tenant,
    )
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

from firestore_common import (
    collection_name,
    get_firestore_client,
    global_collection,
    global_document,
    normalize_record,
    tenant_doc_ref,
    utcnow,
)

logger = logging.getLogger("castro_crm.tenants")

PLAN_OPTIONS = ("starter", "professional", "enterprise", "premium")

_SLUG_RE = re.compile(r"^[a-z][a-z0-9\-]{2,63}$")


# ---------------------------------------------------------------------------
# Cache em memoria (thread-safe)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_tenants_by_id: dict[str, dict] = {}
# None = cache nunca foi populado (forca refresh na primeira call). Usar
# valor numerico inicial 0 era bug: time.monotonic() retorna seconds desde
# o container boot — pequeno na primeira call — entao 0 - 0.5 < 60 e o
# refresh nao era disparado, deixando o cache vazio ate o TTL expirar.
_last_refresh: float | None = None
_CACHE_TTL_SECONDS = 60


def _needs_refresh() -> bool:
    if _last_refresh is None:
        return True
    return time.monotonic() - _last_refresh > _CACHE_TTL_SECONDS


def refresh_tenants() -> None:
    """Recarrega todos os tenants ativos do Firestore para o cache."""
    global _last_refresh

    rows: dict[str, dict] = {}
    for snap in global_collection("tenants").stream():
        data = snap.to_dict() or {}
        if "id" not in data:
            data["id"] = snap.id
        rows[str(data["id"])] = data

    with _lock:
        _tenants_by_id.clear()
        _tenants_by_id.update(rows)
        _last_refresh = time.monotonic()

    logger.info("Tenant cache refreshed: %d tenants", len(rows))


def _ensure_cache() -> None:
    if _needs_refresh():
        refresh_tenants()


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def get_tenant(tenant_id: str) -> dict | None:
    """Retorna o doc do tenant pelo id (slug)."""
    if not tenant_id:
        return None
    _ensure_cache()
    with _lock:
        cached = _tenants_by_id.get(str(tenant_id))
    if cached:
        return normalize_record(cached)
    # Fallback: leitura direta caso o cache esteja stale.
    snap = tenant_doc_ref(tenant_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    if "id" not in data:
        data["id"] = snap.id
    return normalize_record(data)


def list_tenants(active_only: bool = True) -> list[dict]:
    """Retorna lista de tenants. Filtro padrao: somente ativos."""
    _ensure_cache()
    with _lock:
        rows = list(_tenants_by_id.values())
    if active_only:
        rows = [t for t in rows if t.get("is_active", True)]
    rows.sort(key=lambda t: str(t.get("name") or t.get("id") or ""))
    return [normalize_record(t) for t in rows]


def tenant_exists(tenant_id: str) -> bool:
    return get_tenant(tenant_id) is not None


# ---------------------------------------------------------------------------
# Escrita (super-admin Castro Intelligence)
# ---------------------------------------------------------------------------

def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug or ""):
        raise ValueError(
            "Slug invalido. Use minusculas, comeco com letra, 3-64 chars, "
            "apenas a-z, 0-9 e hifen."
        )


def create_tenant(
    tenant_id: str,
    name: str,
    cnpj: str = "",
    plan: str = "professional",
    settings: dict | None = None,
    billing: dict | None = None,
) -> dict:
    """Cria um novo tenant. Retorna o doc criado.

    O tenant_id e tambem o slug do path (tenants/{tenant_id}). Deve ser
    URL-safe e estavel (nao mudar depois).
    """
    _validate_slug(tenant_id)
    if not name or not name.strip():
        raise ValueError("name obrigatorio")
    if plan not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    if tenant_exists(tenant_id):
        raise ValueError(f"Tenant '{tenant_id}' ja existe")

    now = utcnow()
    doc = {
        "id": tenant_id,
        "name": name.strip(),
        "slug": tenant_id,
        "cnpj": (cnpj or "").strip(),
        "plan": plan,
        "is_active": True,
        "settings": settings or {},
        "billing": billing or {"status": "trial", "next_due": None},
        "created_at": now,
        "updated_at": now,
    }
    tenant_doc_ref(tenant_id).set(doc)
    refresh_tenants()
    logger.info("Tenant criado: id=%s name=%s plan=%s", tenant_id, name, plan)
    return normalize_record(doc)


def update_tenant(tenant_id: str, **fields: Any) -> bool:
    """Atualiza campos do tenant. Retorna True se atualizou."""
    allowed = {"name", "cnpj", "plan", "settings", "billing", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "plan" in updates and updates["plan"] not in PLAN_OPTIONS:
        raise ValueError(f"plan invalido. Opcoes: {', '.join(PLAN_OPTIONS)}")
    updates["updated_at"] = utcnow()
    tenant_doc_ref(tenant_id).set(updates, merge=True)
    refresh_tenants()
    return True


def deactivate_tenant(tenant_id: str) -> bool:
    """Marca tenant como inativo (soft delete). Dados permanecem."""
    return update_tenant(tenant_id, is_active=False)


def activate_tenant(tenant_id: str) -> bool:
    return update_tenant(tenant_id, is_active=True)


# ---------------------------------------------------------------------------
# phone_routing — indice global phone_number_id -> tenant_id + channel_id
# ---------------------------------------------------------------------------

def upsert_phone_routing(phone_number_id: str, tenant_id: str, channel_id) -> None:
    """Atualiza/cria o indice phone_routing/{phone_number_id} para
    permitir que o webhook resolva tenant a partir do payload da Meta
    em O(1).
    """
    if not phone_number_id:
        raise ValueError("phone_number_id obrigatorio")
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    global_document("phone_routing", phone_number_id).set(
        {
            "tenant_id": str(tenant_id),
            "channel_id": channel_id,
            "updated_at": utcnow(),
        },
        merge=True,
    )


def lookup_phone_routing(phone_number_id: str) -> dict | None:
    """Retorna {tenant_id, channel_id} para um phone_number_id, ou None."""
    if not phone_number_id:
        return None
    snap = global_document("phone_routing", phone_number_id).get()
    if not snap.exists:
        return None
    return snap.to_dict() or None


def remove_phone_routing(phone_number_id: str) -> None:
    """Remove a entrada de routing (chamado quando canal e desativado)."""
    if not phone_number_id:
        return
    global_document("phone_routing", phone_number_id).delete()
```

## test_meta_app_review.py

```python
# -*- coding: utf-8 -*-
"""
Script para executar as chamadas de API necessarias para completar
os testes de caso de uso na revisao do app Meta.

Uso:
  python test_meta_app_review.py
  python test_meta_app_review.py --token SEU_TOKEN
  python test_meta_app_review.py --section whatsapp_business_management
  python test_meta_app_review.py --dry-run

Secoes disponiveis:
  whatsapp_business_management, whatsapp_business_messaging,
  public_profile

Permissions FORA do escopo do produto (revisao 2026-05-08):
  - business_management: reprovada pela Meta — e permission de Ads
    Manager (manage ad accounts, impressions, conversions), nao de
    Embedded Signup do WhatsApp.
  - manage_app_solution: nao se aplica — Castro Intelligence atende
    clientes finais como Tech Provider direto, nao intermedia
    Solution Partners.
  - whatsapp_business_manage_events: caso de uso e Conversions API
    for WhatsApp (eventos de conversao para Meta Events Manager) —
    feature nao implementada no produto. Pedir sem implementacao
    levaria a mesma reprovacao que business_management.

As funcoes correspondentes permanecem comentadas como referencia
historica — caso o roadmap mude e essas perms voltem ao escopo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Carrega .env
# ---------------------------------------------------------------------------

def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
APP_ID = os.getenv("META_APP_ID", "")
APP_SECRET = os.getenv("META_APP_SECRET", "")

# Token de usuario temporario (Graph API Explorer) tem mais permissoes
# que o system user token para fins de teste de app review
DEFAULT_TOKEN = os.getenv("authorization_bearer_token_temp", "") or os.getenv("WHATSAPP_TOKEN", "")

# Numero de teste para envio de mensagem (use seu proprio numero)
TEST_PHONE = "5531971957758"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_call(method: str, path: str, token: str, params: dict | None = None,
             body: dict | None = None, label: str = "") -> dict:
    """Faz uma chamada a Graph API e retorna o resultado."""
    url = f"{GRAPH_API_BASE}/{path.lstrip('/')}"

    if method == "GET" and params:
        url += "?" + urlencode({**params, "access_token": token})
    elif method == "GET":
        url += "?" + urlencode({"access_token": token})

    headers = {"Accept": "application/json"}

    data = None
    if method in ("POST", "DELETE") and body is not None:
        merged = {**body, "access_token": token}
        data = json.dumps(merged).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif method in ("POST", "DELETE"):
        data = urlencode({"access_token": token}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw) if raw.strip() else {}
            return {"ok": True, "status": response.status, "body": result}
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            error_body = json.loads(raw_body)
        except json.JSONDecodeError:
            error_body = raw_body
        return {"ok": False, "status": exc.code, "body": error_body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def print_result(label: str, result: dict) -> None:
    ok = result.get("ok", False)
    status = result.get("status", "?")
    icon = "OK" if ok else "FALHOU"
    print(f"  [{icon}] {label} (HTTP {status})")
    if not ok:
        body = result.get("body", result.get("error", ""))
        if isinstance(body, dict):
            error = body.get("error", {})
            if isinstance(error, dict):
                print(f"         code={error.get('code')} {error.get('message', '')[:120]}")
            else:
                print(f"         {str(body)[:150]}")
        else:
            print(f"         {str(body)[:150]}")


def run_test(label: str, method: str, path: str, token: str,
             params: dict | None = None, body: dict | None = None,
             dry_run: bool = False) -> dict:
    if dry_run:
        print(f"  [DRY] {label}: {method} /{path}")
        return {"ok": True, "dry_run": True}
    result = api_call(method, path, token, params=params, body=body, label=label)
    print_result(label, result)
    return result


# ---------------------------------------------------------------------------
# Secao 1: business_management — DESCONTINUADA (App Review 2026-05-08)
# ---------------------------------------------------------------------------
# A Meta reprovou em 2026-05-08 explicando que essa permission e para
# gerenciar Ad Accounts (impressions, conversions, ad spend) — nao tem
# relacao com Embedded Signup do WhatsApp. O fluxo de coexistence usa
# whatsapp_business_management + whatsapp_business_messaging (ambas
# aprovadas Advanced) + featureType=whatsapp_business_app_onboarding
# no popup do FB.login. Codigo abaixo preservado como referencia.
#
# def test_business_management(token: str, dry_run: bool = False) -> None:
#     print("\n=== business_management (0/1 obrigatoria) ===\n")
#     run_test("GET /me/businesses", "GET", "me/businesses",
#              token, params={"fields": "id,name,created_time"}, dry_run=dry_run)
#     run_test("GET /app", "GET", APP_ID,
#              token, params={"fields": "id,name,category"}, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 2: whatsapp_business_management
# ---------------------------------------------------------------------------

def test_whatsapp_business_management(token: str, dry_run: bool = False) -> None:
    print("\n=== whatsapp_business_management ===\n")

    # WABA info
    run_test("GET WABA info", "GET", WABA_ID,
             token, params={"fields": "id,name,currency,timezone_id,message_template_namespace"},
             dry_run=dry_run)

    # Phone numbers na WABA
    run_test("GET WABA phone_numbers", "GET", f"{WABA_ID}/phone_numbers",
             token, params={"fields": "id,display_phone_number,verified_name,quality_rating,status,platform_type,code_verification_status,name_status"},
             dry_run=dry_run)

    # Phone number individual
    run_test("GET phone number detail", "GET", PHONE_NUMBER_ID,
             token, params={"fields": "id,display_phone_number,verified_name,quality_rating,status,platform_type,code_verification_status"},
             dry_run=dry_run)

    # Message templates
    run_test("GET message_templates", "GET", f"{WABA_ID}/message_templates",
             token, params={"fields": "id,name,status,language,category,components"},
             dry_run=dry_run)

    # Subscribed apps (verificar inscricao do webhook)
    run_test("GET subscribed_apps", "GET", f"{WABA_ID}/subscribed_apps",
             token, dry_run=dry_run)

    # POST subscribe (idempotente — nao causa problemas)
    run_test("POST subscribed_apps", "POST", f"{WABA_ID}/subscribed_apps",
             token, dry_run=dry_run)

    # Analytics (ultimos 30 dias)
    run_test("GET analytics", "GET", f"{WABA_ID}/analytics",
             token, params={
                 "fields": "phone_numbers,granularity,data_points",
                 "granularity": "DAILY",
                 "start": str(int(time.time()) - 30 * 86400),
                 "end": str(int(time.time())),
             }, dry_run=dry_run)

    # Conversation analytics
    run_test("GET conversation_analytics", "GET", f"{WABA_ID}/conversation_analytics",
             token, params={
                 "granularity": "DAILY",
                 "start": str(int(time.time()) - 30 * 86400),
                 "end": str(int(time.time())),
             }, dry_run=dry_run)

    # Business profile do numero
    run_test("GET business_profile", "GET", f"{PHONE_NUMBER_ID}/whatsapp_business_profile",
             token, params={"fields": "about,address,description,email,profile_picture_url,websites,vertical"},
             dry_run=dry_run)

    # Commerce settings
    run_test("GET whatsapp_commerce_settings", "GET", f"{PHONE_NUMBER_ID}/whatsapp_commerce_settings",
             token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 3: whatsapp_business_messaging
# ---------------------------------------------------------------------------

def test_whatsapp_business_messaging(token: str, dry_run: bool = False) -> None:
    print("\n=== whatsapp_business_messaging ===\n")

    # Enviar mensagem de texto
    result = run_test("POST send text message", "POST", f"{PHONE_NUMBER_ID}/messages",
             token, body={
                 "messaging_product": "whatsapp",
                 "to": TEST_PHONE,
                 "type": "text",
                 "text": {"body": "Teste de validacao do app Meta - mensagem de texto"}
             }, dry_run=dry_run)

    # Marcar como lida (precisa de um message_id real)
    msg_id = None
    if result.get("ok") and not dry_run:
        messages = result.get("body", {}).get("messages", [])
        if messages:
            msg_id = messages[0].get("id")

    if msg_id:
        run_test("POST mark_as_read", "POST", f"{PHONE_NUMBER_ID}/messages",
                 token, body={
                     "messaging_product": "whatsapp",
                     "status": "read",
                     "message_id": msg_id
                 }, dry_run=dry_run)
    else:
        print("  [SKIP] mark_as_read - sem message_id (precisa de msg inbound recente)")

    # Enviar template (hello_world e um template padrao que existe em todas as WABAs)
    run_test("POST send template message", "POST", f"{PHONE_NUMBER_ID}/messages",
             token, body={
                 "messaging_product": "whatsapp",
                 "to": TEST_PHONE,
                 "type": "template",
                 "template": {
                     "name": "hello_world",
                     "language": {"code": "en_US"}
                 }
             }, dry_run=dry_run)

    # Upload de media (text file simples como teste)
    print("  [INFO] Para teste de media upload, use o Graph API Explorer manualmente")


# ---------------------------------------------------------------------------
# Secao 4: whatsapp_business_manage_events — DESCONTINUADA (2026-05-08)
# ---------------------------------------------------------------------------
# Caso de uso real dessa permission e Conversions API for WhatsApp —
# enviar eventos (Purchase, Lead, AddToCart) para Meta Events Manager
# e mensurar ROI de anuncios click-to-WhatsApp. Feature nao
# implementada no produto. Pedir sem implementacao levaria a mesma
# reprovacao que business_management ("nao demonstra caso de uso").
# A implementacao original abaixo testava webhook subscriptions
# (GET/POST /APP_ID/subscriptions), o que nao requer essa permission.
#
# def test_whatsapp_business_manage_events(token: str, dry_run: bool = False) -> None:
#     print("\n=== whatsapp_business_manage_events ===\n")
#     app_token = f"{APP_ID}|{APP_SECRET}" if APP_ID and APP_SECRET else ""
#     if not app_token:
#         print("  [SKIP] META_APP_ID ou META_APP_SECRET nao configurado")
#         return
#     run_test("GET app subscriptions", "GET", f"{APP_ID}/subscriptions",
#              app_token, dry_run=dry_run)
#     run_test("POST subscribe webhook field", "POST", f"{APP_ID}/subscriptions",
#              app_token, body={
#                  "object": "whatsapp_business_account",
#                  "fields": "messages",
#                  "callback_url": "https://castro-crm-286866630844.southamerica-east1.run.app/webhook",
#                  "verify_token": "castro-webhook-2026",
#              }, dry_run=dry_run)
#     run_test("GET WABA subscribed_apps", "GET", f"{WABA_ID}/subscribed_apps",
#              token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Secao 5: public_profile
# ---------------------------------------------------------------------------

def test_public_profile(token: str, dry_run: bool = False) -> None:
    print("\n=== public_profile ===\n")

    # Perfil do usuario autenticado
    run_test("GET /me", "GET", "me",
             token, params={"fields": "id,name"}, dry_run=dry_run)

    # Perfil com mais campos
    run_test("GET /me (extended)", "GET", "me",
             token, params={"fields": "id,name,email"}, dry_run=dry_run)

    # Accounts (paginas)
    run_test("GET /me/accounts", "GET", "me/accounts",
             token, params={"fields": "id,name,category"}, dry_run=dry_run)

    # Permissions
    run_test("GET /me/permissions", "GET", "me/permissions",
             token, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_SECTIONS = {
    # Permissions fora do escopo (revisao 2026-05-08) — ver header:
    #   business_management, manage_app_solution,
    #   whatsapp_business_manage_events.
    "whatsapp_business_management": test_whatsapp_business_management,
    "whatsapp_business_messaging": test_whatsapp_business_messaging,
    "public_profile": test_public_profile,
}

def main() -> int:
    parser = argparse.ArgumentParser(description="Testes de caso de uso para app review Meta")
    parser.add_argument("--token", default="", help="Token de acesso (default: authorization_bearer_token_temp do .env)")
    parser.add_argument("--section", default="all", choices=["all", *ALL_SECTIONS.keys()],
                        help="Qual secao testar (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria executado")
    parser.add_argument("--test-phone", default="", help="Numero de telefone para envio de teste")
    args = parser.parse_args()

    token = args.token or DEFAULT_TOKEN
    if not token:
        print("ERRO: Nenhum token disponivel.", file=sys.stderr)
        print("Use --token SEU_TOKEN ou configure authorization_bearer_token_temp no .env", file=sys.stderr)
        return 1

    global TEST_PHONE
    if args.test_phone:
        TEST_PHONE = args.test_phone

    print(f"Graph API: {GRAPH_API_BASE}")
    print(f"App ID: {APP_ID}")
    print(f"WABA ID: {WABA_ID}")
    print(f"Phone ID: {PHONE_NUMBER_ID}")
    print(f"Token: ...{token[-12:]}")
    print(f"Test Phone: {TEST_PHONE}")
    print(f"Dry Run: {args.dry_run}")

    if args.section == "all":
        for name, func in ALL_SECTIONS.items():
            func(token, dry_run=args.dry_run)
    else:
        ALL_SECTIONS[args.section](token, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print("Concluido! Verifique no App Dashboard > Testar Casos de Uso")
    print("se as chamadas foram registradas (pode levar ate 24h).")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## transcription_service.py

```python
# -*- coding: utf-8 -*-

from __future__ import annotations

"""
Transcricao de audio via Faster Whisper (CTranslate2).
Substitui o fluxo anterior baseado em Google Cloud Speech-to-Text.
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger("castro_crm.transcription")

_whisper_model = None

# Tamanho do modelo. Opcoes comuns: tiny, base, small, medium, large-v3.
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")

# Dispositivo: cpu, cuda ou auto.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")

# Tipo de computacao: int8, float16, int8_float16.
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_MIME_EXTENSION_MAP = {
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/opus": ".ogg",
    "application/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/amr": ".amr",
    "audio/amr-wb": ".amr",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
}


def init_speech_client():
    """Inicializa o modelo Faster Whisper uma vez. Retorna True se ok."""
    global _whisper_model
    if _whisper_model is not None:
        return True
    try:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        logger.info(
            "Faster Whisper carregado | modelo=%s | device=%s | compute=%s",
            WHISPER_MODEL_SIZE,
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
        return True
    except Exception as exc:
        logger.error("Falha ao carregar Faster Whisper: %s", exc, exc_info=True)
        _whisper_model = None
        return False


def get_speech_client():
    return _whisper_model


def _resolve_extension(media_mime: str | None) -> str:
    mime = (media_mime or "").lower().strip()
    ext = _MIME_EXTENSION_MAP.get(mime)
    if not ext:
        for key, value in _MIME_EXTENSION_MAP.items():
            if mime.startswith(key.split(";")[0].strip()):
                ext = value
                break
    return ext or ".ogg"


def _convert_to_wav(audio_bytes: bytes, input_ext: str) -> bytes | None:
    """
    Converte audio arbitrario para WAV 16kHz mono via FFmpeg para reduzir
    problemas de codec no processo de transcricao.
    """
    tmp_in = None
    tmp_out = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=input_ext, delete=False)
        tmp_in.write(audio_bytes)
        tmp_in.close()

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_out.close()

        cmd = [
            "ffmpeg",
            "-i",
            tmp_in.name,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            "-y",
            tmp_out.name,
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("FFmpeg conversao falhou (code=%d): %s", result.returncode, stderr_text)
            return None

        with open(tmp_out.name, "rb") as fh:
            wav_data = fh.read()

        if len(wav_data) < 100:
            logger.error("WAV convertido muito pequeno (%d bytes)", len(wav_data))
            return None

        return wav_data
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout na conversao para WAV")
        return None
    except Exception as exc:
        logger.error("Erro na conversao para WAV: %s", exc)
        return None
    finally:
        for handle in (tmp_in, tmp_out):
            if handle is not None:
                try:
                    os.unlink(handle.name if hasattr(handle, "name") else handle)
                except OSError:
                    pass


def transcribe_audio_bytes(
    audio_content: bytes,
    *,
    media_mime: str | None = None,
    language_code: str = "pt-BR",
    timeout_s: float = 30.0,
) -> str:
    """
    Transcreve bytes de audio usando Faster Whisper.
    Mantem a assinatura compativel com a implementacao anterior.
    """
    model = get_speech_client()
    if model is None or not audio_content:
        return ""

    whisper_lang = language_code.split("-")[0].lower() if language_code else "pt"

    tmp_audio = None
    try:
        input_ext = _resolve_extension(media_mime)
        wav_data = _convert_to_wav(audio_content, input_ext)

        if wav_data is None:
            logger.warning("Conversao WAV falhou, tentando arquivo original")
            tmp_audio = tempfile.NamedTemporaryFile(suffix=input_ext, delete=False)
            tmp_audio.write(audio_content)
            tmp_audio.close()
            audio_path = tmp_audio.name
        else:
            tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_audio.write(wav_data)
            tmp_audio.close()
            audio_path = tmp_audio.name

        segments, info = model.transcribe(
            audio_path,
            language=whisper_lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 200,
            },
        )

        parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)

        transcript = " ".join(parts).strip()
        if transcript:
            logger.info(
                "Transcricao concluida | idioma=%s | prob=%.2f | caracteres=%d",
                info.language,
                info.language_probability,
                len(transcript),
            )
        return transcript
    except Exception as exc:
        logger.error("Falha na transcricao Faster Whisper: %s", exc, exc_info=True)
        return ""
    finally:
        if tmp_audio is not None:
            try:
                os.unlink(tmp_audio.name)
            except OSError:
                pass
```

## webhook.py

```python
# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from config import (
    REQUIRE_WEBHOOK_SIGNATURE, WHATSAPP_APP_SECRET,
    FEATURE_AUDIO_TRANSCRIPTION, FEATURE_MESSAGE_STATUS,
    STT_LANGUAGE_CODE, STT_TIMEOUT_SECONDS, STT_FALLBACK_TEXT,
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_TOKEN,
)
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit,
    update_wa_message_transcription,
    get_user_by_id, get_wa_message_by_wa_message_id, get_wa_contact,
    assign_wa_contact, update_wa_contact_qualification,
    normalize_br_phone,
)
from media import download_media
from channel_service import get_channel_by_phone_id, get_default_channel, CHANNEL_TYPE_COEXISTENCE
from bot_service import process_bot_message
from firestore_common import set_tenant_context, reset_tenant_context
from tenant_service import lookup_phone_routing
from pii_redaction import redact_phone, redact_name
from pending_events import enqueue_pending_event

logger = logging.getLogger("castro_crm.webhook")

# Tenant default usado quando o webhook recebe payload sem phone_number_id
# valido OU quando phone_routing ainda nao tem entrada pra esse numero.
# Sub-fase: enquanto canais sao flat, canal default pertence a 'hubloc'.
_WEBHOOK_DEFAULT_TENANT = "hubloc"


def _resolve_webhook_tenant(channel, phone_number_id: str | None = None):
    """Resolve tenant_id pra um payload de webhook.

    Ordem de preferencia (Fase 2C):
      1. `phone_routing[phone_number_id]` se phone_number_id for fornecido
         e existir indice (caminho oficial pra multi-tenant).
      2. `channel.tenant_id` denormalizado no doc do canal (fallback
         enquanto canais nao migram pra subcolecao).
      3. `_WEBHOOK_DEFAULT_TENANT` (single-tenant Hubloc).
    """
    if phone_number_id:
        try:
            routing = lookup_phone_routing(str(phone_number_id))
        except Exception as exc:
            logger.warning("phone_routing lookup falhou para %s: %s", phone_number_id, exc)
            routing = None
        if routing and routing.get("tenant_id"):
            return str(routing["tenant_id"])
    if channel and channel.get("tenant_id"):
        return str(channel["tenant_id"])
    return _WEBHOOK_DEFAULT_TENANT


def _fallback_reply_preview(message):
    content = str(message.get("content") or "").strip()
    if content:
        return content

    transcription = str(message.get("transcription") or "").strip()
    if transcription:
        return transcription

    filename = str(message.get("filename") or "").strip()
    msg_type = str(message.get("msg_type") or "").strip().lower()
    labels = {
        "audio": "Audio",
        "document": "Documento",
        "gif": "Video",
        "image": "Imagem",
        "location": "Localizacao",
        "sticker": "Figurinha",
        "template": "Template",
        "video": "Video",
    }
    if filename and msg_type in labels:
        return f"{labels[msg_type]}: {filename}"
    return labels.get(msg_type, "Mensagem")


def _fallback_reply_sender(message):
    direction = str(message.get("direction") or "").strip().lower()
    if direction == "inbound":
        return "Cliente"
    if direction == "system":
        return "Sistema"
    operator_id = message.get("operator_id")
    operator = get_user_by_id(operator_id) if operator_id else None
    return str((operator or {}).get("display_name") or "Equipe")


def _resolve_reply_reference(contact_id, message_context):
    context = message_context if isinstance(message_context, dict) else {}
    original_wa_message_id = str(context.get("id") or "").strip()
    if not original_wa_message_id:
        return {}

    original_message = get_wa_message_by_wa_message_id(original_wa_message_id)
    if not original_message:
        logger.info("Resposta recebida sem mensagem original local | wa_context_id=%s", original_wa_message_id[:32])
        return {}
    if int(original_message.get("contact_id") or 0) != int(contact_id):
        logger.warning(
            "Resposta recebida com contexto de outro contato | contact_id=%s original_contact_id=%s wa_context_id=%s",
            contact_id,
            original_message.get("contact_id"),
            original_wa_message_id[:32],
        )
        return {}

    return {
        "reply_to_message_id": int(original_message.get("id") or 0) or None,
        "reply_to_preview": _fallback_reply_preview(original_message)[:280],
        "reply_to_sender_name": _fallback_reply_sender(original_message)[:80],
    }


def validate_signature(payload_bytes, signature_header):
    """
    Valida assinatura HMAC-SHA256 do webhook da Meta.
    Em dev pode operar sem APP_SECRET; em runtime endurecido a assinatura e obrigatoria.
    """
    if not WHATSAPP_APP_SECRET:
        return not REQUIRE_WEBHOOK_SIGNATURE

    if not signature_header:
        logger.warning("Webhook recebido sem assinatura")
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    received = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected, received)


def _resolve_webhook_channel(value):
    """Resolve o canal a partir dos metadados do webhook.

    Retorna (channel_dict, reason) onde reason e:
      - None: canal resolvido normalmente.
      - 'no_phone_number_id': metadata sem phone_number_id.
      - 'no_channel_for_phone': phone_id nao bate com canal cadastrado.
      - 'no_default_channel': fallback default tambem nao existe.

    Quando channel e None, o caller deve enfileirar em
    pending_webhook_events em vez de processar com canal sintetico
    (default__) que nao casa com selectedThreadId no frontend.
    """
    metadata = value.get("metadata", {})
    phone_number_id = str(metadata.get("phone_number_id", "")).strip()

    if phone_number_id:
        channel = get_channel_by_phone_id(phone_number_id)
        if channel:
            return channel, None
        logger.warning(
            "Webhook: phone_number_id=%s nao bate com nenhum canal cadastrado.",
            phone_number_id,
        )
        default = get_default_channel()
        if default:
            return default, "no_channel_for_phone"
        return None, "no_channel_for_phone"

    logger.warning(
        "Webhook: metadata sem phone_number_id. Payload metadata=%s",
        metadata,
    )
    default = get_default_channel()
    if default:
        return default, "no_phone_number_id"
    return None, "no_phone_number_id"


async def _send_bot_reply(wa_id: str, text: str, contact_id: int, token: str, phone_id: str,
                          channel_id=None, channel_owner_user_id=None):
    """Envia resposta do bot via WhatsApp Cloud API e salva no banco.

    sender_user_id=None marca a mensagem como originada pelo bot
    automatico (nao por operador humano).
    """
    import httpx
    from config import GRAPH_API_BASE
    from database import save_wa_message

    wa_target = "".join(ch for ch in str(wa_id) if ch.isdigit())
    url = f"{GRAPH_API_BASE}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload_msg = {
        "messaging_product": "whatsapp",
        "to": wa_target,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload_msg, headers=headers)
            result = resp.json()
        wa_msg_id = result.get("messages", [{}])[0].get("id", "") if resp.status_code == 200 else ""
        save_wa_message(
            wa_message_id=wa_msg_id,
            contact_id=contact_id,
            direction="outbound",
            msg_type="text",
            content=text,
            status="sent" if resp.status_code == 200 else "failed",
            timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=None,
            channel_id=channel_id,
            channel_owner_user_id=channel_owner_user_id,
            sender_user_id=None,
        )
        if resp.status_code == 200:
            logger.info("[BOT] Resposta enviada para %s | contact=%d", redact_phone(wa_id), contact_id)
        else:
            logger.warning("[BOT] Falha ao enviar resposta | status=%s | erro=%s", resp.status_code, result)
    except Exception as e:
        logger.error("[BOT] Erro ao enviar resposta: %s", e, exc_info=True)


# Fields que dependem de canal resolvido para escrever mensagem/contato.
# smb_app_state_sync entra aqui porque o upsert_wa_contact agora requer
# channel_id pra gerar conversation_id deterministico. Eventos fora
# dessa lista (statuses, account_update) nao precisam de canal.
_CHANNEL_DEPENDENT_FIELDS = ("smb_message_echoes", "history", "messages", "smb_app_state_sync")


async def process_webhook_payload(payload, ws_notify_callback=None):
    """
    Processa o payload completo do webhook.

    Garantia anti-perda: nunca propaga exception ao caller — qualquer
    erro/canal nao resolvido enfileira em pending_webhook_events e o
    handler HTTP retorna 200 imediato pra Meta. Operadores reprocessam
    via UI admin assim que o canal estiver indexado (ex: depois do
    Embedded Signup completar).
    """
    if payload.get("object") != "whatsapp_business_account":
        return

    # Resolve tenant uma unica vez no inicio do payload — todos os
    # changes deste payload vem do mesmo phone_number_id (mesma WABA).
    first_value = ((payload.get("entry") or [{}])[0].get("changes") or [{}])[0].get("value", {})
    first_phone_id = str((first_value.get("metadata") or {}).get("phone_number_id") or "").strip()
    first_channel, _first_reason = _resolve_webhook_channel(first_value)
    tenant_id = _resolve_webhook_tenant(first_channel, phone_number_id=first_phone_id)
    ctx_token = set_tenant_context(tenant_id)
    try:
        await _process_webhook_payload_inner(payload, ws_notify_callback)
    except Exception as exc:
        # Erro nao tratado durante processamento → enfileira pra retry
        # humano em vez de devolver 5xx pra Meta.
        try:
            enqueue_pending_event(
                payload=payload,
                change_field="exception",
                phone_number_id=first_phone_id,
                reason=f"unhandled_exception:{type(exc).__name__}:{str(exc)[:200]}",
            )
        except Exception as enq_exc:
            logger.error(
                "Falha critica: nao consegui enfileirar payload pendente | erro=%s",
                enq_exc, exc_info=True,
            )
        logger.error("Webhook processing error (enqueued): %s", exc, exc_info=True)
    finally:
        reset_tenant_context(ctx_token)


async def _process_webhook_payload_inner(payload, ws_notify_callback=None):
    """Implementacao do processamento. Tenant_context ja setado pelo wrapper.

    Enfileira changes individuais que dependem de canal nao resolvido
    em vez de processar com canal sintetico (default__) que nao casa
    com selectedThreadId no frontend.
    """
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            field = change.get("field", "")

            # Determina field efetivo para enfileiramento (webhooks padrao
            # da Cloud API entregam 'field=messages' mas o detection abaixo
            # usa 'field=="" with messages key' historicamente).
            effective_field = field if field else ("messages" if "messages" in value else "")

            # Resolve canal para este change
            channel, reason = _resolve_webhook_channel(value)

            # Eventos que dependem de canal pra serem persistidos
            # corretamente. Sem canal, enfileira (zero perda).
            if channel is None and effective_field in _CHANNEL_DEPENDENT_FIELDS:
                phone_id = str((value.get("metadata") or {}).get("phone_number_id") or "").strip()
                # Enfileira o payload INTEIRO (nao so o change) — facilita
                # retry reusando process_webhook_payload e idempotencia
                # via wa_message_id em save_wa_message.
                enqueue_pending_event(
                    payload=payload,
                    change_field=effective_field,
                    phone_number_id=phone_id,
                    reason=reason or "no_channel",
                )
                # Para outros changes deste payload (se houver) seguimos
                # o loop — eles podem ser smb_app_state_sync/etc que nao
                # dependem de canal.
                continue

            if field == "smb_message_echoes":
                await _process_smb_message_echoes(value, ws_notify_callback, channel=channel)

            elif field == "smb_app_state_sync":
                _process_smb_app_state_sync(value, channel=channel)

            elif field == "history":
                await _process_history(value, ws_notify_callback, channel=channel)

            elif field == "account_update":
                _process_account_update(value)

            else:
                # Webhooks padrao da Cloud API (messages, statuses)
                if "messages" in value:
                    await _process_messages(value, ws_notify_callback, channel=channel)

                if "statuses" in value and FEATURE_MESSAGE_STATUS:
                    _process_statuses(value)


async def _process_messages(value, ws_notify_callback, channel=None):
    """Processa mensagens recebidas de clientes."""
    contacts_data = value.get("contacts", [])
    contact_info = contacts_data[0] if contacts_data else {}
    contact_name = contact_info.get("profile", {}).get("name", "")

    # Extrair dados do canal para enriquecer contato/mensagem
    channel_id = channel.get("id") if channel else None
    channel_phone_id = str(channel.get("phone_number_id", "")) if channel else ""
    channel_type = str(channel.get("channel_type", "")) if channel else ""
    channel_owner_id = channel.get("owner_user_id") if channel else None
    channel_token = str(channel.get("access_token", "")).strip() if channel else ""

    for msg in value.get("messages", []):
        # Normaliza nono digito BR — Meta entrega numero ora com '9' ora sem
        # (numeros antigos/legados). Sem normalizacao, o mesmo cliente cria
        # contatos e conversations duplicadas.
        wa_id = normalize_br_phone(msg.get("from", ""))
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")

        # Converter timestamp Unix para ISO
        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                ts_iso = datetime.now(timezone.utc).isoformat()

        # Registrar ou atualizar contato (com dados do canal)
        contact_id = upsert_wa_contact(
            wa_id, contact_name,
            channel_id=channel_id,
            phone_number_id=channel_phone_id,
            source_channel_type=channel_type,
            auto_assign_user_id=channel_owner_id if channel_type == CHANNEL_TYPE_COEXISTENCE else None,
        )
        reply_fields = _resolve_reply_reference(contact_id, msg.get("context"))

        # Helper para download usando token do canal correto
        _dl_token = channel_token or WHATSAPP_TOKEN or None

        # Extrair conteudo conforme o tipo
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""
        effective_msg_type = msg_type
        _audio_bytes_for_stt = None
        _audio_mime_for_stt = None
        image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
        audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
        video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
        sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
        document_msg = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
        unsupported = msg.get("unsupported", {}) if isinstance(msg.get("unsupported"), dict) else {}

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")

        elif msg_type == "image" or image.get("id"):
            effective_msg_type = "image"
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            media_result = await download_media(media_id_str, "image", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "audio" or audio.get("id"):
            effective_msg_type = "audio"
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            media_result = await download_media(media_id_str, "audio", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]
            _audio_bytes_for_stt = media_result.get("content") if media_result else None
            _audio_mime_for_stt = media_mime

        elif msg_type == "video" or video.get("id"):
            effective_msg_type = "gif" if video.get("gif") else "video"
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            media_result = await download_media(media_id_str, "video", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "sticker" or sticker.get("id"):
            effective_msg_type = "sticker"
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            media_result = await download_media(media_id_str, "sticker", token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "document" or document_msg.get("id"):
            effective_msg_type = "document"
            media_id_str = document_msg.get("id", "")
            media_mime = document_msg.get("mime_type", "")
            filename = document_msg.get("filename", "")
            content = document_msg.get("caption", "")
            media_result = await download_media(media_id_str, "document", filename, token=_dl_token)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "location":
            loc = msg.get("location", {})
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_address = loc.get("address", "")
            content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

        elif msg_type == "contacts":
            # Cartao de contato - salvar como texto JSON
            content = str(msg.get("contacts", []))

        elif msg_type == "reaction":
            reaction = msg.get("reaction", {})
            content = reaction.get("emoji", "")

        elif msg_type == "unsupported":
            errors = msg.get("errors", []) if isinstance(msg.get("errors"), list) else []
            error_code = ""
            if errors and isinstance(errors[0], dict):
                error_code = str(errors[0].get("code") or "")
            detail = unsupported.get("type", "") or error_code or "unsupported"
            content = f"[{detail}]"
            logger.info(
                "Mensagem unsupported sem midia tratavel | keys=%s | wa_id=%s | id=%s",
                sorted(msg.keys()),
                redact_phone(wa_id),
                msg_id[:20],
            )

        else:
            content = f"[{msg_type}]"
            logger.info("Tipo de mensagem nao tratado: %s", msg_type)

        # Persistir. sender_user_id=None em inbound (cliente final).
        # channel_owner_user_id captura o dono do numero (relevante p/ coexistence).
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="inbound",
            msg_type=effective_msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="received",
            timestamp_wa=ts_iso,
            channel_id=channel_id,
            phone_number_id=channel_phone_id,
            channel_owner_user_id=channel_owner_id,
            sender_user_id=None,
            **reply_fields,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            redact_name(contact_name), redact_phone(wa_id), effective_msg_type, msg_id[:20]
        )

        # -- Bot: processar mensagem se ativo e contato sem operador --
        # Gate: nao dispara se contato ja foi qualificado pelo bot (bot_completed=True)
        # mesmo que ainda nao tenha operador atribuido. O contato esta na fila
        # do departamento e redirigir pro bot reiniciaria o fluxo do zero.
        if effective_msg_type == "text" and content.strip():
            _contact_for_bot = get_wa_contact(contact_id)
            if (
                _contact_for_bot
                and not _contact_for_bot.get("assigned_to")
                and not _contact_for_bot.get("bot_completed")
            ):
                bot_reply = process_bot_message(contact_id, content, contact_name)
                if bot_reply:
                    _bot_token = (channel_token or WHATSAPP_TOKEN or "").strip()
                    _bot_phone_id = channel_phone_id or WHATSAPP_PHONE_NUMBER_ID
                    await _send_bot_reply(
                        wa_id, bot_reply, contact_id, _bot_token, _bot_phone_id,
                        channel_id=channel_id,
                        channel_owner_user_id=channel_owner_id,
                    )

        # -- Lead convertido: capturar rating ou rerouting --
        _contact_fresh = get_wa_contact(contact_id)
        if _contact_fresh and _contact_fresh.get("qualification") == "convertido":
            _has_pending_rating = (
                _contact_fresh.get("rating_requested_at")
                and _contact_fresh.get("rating") is None
            )

            if _has_pending_rating and effective_msg_type == "text" and content.strip().isdigit():
                _rating_val = int(content.strip())
                if 1 <= _rating_val <= 10:
                    # Capturar avaliacao
                    from firestore_common import document as _fs_doc, utcnow as _fs_now
                    _fs_doc("wa_contacts", contact_id).set({
                        "rating": _rating_val,
                        "rating_received_at": _fs_now().isoformat(),
                    }, merge=True)
                    # Marcar a mensagem de resposta como admin_only
                    if db_id:
                        _fs_doc("wa_messages", db_id).set({
                            "is_rating_message": True,
                            "visibility": "admin_only",
                        }, merge=True)
                    logger.info("[RATING] Contato %d avaliou com nota %d", contact_id, _rating_val)
            else:
                # Nao eh rating — lead convertido retornando, reatribuir ao operador original
                _original_op = _contact_fresh.get("original_operator_id") or _contact_fresh.get("converted_by_user_id")
                if _original_op:
                    _op_user = get_user_by_id(_original_op)
                    if _op_user:
                        assign_wa_contact(
                            contact_id, _original_op,
                            _contact_fresh.get("department_id"),
                            transferred_by=None,
                            reason="Lead convertido retornou",
                            summary="Reatribuido automaticamente ao operador original",
                        )
                        update_wa_contact_qualification(contact_id, "em_atendimento")
                        logger.info(
                            "[REROUTE] Lead convertido %d reatribuido ao operador %d (%s)",
                            contact_id, _original_op, _op_user.get("display_name"),
                        )

        # Transcricao de audio inbound
        if FEATURE_AUDIO_TRANSCRIPTION and _audio_bytes_for_stt and db_id:
            try:
                from transcription_service import get_speech_client, transcribe_audio_bytes
                speech_client = get_speech_client()
                if speech_client:
                    transcript = transcribe_audio_bytes(
                        _audio_bytes_for_stt,
                        media_mime=_audio_mime_for_stt,
                        language_code=STT_LANGUAGE_CODE,
                        timeout_s=STT_TIMEOUT_SECONDS,
                    )
                    if not transcript and STT_FALLBACK_TEXT:
                        transcript = STT_FALLBACK_TEXT
                    if transcript:
                        update_wa_message_transcription(db_id, transcript)
                        logger.info("[STT] Transcricao salva | msg_id=%s | len=%d", db_id, len(transcript))
            except Exception as stt_exc:
                logger.error("[STT] Falha na transcricao: %s", stt_exc, exc_info=True)

        # Notificar operadores conectados via WebSocket
        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "contact_name": contact_name,
                    "wa_id": wa_id,
                    "msg_type": effective_msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                    **reply_fields,
                },
            })


def _process_statuses(value):
    """Processa atualizacoes de status de mensagens enviadas."""
    for status in value.get("statuses", []):
        msg_id = status.get("id", "")
        state = status.get("status", "")
        timestamp = status.get("timestamp", "")

        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                pass

        update_wa_message_status(msg_id, state, ts_iso)
        logger.info("[WA STATUS] %s -> %s", msg_id[:20], state)


# ---------------------------------------------------------------------------
# Coexistence: smb_message_echoes
# ---------------------------------------------------------------------------

def _parse_unix_timestamp(timestamp):
    """Converte timestamp Unix para ISO 8601 UTC."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, OSError):
        return datetime.now(timezone.utc).isoformat()


def _get_business_phone_number(metadata):
    """Extrai o numero do telefone comercial do metadata do webhook."""
    return str(metadata.get("display_phone_number", "")).replace("+", "").replace(" ", "").replace("-", "")


async def _process_smb_message_echoes(value, ws_notify_callback=None, channel=None):
    """
    Processa mensagens enviadas pelo app WhatsApp Business (celular/companion device).
    Estas sao mensagens OUTBOUND enviadas pela empresa, ecoadas para o CRM.
    Nao abrem janela de servico e nao disparam automacao.
    """
    metadata = value.get("metadata", {})
    echoes = value.get("message_echoes", [])

    # Em smb_message_echoes, "quem enviou" foi o proprio dono do numero
    # operando o WhatsApp do celular — channel_owner_user_id e sender_user_id
    # apontam pra mesma pessoa.
    channel_id_outer = channel.get("id") if channel else None
    channel_owner_outer = channel.get("owner_user_id") if channel else None
    channel_phone_id_outer = str(channel.get("phone_number_id", "")) if channel else ""
    channel_type_outer = str(channel.get("channel_type", "")) if channel else ""

    for echo in echoes:
        business_phone = echo.get("from", "")
        customer_phone = echo.get("to", "")
        msg_id = echo.get("id", "")
        msg_type = echo.get("type", "unknown")
        timestamp = echo.get("timestamp", "")
        ts_iso = _parse_unix_timestamp(timestamp)

        if not customer_phone:
            logger.warning("[SMB ECHO] Mensagem sem destinatario | id=%s", msg_id[:20])
            continue

        # Normalizar telefone do cliente e criar/atualizar contato
        normalized_phone = normalize_br_phone(customer_phone)
        contact_id = upsert_wa_contact(
            normalized_phone, "",
            channel_id=channel_id_outer,
            phone_number_id=channel_phone_id_outer,
            source_channel_type=channel_type_outer,
            auto_assign_user_id=channel_owner_outer if channel_type_outer == CHANNEL_TYPE_COEXISTENCE else None,
        )

        # Extrair conteudo conforme tipo de mensagem
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""
        effective_msg_type = msg_type

        if msg_type == "text":
            text_obj = echo.get("text", {})
            content = text_obj.get("body", "") if isinstance(text_obj, dict) else ""

        elif msg_type == "image":
            image = echo.get("image", {}) if isinstance(echo.get("image"), dict) else {}
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = echo.get("audio", {}) if isinstance(echo.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "audio")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = echo.get("video", {}) if isinstance(echo.get("video"), dict) else {}
            effective_msg_type = "gif" if video.get("gif") else "video"
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "video")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = echo.get("sticker", {}) if isinstance(echo.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str:
                media_result = await download_media(media_id_str, "sticker")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = echo.get("document", {}) if isinstance(echo.get("document"), dict) else {}
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "document", filename)
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "location":
            loc = echo.get("location", {}) if isinstance(echo.get("location"), dict) else {}
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_address = loc.get("address", "")
            content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

        elif msg_type == "contacts":
            content = str(echo.get("contacts", []))

        elif msg_type == "reaction":
            reaction = echo.get("reaction", {}) if isinstance(echo.get("reaction"), dict) else {}
            content = reaction.get("emoji", "")

        else:
            content = f"[{msg_type}]"

        # Salvar como outbound com source phone_app. operator_id=owner
        # tambem (em smb_echoes o humano dono do numero digitou pelo
        # celular) — sem isso o frontend rotula como "Bot".
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="outbound",
            msg_type=effective_msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="sent",
            timestamp_wa=ts_iso,
            operator_id=channel_owner_outer,
            channel_id=channel_id_outer,
            phone_number_id=channel_phone_id_outer,
            channel_owner_user_id=channel_owner_outer,
            sender_user_id=channel_owner_outer,
        )

        logger.info(
            "[SMB ECHO] %s -> %s | tipo=%s | id=%s",
            business_phone, customer_phone, effective_msg_type, msg_id[:20],
        )

        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "wa_id": normalized_phone,
                    "msg_type": effective_msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                    "direction": "outbound",
                    "source": "phone_app",
                },
            })


# ---------------------------------------------------------------------------
# Coexistence: smb_app_state_sync
# ---------------------------------------------------------------------------

def _process_smb_app_state_sync(value, channel=None):
    """
    Processa sincronizacao de contatos do app WhatsApp Business.
    Recebe add/remove de contatos da lista telefonica do celular.

    Precisa de `channel` resolvido pra propagar `channel_id` no
    upsert_wa_contact. Sem channel_id, upsert_wa_conversation interno
    levanta ConversationIdError (defesa de save_wa_message contra
    ids 'default__'). Caller resolve via _resolve_webhook_channel.
    """
    state_sync = value.get("state_sync", [])
    if not state_sync:
        return

    # Channel context para enriquecer contatos sincronizados (mesma
    # logica de _process_messages e _process_history).
    sync_channel_id = channel.get("id") if channel else None
    sync_channel_owner = channel.get("owner_user_id") if channel else None
    sync_channel_phone = str(channel.get("phone_number_id", "")) if channel else ""
    sync_channel_type = str(channel.get("channel_type", "")) if channel else ""

    for item in state_sync:
        item_type = item.get("type", "")
        if item_type != "contact":
            logger.info("[SMB SYNC] Tipo desconhecido: %s", item_type)
            continue

        contact_data = item.get("contact", {})
        action = item.get("action", "")
        phone = str(contact_data.get("phone_number", "")).strip()
        full_name = str(contact_data.get("full_name", "")).strip()
        first_name = str(contact_data.get("first_name", "")).strip()

        if not phone:
            continue

        normalized_phone = normalize_br_phone(phone)
        display_name = full_name or first_name

        if action == "add":
            # from_message_event=False — contato vem da agenda telefonica
            # do dono, nao de uma conversa real. Nao cria wa_conversation
            # nem popula last_message_at, evitando poluir a sidebar com
            # threads vazias. Quando o operador iniciar conversa ou o
            # cliente mandar mensagem, ai sim a thread nasce.
            contact_id = upsert_wa_contact(
                normalized_phone, display_name,
                channel_id=sync_channel_id,
                phone_number_id=sync_channel_phone,
                source_channel_type=sync_channel_type,
                auto_assign_user_id=None,  # state_sync nao atribui
                from_message_event=False,
            )
            logger.info(
                "[SMB SYNC] Contato sincronizado | phone=%s name=%s id=%s",
                redact_phone(normalized_phone), redact_name(display_name), contact_id,
            )

        elif action == "remove":
            # Nao deletamos contatos, apenas logamos a remocao.
            # O contato pode ter historico de mensagens que precisa ser preservado.
            logger.info(
                "[SMB SYNC] Contato removido no celular (preservado no CRM) | phone=%s name=%s",
                normalized_phone, display_name,
            )

        else:
            logger.warning("[SMB SYNC] Acao desconhecida: %s | phone=%s", action, phone)


# ---------------------------------------------------------------------------
# Coexistence: history (importacao de 180 dias)
# ---------------------------------------------------------------------------

async def _process_history(value, ws_notify_callback=None, channel=None):
    """
    Processa webhooks de historico do app WhatsApp Business.
    Importa ate 180 dias de mensagens em fases (0, 1, 2) e chunks.
    Tambem trata media assets enviados em webhooks separados.
    """
    metadata = value.get("metadata", {})
    business_phone = _get_business_phone_number(metadata)

    # Caso 1: webhook com 'messages' - media assets do historico
    if "messages" in value and "history" not in value:
        await _process_history_media_assets(value, business_phone)
        return

    history_entries = value.get("history", [])
    if not history_entries:
        return

    # Channel context para enriquecer contatos/mensagens importadas.
    hist_channel_id = channel.get("id") if channel else None
    hist_channel_owner = channel.get("owner_user_id") if channel else None
    hist_channel_phone = str(channel.get("phone_number_id", "")) if channel else ""
    hist_channel_type = str(channel.get("channel_type", "")) if channel else ""

    for hist in history_entries:
        # Verificar se e um erro (empresa recusou compartilhar historico)
        errors = hist.get("errors", [])
        if errors:
            for err in errors:
                code = err.get("code", 0)
                title = err.get("title", "")
                logger.warning("[HISTORY] Erro na sincronizacao | code=%s title=%s", code, title)
            continue

        hist_metadata = hist.get("metadata", {})
        phase = hist_metadata.get("phase", -1)
        chunk_order = hist_metadata.get("chunk_order", 0)
        progress = hist_metadata.get("progress", 0)

        logger.info(
            "[HISTORY] Recebido | phase=%s chunk=%s progress=%s%%",
            phase, chunk_order, progress,
        )

        threads = hist.get("threads", [])
        for thread in threads:
            thread_phone = str(thread.get("id", "")).strip()
            if not thread_phone:
                continue

            normalized_thread_phone = normalize_br_phone(thread_phone)
            contact_id = upsert_wa_contact(
                normalized_thread_phone, "",
                channel_id=hist_channel_id,
                phone_number_id=hist_channel_phone,
                source_channel_type=hist_channel_type,
                auto_assign_user_id=hist_channel_owner if hist_channel_type == CHANNEL_TYPE_COEXISTENCE else None,
            )
            messages = thread.get("messages", [])

            # Normaliza business_phone uma vez (nono digito BR) — comparacao
            # com msg_from/msg_to crus dava direction errada quando empresa
            # cadastrou o numero sem 9 e o webhook entrega com (ou vice-versa).
            business_phone_normalized = normalize_br_phone(business_phone) if business_phone else ""

            for msg in messages:
                msg_from_raw = str(msg.get("from", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_to_raw = str(msg.get("to", "")).replace("+", "").replace(" ", "").replace("-", "")
                msg_from = normalize_br_phone(msg_from_raw) if msg_from_raw else ""
                msg_to = normalize_br_phone(msg_to_raw) if msg_to_raw else ""
                msg_id = msg.get("id", "")
                msg_type = msg.get("type", "unknown")
                timestamp = msg.get("timestamp", "")
                ts_iso = _parse_unix_timestamp(timestamp)
                history_context = msg.get("history_context", {})
                msg_status = str(history_context.get("status", "")).lower()

                # Determinar direcao: se 'from' e o telefone da empresa, e outbound
                is_outbound = (msg_from == business_phone_normalized) or bool(msg_to)
                direction = "outbound" if is_outbound else "inbound"

                # media_placeholder: midia sera enviada em webhook separado
                if msg_type == "media_placeholder":
                    save_wa_message(
                        wa_message_id=msg_id,
                        contact_id=contact_id,
                        direction=direction,
                        msg_type="media_placeholder",
                        content="[Midia do historico - aguardando]",
                        status=msg_status or "delivered",
                        timestamp_wa=ts_iso,
                        operator_id=hist_channel_owner if direction == "outbound" else None,
                        channel_id=hist_channel_id,
                        phone_number_id=hist_channel_phone,
                        channel_owner_user_id=hist_channel_owner,
                        sender_user_id=hist_channel_owner if direction == "outbound" else None,
                    )
                    continue

                # Extrair conteudo conforme tipo
                content = ""
                media_path = ""
                media_mime = ""
                media_id_str = ""
                latitude = None
                longitude = None
                filename = ""
                effective_msg_type = msg_type

                if msg_type == "text":
                    text_obj = msg.get("text", {})
                    content = text_obj.get("body", "") if isinstance(text_obj, dict) else ""

                elif msg_type == "image":
                    image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
                    media_id_str = image.get("id", "")
                    media_mime = image.get("mime_type", "")
                    content = image.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "image")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "audio":
                    audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
                    media_id_str = audio.get("id", "")
                    media_mime = audio.get("mime_type", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "audio")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "video":
                    video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
                    effective_msg_type = "gif" if video.get("gif") else "video"
                    media_id_str = video.get("id", "")
                    media_mime = video.get("mime_type", "")
                    content = video.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "video")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "document":
                    doc = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
                    media_id_str = doc.get("id", "")
                    media_mime = doc.get("mime_type", "")
                    filename = doc.get("filename", "")
                    content = doc.get("caption", "")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "document", filename)
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "sticker":
                    sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
                    media_id_str = sticker.get("id", "")
                    media_mime = sticker.get("mime_type", "image/webp")
                    if media_id_str:
                        media_result = await download_media(media_id_str, "sticker")
                        if media_result:
                            media_path = media_result["path"]
                            media_mime = media_result["mime_type"]

                elif msg_type == "location":
                    loc = msg.get("location", {}) if isinstance(msg.get("location"), dict) else {}
                    latitude = loc.get("latitude")
                    longitude = loc.get("longitude")
                    loc_name = loc.get("name", "")
                    loc_address = loc.get("address", "")
                    content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

                elif msg_type == "contacts":
                    content = str(msg.get("contacts", []))

                elif msg_type == "reaction":
                    reaction = msg.get("reaction", {}) if isinstance(msg.get("reaction"), dict) else {}
                    content = reaction.get("emoji", "")

                else:
                    content = f"[{msg_type}]"

                save_wa_message(
                    wa_message_id=msg_id,
                    contact_id=contact_id,
                    direction=direction,
                    msg_type=effective_msg_type,
                    content=content,
                    media_path=media_path,
                    media_mime=media_mime,
                    media_id=media_id_str,
                    latitude=latitude,
                    longitude=longitude,
                    filename=filename,
                    status=msg_status or ("received" if direction == "inbound" else "sent"),
                    timestamp_wa=ts_iso,
                    operator_id=hist_channel_owner if direction == "outbound" else None,
                    channel_id=hist_channel_id,
                    phone_number_id=hist_channel_phone,
                    channel_owner_user_id=hist_channel_owner,
                    sender_user_id=hist_channel_owner if direction == "outbound" else None,
                )

            logger.info(
                "[HISTORY] Thread processada | phone=%s msgs=%d phase=%s",
                thread_phone, len(messages), phase,
            )

        if progress == 100:
            logger.info("[HISTORY] Sincronizacao completa (100%%)")
            log_audit(
                user_id=None,
                action="history_sync_complete",
                detail=f"Importacao do historico de mensagens concluida (phase={phase})",
            )


async def _process_history_media_assets(value, business_phone):
    """
    Processa webhooks de historico que contem media assets.
    Estes sao enviados separadamente dos threads, com 'messages' contendo
    a midia real de mensagens que eram media_placeholder.
    """
    for msg in value.get("messages", []):
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")
        ts_iso = _parse_unix_timestamp(timestamp)

        media_path = ""
        media_mime = ""
        media_id_str = ""
        filename = ""
        content = ""

        if msg_type == "image":
            image = msg.get("image", {}) if isinstance(msg.get("image"), dict) else {}
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "image")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = msg.get("audio", {}) if isinstance(msg.get("audio"), dict) else {}
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "audio")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = msg.get("video", {}) if isinstance(msg.get("video"), dict) else {}
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "video")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = msg.get("document", {}) if isinstance(msg.get("document"), dict) else {}
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            if media_id_str:
                media_result = await download_media(media_id_str, "document", filename)
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = msg.get("sticker", {}) if isinstance(msg.get("sticker"), dict) else {}
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            if media_id_str:
                media_result = await download_media(media_id_str, "sticker")
                if media_result:
                    media_path = media_result["path"]
                    media_mime = media_result["mime_type"]

        else:
            logger.info("[HISTORY MEDIA] Tipo nao tratado: %s | id=%s", msg_type, msg_id[:20])
            continue

        if not media_path:
            logger.warning("[HISTORY MEDIA] Nao foi possivel baixar midia | id=%s type=%s", msg_id[:20], msg_type)
            continue

        # Atualiza a mensagem placeholder existente com a midia real
        existing = get_wa_message_by_wa_message_id(msg_id)
        if existing:
            from firestore_common import document
            document("wa_messages", existing["id"]).set({
                "msg_type": msg_type,
                "content": content or existing.get("content", ""),
                "media_path": media_path,
                "media_mime": media_mime,
                "media_id": media_id_str,
                "filename": filename,
            }, merge=True)
            logger.info("[HISTORY MEDIA] Placeholder atualizado | id=%s type=%s", msg_id[:20], msg_type)
        else:
            logger.warning(
                "[HISTORY MEDIA] Mensagem original nao encontrada para media | wa_msg_id=%s",
                msg_id[:20],
            )


# ---------------------------------------------------------------------------
# Coexistence: account_update
# ---------------------------------------------------------------------------

def _process_account_update(value):
    """
    Processa eventos de atualizacao de conta para coexistence.
    Eventos: PARTNER_REMOVED, ACCOUNT_OFFBOARDED, ACCOUNT_RECONNECTED.
    """
    event = str(value.get("event", "")).upper()
    phone_number = value.get("phone_number", "")

    redacted_phone = redact_phone(phone_number)

    if event == "PARTNER_REMOVED":
        logger.warning(
            "[ACCOUNT] Cliente desconectou da API de Nuvem | phone=%s",
            redacted_phone,
        )
        log_audit(
            user_id=None,
            action="coexistence_partner_removed",
            detail=f"Cliente desconectou o numero {phone_number} da API de Nuvem via WhatsApp Business App",
        )

    elif event == "ACCOUNT_OFFBOARDED":
        logger.warning("[ACCOUNT] Conta removida (offboarded) | phone=%s", redacted_phone)
        log_audit(
            user_id=None,
            action="coexistence_offboarded",
            detail=f"Numero {phone_number} foi removido do coexistence (troca de dispositivo ou reinscricao)",
        )

    elif event == "ACCOUNT_RECONNECTED":
        logger.info("[ACCOUNT] Conta reconectada | phone=%s", redacted_phone)
        log_audit(
            user_id=None,
            action="coexistence_reconnected",
            detail=f"Numero {phone_number} reconectado ao coexistence",
        )

    else:
        logger.info("[ACCOUNT] Evento nao tratado: %s | phone=%s", event, redacted_phone)
```

## webhook_google_chat.py

```python
# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook do Google Chat.
Valida JWT do Google e processa mensagens (texto, audio, anexos).
"""

import logging

import httpx
import jwt

from config import GOOGLE_CHAT_PROJECT_NUMBER
from database import (
    upsert_gc_conversation, save_gc_message, log_audit,
)
from google_chat import download_attachment
from media import save_upload_media
from pii_redaction import redact_name

logger = logging.getLogger("castro_crm.webhook_gchat")

# Chaves publicas do Google para validar JWT
GOOGLE_CHAT_CERTS_URL = (
    "https://www.googleapis.com/service_accounts/v1/metadata/x509/"
    "chat@system.gserviceaccount.com"
)

_cached_certs = None


async def _fetch_google_certs():
    """Busca (e cacheia) certificados publicos do Google Chat."""
    global _cached_certs
    if _cached_certs:
        return _cached_certs
    async with httpx.AsyncClient() as client:
        resp = await client.get(GOOGLE_CHAT_CERTS_URL)
        resp.raise_for_status()
        _cached_certs = resp.json()
        return _cached_certs


def _get_public_key(certs, kid):
    """Extrai chave publica pelo kid do header JWT."""
    pem = certs.get(kid)
    if not pem:
        return None
    from cryptography.x509 import load_pem_x509_certificate
    cert = load_pem_x509_certificate(pem.encode("utf-8"))
    return cert.public_key()


async def validate_google_chat_token(auth_header):
    """Valida Bearer token JWT enviado pelo Google Chat.

    Verifica:
    - Assinatura com chave publica do Google
    - Emissor (iss) e chat@system.gserviceaccount.com
    - Audience corresponde ao project number
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Webhook Google Chat: header Authorization ausente")
        return False

    token = auth_header.split(" ", 1)[1]

    try:
        # Decodificar header para pegar kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            logger.warning("Webhook Google Chat: JWT sem kid no header")
            return False

        certs = await _fetch_google_certs()
        public_key = _get_public_key(certs, kid)
        if not public_key:
            # Tentar refresh dos certs (pode ter rotacionado)
            global _cached_certs
            _cached_certs = None
            certs = await _fetch_google_certs()
            public_key = _get_public_key(certs, kid)
            if not public_key:
                logger.warning("Webhook Google Chat: kid=%s nao encontrado nos certs", kid)
                return False

        # Validar JWT
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=GOOGLE_CHAT_PROJECT_NUMBER,
            issuer="chat@system.gserviceaccount.com",
        )
        logger.debug("Webhook Google Chat: JWT validado | sub=%s", payload.get("sub"))
        return True

    except jwt.ExpiredSignatureError:
        logger.warning("Webhook Google Chat: JWT expirado")
        return False
    except jwt.InvalidAudienceError:
        logger.warning("Webhook Google Chat: audience invalido")
        return False
    except jwt.InvalidIssuerError:
        logger.warning("Webhook Google Chat: issuer invalido")
        return False
    except Exception as exc:
        logger.error("Webhook Google Chat: erro na validacao JWT: %s", exc, exc_info=True)
        return False


async def process_google_chat_event(event):
    """Processa evento recebido do Google Chat.

    Tipos de eventos:
    - ADDED_TO_SPACE: Bot adicionado a um space
    - REMOVED_FROM_SPACE: Bot removido de um space
    - MESSAGE: Nova mensagem no space
    - CARD_CLICKED: Acao em card interativo (futuro)
    """
    event_type = event.get("type", "")
    space = event.get("space", {})
    space_id = space.get("name", "")
    space_name = space.get("displayName", "")
    user = event.get("user", {})
    sender_email = user.get("email", "")
    sender_name = user.get("displayName", "")

    if event_type == "ADDED_TO_SPACE":
        logger.info("[GC] Bot adicionado ao space: %s (%s)", space_name, space_id)
        upsert_gc_conversation(
            space_id=space_id,
            space_name=space_name or space_id,
        )
        return {"text": "Hubloc CRM conectado! Mensagens deste space serao sincronizadas com o CRM."}

    elif event_type == "REMOVED_FROM_SPACE":
        logger.info("[GC] Bot removido do space: %s", space_id)
        return {}

    elif event_type == "MESSAGE":
        message = event.get("message", {})
        return await _process_gchat_message(
            message=message,
            space_id=space_id,
            space_name=space_name,
            sender_email=sender_email,
            sender_name=sender_name,
        )

    else:
        logger.info("[GC] Evento nao tratado: %s", event_type)
        return {}


async def _process_gchat_message(message, space_id, space_name, sender_email, sender_name):
    """Processa uma mensagem recebida do Google Chat."""
    gchat_message_id = message.get("name", "")
    text = message.get("text", "") or message.get("argumentText", "")
    create_time = message.get("createTime", "")
    attachments = message.get("attachment", [])

    # Garantir que a conversa existe
    conversation_id = upsert_gc_conversation(
        space_id=space_id,
        space_name=space_name or space_id,
    )

    # Processar anexos (audio, imagens, documentos)
    media_path = ""
    media_mime = ""
    msg_type = "text"

    if attachments:
        attachment = attachments[0]  # Processar primeiro anexo
        content_type = attachment.get("contentType", "")
        resource_name = attachment.get("attachmentDataRef", {}).get("resourceName", "")

        if content_type.startswith("audio/"):
            msg_type = "audio"
        elif content_type.startswith("image/"):
            msg_type = "image"
        elif content_type.startswith("video/"):
            msg_type = "video"
        else:
            msg_type = "document"

        media_mime = content_type

        # Baixar e armazenar o anexo
        if resource_name:
            try:
                content_bytes = download_attachment(resource_name)
                if content_bytes:
                    ext = _mime_to_ext(content_type)
                    filename = f"gchat_{gchat_message_id.split('/')[-1]}{ext}"
                    result = await save_upload_media(content_bytes, filename, content_type)
                    if result:
                        media_path = result.get("path", "")
            except Exception as exc:
                logger.error("[GC] Erro ao baixar anexo: %s", exc, exc_info=True)

    # Salvar mensagem no Firestore
    message_id = save_gc_message(
        conversation_id=conversation_id,
        gchat_message_id=gchat_message_id,
        sender_email=sender_email,
        sender_name=sender_name,
        msg_type=msg_type,
        content=text,
        media_path=media_path,
        media_mime=media_mime,
        source="google_chat",
        create_time=create_time,
    )

    logger.info(
        "[GC IN] %s (%s) | tipo=%s | space=%s",
        redact_name(sender_name), redact_name(sender_email), msg_type, space_id,
    )

    return {}


def _mime_to_ext(mime_type):
    """Converte MIME type para extensao de arquivo."""
    mapping = {
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/mpeg": ".mp3",
        "audio/webm": ".webm",
        "audio/3gpp": ".3gp",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/3gpp": ".3gp",
        "application/pdf": ".pdf",
    }
    return mapping.get(mime_type, ".bin")
```

## frontend/package.json

```json
{
  "name": "castro-intelligence-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "firebase": "^11.0.2",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "typescript": "^5.6.3",
    "vite": "^5.4.10"
  }
}
```

## frontend/tsconfig.app.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```

## frontend/tsconfig.json

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

## frontend/tsconfig.node.json

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

## frontend/vite.config.ts

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/webhook": "http://localhost:8080",
      "/media": "http://localhost:8080",
    },
  },
  build: {
    outDir: "../frontend_dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          firebase: ["firebase/app", "firebase/auth", "firebase/firestore"],
        },
      },
    },
  },
});
```

## frontend/index.html

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Castro Intelligence CRM</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
  </html>
```

## frontend/src/styles.css

```css
@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;700&display=swap");

:root {
  --bg: #f4efe6;
  --panel: rgba(255, 251, 244, 0.86);
  --panel-strong: rgba(255, 255, 255, 0.82);
  --panel-card: rgba(255, 255, 255, 0.64);
  --border: rgba(67, 49, 30, 0.13);
  --text: #2c241d;
  --muted: #7d6958;
  --accent: #0f766e;
  --accent-dark: #115e59;
  --warm: #9a5927;
  --danger: #b91c1c;
  --danger-bg: rgba(185, 28, 28, 0.12);
  --success: #166534;
  --success-bg: rgba(22, 101, 52, 0.12);
  --shadow: 0 24px 64px rgba(63, 44, 24, 0.12);
  --bubble-in: rgba(255, 255, 255, 0.9);
  --bubble-out: rgba(15, 118, 110, 0.12);
  --bubble-sys: rgba(154, 89, 39, 0.12);
  --contact-bg: rgba(255, 255, 255, 0.58);
  --composer-bg: rgba(255, 255, 255, 0.94);
  --attach-bg: rgba(255, 255, 255, 0.98);
  --menu-solid-bg: #fffdf9;
  --menu-solid-border: rgba(67, 49, 30, 0.18);
  --menu-solid-shadow: 0 20px 44px rgba(63, 44, 24, 0.22);
  --panel-solid-bg: #faf6ef;
  --panel-solid-strong: #fffdf9;
  --panel-solid-soft: #f3ede3;
  --hero-bg: linear-gradient(180deg, rgba(255, 251, 244, 0.96), rgba(255, 248, 238, 0.82));
  --page-bg:
    radial-gradient(circle at top left, rgba(154, 89, 39, 0.18), transparent 30%),
    radial-gradient(circle at bottom right, rgba(15, 118, 110, 0.12), transparent 36%),
    linear-gradient(145deg, #f4efe6, #ede2d0);
  font-family: "Space Grotesk", sans-serif;
  color: var(--text);
  background: var(--page-bg);
}

:root.dark {
  --bg: #0f1117;
  --panel: rgba(22, 27, 34, 0.95);
  --panel-strong: rgba(30, 36, 46, 0.96);
  --panel-card: rgba(30, 36, 46, 0.8);
  --border: rgba(255, 255, 255, 0.09);
  --text: #e8e2da;
  --muted: #8b9099;
  --accent: #14b8a6;
  --accent-dark: #0f9488;
  --warm: #d4845a;
  --danger: #f87171;
  --danger-bg: rgba(248, 113, 113, 0.12);
  --success: #4ade80;
  --success-bg: rgba(74, 222, 128, 0.1);
  --shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
  --bubble-in: rgba(40, 48, 60, 0.95);
  --bubble-out: rgba(20, 184, 166, 0.14);
  --bubble-sys: rgba(212, 132, 90, 0.12);
  --contact-bg: rgba(30, 36, 46, 0.7);
  --composer-bg: rgba(22, 27, 34, 0.98);
  --attach-bg: rgba(28, 34, 44, 0.99);
  --menu-solid-bg: #1b232d;
  --menu-solid-border: rgba(255, 255, 255, 0.14);
  --menu-solid-shadow: 0 20px 44px rgba(0, 0, 0, 0.42);
  --panel-solid-bg: #18202a;
  --panel-solid-strong: #1b232d;
  --panel-solid-soft: #222c37;
  --hero-bg: linear-gradient(180deg, rgba(22, 27, 34, 0.98), rgba(18, 22, 30, 0.96));
  --page-bg: linear-gradient(145deg, #0f1117, #131820);
}

* { box-sizing: border-box; }
html, body, #root { height: 100%; margin: 0; }
body { min-height: 100vh; overflow: hidden; }
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }

*::-webkit-scrollbar { width: 10px; height: 10px; }
*::-webkit-scrollbar-thumb {
  background: rgba(125, 105, 88, 0.3);
  border: 2px solid transparent;
  border-radius: 999px;
  background-clip: padding-box;
}

.screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
}

.hero-card {
  border: 1px solid var(--border);
  border-radius: 28px;
  background: var(--hero-bg);
  box-shadow: var(--shadow);
}

.panel {
  border-right: 1px solid var(--border);
  background: var(--hero-bg);
}

.hero-card {
  width: min(560px, 100%);
  padding: 2rem;
}

.hero-card h1 { margin: 0; font-size: clamp(2rem, 4vw, 3rem); line-height: 0.98; }
.hero-card p { color: var(--muted); }
.eyebrow {
  margin: 0 0 0.4rem;
  color: var(--muted);
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.crm-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.crm-topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0 1.4rem;
  height: 58px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.topbar-brand .eyebrow { margin: 0; }

.topbar-user {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
}

.topbar-user strong { font-size: 0.95rem; line-height: 1.2; }

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.crm-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 62px minmax(270px, 320px) minmax(0, 1fr) minmax(300px, 360px);
  grid-template-rows: 1fr;
  gap: 0;
}

.crm-nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 1rem 0.35rem;
  background: var(--panel);
  border-right: 1px solid var(--border);
}

.nav-item {
  position: relative;
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: var(--muted);
  transition: background 0.15s, color 0.15s;
}

.nav-item:hover { background: rgba(15, 118, 110, 0.08); color: var(--text); }
.nav-item.active { background: rgba(15, 118, 110, 0.12); color: var(--accent); }

.nav-item svg { width: 22px; height: 22px; }

.nav-label {
  display: block;
  margin-top: 2px;
  font-size: 0.6rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  line-height: 1;
}

.nav-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--accent);
  color: white;
  font-size: 0.65rem;
  font-weight: 700;
  font-family: "IBM Plex Mono", monospace;
  padding: 0 4px;
  line-height: 1;
}

.panel {
  min-height: 0;
  height: 100%;
  overflow: hidden;
  padding: 1rem;
}

.chat-panel,
.sidebar {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.detail-panel {
  min-height: 0;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow: hidden;
  border-right: none;
}

/* scroll handled by .detail-scroll above */

.panel-head,
.toolbar,
.row,
.contact-banner,
.chips {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.panel-head--stacked {
  align-items: flex-start;
}

.operator-presence-strip {
  display: flex;
  align-items: center;
  gap: 0.42rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.operator-presence-dot,
.contact-operator-dot {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1;
}

.panel-head h2,
.card h3 { margin: 0; }

.sub {
  color: var(--muted);
  font-size: 0.86rem;
}

.toolbar { align-items: stretch; flex-wrap: wrap; }
.toolbar.right { justify-content: flex-end; }
.toolbar select.compact { width: auto; min-width: 0; padding: 0.6rem 0.7rem; font-size: 0.82rem; }

input,
select,
textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--panel-strong);
  color: var(--text);
  padding: 0.85rem 0.95rem;
  outline: none;
  color-scheme: inherit;
}

input:focus,
select:focus,
textarea:focus {
  border-color: rgba(15, 118, 110, 0.38);
  box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.08);
}

.primary,
.ghost {
  border: none;
  border-radius: 16px;
  padding: 0.9rem 1.1rem;
  font-weight: 600;
}

.primary { background: var(--accent); color: white; }
.ghost { background: rgba(15, 118, 110, 0.1); color: var(--accent-dark); }
.primary:disabled,
.ghost:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.pill,
.chip,
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 0.35rem 0.72rem;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.74rem;
}

.pill.ok { background: rgba(15, 118, 110, 0.12); color: var(--accent-dark); }
.pill.warn,
.chip { background: rgba(154, 89, 39, 0.12); color: var(--warm); }
.badge { min-width: 1.9rem; background: var(--accent-dark); color: white; }

.contact-list,
.messages,
.detail-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding-right: 0.3rem;
}

.contact-list {
  gap: 0.7rem;
}

.contact {
  width: 100%;
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 0.7rem;
  padding: 0.8rem;
  border: 1px solid transparent;
  border-radius: 20px;
  background: var(--contact-bg);
  text-align: left;
  color: inherit;
}

.contact--team-accent {
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}

.contact.active {
  border-color: rgba(15, 118, 110, 0.2);
  background: rgba(15, 118, 110, 0.08);
}

.avatar {
  width: 52px;
  height: 52px;
  border-radius: 18px;
  overflow: hidden;
  display: grid;
  place-items: center;
  font-weight: 700;
  color: var(--accent-dark);
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.16), rgba(154, 89, 39, 0.2));
}

.avatar img { width: 100%; height: 100%; object-fit: cover; }
.contact-copy { min-width: 0; }
.contact-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.contact-meta {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  flex-shrink: 0;
  color: var(--muted);
  font-size: 0.82rem;
}

.contact-operator-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.35rem;
}

.alert {
  border-radius: 16px;
  padding: 0.6rem 1rem;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.alert-close {
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  font-size: 1rem;
  padding: 0 0.2rem;
  opacity: 0.6;
  flex-shrink: 0;
  line-height: 1;
}

.alert-close:hover {
  opacity: 1;
}

.alert.danger { background: var(--danger-bg); color: var(--danger); }
.alert.success { background: var(--success-bg); color: var(--success); }

.contact-banner,
.card,
.empty {
  border: 1px solid var(--border);
  border-radius: 22px;
  background: var(--panel-card);
}

.contact-banner { padding: 1rem; align-items: flex-start; }
.banner-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 0.3rem; flex-shrink: 0; }

.audio-container {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-top: 0.7rem;
}

.audio-container audio {
  margin-top: 0;
  width: 100%;
}

.transcription-text {
  margin: 0;
  font-size: 0.87rem;
  color: var(--muted);
  font-style: italic;
  padding: 0.45rem 0.75rem;
  border-left: 2px solid var(--accent);
  background: rgba(20, 184, 166, 0.07);
  border-radius: 0 10px 10px 0;
  line-height: 1.5;
  white-space: pre-wrap;
}

.transcribe-btn {
  align-self: flex-start;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.28rem 0.72rem;
  font-size: 0.8rem;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.transcribe-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.transcribe-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.assume-btn {
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0.4rem 0.9rem;
  font-size: 0.82rem;
  font-weight: 600;
  background: transparent;
  color: var(--accent-dark);
  cursor: pointer;
  transition: background 0.18s ease, color 0.18s ease;
}
.assume-btn:hover:not(:disabled) { background: var(--accent); color: white; }
.assume-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.messages {
  gap: 0.8rem;
  padding-right: 0.35rem;
}

.bubble {
  max-width: min(82%, 620px);
  padding: 0.95rem 1rem;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--bubble-in);
}

.bubble.has-actions {
  position: relative;
  padding-right: 3rem;
}

.bubble.inbound { align-self: flex-start; border-top-left-radius: 10px; }
.bubble.outbound {
  align-self: flex-end;
  border-top-right-radius: 10px;
  background: var(--bubble-out);
}
.bubble.system {
  align-self: center;
  max-width: 100%;
  background: var(--bubble-sys);
}

.bubble--team-accent {
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}
.bubble header,
.bubble footer {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.bubble p { margin: 0.5rem 0 0; white-space: pre-wrap; }
.bubble audio,
.bubble video,
.bubble img {
  width: 100%;
  margin-top: 0.7rem;
  border-radius: 18px;
}
.media-button {
  width: 100%;
  margin-top: 0.7rem;
  padding: 0;
  border: none;
  background: transparent;
}
.media-button .media {
  margin-top: 0;
  cursor: zoom-in;
}
.media-button:hover .media {
  transform: scale(1.01);
  box-shadow: 0 14px 28px rgba(44, 36, 29, 0.14);
}
.media {
  display: block;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.video-media { background: rgba(44, 36, 29, 0.08); }
.video-download-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.7rem;
  padding: 0.65rem 1rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel-strong);
  color: var(--accent-dark);
  font-size: 0.88rem;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s;
}
.video-download-link:hover {
  background: rgba(15, 118, 110, 0.08);
  border-color: var(--accent);
}
.video-download-link svg { width: 18px; height: 18px; flex-shrink: 0; }
.gif-video { cursor: zoom-in; }
.sticker-button {
  width: auto;
  max-width: 180px;
}
.sticker-media {
  max-width: 180px;
  background: transparent;
  box-shadow: none;
}
.bubble footer {
  margin-top: 0.6rem;
  color: var(--muted);
  font-size: 0.84rem;
}

.bubble-menu-anchor {
  position: absolute;
  top: 0.7rem;
  right: 0.7rem;
}

.bubble-menu-trigger {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 999px;
  display: grid;
  place-items: center;
  padding: 0;
  background: rgba(15, 118, 110, 0.08);
  color: var(--accent-dark);
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease;
}

.bubble-menu-trigger:hover {
  background: rgba(15, 118, 110, 0.14);
  transform: translateY(-1px);
}

.bubble-menu {
  top: calc(100% + 0.3rem);
  right: 0;
  left: auto;
  bottom: auto;
  min-width: 150px;
  z-index: 5;
}

.reply-quote {
  margin-top: 0.65rem;
  padding: 0.7rem 0.8rem;
  border-left: 3px solid var(--accent);
  border-radius: 14px;
  background: rgba(15, 118, 110, 0.08);
}

.reply-quote.compact {
  margin-top: 0;
}

.reply-quote__sender {
  display: block;
  color: var(--accent-dark);
  font-size: 0.76rem;
  font-weight: 700;
}

.reply-quote p {
  margin: 0.3rem 0 0;
  color: var(--text);
  font-size: 0.88rem;
  line-height: 1.4;
}

.lightbox {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 2rem;
  background: rgba(25, 20, 16, 0.82);
  backdrop-filter: blur(8px);
}

.lightbox-close {
  position: absolute;
  top: 1.2rem;
  right: 1.2rem;
  border: none;
  border-radius: 999px;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.14);
  color: white;
}

.lightbox-content {
  max-width: min(92vw, 1080px);
  max-height: calc(100vh - 5rem);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-media {
  max-width: 100%;
  max-height: calc(100vh - 5rem);
  border-radius: 24px;
  box-shadow: 0 28px 70px rgba(0, 0, 0, 0.32);
}

.composer { margin-top: auto; }

.composer-reply-preview {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
  margin-bottom: 0.65rem;
}

.composer-reply-preview .reply-quote {
  flex: 1;
}

.reply-preview-close {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 999px;
  background: rgba(185, 28, 28, 0.08);
  color: var(--danger);
  font-size: 1rem;
  cursor: pointer;
}

.composer-shell {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 0.7rem;
  min-height: 64px;
  padding: 0.45rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--composer-bg);
  box-shadow: 0 18px 38px rgba(63, 44, 24, 0.08);
}

.composer-shell.is-recording {
  border-color: rgba(185, 28, 28, 0.16);
  background: rgba(255, 249, 248, 0.96);
}

.composer-menu {
  position: relative;
  display: flex;
  align-items: center;
}

.composer-field {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.composer-field textarea {
  min-height: 26px;
  max-height: 140px;
  resize: none;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  padding: 0.7rem 0;
  line-height: 1.5;
}

.composer-field textarea:focus {
  border: none;
  box-shadow: none;
}

.composer-icon {
  width: 48px;
  height: 48px;
  border: none;
  border-radius: 999px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  background: transparent;
  color: var(--text);
  transition: transform 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.composer-icon:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(15, 118, 110, 0.08);
  color: var(--accent-dark);
}

.composer-icon:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.composer-icon svg {
  width: 22px;
  height: 22px;
}

.attach-trigger { color: var(--warm); }

.mic-trigger {
  background: rgba(15, 118, 110, 0.12);
  color: var(--accent-dark);
}

.mic-trigger.send-ready {
  background: var(--accent);
  color: white;
}

.mic-trigger.recording {
  background: rgba(185, 28, 28, 0.12);
  color: var(--danger);
}

.attach-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 0.7rem);
  min-width: 190px;
  z-index: 30;
  padding: 0.35rem;
  border: 1px solid var(--menu-solid-border);
  border-radius: 18px;
  background: var(--menu-solid-bg);
  box-shadow: var(--menu-solid-shadow);
}

.bubble-menu.attach-menu {
  top: calc(100% + 0.3rem);
  right: 0;
  left: auto;
  bottom: auto;
  min-width: 160px;
  background: var(--menu-solid-bg);
  border-color: var(--menu-solid-border);
  box-shadow: var(--menu-solid-shadow);
  opacity: 1;
}

.bubble-menu.attach-menu.open-upward {
  top: auto;
  bottom: calc(100% + 0.3rem);
}

.bubble-menu.attach-menu .attach-option {
  font-weight: 600;
}

.bubble-menu.attach-menu .attach-option:hover {
  background: rgba(15, 118, 110, 0.14);
}

.attach-option {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  border: none;
  border-radius: 14px;
  background: transparent;
  color: var(--text);
  padding: 0.75rem 0.9rem;
  text-align: left;
}

.attach-option:hover { background: rgba(15, 118, 110, 0.08); }
.attach-option svg {
  width: 20px;
  height: 20px;
  color: var(--accent-dark);
}

.recording-status {
  flex: 1;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 0.8rem;
  color: var(--danger);
}

.recording-status strong {
  font-family: "IBM Plex Mono", monospace;
  color: var(--text);
}

.recording-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--danger);
  box-shadow: 0 0 0 6px rgba(185, 28, 28, 0.14);
  animation: pulse 1.2s ease-in-out infinite;
}

.recording-cancel {
  margin-left: auto;
  border: none;
  border-radius: 999px;
  background: rgba(185, 28, 28, 0.08);
  color: var(--danger);
  padding: 0.55rem 0.85rem;
}

.button-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

.card {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
}

.detail-panel {
  font-size: 0.85rem;
  padding: 0.6rem;
}

.detail-panel select,
.detail-panel input,
.detail-panel textarea,
.detail-panel button {
  font-size: 0.82rem;
}

.detail-panel .card {
  padding: 0.75rem;
  gap: 0.5rem;
}

.collapsible-card {
  padding: 0 !important;
  overflow: hidden;
}

.collapsible-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.4rem 0.75rem;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  font: inherit;
  text-align: left;
}

.collapsible-header:hover {
  background: var(--bg-alt);
}

.collapsible-header h3 {
  margin: 0;
  font-size: 0.85rem;
}

.collapsible-arrow {
  font-size: 0.7rem;
  transition: transform 0.2s ease;
  opacity: 0.5;
}

.collapsible-arrow.open {
  transform: rotate(180deg);
}

.collapsible-body {
  display: grid;
  gap: 0.5rem;
  padding: 0 0.75rem 0.75rem;
  max-height: 40vh;
  overflow-y: auto;
}

/* detail-scroll styles unified above */

.empty {
  padding: 1rem 1.1rem;
  color: var(--muted);
}

.empty.large {
  flex: 1;
  min-height: 280px;
  display: grid;
  place-items: center;
}

.admin-user-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.admin-user-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.3rem;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel-strong);
}

.admin-user-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.admin-user-info strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
}

.admin-user-info .sub {
  font-size: 0.7rem;
}

.admin-user-edit {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 140px;
}

.admin-user-edit select {
  padding: 0.4rem 0.6rem;
  border-radius: 10px;
  font-size: 0.82rem;
}

.quick-suggestions {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--attach-bg);
  box-shadow: var(--shadow);
  max-height: 180px;
  overflow: auto;
}

.quick-suggestion-item {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  width: 100%;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--text);
  padding: 0.55rem 0.8rem;
  text-align: left;
  cursor: pointer;
}

.quick-suggestion-item:hover {
  background: rgba(15, 118, 110, 0.08);
}

.quick-suggestion-item strong {
  flex-shrink: 0;
  color: var(--accent-dark);
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.84rem;
}

.quick-suggestion-item .sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 0.5rem);
  min-width: 200px;
  padding: 0.35rem;
  border: 1px solid var(--menu-solid-border);
  border-radius: 18px;
  background: var(--menu-solid-bg);
  box-shadow: var(--menu-solid-shadow);
  z-index: 30;
}

.settings-modal {
  width: min(640px, 92vw);
  max-height: calc(100vh - 4rem);
  overflow: auto;
  padding: 2rem;
  border-radius: 24px;
  background: var(--panel-strong);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  color: var(--text);
}

.settings-section {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1.2rem;
  background: var(--panel-card);
}

.settings-section h3 { margin: 0 0 0.8rem; }

.settings-block {
  margin-bottom: 0.8rem;
}

.settings-toggle {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  font-size: 0.92rem;
}

.settings-toggle input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--accent);
  cursor: pointer;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.08); opacity: 0.82; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 860px) {
  body { overflow: auto; }
  .crm-layout { height: auto; min-height: 100vh; overflow: visible; }
  .crm-topbar { height: auto; padding: 0.6rem 1rem; flex-wrap: wrap; gap: 0.5rem; }
  .topbar-user { align-items: flex-start; }
  .crm-grid {
    flex: none;
    height: auto;
    grid-template-columns: 1fr;
    padding: 0.8rem;
  }
  .crm-nav { flex-direction: row; border-right: none; border-bottom: 1px solid var(--border); padding: 0.5rem; }
  .panel {
    min-height: auto;
    overflow: visible;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .panel-head,
  .toolbar,
  .contact-banner { flex-direction: column; align-items: stretch; }
  .composer-shell { border-radius: 0; }
  .recording-status { flex-wrap: wrap; }
  .recording-cancel { margin-left: 0; }
  .bubble { max-width: 100%; }
  .gc-panel { width: 100vw; }
}

/* ---------------------------------------------------------------------------
   Google Chat Panel (slide-in)
--------------------------------------------------------------------------- */

.gc-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 370px;
  height: 100vh;
  background: var(--panel-solid-bg);
  border-left: 1px solid var(--border);
  box-shadow: -12px 0 32px rgba(0, 0, 0, 0.18);
  z-index: 50;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}

.gc-panel--open {
  transform: translateX(0);
}

/* Header */
.gc-panel__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  background: var(--panel-solid-strong);
  min-height: 52px;
}

.gc-panel__title {
  flex: 1;
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gc-panel__back,
.gc-panel__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text);
  transition: background 0.15s;
}

.gc-panel__back:hover,
.gc-panel__close:hover {
  background: var(--border);
}

/* Conversation list */
.gc-panel__list {
  flex: 1;
  overflow-y: auto;
  padding: 0.25rem 0;
}

.gc-panel__empty {
  padding: 2rem 1.25rem;
  text-align: center;
  color: var(--muted);
  font-size: 0.88rem;
  line-height: 1.5;
}

.gc-conv-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  width: 100%;
  padding: 0.7rem 1rem;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
  border-bottom: 1px solid var(--border);
}

.gc-conv-item:hover {
  background: var(--panel-solid-soft);
}

.gc-conv-item__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  flex-shrink: 0;
}

.gc-conv-item__avatar svg {
  stroke: #fff;
}

.gc-conv-item__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.gc-conv-item__name {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gc-conv-item__preview {
  font-size: 0.8rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gc-conv-item__meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.3rem;
  flex-shrink: 0;
}

.gc-conv-item__time {
  font-size: 0.72rem;
  color: var(--muted);
}

.gc-conv-item__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background: var(--accent);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 600;
}

/* Messages */
.gc-panel__messages {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.gc-msg {
  display: flex;
  flex-direction: column;
  max-width: 85%;
  padding: 0.5rem 0.75rem;
  border-radius: 12px;
  font-size: 0.88rem;
  line-height: 1.45;
  word-break: break-word;
}

.gc-msg--in {
  align-self: flex-start;
  background: var(--bubble-in);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.gc-msg--out {
  align-self: flex-end;
  background: var(--bubble-out);
  border-bottom-right-radius: 4px;
}

.gc-msg__sender {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 0.15rem;
}

.gc-msg__text {
  color: var(--text);
}

.gc-msg__time {
  font-size: 0.68rem;
  color: var(--muted);
  align-self: flex-end;
  margin-top: 0.2rem;
}

.gc-msg__audio {
  max-width: 100%;
  height: 36px;
}

.gc-msg__image {
  max-width: 100%;
  border-radius: 8px;
  margin: 0.25rem 0;
}

/* Composer */
.gc-panel__composer {
  display: flex;
  align-items: flex-end;
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border-top: 1px solid var(--border);
  background: var(--panel-solid-strong);
}

.gc-panel__input {
  flex: 1;
  resize: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.65rem;
  font-size: 0.88rem;
  font-family: inherit;
  background: var(--panel-solid-bg);
  color: var(--text);
  outline: none;
  max-height: 100px;
  line-height: 1.4;
}

.gc-panel__input:focus {
  border-color: var(--accent);
}

.gc-panel__send {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.gc-panel__send:hover:not(:disabled) {
  background: var(--accent-dark);
}

.gc-panel__send:disabled {
  opacity: 0.4;
  cursor: default;
}

/* TopBar badge */
.gc-topbar-badge {
  position: absolute;
  top: -4px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--danger);
  color: #fff;
  font-size: 0.62rem;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* Toast notification */
.gc-toast {
  position: fixed;
  bottom: 1.5rem;
  right: 1.5rem;
  min-width: 280px;
  max-width: 380px;
  padding: 0.75rem 1rem;
  background: var(--panel-strong);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 60;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  cursor: pointer;
  animation: gc-toast-in 0.3s ease;
}

.gc-toast__text {
  flex: 1;
}

.gc-toast__title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
}

.gc-toast__body {
  font-size: 0.78rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes gc-toast-in {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
```

## frontend/src/api.ts

```ts
import type { Auth } from "firebase/auth";

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function buildHeaders(auth: Auth | null, initHeaders?: HeadersInit, isFormData = false) {
  const headers = new Headers(initHeaders || {});
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = auth?.currentUser ? await auth.currentUser.getIdToken() : "";
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function request<T>(auth: Auth | null, path: string, init: RequestInit = {}, isFormData = false): Promise<T> {
  const headers = await buildHeaders(auth, init.headers, isFormData);
  const response = await fetch(path, {
    ...init,
    headers,
  });

  const raw = await response.text();
  const payload = raw ? JSON.parse(raw) : {};
  if (!response.ok) {
    const message = payload.detail || payload.error || payload.message || `Erro HTTP ${response.status}`;
    throw new ApiError(String(message), response.status);
  }
  return payload as T;
}

export function getJson<T>(auth: Auth | null, path: string) {
  return request<T>(auth, path, { method: "GET" });
}

export function sendJson<T>(auth: Auth | null, path: string, body?: JsonValue | Record<string, unknown>) {
  return request<T>(auth, path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function putJson<T>(auth: Auth | null, path: string, body?: JsonValue | Record<string, unknown>) {
  return request<T>(auth, path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function deleteJson<T>(auth: Auth | null, path: string) {
  return request<T>(auth, path, { method: "DELETE" });
}

export function sendForm<T>(auth: Auth | null, path: string, formData: FormData) {
  return request<T>(auth, path, {
    method: "POST",
    body: formData,
  }, true);
}
```

## frontend/src/firebase.ts

```ts
import { initializeApp, type FirebaseApp } from "firebase/app";
import { browserLocalPersistence, getAuth, GoogleAuthProvider, setPersistence, type Auth } from "firebase/auth";
import { getFirestore, initializeFirestore, persistentLocalCache, persistentMultipleTabManager, type Firestore } from "firebase/firestore";

import type { FirebaseWebConfig } from "./types";

export type FirebaseBundle = {
  app: FirebaseApp;
  auth: Auth;
  db: Firestore;
  provider: GoogleAuthProvider;
};

let bundle: FirebaseBundle | null = null;

export async function initializeFirebaseBundle(config: FirebaseWebConfig): Promise<FirebaseBundle> {
  if (bundle) {
    return bundle;
  }

  const app = initializeApp({
    apiKey: config.apiKey,
    authDomain: config.authDomain,
    projectId: config.projectId,
    storageBucket: config.storageBucket,
    appId: config.appId,
    messagingSenderId: config.messagingSenderId || undefined,
    measurementId: config.measurementId || undefined,
  });

  const auth = getAuth(app);
  await setPersistence(auth, browserLocalPersistence);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  let db: Firestore;
  try {
    db = initializeFirestore(app, {
      localCache: persistentLocalCache({
        tabManager: persistentMultipleTabManager(),
      }),
    });
  } catch {
    db = getFirestore(app);
  }

  bundle = {
    app,
    auth,
    db,
    provider,
  };

  return bundle;
}
```

## frontend/src/types.ts

```ts
export type TransportMode = "snapshot" | "polling";

export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  storageBucket: string;
  appId: string;
  messagingSenderId?: string;
  measurementId?: string;
};

export type ClientConfig = {
  auth_mode: "firebase" | string;
  chat_delivery_mode: TransportMode;
  polling_interval_ms: number;
  data_backend: "firestore" | string;
  media_storage_backend: string;
  feature_message_status: boolean;
  feature_google_chat: boolean;
  allowed_email_domain: string;
  firebase_web_config: FirebaseWebConfig;
  firestore: {
    snapshot_enabled: boolean;
    collections: Record<string, string>;
  };
};

export type SessionUser = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  department_id?: number | null;
  department_name?: string;
  email?: string;
  firebase_uid?: string;
  avatar_path?: string;
  is_active?: number;
};

export type BotKey = "comercial" | "financeiro" | "administrativo" | "sac";

export type Department = {
  id: number;
  name: string;
  description?: string;
  is_active?: number;
  sort_order?: number;
  bot_key?: BotKey | null;
};

export type Channel = {
  id: number;
  channel_type: "standard" | "coexistence";
  label: string;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string;
  owner_user_id?: number | null;
  owner_firebase_uid?: string;
  default_department_id?: number | null;
  is_bot_enabled?: boolean;
  is_active?: boolean;
  webhook_subscribed?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type Operator = {
  id: number;
  username?: string;
  display_name: string;
  department_id?: number | null;
  department_name?: string;
  avatar_path?: string;
  role: string;
  email?: string;
  firebase_uid?: string;
};

export type Contact = {
  id: number;
  wa_id: string;
  display_name: string;
  declared_name?: string;
  whatsapp_profile_name?: string;
  created_source?: "webhook" | "manual" | string;
  created_by_user_id?: number | null;
  phone_formatted?: string;
  qualification?: string;
  notes?: string;
  assigned_to?: number | null;
  assigned_name?: string;
  assigned_role?: string;
  assigned_to_uid?: string;
  department_id?: number | null;
  department_name?: string;
  channel_id?: number | null;
  phone_number_id?: string;
  source_channel_type?: "standard" | "coexistence" | string;
  original_operator_id?: number | null;
  converted_by_user_id?: number | null;
  rating?: number | null;
  unread_count?: number;
  unread?: number;
  is_archived?: number;
  first_seen_at?: string;
  last_message_at?: string;
  last_inbound_at?: string;
  contact_avatar_path?: string;
  attendance_protocol?: string;
  attendance_started_at?: string;
  bot_completed?: boolean;
  bot_setor_nome?: string;
};

// Conversation = thread unica (channel_id + wa_id). Mesmo wa_id em
// dois canais aparece como duas Conversations distintas.
// id deterministico: "{channel_id}__{wa_id}"
export type Conversation = {
  id: string;
  contact_id: number;
  wa_id: string;
  channel_id: number | null;
  channel_label?: string;
  channel_type?: "standard" | "coexistence" | string;
  channel_phone_number?: string;
  source_channel_type?: "standard" | "coexistence" | string;
  phone_number_id?: string;
  assigned_to?: number | null;
  assigned_to_uid?: string;
  department_id?: number | null;
  unread_count?: number;
  unread?: number;
  status?: "open" | "archived" | string;
  last_message_at?: string;
  last_inbound_at?: string;
  last_outbound_at?: string;
  created_at?: string;
  // Dados do contato denormalizados (join in-memory feito pelo backend)
  display_name?: string;
  declared_name?: string;
  phone_formatted?: string;
  qualification?: string;
  notes?: string;
  rating?: number | null;
  is_archived?: number;
  contact_avatar_path?: string;
  attendance_protocol?: string;
  attendance_started_at?: string;
};

export type MessageReplyReference = {
  message_id: number;
  preview: string;
  sender_name: string;
};

export type ChatMessage = {
  id: number;
  wa_message_id?: string;
  contact_id: number;
  conversation_id?: string | null;
  direction: "inbound" | "outbound" | "system" | string;
  msg_type: "text" | "image" | "audio" | "video" | "gif" | "sticker" | "document" | "system" | string;
  content?: string;
  media_path?: string;
  media_mime?: string;
  filename?: string;
  status?: string;
  // operator_id e o legado; sender_user_id e o novo (Fase 2C). Sao iguais
  // quando o operador atribuido envia. Diferem em coexistence quando a
  // thread foi transferida — channel_owner_user_id mostra o dono fisico
  // do numero, sender_user_id mostra quem digitou de fato.
  operator_id?: number | null;
  sender_user_id?: number | null;
  channel_owner_user_id?: number | null;
  operator_name?: string;
  assigned_to_uid?: string;
  created_at?: string;
  timestamp_wa?: string;
  transcription?: string;
  reply_to_message_id?: number | null;
  reply_to_preview?: string;
  reply_to_sender_name?: string;
  channel_id?: number | null;
  phone_number_id?: string;
  is_rating_message?: boolean;
  visibility?: "all" | "admin_only" | string;
  is_corrected?: boolean;
  corrected_by_message_id?: number | null;
};

export type TransferRequest = {
  conversation_id?: string;
  contact_id?: number;
  to_user_id: number;
  to_department_id?: number | null;
  reason: string;
  summary: string;
};

export type TemplateButton = {
  type: "QUICK_REPLY" | "URL" | "PHONE_NUMBER" | string;
  text: string;
  url?: string;
  phone_number?: string;
};

export type TemplateComponent = {
  type: "HEADER" | "BODY" | "FOOTER" | "BUTTONS" | string;
  text?: string;
  format?: "TEXT" | "IMAGE" | "VIDEO" | "DOCUMENT" | string;
  example?: {
    body_text?: string[][];
    header_text?: string[];
    header_handle?: string[];
  };
  buttons?: TemplateButton[];
};

export type WhatsAppTemplate = {
  id?: string;
  name: string;
  language: string;
  category: "MARKETING" | "UTILITY" | "AUTHENTICATION" | string;
  status: "APPROVED" | "PENDING" | "REJECTED" | "PAUSED" | string;
  components: TemplateComponent[];
};

export type TemplateParameterValue = {
  type: "text";
  text: string;
};

export type TemplateSendComponent = {
  type: "header" | "body" | "button";
  sub_type?: "quick_reply" | "url";
  index?: string;
  parameters: TemplateParameterValue[];
};

export type SystemSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_roles: string[];
  quick_message_max: number;
  quick_messages_global: { shortcut: string; message: string }[];
  notification_sound_enabled: boolean;
  alarm_enabled: boolean;
  alarm_threshold_minutes: number;
  alarm_department_ids: number[];
  alarm_sound_path: string;
  notification_sound_path: string;
  bot_enabled: boolean;
};

export type UserSettings = {
  chat_prefix_enabled: boolean;
  chat_prefix_name: string;
  quick_messages: { shortcut: string; message: string }[];
};

export type ActiveView = "novos" | "meus" | "nao_qualificados" | "equipe" | "bot";

export type SettingsPage = false | "menu" | "chat" | "quick" | "admin" | "whatsapp" | "dashboard";

export type QuickMessage = { shortcut: string; message: string };

// -- Google Chat (comunicacao interna) --

export type GcConversation = {
  id: number;
  space_id: string;
  space_name: string;
  participants: string[];
  last_message: string;
  last_message_at?: string;
  unread_count: Record<string, number>;
  created_at?: string;
};

export type GcMessage = {
  id: number;
  conversation_id: number;
  gchat_message_id: string;
  sender_email: string;
  sender_name: string;
  msg_type: "text" | "audio" | "image" | "video" | "document" | string;
  content?: string;
  media_path?: string;
  media_mime?: string;
  source: "google_chat" | "crm" | string;
  create_time?: string;
  created_at?: string;
};
```

## frontend/src/vite-env.d.ts

```ts
/// <reference types="vite/client" />
```

## frontend/src/hooks/useClickOutside.ts

```ts
import { useEffect } from "react";

export function useClickOutside(ref: { current: HTMLElement | null }, active: boolean, onClose: () => void) {
  useEffect(() => {
    if (!active) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [active, onClose, ref]);
}
```

## frontend/src/utils/errors.ts

```ts
import { ApiError } from "../api";

export function errorText(error: unknown) {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Erro inesperado";
}
```

## frontend/src/utils/firebase-helpers.ts

```ts
import type { ClientConfig } from "../types";

export function firebaseReady(config: ClientConfig | null) {
  if (!config) return false;
  const item = config.firebase_web_config;
  return Boolean(item.apiKey && item.authDomain && item.projectId && item.appId);
}
```

## frontend/src/utils/formatting.ts

```ts
import type { ChatMessage, MessageReplyReference } from "../types";

const dtf = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export function when(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--" : dtf.format(date);
}

export function formatRecordingTime(seconds: number) {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
  const rest = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

export function messageTypeLabel(value?: string) {
  const kind = String(value || "").trim().toLowerCase();
  if (!kind) return "mensagem";
  if (kind === "unsupported" || kind === "unknown") return "midia";
  return kind;
}

export function messageContentLabel(message: ChatMessage) {
  const content = String(message.content || "").trim();
  if (!content) return "";
  const kind = String(message.msg_type || "").trim().toLowerCase();
  if (content.toLowerCase() === "[unknown]" || content.toLowerCase() === "[unsupported]" || kind === "unsupported" || kind === "unknown") {
    return "Midia nao suportada pelo payload recebido do WhatsApp.";
  }
  return content;
}

export function messageSenderLabel(message: ChatMessage) {
  if (message.direction === "outbound") return message.operator_name || (message.operator_id ? "Equipe" : "Bot");
  if (message.direction === "inbound") return "Cliente";
  return "Sistema";
}

export function messageCopyText(message: ChatMessage) {
  const content = messageContentLabel(message);
  if (content) return content;
  return String(message.transcription || "").trim();
}

export function messagePreviewText(message: ChatMessage) {
  const copyText = messageCopyText(message);
  if (copyText) return copyText;

  const filename = String(message.filename || "").trim();
  const kind = String(message.msg_type || "").trim().toLowerCase();
  if (filename && kind === "document") return `Documento: ${filename}`;
  if (filename && kind === "video") return `Video: ${filename}`;
  if (filename && kind === "image") return `Imagem: ${filename}`;
  if (filename && kind === "audio") return `Audio: ${filename}`;

  if (kind === "audio") return "Audio";
  if (kind === "image") return "Imagem";
  if (kind === "video" || kind === "gif") return "Video";
  if (kind === "sticker") return "Figurinha";
  if (kind === "document") return "Documento";
  if (kind === "location") return "Localizacao";
  if (kind === "template") return "Template";
  return "Mensagem";
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 3)).trimEnd()}...`;
}

export function buildMessageReplyReference(message: ChatMessage): MessageReplyReference {
  return {
    message_id: message.id,
    preview: truncateText(messagePreviewText(message), 280),
    sender_name: truncateText(messageSenderLabel(message), 80),
  };
}

export function messageMoment(value?: string) {
  if (!value) return Number.NaN;
  const date = new Date(value);
  return date.getTime();
}
```

## frontend/src/utils/media.ts

```ts
import type { ChatMessage } from "../types";

export type LightboxMedia = {
  src: string;
  kind: "image" | "video";
  alt: string;
  gifLike?: boolean;
};

export type ResolvedMessageMedia =
  | { kind: "image"; alt: string; gifLike: boolean; sticker: boolean }
  | { kind: "video"; alt: string; gifLike: boolean }
  | { kind: "audio" }
  | { kind: "document" };

export function resolveMessageMedia(message: ChatMessage): ResolvedMessageMedia | null {
  if (!message.media_path) return null;

  const msgType = String(message.msg_type || "").toLowerCase();
  const mime = String(message.media_mime || "").toLowerCase();
  const alt = message.filename || (msgType === "sticker" ? "figurinha" : "midia");

  if (msgType === "audio" || mime.startsWith("audio/")) return { kind: "audio" };
  if (msgType === "gif") {
    if (mime.startsWith("image/")) return { kind: "image", alt, gifLike: true, sticker: false };
    return { kind: "video", alt, gifLike: true };
  }
  if (msgType === "sticker") return { kind: "image", alt, gifLike: false, sticker: true };
  if (msgType === "image" || mime.startsWith("image/")) return { kind: "image", alt, gifLike: mime === "image/gif", sticker: false };
  if (msgType === "video" || mime.startsWith("video/")) return { kind: "video", alt, gifLike: false };
  return { kind: "document" };
}
```

## frontend/src/utils/normalization.ts

```ts
import type { ChatMessage, Contact, Conversation } from "../types";

export function iso(value: unknown) {
  if (!value) return "";
  if (typeof value === "string") return value;
  const item = value as { toDate?: () => Date; seconds?: number; nanoseconds?: number };
  if (typeof item.toDate === "function") return item.toDate().toISOString();
  if (typeof item.seconds === "number") {
    return new Date(item.seconds * 1000 + Math.floor((item.nanoseconds || 0) / 1_000_000)).toISOString();
  }
  return String(value);
}

export function num(value: unknown) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function normalizeContact(record: Record<string, unknown>, docId: string): Contact {
  return {
    id: num(record.id ?? docId),
    wa_id: String(record.wa_id || ""),
    display_name: String(record.display_name || record.phone_formatted || "Contato"),
    declared_name: String(record.declared_name || ""),
    whatsapp_profile_name: String(record.whatsapp_profile_name || ""),
    created_source: String(record.created_source || ""),
    created_by_user_id: record.created_by_user_id == null ? null : num(record.created_by_user_id),
    phone_formatted: String(record.phone_formatted || ""),
    qualification: String(record.qualification || ""),
    notes: String(record.notes || ""),
    assigned_to: record.assigned_to == null ? null : num(record.assigned_to),
    assigned_name: String(record.assigned_name || ""),
    assigned_role: String(record.assigned_role || ""),
    assigned_to_uid: String(record.assigned_to_uid || ""),
    department_id: record.department_id == null ? null : num(record.department_id),
    department_name: String(record.department_name || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    phone_number_id: String(record.phone_number_id || ""),
    source_channel_type: String(record.source_channel_type || ""),
    unread_count: num(record.unread_count ?? record.unread ?? 0),
    unread: num(record.unread ?? record.unread_count ?? 0),
    is_archived: num(record.is_archived ?? 0),
    first_seen_at: iso(record.first_seen_at),
    last_message_at: iso(record.last_message_at),
    last_inbound_at: iso(record.last_inbound_at),
    contact_avatar_path: String(record.contact_avatar_path || ""),
    attendance_protocol: String(record.attendance_protocol || ""),
    attendance_started_at: iso(record.attendance_started_at),
    bot_completed: Boolean(record.bot_completed),
    bot_setor_nome: String(record.bot_setor_nome || ""),
  };
}

export function normalizeMessage(record: Record<string, unknown>, docId: string): ChatMessage {
  return {
    id: num(record.id ?? docId),
    contact_id: num(record.contact_id),
    conversation_id: record.conversation_id == null ? null : String(record.conversation_id),
    direction: String(record.direction || "system"),
    msg_type: String(record.msg_type || "text"),
    content: String(record.content || ""),
    media_path: String(record.media_path || ""),
    media_mime: String(record.media_mime || ""),
    filename: String(record.filename || ""),
    status: String(record.status || ""),
    operator_id: record.operator_id == null ? null : num(record.operator_id),
    sender_user_id: record.sender_user_id == null ? null : num(record.sender_user_id),
    channel_owner_user_id: record.channel_owner_user_id == null ? null : num(record.channel_owner_user_id),
    operator_name: String(record.operator_name || ""),
    created_at: iso(record.created_at),
    timestamp_wa: iso(record.timestamp_wa),
    transcription: String(record.transcription || ""),
    reply_to_message_id: record.reply_to_message_id == null ? null : num(record.reply_to_message_id),
    reply_to_preview: String(record.reply_to_preview || ""),
    reply_to_sender_name: String(record.reply_to_sender_name || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    phone_number_id: String(record.phone_number_id || ""),
    is_corrected: Boolean(record.is_corrected),
    corrected_by_message_id: record.corrected_by_message_id == null ? null : num(record.corrected_by_message_id),
  };
}

export function normalizeConversation(record: Record<string, unknown>, docId: string): Conversation {
  return {
    id: String(record.id || docId),
    contact_id: num(record.contact_id),
    wa_id: String(record.wa_id || ""),
    channel_id: record.channel_id == null ? null : num(record.channel_id),
    channel_label: String(record.channel_label || ""),
    channel_type: String(record.channel_type || ""),
    channel_phone_number: String(record.channel_phone_number || ""),
    source_channel_type: String(record.source_channel_type || ""),
    phone_number_id: String(record.phone_number_id || ""),
    assigned_to: record.assigned_to == null ? null : num(record.assigned_to),
    assigned_to_uid: String(record.assigned_to_uid || ""),
    department_id: record.department_id == null ? null : num(record.department_id),
    unread_count: num(record.unread_count ?? record.unread ?? 0),
    unread: num(record.unread ?? record.unread_count ?? 0),
    status: String(record.status || "open"),
    last_message_at: iso(record.last_message_at),
    last_inbound_at: iso(record.last_inbound_at),
    last_outbound_at: iso(record.last_outbound_at),
    created_at: iso(record.created_at),
    display_name: String(record.display_name || ""),
    declared_name: String(record.declared_name || ""),
    phone_formatted: String(record.phone_formatted || ""),
    qualification: String(record.qualification || ""),
    notes: String(record.notes || ""),
    rating: record.rating == null ? null : num(record.rating),
    is_archived: num(record.is_archived ?? 0),
    contact_avatar_path: String(record.contact_avatar_path || ""),
    attendance_protocol: String(record.attendance_protocol || ""),
    attendance_started_at: iso(record.attendance_started_at),
  };
}
```

## frontend/src/utils/storage.ts

```ts
import type { TransportMode } from "../types";

const TRANSPORT_KEY = "crm_transport_mode";
const THEME_KEY = "crm_theme";

export function transportPref() {
  try {
    const mode = window.localStorage.getItem(TRANSPORT_KEY);
    return mode === "snapshot" || mode === "polling" ? mode : null;
  } catch {
    return null;
  }
}

export function setTransportPref(mode: TransportMode) {
  try {
    window.localStorage.setItem(TRANSPORT_KEY, mode);
  } catch {
    return;
  }
}

export function themePref(): "dark" | "light" {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    // ignore
  }
  return "dark";
}

export function applyTheme(theme: "dark" | "light") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* ignore */ }
}
```

## frontend/src/App.tsx

```tsx
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { CrmProvider, useCrm } from "./context/CrmContext";
import { MoonIcon, SunIcon, GearIcon, PlusIcon, AddressBookIcon, PhotoIcon, VideoIcon, FileIcon, MapPinIcon, MicIcon, SendIcon, SearchIcon, DotsIcon, CloseIcon } from "./components/icons";
import { when, formatRecordingTime, messageTypeLabel, messageContentLabel, messageSenderLabel } from "./utils/formatting";
import { resolveMessageMedia } from "./utils/media";
import { useClickOutside } from "./hooks/useClickOutside";
import { InternalChatPanel, GcBadgeIcon } from "./components/gchat/InternalChatPanel";
import { getJson, sendJson, putJson, deleteJson, sendForm } from "./api";
import type { Channel, ChatMessage, Contact, Conversation, Department, Operator, TemplateComponent, TemplateSendComponent, WhatsAppTemplate } from "./types";

const TEAM_OPERATOR_COLORS = ["#0f766e", "#1d4ed8", "#c2410c", "#7c3aed", "#be123c", "#0f766e", "#0369a1", "#15803d", "#b45309", "#4338ca"];

function withAlpha(hex: string, alpha: string) {
  return `${hex}${alpha}`;
}

function operatorColor(seed: number | string) {
  const text = String(seed || "operator");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) hash = ((hash << 5) - hash + text.charCodeAt(index)) | 0;
  return TEAM_OPERATOR_COLORS[Math.abs(hash) % TEAM_OPERATOR_COLORS.length];
}

function operatorLogin(operator: Partial<Operator> | null | undefined) {
  return String(operator?.username || operator?.email?.split("@")[0] || operator?.display_name || "").trim();
}

function operatorInitial(operator: Partial<Operator> | null | undefined) {
  return (operatorLogin(operator) || "?").slice(0, 1).toUpperCase();
}

function findAssignedOperator(contact: Contact | null | undefined, operators: Operator[]) {
  if (!contact?.assigned_to) return null;
  return operators.find((operator) => operator.id === contact.assigned_to) || null;
}

function findMessageOperator(message: ChatMessage, operators: Operator[], selectedContact: Contact | null) {
  if (message.operator_id) {
    const operator = operators.find((item) => item.id === message.operator_id);
    if (operator) return operator;
  }
  if (message.operator_name) {
    const byName = operators.find((item) => item.display_name === message.operator_name);
    if (byName) return byName;
  }
  return findAssignedOperator(selectedContact, operators);
}

function operatorAccentStyle(color: string | null): CSSProperties | undefined {
  if (!color) return undefined;
  return {
    borderColor: withAlpha(color, "55"),
    boxShadow: `inset 4px 0 0 ${color}`,
  };
}

// ---------------------------------------------------------------------------
// Small inline sub-components (consume context via useCrm)
// ---------------------------------------------------------------------------

function BootScreen() {
  return <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Carregando Firebase e Firestore</h1></div></div>;
}

function LoginScreen() {
  const { config, bundle, busyLogin, error, loginWithGoogle, loginWithEmail } = useCrm();
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="screen"><div className="hero-card"><p className="eyebrow">Hubloc CRM</p><h1>Entrar</h1>
      <p>{config?.allowed_email_domain ? `Use sua conta ${config.allowed_email_domain}.` : "Use uma conta Google autorizada."}</p>
      <button className="primary" onClick={() => void loginWithGoogle()} disabled={!bundle || busyLogin}>{busyLogin ? "Conectando..." : "Entrar com Google"}</button>
      <button className="ghost" style={{ marginTop: "0.6rem" }} onClick={() => setShowEmailForm((v) => !v)}>{showEmailForm ? "Ocultar email/senha" : "Entrar com email/senha"}</button>
      {showEmailForm && (
        <form style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.8rem" }} onSubmit={(e) => { e.preventDefault(); if (email.trim() && password) void loginWithEmail(email.trim(), password); }}>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" autoComplete="email" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="senha" autoComplete="current-password" />
          <button className="primary" type="submit" disabled={!bundle || busyLogin || !email.trim() || !password}>{busyLogin ? "Conectando..." : "Entrar"}</button>
        </form>
      )}
      {error ? <div className="alert danger">{error}</div> : null}
    </div></div>
  );
}

function TopBar() {
  const { sessionUser, config, theme, toggleTheme, showSettings, setShowSettings, toggleSettingsMenu, openSettingsPage, settingsMenuRef, logout } = useCrm();
  const [gcOpen, setGcOpen] = useState(false);
  useClickOutside(settingsMenuRef, showSettings === "menu", () => setShowSettings(false));
  if (!sessionUser) return null;
  const gcEnabled = config?.feature_google_chat ?? false;
  return (
    <header className="crm-topbar">
      <div className="topbar-brand"><p className="eyebrow">Hubloc CRM</p></div>
      <div className="topbar-user">
        <strong>{sessionUser.display_name}</strong>
        <span className="sub">{sessionUser.email || sessionUser.username} · <span className="chip">{sessionUser.role}</span>{sessionUser.department_name ? <> · <span className="chip">{sessionUser.department_name}</span></> : null}</span>
      </div>
      <div className="topbar-actions">
        <button className="composer-icon" onClick={toggleTheme} title={theme === "dark" ? "Tema claro" : "Tema escuro"} aria-label="Alternar tema">
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
        {gcEnabled && (
          <button className="composer-icon" onClick={() => setGcOpen((v) => !v)} title="Chat Interno" aria-label="Chat Interno">
            <GcBadgeIcon totalUnread={0} />
          </button>
        )}
        <div ref={settingsMenuRef} style={{ position: "relative" }}>
          <button className="composer-icon" onClick={toggleSettingsMenu} title="Configuracoes" aria-label="Configuracoes"><GearIcon /></button>
          {showSettings === "menu" && (
            <div className="settings-dropdown">
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("chat")}><span>💬</span><span>Chat</span></button>
              <button type="button" className="attach-option" onClick={() => void openSettingsPage("quick")}><span>⚡</span><span>Mensagens rapidas</span></button>
              {sessionUser.role === "admin" && <button type="button" className="attach-option" onClick={() => void openSettingsPage("admin")}><span>🔧</span><span>Administracao</span></button>}
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor") && <button type="button" className="attach-option" onClick={() => void openSettingsPage("whatsapp")}><span>📱</span><span>WhatsApp Coexistence</span></button>}
              {(sessionUser.role === "admin" || sessionUser.role === "supervisor") && <button type="button" className="attach-option" onClick={() => void openSettingsPage("dashboard")}><span>📊</span><span>Dashboard</span></button>}
            </div>
          )}
        </div>
        <button className="ghost" style={{ padding: "0.55rem 1rem", fontSize: "0.9rem" }} onClick={() => void logout()}>Sair</button>
      </div>
      {gcEnabled && <InternalChatPanel open={gcOpen} onClose={() => setGcOpen(false)} />}
    </header>
  );
}

function NavBar() {
  const { activeView, setActiveView, setQualificationFilter, setEquipeOperatorFilter, isManagerRole, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, systemSettings } = useCrm();
  return (
    <nav className="crm-nav">
      {isManagerRole && systemSettings.bot_enabled && <button className={`nav-item ${activeView === "bot" ? "active" : ""}`} onClick={() => { setActiveView("bot"); setQualificationFilter(""); }} title="Contatos no bot">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="3"/><line x1="8" y1="16" x2="8" y2="16.01"/><line x1="16" y1="16" x2="16" y2="16.01"/><line x1="12" y1="19" x2="12" y2="19.01"/></svg>
        <span className="nav-label">Bot</span>
        {botUnread > 0 && <span className="nav-badge">{botUnread > 99 ? "99+" : botUnread}</span>}
      </button>}
      <button className={`nav-item ${activeView === "novos" ? "active" : ""}`} onClick={() => { setActiveView("novos"); setQualificationFilter(""); }} title="Novos leads">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="12" y1="8" x2="12" y2="14"/><line x1="9" y1="11" x2="15" y2="11"/></svg>
        <span className="nav-label">Novos</span>
        {novosUnread > 0 && <span className="nav-badge">{novosUnread > 99 ? "99+" : novosUnread}</span>}
      </button>
      <button className={`nav-item ${activeView === "meus" ? "active" : ""}`} onClick={() => { setActiveView("meus"); setQualificationFilter(""); }} title="Meus atendimentos">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        <span className="nav-label">Meus</span>
        {meusUnread > 0 && <span className="nav-badge">{meusUnread > 99 ? "99+" : meusUnread}</span>}
      </button>
      <button className={`nav-item ${activeView === "nao_qualificados" ? "active" : ""}`} onClick={() => { setActiveView("nao_qualificados"); setQualificationFilter(""); }} title="Nao qualificados">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>
        <span className="nav-label">N/Q</span>
        {nqUnread > 0 && <span className="nav-badge">{nqUnread > 99 ? "99+" : nqUnread}</span>}
      </button>
      {isManagerRole && <button className={`nav-item ${activeView === "equipe" ? "active" : ""}`} onClick={() => { setActiveView("equipe"); setQualificationFilter(""); setEquipeOperatorFilter(""); }} title="Atendimentos da equipe">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <span className="nav-label">Equipe</span>
        {equipeUnread > 0 && <span className="nav-badge">{equipeUnread > 99 ? "99+" : equipeUnread}</span>}
      </button>}
    </nav>
  );
}

type ContactPickerMode = "list" | "create";

function NewContactModal({ onClose }: { onClose: () => void }) {
  const { createManualContact, busyCreateContact, channels, loadAllContacts, openConversationForContact } = useCrm();
  const [mode, setMode] = useState<ContactPickerMode>("list");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const availableChannels = channels.filter(ch => ch.is_active);
  const [channelId, setChannelId] = useState<number | "">(availableChannels.length === 1 ? availableChannels[0].id : "");
  const [search, setSearchLocal] = useState("");
  const [allContacts, setAllContacts] = useState<Contact[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(false);
  const [busyOpen, setBusyOpen] = useState(false);

  // Carrega contatos quando entra no modo list ou quando search muda (debounce).
  useEffect(() => {
    if (mode !== "list") return;
    let disposed = false;
    setLoadingList(true);
    const handle = window.setTimeout(async () => {
      const res = await loadAllContacts(search);
      if (disposed) return;
      setAllContacts(res.contacts);
      setTotal(res.total);
      setLoadingList(false);
    }, search ? 250 : 0);
    return () => { disposed = true; window.clearTimeout(handle); };
  }, [mode, search, loadAllContacts]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !phone.trim()) return;
    const result = await createManualContact(name.trim(), phone.trim(), channelId ? Number(channelId) : undefined);
    if (result) onClose();
  }

  async function handlePickContact(contact: Contact) {
    if (busyOpen) return;
    setBusyOpen(true);
    try {
      const channel = contact.channel_id || (availableChannels.length === 1 ? availableChannels[0].id : undefined);
      const convId = await openConversationForContact(contact.id, channel);
      if (convId) onClose();
    } finally {
      setBusyOpen(false);
    }
  }

  if (mode === "create") {
    return (
      <div className="lightbox" role="dialog" aria-modal="true" aria-label="Novo contato" onClick={onClose}>
        <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
        <div className="settings-modal" style={{ width: "min(420px, 92vw)" }} onClick={(e) => e.stopPropagation()}>
          <p className="eyebrow">Novo contato</p>
          <h2 style={{ margin: "0 0 1rem" }}>Criar contato manual</h2>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do contato" autoFocus required />
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Telefone (ex: 31999990000)" required />
            {availableChannels.length > 1 && (
              <select value={channelId} onChange={(e) => setChannelId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Selecionar canal</option>
                {availableChannels.map(ch => <option key={ch.id} value={ch.id}>{ch.label || ch.display_phone_number}</option>)}
              </select>
            )}
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "space-between" }}>
              <button type="button" className="ghost" onClick={() => setMode("list")}>Voltar</button>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
                <button type="submit" className="primary" disabled={busyCreateContact || !name.trim() || !phone.trim()}>{busyCreateContact ? "Criando..." : "Criar contato"}</button>
              </div>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Selecionar contato" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" style={{ width: "min(520px, 92vw)", maxHeight: "85vh", display: "flex", flexDirection: "column" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
          <p className="eyebrow" style={{ margin: 0 }}>Total de contatos ({total})</p>
        </div>
        <input
          value={search}
          onChange={(e) => setSearchLocal(e.target.value)}
          placeholder="Buscar contato por nome ou telefone"
          autoFocus
          style={{ marginBottom: "0.75rem" }}
        />
        <button
          type="button"
          className="primary"
          onClick={() => setMode("create")}
          style={{ width: "100%", marginBottom: "0.75rem" }}
        >
          + Novo contato
        </button>
        <div style={{ flex: 1, overflowY: "auto", borderTop: "1px solid var(--border, #2a2f3a)", paddingTop: "0.5rem" }}>
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>Contatos Salvos</p>
          {loadingList && allContacts.length === 0 ? (
            <p className="sub" style={{ padding: "0.5rem 0" }}>Carregando...</p>
          ) : allContacts.length === 0 ? (
            <p className="sub" style={{ padding: "0.5rem 0" }}>{search ? "Nenhum contato encontrado." : "Nenhum contato sincronizado."}</p>
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {allContacts.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => handlePickContact(c)}
                    disabled={busyOpen}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "0.5rem 0.75rem",
                      background: "transparent",
                      border: "none",
                      borderBottom: "1px solid var(--border-soft, #1c2029)",
                      color: "inherit",
                      cursor: busyOpen ? "default" : "pointer",
                    }}
                  >
                    <div style={{ fontWeight: 500 }}>{c.display_name || c.declared_name || c.wa_id}</div>
                    <div className="sub">{c.phone_formatted || c.wa_id}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function ContactList() {
  const { activeView, filteredConversations, contactsById, selectedThreadId, setSelectedThreadId, search, setSearch, qualificationFilter, setQualificationFilter, equipeOperatorFilter, setEquipeOperatorFilter, operators, sessionUser, loadAllContacts } = useCrm();
  const [showNewContact, setShowNewContact] = useState(false);
  // Total de contatos do tenant (inclui agenda telefonica do state_sync,
  // nao apenas conversas ativas). Usado no header da sidebar.
  const [totalContacts, setTotalContacts] = useState(0);
  useEffect(() => {
    let disposed = false;
    void loadAllContacts().then((res) => {
      if (!disposed) setTotalContacts(res.total);
    });
    return () => { disposed = true; };
  }, [loadAllContacts]);
  const viewTitle = activeView === "bot" ? "Bot" : activeView === "novos" ? "Novos Leads" : activeView === "meus" ? "Meus Atendimentos" : activeView === "equipe" ? "Equipe" : "Nao Qualificados";

  // Helper robusto: last_message_at pode vir como string ISO (do polling
  // /api/wa/conversations) OU como Firestore Timestamp object (do snapshot
  // direto). Converte ambos para epoch ms para ordenacao.
  const toMillis = (v: unknown): number => {
    if (!v) return 0;
    if (typeof v === "string") return new Date(v).getTime() || 0;
    if (typeof v === "number") return v;
    if (v instanceof Date) return v.getTime();
    if (typeof v === "object" && v !== null && typeof (v as { toDate?: () => Date }).toDate === "function") {
      return (v as { toDate: () => Date }).toDate().getTime();
    }
    if (typeof v === "object" && v !== null && "seconds" in v) {
      return Number((v as { seconds: number }).seconds) * 1000;
    }
    return 0;
  };
  type RenderItem = { contact: Contact; conversation: Conversation };
  // Fase 3.D: cada item da sidebar e uma Conversation. O Contact e
  // resolvido via contactsById (join in-memory). Mesmo wa_id em 2 canais
  // = 2 entradas distintas, com badge proprio do canal.
  const renderItems: RenderItem[] = filteredConversations
    .slice()
    .sort((a, b) => toMillis(b.last_message_at) - toMillis(a.last_message_at))
    .flatMap((conversation): RenderItem[] => {
      const contact = contactsById.get(conversation.contact_id);
      return contact ? [{ contact, conversation }] : [];
    });

  const visibleTeamOperators = activeView === "equipe"
    ? operators
      .filter((operator) => operator.id !== sessionUser?.id && filteredConversations.some((conv) => conv.assigned_to === operator.id))
      .sort((left, right) => left.display_name.localeCompare(right.display_name))
    : [];
  return (
    <aside className="panel sidebar">
      <div className={`panel-head ${activeView === "equipe" ? "panel-head--stacked" : ""}`}>
        <div>
          <p className="eyebrow">{viewTitle}</p>
          <h2>{renderItems.length} conversa{renderItems.length !== 1 ? "s" : ""}</h2>
          {totalContacts > 0 && activeView === "meus" ? (
            <p className="sub" style={{ marginTop: "0.15rem" }}>{totalContacts} contato{totalContacts !== 1 ? "s" : ""} cadastrado{totalContacts !== 1 ? "s" : ""}</p>
          ) : null}
        </div>
        {activeView === "equipe" && visibleTeamOperators.length ? (
          <div className="operator-presence-strip" aria-label="Operadores com conversas visiveis">
            {visibleTeamOperators.map((operator) => {
              const color = operatorColor(operator.id);
              return (
                <span
                  key={operator.id}
                  className="operator-presence-dot"
                  title={operator.display_name}
                  aria-label={operator.display_name}
                  style={{ borderColor: withAlpha(color, "55"), background: `linear-gradient(135deg, ${withAlpha(color, "2e")}, ${withAlpha(color, "14")})`, color }}
                >
                  {operatorInitial(operator)}
                </span>
              );
            })}
          </div>
        ) : null}
      </div>
      <div className="toolbar">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar contato" />
        {activeView === "meus" && <>
          <button type="button" className="composer-icon" style={{ width: 36, height: 36, flexShrink: 0 }} onClick={() => setShowNewContact(true)} title="Selecionar ou criar contato" aria-label="Selecionar contato"><AddressBookIcon /></button>
          <select className="compact" value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}><option value="">Todos</option><option value="novo">Novo</option><option value="em_atendimento">Em atend.</option><option value="qualificado">Qualificado</option><option value="convertido">Convertido</option></select>
        </>}
        {activeView === "equipe" && <select className="compact" value={equipeOperatorFilter} onChange={(e) => setEquipeOperatorFilter(e.target.value)}><option value="">Todos operadores</option>{operators.filter((op) => op.id !== sessionUser?.id).map((op) => <option key={op.id} value={String(op.id)}>{op.display_name}</option>)}</select>}
      </div>
      <div className="contact-list">
        {renderItems.map(({ contact, conversation }) => {
          // Fase 3.D: assigned/department vem da Conversation (cutover Fase 2C);
          // qualification/notes/avatar continuam no Contact.
          const assignedOperator = activeView === "equipe"
            ? (operators.find((o) => o.id === conversation.assigned_to) || null)
            : null;
          const accent = assignedOperator ? operatorColor(assignedOperator.id) : null;
          const lastMessageAt = conversation.last_message_at || contact.last_message_at;
          const unreadCount = conversation.unread_count ?? conversation.unread ?? 0;
          const channelLabel = conversation.channel_label || "";
          const channelType = conversation.channel_type || conversation.source_channel_type || contact.source_channel_type || "";
          const isActive = selectedThreadId === conversation.id;
          const handleClick = () => setSelectedThreadId(conversation.id);
          return (
            <button key={conversation.id} className={`contact ${isActive ? "active" : ""} ${accent ? "contact--team-accent" : ""}`} onClick={handleClick} style={operatorAccentStyle(accent)}>
              <div className="avatar">{contact.contact_avatar_path ? <img src={contact.contact_avatar_path} alt={contact.display_name} /> : <span>{contact.display_name.slice(0, 1).toUpperCase()}</span>}</div>
              <div className="contact-copy">
                <div className="row">
                  <strong>{contact.display_name}</strong>
                  <div className="contact-meta">
                    {assignedOperator ? (
                      <span
                        className="contact-operator-dot"
                        title={assignedOperator.display_name}
                        aria-label={assignedOperator.display_name}
                        style={{ borderColor: withAlpha(accent || "#0f766e", "55"), background: withAlpha(accent || "#0f766e", "18"), color: accent || "#0f766e" }}
                      >
                        {operatorInitial(assignedOperator)}
                      </span>
                    ) : null}
                    <span>{when(lastMessageAt)}</span>
                  </div>
                </div>
                <div className="sub">{contact.phone_formatted || contact.wa_id}{activeView === "equipe" && assignedOperator ? ` · ${assignedOperator.display_name}` : ""}</div>
                <div className="row">
                  <span className="chip">{contact.qualification || "novo"}</span>
                  {channelLabel ? (
                    <span className="chip" style={{ fontSize: "0.65rem", background: channelType === "coexistence" ? "#dbeafe" : "#dcfce7", color: channelType === "coexistence" ? "#1e40af" : "#166534" }} title={channelType === "coexistence" ? "Canal Coexistence (numero pessoal)" : "Canal Standard (Cloud API)"}>
                      {channelLabel}
                    </span>
                  ) : channelType === "coexistence" ? (
                    <span className="chip" style={{ fontSize: "0.65rem", opacity: 0.7 }}>coex</span>
                  ) : null}
                  {unreadCount ? <b className="badge">{unreadCount}</b> : null}
                </div>
              </div>
            </button>
          );
        })}
        {!renderItems.length ? <div className="empty">{activeView === "bot" ? "Nenhum contato no bot." : activeView === "novos" ? "Nenhum lead novo na fila." : activeView === "meus" ? "Nenhum atendimento ativo." : activeView === "equipe" ? "Nenhum atendimento da equipe." : "Nenhum contato nao qualificado."}</div> : null}
      </div>
      {showNewContact && <NewContactModal onClose={() => setShowNewContact(false)} />}
    </aside>
  );
}

function MessageMedia({ message }: { message: ChatMessage }) {
  const { transcribingMessageId, transcribeMessage, openLightbox } = useCrm();
  const media = resolveMessageMedia(message);
  if (!media || !message.media_path) return null;

  if (media.kind === "image") {
    const cls = ["media"];
    if (media.sticker) cls.push("sticker-media");
    if (media.gifLike) cls.push("gif-media");
    return <button type="button" className={`media-button ${media.sticker ? "sticker-button" : ""}`} onClick={() => openLightbox(message.media_path || "", "image", media.alt, media.gifLike)} aria-label="Ampliar imagem"><img className={cls.join(" ")} src={message.media_path} alt={media.alt} loading="lazy" /></button>;
  }
  if (media.kind === "video") {
    if (media.gifLike) return <button type="button" className="media-button gif-button" onClick={() => openLightbox(message.media_path || "", "video", media.alt, true)} aria-label="Ampliar GIF"><video className="media video-media gif-video" src={message.media_path} autoPlay loop muted playsInline /></button>;
    return <a href={message.media_path} download={message.filename || "video"} target="_blank" rel="noreferrer" className="video-download-link"><VideoIcon /> <span>Baixar video{message.filename ? ` — ${message.filename}` : ""}</span></a>;
  }
  if (media.kind === "audio") return (
    <div className="audio-container">
      <audio controls src={message.media_path} />
      {message.transcription ? <p className="transcription-text">{message.transcription}</p> : (
        <button type="button" className="transcribe-btn" onClick={() => void transcribeMessage(message.id)} disabled={transcribingMessageId === message.id}>{transcribingMessageId === message.id ? "Transcrevendo..." : "🔤 Transcrever"}</button>
      )}
    </div>
  );
  return <a href={message.media_path} target="_blank" rel="noreferrer">Abrir {message.filename || "arquivo"}</a>;
}

function ReplyQuote({ senderName, preview, compact = false }: { senderName: string; preview: string; compact?: boolean }) {
  if (!preview.trim()) return null;
  return (
    <div className={`reply-quote ${compact ? "compact" : ""}`}>
      <span className="reply-quote__sender">{senderName.trim() || "Mensagem"}</span>
      <p>{preview}</p>
    </div>
  );
}

function ChatPanel() {
  const ctx = useCrm();
  const { activeView, operators, selectedContact, sessionUser, error, notice, config, messagesRef, scrollIntentRef, prevMessageCountRef, messages, selectedContactId, loadingMore, setLoadingMore, messageLimit, setMessageLimit, visibleMessages, visibleMessagesFiltered, showChatSearch, chatSearch, setChatSearch, toggleChatSearch, showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef, busyAssume, assumeContact, quickSuggestions, applyQuickMessage, replyTarget, startReplyToMessage, cancelReply, copyMessageText, draft, handleDraftChange, handleDraftKeyDown, submitText, recording, recordingSeconds, discardRecording, handlePrimaryAction, busySend, busyAudio, busyUpload, busyComposerAction, showAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, sendLocation, handleImageSelected, submitFile, imageInputRef, videoInputRef, documentInputRef, attachMenuRef, composerInputRef, correctionTarget, startCorrection, cancelCorrection, correctMessage, updateDeclaredName } = { ...ctx, busyComposerAction: ctx.busyAudio || ctx.busySend };
  const hasDraft = Boolean(draft.trim());
  const [editingNickname, setEditingNickname] = useState(false);
  const [nicknameInput, setNicknameInput] = useState("");
  const [openMessageMenuId, setOpenMessageMenuId] = useState<number | null>(null);
  const [openMessageMenuDirection, setOpenMessageMenuDirection] = useState<"down" | "up">("down");
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const activeMessageMenuRef = useRef<HTMLDivElement | null>(null);
  const selectedOperator = activeView === "equipe" ? findAssignedOperator(selectedContact, operators) : null;
  const selectedOperatorColor = selectedOperator ? operatorColor(selectedOperator.id) : null;
  const noInboundWindow = selectedContact && !selectedContact.last_inbound_at;
  const isManualContact = selectedContact?.created_source === "manual";
  const chatIsEmpty = selectedContact && visibleMessages.length === 0;
  useClickOutside(activeMessageMenuRef, openMessageMenuId !== null, () => setOpenMessageMenuId(null));

  // Scroll management — must live here (not in CrmProvider) because messagesRef is attached to a DOM node inside this component
  useEffect(() => {
    const container = messagesRef.current;
    if (!container) return;
    if (scrollIntentRef.current === "load_older") {
      // Older messages loaded (or all messages already fetched — count unchanged)
      if (messages.length > prevMessageCountRef.current) {
        const newH = container.scrollHeight;
        const prevH = container.dataset.prevScrollHeight;
        if (prevH) container.scrollTop = newH - Number(prevH);
      }
      scrollIntentRef.current = "normal";
    } else if (scrollIntentRef.current === "normal") {
      // Auto-scroll to bottom when:
      // - initial load (prevCount === 0)
      // - new message arrived (count increased) and user was reasonably near bottom
      // - user is already near the bottom
      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const isNewMessage = messages.length > prevMessageCountRef.current && prevMessageCountRef.current > 0;
      if (prevMessageCountRef.current === 0 || isNewMessage || distFromBottom < 300) {
        container.scrollTop = container.scrollHeight;
      }
    }
    prevMessageCountRef.current = messages.length;
    setLoadingMore(false);
  }, [messages, selectedContactId]);

  // Infinite scroll — attach scroll listener to load older messages
  useEffect(() => {
    const container = messagesRef.current;
    if (!container || !selectedContactId) return undefined;
    const handleScroll = () => {
      const hasPotentialOlderMessages = messages.length >= messageLimit;
      if (container.scrollTop < 40 && !loadingMore && hasPotentialOlderMessages) {
        container.dataset.prevScrollHeight = String(container.scrollHeight);
        scrollIntentRef.current = "load_older";
        setLoadingMore(true);
        setMessageLimit((prev) => prev + 15);
      }
    };
    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [selectedContactId, loadingMore, messageLimit, messages.length]);

  useEffect(() => {
    setOpenMessageMenuId(null);
  }, [selectedContactId]);

  useEffect(() => {
    if (openMessageMenuId === null) {
      setOpenMessageMenuDirection("down");
      return undefined;
    }

    const updateMenuDirection = () => {
      const anchor = activeMessageMenuRef.current;
      const container = messagesRef.current;
      const menu = anchor?.querySelector<HTMLElement>(".bubble-menu");
      if (!anchor || !container || !menu) return;

      const anchorRect = anchor.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const menuHeight = menu.offsetHeight;
      const gap = 8;
      const spaceBelow = containerRect.bottom - anchorRect.bottom;
      const spaceAbove = anchorRect.top - containerRect.top;
      setOpenMessageMenuDirection(spaceBelow < menuHeight + gap && spaceAbove > spaceBelow ? "up" : "down");
    };

    const frameId = window.requestAnimationFrame(updateMenuDirection);
    const scrollContainer = messagesRef.current;
    scrollContainer?.addEventListener("scroll", updateMenuDirection, { passive: true });
    window.addEventListener("resize", updateMenuDirection);

    return () => {
      window.cancelAnimationFrame(frameId);
      scrollContainer?.removeEventListener("scroll", updateMenuDirection);
      window.removeEventListener("resize", updateMenuDirection);
    };
  }, [messagesRef, openMessageMenuId]);

  return (
    <main className="panel chat-panel">
      {error ? <div className="alert danger"><span>{error}</span><button type="button" className="alert-close" onClick={() => ctx.setError("")}>&#10005;</button></div> : null}
      {notice ? <div className="alert success"><span>{notice}</span><button type="button" className="alert-close" onClick={() => ctx.setNotice("")}>&#10005;</button></div> : null}
      {selectedContact ? <>
        <div className="contact-banner">
          <div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", flexWrap: "wrap" }}>
              <strong>{selectedContact.whatsapp_profile_name || selectedContact.phone_formatted || selectedContact.wa_id}</strong>
              {selectedContact.declared_name ? (
                <span className="sub" style={{ fontSize: "0.82rem" }}>- {selectedContact.declared_name}</span>
              ) : null}
            </div>
            {selectedOperator ? (
              <div className="contact-operator-chip">
                <span
                  className="contact-operator-dot"
                  title={selectedOperator.display_name}
                  aria-label={selectedOperator.display_name}
                  style={{ borderColor: withAlpha(selectedOperatorColor || "#0f766e", "55"), background: withAlpha(selectedOperatorColor || "#0f766e", "18"), color: selectedOperatorColor || "#0f766e" }}
                >
                  {operatorInitial(selectedOperator)}
                </span>
                <span className="sub" style={{ color: selectedOperatorColor || undefined }}>{selectedOperator.display_name}</span>
              </div>
            ) : null}
            <div className="sub">{selectedContact.phone_formatted || selectedContact.wa_id}{selectedContact.assigned_name ? ` · ${selectedContact.assigned_name}` : ""}</div>
            {selectedContact.attendance_protocol ? <div className="sub" style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: "0.72rem", marginTop: "0.2rem" }}>{selectedContact.attendance_protocol}{selectedContact.attendance_started_at ? ` · inicio ${when(selectedContact.attendance_started_at)}` : ""}</div> : null}
          </div>
          <div className="banner-actions">
            <div className="chips">
              <span className="chip">{selectedContact.department_name || "Sem setor"}</span>
              <span className="chip">{selectedContact.qualification || "sem classificacao"}</span>
            </div>
            <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.4rem", justifyContent: "flex-end" }}>
              {!selectedContact.assigned_to || selectedContact.assigned_to !== sessionUser!.id ? <button className="assume-btn" onClick={() => void assumeContact(selectedContact.id)} disabled={busyAssume}>{busyAssume ? "Assumindo..." : "Assumir atendimento"}</button> : null}
              <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleChatSearch} aria-label="Buscar na conversa" title="Buscar na conversa">{showChatSearch ? <CloseIcon /> : <SearchIcon />}</button>
              <div ref={dotsMenuRef} style={{ position: "relative" }}>
                <button className="composer-icon" style={{ width: 34, height: 34 }} onClick={toggleDotsMenu} aria-label="Mais opcoes" title="Mais opcoes"><DotsIcon /></button>
                {showDotsMenu ? (
                  <div className="attach-menu" style={{ right: 0, left: "auto", bottom: "auto", top: "calc(100% + 0.5rem)", minWidth: 220 }}>
                    <button type="button" className="attach-option" onClick={() => { setShowTemplatePicker(true); closeDotsMenu(); }}><span>📋</span><span>Enviar template</span></button>
                    <div style={{ height: 1, background: "var(--border)", margin: "0.3rem 0.5rem" }} />
                    <button type="button" className="attach-option" onClick={() => { setNicknameInput(selectedContact.declared_name || ""); setEditingNickname(true); closeDotsMenu(); }}><span>✏️</span><span>Editar apelido</span></button>
                    {selectedContact.attendance_protocol ? <button type="button" className="attach-option" onClick={() => { navigator.clipboard.writeText(selectedContact.attendance_protocol!).catch(() => {}); closeDotsMenu(); ctx.setNotice(`Protocolo copiado: ${selectedContact.attendance_protocol}`); }}><span>📋</span><span>Copiar protocolo</span></button> : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {editingNickname ? (
          <form className="toolbar" onSubmit={(e) => { e.preventDefault(); void updateDeclaredName(selectedContact.id, nicknameInput.trim()); setEditingNickname(false); }} style={{ gap: "0.4rem" }}>
            <input value={nicknameInput} onChange={(e) => setNicknameInput(e.target.value)} placeholder="Apelido do contato (vazio para remover)" autoFocus style={{ flex: 1 }} />
            <button type="submit" className="ghost" style={{ padding: "0.6rem 0.8rem", fontSize: "0.82rem" }}>Salvar</button>
            <button type="button" className="ghost" style={{ padding: "0.6rem 0.8rem", fontSize: "0.82rem", opacity: 0.6 }} onClick={() => setEditingNickname(false)}>x</button>
          </form>
        ) : null}
        {showChatSearch ? <div className="toolbar"><input value={chatSearch} onChange={(e) => setChatSearch(e.target.value)} placeholder="Buscar na conversa..." autoFocus />{chatSearch ? <span className="sub">{(visibleMessagesFiltered ?? []).length} resultado(s)</span> : null}</div> : null}

        <div className="messages" ref={messagesRef}>
          {chatIsEmpty && isManualContact ? (
            <div className="empty" style={{ alignSelf: "center", textAlign: "center", marginTop: "2rem" }}>
              <p style={{ marginBottom: "0.5rem" }}>Contato criado manualmente.</p>
              <p>Envie um template para iniciar a conversa.</p>
            </div>
          ) : null}
          {loadingMore && <div className="sub" style={{ textAlign: "center", padding: "0.5rem" }}>Carregando mensagens anteriores...</div>}
          {(visibleMessagesFiltered ?? visibleMessages).map((message) => {
            const canInteract = message.direction !== "system";
            const isMenuOpen = openMessageMenuId === message.id;
            const bubbleOperator = activeView === "equipe" && message.direction === "outbound" ? findMessageOperator(message, operators, selectedContact) : null;
            const bubbleColor = bubbleOperator ? operatorColor(bubbleOperator.id) : null;
            return (
              <article key={message.id} className={`bubble ${message.direction} ${canInteract ? "has-actions" : ""} ${bubbleColor ? "bubble--team-accent" : ""}`} style={operatorAccentStyle(bubbleColor)}>
                {canInteract ? (
                  <div className="bubble-menu-anchor" ref={isMenuOpen ? activeMessageMenuRef : null}>
                    <button type="button" className="bubble-menu-trigger" onClick={() => setOpenMessageMenuId((current) => current === message.id ? null : message.id)} aria-label="Acoes da mensagem" aria-expanded={isMenuOpen}>v</button>
                    {isMenuOpen ? (
                      <div className={`bubble-menu attach-menu ${openMessageMenuDirection === "up" ? "open-upward" : ""}`}>
                        <button type="button" className="attach-option" onClick={() => { startReplyToMessage(message); setOpenMessageMenuId(null); }}><span>Responder</span></button>
                        <button type="button" className="attach-option" onClick={() => { void copyMessageText(message); setOpenMessageMenuId(null); }}><span>Copiar</span></button>
                        {message.direction === "outbound" && message.msg_type === "text" && !message.is_corrected && (message.operator_id === sessionUser?.id || sessionUser?.role === "admin" || sessionUser?.role === "supervisor") ? (
                          <button type="button" className="attach-option" onClick={() => { startCorrection(message); setOpenMessageMenuId(null); }}><span>Corrigir</span></button>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <header><strong style={bubbleColor ? { color: bubbleColor } : undefined}>{messageSenderLabel(message)}</strong><span>{when(message.created_at || message.timestamp_wa)}</span></header>
                {message.reply_to_preview ? <ReplyQuote senderName={message.reply_to_sender_name || "Mensagem"} preview={message.reply_to_preview} /> : null}
                {messageContentLabel(message) ? <p>{messageContentLabel(message)}</p> : null}
                <MessageMedia message={message} />
                <footer><span>{messageTypeLabel(message.msg_type)}{message.is_corrected ? " · corrigida" : ""}</span>{config?.feature_message_status !== false && <span>{message.status || "ok"}</span>}</footer>
              </article>
            );
          })}
          {visibleMessagesFiltered !== null && visibleMessagesFiltered.length === 0 ? <div className="empty" style={{ alignSelf: "center" }}>Nenhuma mensagem encontrada para "{chatSearch}".</div> : null}
        </div>

        {quickSuggestions.length > 0 && (
          <div className="quick-suggestions">{quickSuggestions.map((qm, idx) => (
            <button key={idx} type="button" className="quick-suggestion-item" onClick={() => applyQuickMessage(qm)}>
              <strong>{qm.shortcut.startsWith("/") ? qm.shortcut : `/${qm.shortcut}`}</strong>
              <span className="sub">{qm.message.length > 80 ? qm.message.slice(0, 80) + "..." : qm.message}</span>
            </button>
          ))}</div>
        )}

        {noInboundWindow ? (
          <div className="composer" style={{ padding: "0.8rem 1rem" }}>
            <div className="sub" style={{ textAlign: "center", width: "100%" }}>Janela de 24h indisponivel. Use o menu de templates para iniciar a conversa.</div>
          </div>
        ) : (
        <form className="composer" onSubmit={correctionTarget ? (e) => { e.preventDefault(); if (draft.trim()) void correctMessage(correctionTarget.id, draft.trim()); } : submitText}>
          {correctionTarget ? (
            <div className="composer-reply-preview" style={{ borderLeft: "3px solid var(--warm)" }}>
              <div style={{ flex: 1 }}>
                <span className="sub" style={{ fontWeight: 600, color: "var(--warm)" }}>Corrigindo mensagem</span>
                <p style={{ margin: "0.2rem 0 0", fontSize: "0.85rem" }}>{(correctionTarget.content || "").slice(0, 100)}</p>
              </div>
              <button type="button" className="reply-preview-close" onClick={cancelCorrection} aria-label="Cancelar correcao">x</button>
            </div>
          ) : replyTarget ? (
            <div className="composer-reply-preview">
              <ReplyQuote senderName={replyTarget.sender_name} preview={replyTarget.preview} compact />
              <button type="button" className="reply-preview-close" onClick={cancelReply} aria-label="Cancelar resposta">x</button>
            </div>
          ) : null}
          <div className={`composer-shell ${recording ? "is-recording" : ""}`}>
            <div className="composer-menu" ref={attachMenuRef}>
              <button type="button" className="composer-icon attach-trigger" onClick={toggleAttachMenu} disabled={!selectedContact || busyUpload || busyAudio} aria-label="Abrir menu de anexos"><PlusIcon /></button>
              {showAttachMenu ? (
                <div className="attach-menu">
                  <button type="button" className="attach-option" onClick={openImagePicker}><PhotoIcon /><span>Foto</span></button>
                  <button type="button" className="attach-option" onClick={openVideoPicker}><VideoIcon /><span>Vídeo</span></button>
                  <button type="button" className="attach-option" onClick={openDocPicker}><FileIcon /><span>Documento</span></button>
                  <button type="button" className="attach-option" onClick={() => void sendLocation()}><MapPinIcon /><span>Localização</span></button>
                </div>
              ) : null}
              <input ref={imageInputRef} type="file" accept="image/*" onChange={handleImageSelected} hidden />
              <input ref={videoInputRef} type="file" accept="video/*" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Vídeo"); }} hidden />
              <input ref={documentInputRef} type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.zip,.csv" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void submitFile(f, "Documento"); }} hidden />
            </div>
            <div className="composer-field">
              {recording ? <div className="recording-status"><span className="recording-dot" /><span>Gravando audio</span><strong>{formatRecordingTime(recordingSeconds)}</strong><button type="button" className="recording-cancel" onClick={discardRecording}>Cancelar</button></div> : <textarea ref={composerInputRef} value={draft} onChange={handleDraftChange} onKeyDown={handleDraftKeyDown} rows={1} placeholder="Digite uma mensagem" disabled={busySend || busyAudio} />}
            </div>
            <button type="button" className={`composer-icon mic-trigger ${recording ? "recording" : ""} ${hasDraft && !recording ? "send-ready" : ""}`} onClick={handlePrimaryAction} disabled={!selectedContact || busyUpload || busyComposerAction} aria-label={recording ? "Enviar audio gravado" : hasDraft ? "Enviar mensagem" : "Gravar audio"}>
              {busyComposerAction ? <span className="button-spinner" aria-hidden="true" /> : recording || hasDraft ? <SendIcon /> : <MicIcon />}
            </button>
          </div>
        </form>
        )}
      </> : <div className="empty large">Selecione um contato para abrir a conversa.</div>}
      {showTemplatePicker && selectedContact ? (
        <TemplatePickerModal
          contactId={selectedContact.id}
          channelId={selectedContact.channel_id ?? null}
          onClose={() => setShowTemplatePicker(false)}
        />
      ) : null}
    </main>
  );
}

function countBodyPlaceholders(text: string): number {
  const matches = text.match(/\{\{\d+\}\}/g);
  return matches ? matches.length : 0;
}

function renderTemplatePreview(components: TemplateComponent[], vars: Record<string, string>): { header: string; body: string; footer: string; buttons: string[] } {
  let header = "";
  let body = "";
  let footer = "";
  const buttons: string[] = [];
  for (const c of components || []) {
    const type = String(c.type || "").toUpperCase();
    if (type === "HEADER" && c.format === "TEXT" && c.text) {
      header = c.text.replace(/\{\{(\d+)\}\}/g, (_, idx) => vars[`header_${idx}`] || `{{${idx}}}`);
    } else if (type === "BODY" && c.text) {
      body = c.text.replace(/\{\{(\d+)\}\}/g, (_, idx) => vars[`body_${idx}`] || `{{${idx}}}`);
    } else if (type === "FOOTER" && c.text) {
      footer = c.text;
    } else if (type === "BUTTONS" && c.buttons) {
      for (const b of c.buttons) {
        buttons.push(b.text || "");
      }
    }
  }
  return { header, body, footer, buttons };
}

function TemplatePickerModal({ contactId, channelId, onClose }: { contactId: number; channelId: number | null; onClose: () => void }) {
  const { fetchTemplates, sendTemplate, busyTemplate } = useCrm();
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<"ALL" | "MARKETING" | "UTILITY" | "AUTHENTICATION">("ALL");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setLoadError("");
      const list = await fetchTemplates(channelId);
      if (!cancelled) {
        setTemplates(list);
        setLoading(false);
        if (!list.length) setLoadError("Nenhum template aprovado encontrado na WABA.");
      }
    })();
    return () => { cancelled = true; };
  }, [fetchTemplates, channelId]);

  const selected = selectedIdx !== null ? templates[selectedIdx] : null;
  const filtered = categoryFilter === "ALL" ? templates : templates.filter((t) => String(t.category).toUpperCase() === categoryFilter);
  const preview = selected ? renderTemplatePreview(selected.components || [], vars) : null;

  // Discover placeholders once template selected
  const bodyComp = selected?.components?.find((c) => String(c.type).toUpperCase() === "BODY");
  const headerComp = selected?.components?.find((c) => String(c.type).toUpperCase() === "HEADER" && c.format === "TEXT");
  const bodyPlaceholders = bodyComp?.text ? countBodyPlaceholders(bodyComp.text) : 0;
  const headerPlaceholders = headerComp?.text ? countBodyPlaceholders(headerComp.text) : 0;

  function pickTemplate(idx: number) {
    setSelectedIdx(idx);
    setVars({});
  }

  async function submit() {
    if (!selected) return;
    const components: TemplateSendComponent[] = [];
    if (headerPlaceholders > 0) {
      const parameters = [];
      for (let i = 1; i <= headerPlaceholders; i += 1) {
        parameters.push({ type: "text" as const, text: vars[`header_${i}`] || "" });
      }
      components.push({ type: "header", parameters });
    }
    if (bodyPlaceholders > 0) {
      const parameters = [];
      for (let i = 1; i <= bodyPlaceholders; i += 1) {
        parameters.push({ type: "text" as const, text: vars[`body_${i}`] || "" });
      }
      components.push({ type: "body", parameters });
    }
    const ok = await sendTemplate({
      contactId,
      templateName: selected.name,
      language: selected.language,
      components: components.length ? components : undefined,
    });
    if (ok) onClose();
  }

  const canSubmit = selected && !busyTemplate
    && Array.from({ length: bodyPlaceholders }, (_, i) => `body_${i + 1}`).every((k) => (vars[k] || "").trim())
    && Array.from({ length: headerPlaceholders }, (_, i) => `header_${i + 1}`).every((k) => (vars[k] || "").trim());

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enviar template" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 820, maxHeight: "85vh", overflow: "auto" }}>
        <h2 style={{ margin: "0 0 1rem" }}>Enviar template WhatsApp</h2>

        {loading ? <p>Carregando templates aprovados da Meta...</p> : null}
        {loadError ? (
          <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "0.8rem", color: "#991b1b", marginBottom: "1rem" }}>
            {loadError} Crie e aprove um template em <a href="https://business.facebook.com/wa/manage/message-templates" target="_blank" rel="noreferrer">WhatsApp Manager</a>.
          </div>
        ) : null}

        {!loading && templates.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1rem" }}>
            <div>
              <div style={{ display: "flex", gap: "0.3rem", marginBottom: "0.6rem", flexWrap: "wrap" }}>
                {(["ALL", "MARKETING", "UTILITY", "AUTHENTICATION"] as const).map((c) => (
                  <button key={c} type="button" className="chip" onClick={() => setCategoryFilter(c)} style={{ cursor: "pointer", opacity: categoryFilter === c ? 1 : 0.6 }}>{c}</button>
                ))}
              </div>
              <div style={{ maxHeight: "55vh", overflowY: "auto", border: "1px solid var(--border)", borderRadius: 8 }}>
                {filtered.map((t, idx) => {
                  const globalIdx = templates.indexOf(t);
                  const active = globalIdx === selectedIdx;
                  return (
                    <button
                      key={`${t.name}-${t.language}`}
                      type="button"
                      onClick={() => pickTemplate(globalIdx)}
                      style={{
                        display: "block", width: "100%", textAlign: "left",
                        padding: "0.6rem 0.8rem",
                        border: "none",
                        borderBottom: idx < filtered.length - 1 ? "1px solid var(--border)" : "none",
                        background: active ? "var(--accent, #e0f2fe)" : "transparent",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{t.name}</div>
                      <div className="sub" style={{ fontSize: "0.72rem" }}>{t.category} · {t.language}</div>
                    </button>
                  );
                })}
                {filtered.length === 0 ? <p style={{ padding: "0.8rem", textAlign: "center" }} className="sub">Sem templates nessa categoria.</p> : null}
              </div>
            </div>

            <div>
              {selected ? (
                <>
                  <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.8rem", background: "var(--bg-muted, #f9fafb)", marginBottom: "1rem" }}>
                    <div className="sub" style={{ fontSize: "0.7rem", marginBottom: "0.3rem" }}>Preview</div>
                    {preview?.header ? <div style={{ fontWeight: 600, marginBottom: "0.3rem" }}>{preview.header}</div> : null}
                    {preview?.body ? <div style={{ whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>{preview.body}</div> : null}
                    {preview?.footer ? <div className="sub" style={{ fontSize: "0.75rem", marginTop: "0.3rem" }}>{preview.footer}</div> : null}
                    {preview?.buttons && preview.buttons.length > 0 ? (
                      <div style={{ display: "flex", gap: "0.3rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
                        {preview.buttons.map((b, i) => <span key={i} className="chip" style={{ fontSize: "0.72rem" }}>{b}</span>)}
                      </div>
                    ) : null}
                  </div>

                  {(headerPlaceholders > 0 || bodyPlaceholders > 0) ? (
                    <div style={{ marginBottom: "1rem" }}>
                      <div className="sub" style={{ marginBottom: "0.4rem", fontWeight: 600 }}>Variáveis</div>
                      {Array.from({ length: headerPlaceholders }, (_, i) => i + 1).map((n) => (
                        <div key={`h-${n}`} style={{ marginBottom: "0.4rem" }}>
                          <label className="sub" style={{ fontSize: "0.75rem" }}>Cabeçalho {`{{${n}}}`}</label>
                          <input
                            style={{ width: "100%", padding: "0.4rem 0.6rem" }}
                            value={vars[`header_${n}`] || ""}
                            onChange={(e) => setVars((v) => ({ ...v, [`header_${n}`]: e.target.value }))}
                          />
                        </div>
                      ))}
                      {Array.from({ length: bodyPlaceholders }, (_, i) => i + 1).map((n) => (
                        <div key={`b-${n}`} style={{ marginBottom: "0.4rem" }}>
                          <label className="sub" style={{ fontSize: "0.75rem" }}>Corpo {`{{${n}}}`}</label>
                          <input
                            style={{ width: "100%", padding: "0.4rem 0.6rem" }}
                            value={vars[`body_${n}`] || ""}
                            onChange={(e) => setVars((v) => ({ ...v, [`body_${n}`]: e.target.value }))}
                          />
                        </div>
                      ))}
                    </div>
                  ) : <p className="sub" style={{ fontSize: "0.8rem" }}>Template sem variáveis.</p>}

                  <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                    <button type="button" className="ghost" onClick={onClose}>Cancelar</button>
                    <button type="button" className="primary" onClick={() => void submit()} disabled={!canSubmit}>
                      {busyTemplate ? "Enviando..." : "Enviar template"}
                    </button>
                  </div>
                </>
              ) : (
                <p className="sub">Selecione um template na lista à esquerda.</p>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CollapsibleCard({ title, defaultOpen = true, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="card collapsible-card">
      <button type="button" className="collapsible-header" onClick={() => setOpen((v) => !v)}>
        <h3>{title}</h3>
        <span className={`collapsible-arrow ${open ? "open" : ""}`}>&#9662;</span>
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

function DetailPanel() {
  const { bundle, selectedContact, selectedThreadId, conversations, sessionUser, isManagerRole, operators, departments, channels, qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary, busySave, busyTransfer, saveQualification, transferContact, editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole, setError, setNotice, refreshPollingViews } = useCrm();
  const [busyReturnBot, setBusyReturnBot] = useState(false);
  const [bulkFromUser, setBulkFromUser] = useState<number | "">("");
  const [bulkAction, setBulkAction] = useState<"return_to_bot" | "transfer">("return_to_bot");
  const [bulkToUser, setBulkToUser] = useState<number | "">("");
  const [busyBulk, setBusyBulk] = useState(false);
  const [busyResetCounter, setBusyResetCounter] = useState<number | null>(null);

  const resetAssumeCounter = useCallback(async (userId: number, displayName: string) => {
    if (!bundle) return;
    setBusyResetCounter(userId);
    try {
      await sendJson(bundle.auth, `/api/admin/operator/${userId}/reset-assume-counter`, {});
      setNotice(`Contador de ${displayName} resetado.`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyResetCounter(null);
  }, [bundle, setError, setNotice]);

  const returnToBot = useCallback(async (contactId: number) => {
    if (!bundle) return;
    setBusyReturnBot(true);
    try {
      await sendJson(bundle.auth, `/api/wa/contact/${contactId}/return-to-bot`);
      setNotice("Contato devolvido ao bot");
      await refreshPollingViews();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyReturnBot(false);
  }, [bundle, setError, setNotice, refreshPollingViews]);

  const executeBulkReassign = useCallback(async () => {
    if (!bundle || !bulkFromUser) return;
    setBusyBulk(true);
    try {
      const res = await sendJson<{ count: number }>(bundle.auth, "/api/admin/bulk-reassign", {
        from_user_id: bulkFromUser,
        action: bulkAction,
        to_user_id: bulkAction === "transfer" ? bulkToUser || undefined : undefined,
      });
      setNotice(`${res.count} contato(s) reatribuido(s)`);
      setBulkFromUser("");
      await refreshPollingViews();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyBulk(false);
  }, [bundle, bulkFromUser, bulkAction, bulkToUser, setError, setNotice, refreshPollingViews]);

  // V2 Fase 3: prioriza o canal da thread selecionada (selectedThreadId)
  // sobre o canal "primario" do contato. Se o usuario abriu a linha do
  // canal coexistence, o painel direito reflete esse canal.
  const selectedThread = selectedThreadId ? conversations.find((c) => c.id === selectedThreadId) : null;
  const threadChannelId = selectedThread?.channel_id ?? selectedContact?.channel_id ?? null;
  const contactChannel = threadChannelId ? channels.find((ch) => ch.id === threadChannelId) : null;

  return (
    <aside className="panel detail-panel">
      <div className="panel-head"><div><p className="eyebrow">Contato</p><h2>Operacao</h2></div><span className="sub">{operators.length} operadores - {departments.length} setores</span></div>
      <div className="detail-scroll">
        {selectedContact ? <>
          {/* Info do canal */}
          {contactChannel ? (
            <div style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", opacity: 0.7, display: "flex", gap: "0.3rem", alignItems: "center" }}>
              <span className="chip" style={{ fontSize: "0.65rem" }}>{contactChannel.channel_type === "standard" ? "Cloud API" : "Coexistence"}</span>
              <span>{contactChannel.label}</span>
            </div>
          ) : null}

          {/* Rating (visivel apenas para admin/supervisor) */}
          {isManagerRole && selectedContact.qualification === "convertido" ? (
            <div style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
              {selectedContact.rating != null ? (
                <><span style={{ fontWeight: 600 }}>Avaliacao:</span><span className="chip" style={{ fontSize: "0.8rem", background: selectedContact.rating >= 7 ? "var(--success)" : selectedContact.rating >= 4 ? "#e6a817" : "var(--danger)", color: "#fff" }}>{selectedContact.rating}/10</span></>
              ) : (
                <span className="sub">Avaliacao pendente...</span>
              )}
            </div>
          ) : null}

          <CollapsibleCard title="Qualificacao">
            <select value={qualification} onChange={(e) => setQualification(e.target.value)}><option value="novo">Novo</option><option value="em_atendimento">Em atendimento</option><option value="qualificado">Qualificado</option><option value="nao_qualificado">Nao qualificado</option><option value="convertido">Convertido</option></select>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Notas do atendimento" />
            <button className="primary" onClick={() => void saveQualification()} disabled={busySave}>{busySave ? "Salvando..." : "Salvar"}</button>
            {isManagerRole && selectedContact.assigned_to ? (
              <button className="ghost" style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} disabled={busyReturnBot} onClick={() => { if (confirm("Devolver este contato para a fila do bot?")) void returnToBot(selectedContact.id); }}>{busyReturnBot ? "Devolvendo..." : "Devolver ao bot"}</button>
            ) : null}
          </CollapsibleCard>
          <CollapsibleCard title="Transferencia" defaultOpen={false}>
            <select value={toUserId} onChange={(e) => setToUserId(e.target.value ? Number(e.target.value) : "")}><option value="">Selecione um operador</option>{operators.filter((item) => item.id !== sessionUser!.id).map((item) => <option key={item.id} value={item.id}>{item.display_name} - {item.department_name || "Sem setor"}</option>)}</select>
            <select value={toDepartmentId} onChange={(e) => setToDepartmentId(e.target.value ? Number(e.target.value) : "")}><option value="">Manter departamento atual</option>{departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
            <input value={transferReason} onChange={(e) => setTransferReason(e.target.value)} placeholder="Motivo da transferencia" />
            <textarea value={transferSummary} onChange={(e) => setTransferSummary(e.target.value)} rows={3} placeholder="Resumo obrigatorio" />
            <button className="primary" onClick={() => void transferContact()} disabled={!toUserId || !transferSummary.trim() || busyTransfer}>{busyTransfer ? "Transferindo..." : "Transferir"}</button>
          </CollapsibleCard>
        </> : <div className="empty">As acoes do contato aparecem aqui.</div>}

        {isManagerRole ? (
          <CollapsibleCard title={sessionUser?.role === "admin" ? "Usuarios e Roles" : "Operadores"} defaultOpen={false}>
            <div className="admin-user-list">{operators.map((op) => (
              <div key={op.id} className="admin-user-row">
                <div className="admin-user-info"><strong>{op.display_name}</strong><span className="sub">{op.email || ""}</span></div>
                {sessionUser?.role === "admin" && editingUserId === op.id ? (
                  <div className="admin-user-edit">
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value)}><option value="admin">admin</option><option value="supervisor">supervisor</option><option value="operador">operador</option></select>
                    <select value={editDeptId} onChange={(e) => setEditDeptId(e.target.value ? Number(e.target.value) : "")}><option value="">Sem setor</option>{departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button className="primary" style={{ flex: 1, padding: "0.5rem" }} onClick={() => void saveUserRole(op.id)} disabled={busyRoleUpdate}>{busyRoleUpdate ? "..." : "Salvar"}</button>
                      <button className="ghost" style={{ padding: "0.5rem 0.7rem" }} onClick={() => setEditingUserId(null)}>✕</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.25rem", flexWrap: "wrap", justifyContent: "flex-end" }}>
                    <span className="chip" style={{ fontSize: "0.68rem" }}>{op.role}</span>
                    {sessionUser?.role === "admin" && <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} onClick={() => startEditUser(op)}>Editar</button>}
                    <button className="ghost" style={{ padding: "0.2rem 0.4rem", fontSize: "0.72rem" }} disabled={busyResetCounter === op.id} onClick={() => void resetAssumeCounter(op.id, op.display_name)} title="Resetar contador">{busyResetCounter === op.id ? "..." : "Reset"}</button>
                  </div>
                )}
              </div>
            ))}</div>
          </CollapsibleCard>
        ) : null}

        {isManagerRole ? (
          <CollapsibleCard title="Reatribuicao em lote" defaultOpen={false}>
            <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Reatribuir todos os contatos de um operador:</span>
            <select value={bulkFromUser} onChange={(e) => setBulkFromUser(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Selecione operador de origem</option>
              {operators.map((op) => <option key={op.id} value={op.id}>{op.display_name}</option>)}
            </select>
            <select value={bulkAction} onChange={(e) => setBulkAction(e.target.value as "return_to_bot" | "transfer")}>
              <option value="return_to_bot">Devolver ao bot</option>
              <option value="transfer">Transferir para operador</option>
            </select>
            {bulkAction === "transfer" ? (
              <select value={bulkToUser} onChange={(e) => setBulkToUser(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Selecione operador destino</option>
                {operators.filter((op) => op.id !== bulkFromUser).map((op) => <option key={op.id} value={op.id}>{op.display_name}</option>)}
              </select>
            ) : null}
            <button className="primary" style={{ marginTop: "0.4rem" }} disabled={!bulkFromUser || (bulkAction === "transfer" && !bulkToUser) || busyBulk} onClick={() => { if (confirm("Reatribuir TODOS os contatos deste operador?")) void executeBulkReassign(); }}>{busyBulk ? "Processando..." : "Executar reatribuicao"}</button>
          </CollapsibleCard>
        ) : null}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// WhatsApp Embedded Signup (Coexistence)
// ---------------------------------------------------------------------------

declare global {
  interface Window {
    fbAsyncInit?: () => void;
    FB?: {
      init: (params: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }) => void;
      login: (callback: (response: { authResponse?: { code?: string } }) => void, params: { config_id: string; response_type: string; override_default_response_type: boolean; extras: Record<string, unknown> }) => void;
    };
  }
}

function WhatsAppSignupModal() {
  const { bundle, setShowSettings } = useCrm();
  const [step, setStep] = useState<"loading" | "ready" | "signing" | "exchanging" | "done" | "error">("loading");
  const [signupConfig, setSignupConfig] = useState<{ app_id: string; config_id: string; graph_api_version: string } | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const fbLoaded = useRef(false);

  useEffect(() => {
    if (!bundle) return;
    getJson<{ app_id: string; config_id: string; graph_api_version: string }>(bundle.auth, "/api/admin/embedded-signup/config")
      .then((cfg) => {
        setSignupConfig(cfg);
        loadFacebookSDK(cfg.app_id, cfg.graph_api_version);
      })
      .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
  }, [bundle]);

  function loadFacebookSDK(appId: string, version: string) {
    if (fbLoaded.current || window.FB) {
      setStep("ready");
      return;
    }
    window.fbAsyncInit = () => {
      window.FB!.init({ appId, autoLogAppEvents: true, xfbml: false, version });
      fbLoaded.current = true;
      setStep("ready");
    };
    const sdkVersion = encodeURIComponent(version);
    const script = document.createElement("script");
    script.src = `https://connect.facebook.net/pt_BR/sdk.js?v=${sdkVersion}`;
    script.async = true;
    script.defer = true;
    script.crossOrigin = "anonymous";
    document.body.appendChild(script);
  }

  const launchSignup = useCallback(() => {
    if (!window.FB || !signupConfig) return;
    setStep("signing");
    window.FB.login(
      (response) => {
        const code = response.authResponse?.code;
        if (!code) {
          setErrorMsg("Signup cancelado ou nenhum codigo retornado.");
          setStep("error");
          return;
        }
        setStep("exchanging");
        sendJson<Record<string, unknown>>(bundle?.auth ?? null, "/api/admin/embedded-signup/exchange", { code, channel_type: "coexistence" })
          .then((data) => { setResult(data); setStep("done"); })
          .catch((e) => { setErrorMsg(String(e.message || e)); setStep("error"); });
      },
      {
        config_id: signupConfig.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: "whatsapp_business_app_onboarding",
          sessionInfoVersion: "3",
        },
      },
    );
  }, [signupConfig, bundle]);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="WhatsApp Coexistence" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
        <h2 style={{ margin: "0 0 1.2rem" }}>WhatsApp Coexistence</h2>

        {step === "loading" && <p>Carregando configuracao...</p>}

        {step === "error" && (
          <div className="settings-section">
            <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, padding: "1rem", color: "#991b1b" }}>
              <strong>Erro:</strong> {errorMsg}
            </div>
            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => setStep("ready")}>Tentar novamente</button>
          </div>
        )}

        {step === "ready" && (
          <div className="settings-section">
            <p style={{ marginBottom: "1rem", lineHeight: 1.6 }}>
              Conecte um numero do WhatsApp Business App ao CRM via Coexistence.
              O administrador do portfolio <strong>cliente</strong> deve fazer login no popup do Facebook.
            </p>
            <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginBottom: "1rem", fontSize: "0.9rem" }}>
              <strong>Requisitos:</strong>
              <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
                <li>Numero ativo no WhatsApp Business App (Android/iOS)</li>
                <li>App versao 2.24.17 ou superior</li>
                <li>Portfolio do cliente verificado no Meta Business Manager</li>
                <li>Camera do celular pronta para escanear QR Code</li>
              </ul>
            </div>
            <button className="primary" style={{ fontSize: "1rem", padding: "0.75rem 1.5rem" }} onClick={launchSignup}>
              Iniciar Embedded Signup
            </button>
          </div>
        )}

        {step === "signing" && (
          <div className="settings-section" style={{ textAlign: "center" }}>
            <p>Aguardando conclusao do signup no popup do Facebook...</p>
            <p style={{ fontSize: "0.85rem", color: "#666" }}>Complete o fluxo no popup: login, selecao do WABA, e escaneamento do QR Code no celular.</p>
          </div>
        )}

        {step === "exchanging" && (
          <div className="settings-section" style={{ textAlign: "center" }}>
            <p>Trocando credenciais e configurando webhooks...</p>
          </div>
        )}

        {step === "done" && result && (
          <div className="settings-section">
            <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "1rem", marginBottom: "1rem" }}>
              <strong>Conexao realizada com sucesso!</strong>
            </div>
            <table style={{ width: "100%", fontSize: "0.9rem", borderCollapse: "collapse" }}>
              <tbody>
                {[
                  ["WABA ID", result.waba_id],
                  ["Phone Number ID", result.phone_number_id],
                  ["Numero", result.display_phone_number],
                  ["Nome Verificado", result.verified_name],
                  ["Status", result.phone_status],
                  ["Plataforma", result.platform_type],
                  ["Qualidade", result.quality_rating],
                  ["Webhook", result.webhook_subscribed ? "Inscrito" : "Falhou"],
                ].map(([label, value]) => (
                  <tr key={String(label)}>
                    <td style={{ padding: "0.4rem 0.8rem 0.4rem 0", fontWeight: 600, whiteSpace: "nowrap" }}>{String(label)}</td>
                    <td style={{ padding: "0.4rem 0", fontFamily: "monospace" }}>{String(value ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, padding: "1rem", marginTop: "1rem", fontSize: "0.85rem" }}>
              <strong>Proximo passo:</strong> Atualize o <code>.env</code> do servidor com os novos valores:
              <pre style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>
{`WHATSAPP_TOKEN=${result.access_token || "???"}
WHATSAPP_PHONE_NUMBER_ID=${result.phone_number_id || "???"}
WHATSAPP_WABA_ID=${result.waba_id || "???"}`}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsModals() {
  const { showSettings, setShowSettings, sessionUser, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, saveUserSettingsAction, saveSystemSettingsAction } = useCrm();
  if (!sessionUser) return null;
  return (
    <>
      {showSettings === "chat" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Configuracoes do Chat" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Chat</h2>
            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              {systemSettings.chat_prefix_roles.includes(sessionUser.role) ? (
                <div className="settings-block">
                  <label className="settings-toggle"><input type="checkbox" checked={userSettings.chat_prefix_enabled} onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} /><span>Usar prefixo (ex: <strong>Rafael:</strong> Bom dia...)</span></label>
                  {userSettings.chat_prefix_enabled && <input value={userSettings.chat_prefix_name} onChange={(e) => setUserSettings((prev) => ({ ...prev, chat_prefix_name: e.target.value }))} placeholder="Nome que aparecera como prefixo" style={{ marginTop: "0.5rem" }} />}
                </div>
              ) : <div className="empty" style={{ fontSize: "0.88rem" }}>Prefixo de mensagem nao habilitado para seu cargo.</div>}
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {showSettings === "quick" ? (
        <div className="lightbox" role="dialog" aria-modal="true" aria-label="Mensagens rapidas" onClick={() => setShowSettings(false)}>
          <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
          <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: "0 0 1.2rem" }}>Mensagens rapidas</h2>
            <div className="settings-section">
              <h3>Minhas mensagens rapidas</h3>
              <div className="settings-block">
                {userSettings.quick_messages.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input value={qm.shortcut} onChange={(e) => { const u = [...userSettings.quick_messages]; u[idx] = { ...u[idx], shortcut: e.target.value }; setUserSettings((prev) => ({ ...prev, quick_messages: u })); }} placeholder="/atalho" style={{ width: 100 }} />
                    <input value={qm.message} onChange={(e) => { const u = [...userSettings.quick_messages]; u[idx] = { ...u[idx], message: e.target.value }; setUserSettings((prev) => ({ ...prev, quick_messages: u })); }} placeholder="Mensagem completa" style={{ flex: 1 }} />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => setUserSettings((prev) => ({ ...prev, quick_messages: prev.quick_messages.filter((_, i) => i !== idx) }))}>X</button>
                  </div>
                ))}
                {userSettings.quick_messages.length < systemSettings.quick_message_max ? (
                  <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => setUserSettings((prev) => ({ ...prev, quick_messages: [...prev.quick_messages, { shortcut: "", message: "" }] }))}>+ Adicionar mensagem rapida</button>
                ) : <div className="sub" style={{ fontSize: "0.82rem" }}>Limite de {systemSettings.quick_message_max} mensagens rapidas atingido.</div>}
              </div>
              <button className="primary" style={{ marginTop: "0.8rem" }} onClick={() => void saveUserSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {showSettings === "whatsapp" ? <WhatsAppSignupModal /> : null}

      {showSettings === "admin" && sessionUser.role === "admin" ? <AdminSettingsModal /> : null}

      {showSettings === "dashboard" && (sessionUser.role === "admin" || sessionUser.role === "supervisor") ? <DashboardModal /> : null}
    </>
  );
}

// ---------------------------------------------------------------------------
// Dashboard Modal (audit metrics, export)
// ---------------------------------------------------------------------------

function DashboardModal() {
  const { bundle, setShowSettings, operators, setError } = useCrm();
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [ratings, setRatings] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);

  const loadDashboard = useCallback(async () => {
    if (!bundle) return;
    setLoading(true);
    try {
      const [sumRes, ratRes] = await Promise.all([
        getJson<Record<string, unknown>>(bundle.auth, `/api/admin/dashboard/summary?date_from=${dateFrom}&date_to=${dateTo}`),
        getJson<{ ratings: Record<string, unknown>[] }>(bundle.auth, `/api/admin/dashboard/ratings?date_from=${dateFrom}&date_to=${dateTo}`),
      ]);
      setSummary(sumRes);
      setRatings(ratRes.ratings || []);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setLoading(false);
  }, [bundle, dateFrom, dateTo, setError]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  const operatorName = (uid: unknown) => {
    const id = typeof uid === "number" ? uid : Number(uid);
    return operators.find((o) => o.id === id)?.display_name || `#${uid}`;
  };

  const exportCsv = useCallback(async () => {
    if (!bundle) return;
    try {
      const token = await bundle.auth.currentUser?.getIdToken();
      const resp = await fetch(`/api/admin/export?date_from=${dateFrom}&date_to=${dateTo}&format=csv`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `export_${dateFrom}_${dateTo}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }, [bundle, dateFrom, dateTo, setError]);

  const peakData = summary?.peak_chart as Record<string, number> | undefined;
  const peakSlots = peakData ? Object.entries(peakData).sort(([a], [b]) => a.localeCompare(b)) : [];
  const peakMax = peakSlots.length ? Math.max(...peakSlots.map(([, v]) => v)) : 1;
  const opsData = (summary?.operators || []) as { user_id: unknown; inbound: number; outbound: number; leads_assumed: number; first_activity: string | null; last_activity: string | null }[];

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Dashboard" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 750, maxHeight: "90vh", overflow: "auto" }}>
        <h2 style={{ margin: "0 0 0.8rem" }}>Dashboard de Auditoria</h2>

        {/* Date range */}
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap" }}>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <span>ate</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          <button className="primary" style={{ padding: "0.4rem 0.8rem" }} onClick={() => void loadDashboard()} disabled={loading}>{loading ? "..." : "Atualizar"}</button>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => void exportCsv()}>Exportar CSV</button>
        </div>

        {summary ? (
          <>
            {/* Summary cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.6rem", marginBottom: "1.2rem" }}>
              {([
                ["Leads recebidos", summary.total_leads_received],
                ["Leads assumidos", summary.total_leads_assumed],
                ["Msgs recebidas", summary.total_messages_inbound],
                ["Msgs enviadas", summary.total_messages_outbound],
                ["Total mensagens", summary.total_messages],
              ] as [string, unknown][]).map(([label, value]) => (
                <div key={label} style={{ background: "var(--card-bg, var(--bg-alt))", borderRadius: 8, padding: "0.8rem", textAlign: "center" }}>
                  <div style={{ fontSize: "1.6rem", fontWeight: 700 }}>{String(value ?? 0)}</div>
                  <div className="sub" style={{ fontSize: "0.75rem" }}>{label}</div>
                </div>
              ))}
            </div>

            {/* Peak chart (bar chart with CSS) */}
            {peakSlots.length > 0 && (
              <div className="settings-section" style={{ marginBottom: "1.2rem" }}>
                <h3>Pico de mensagens (por meia hora)</h3>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 100, overflow: "auto" }}>
                  {peakSlots.map(([slot, count]) => (
                    <div key={slot} style={{ flex: "0 0 auto", display: "flex", flexDirection: "column", alignItems: "center", minWidth: 28 }}>
                      <div style={{ width: 20, height: Math.max(2, (count / peakMax) * 80), background: "var(--accent)", borderRadius: "3px 3px 0 0" }} title={`${slot}: ${count}`} />
                      <span style={{ fontSize: "0.55rem", marginTop: 2, transform: "rotate(-45deg)", whiteSpace: "nowrap" }}>{slot}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Per-operator table */}
            {opsData.length > 0 && (
              <div className="settings-section" style={{ marginBottom: "1.2rem" }}>
                <h3>Por operador</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                    <thead><tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Operador</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Recebidas</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Enviadas</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Assumidos</th>
                    </tr></thead>
                    <tbody>
                      {opsData.map((op) => (
                        <tr key={String(op.user_id)} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "0.4rem" }}>{operatorName(op.user_id)}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.inbound}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.outbound}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>{op.leads_assumed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Ratings table */}
            {ratings.length > 0 && (
              <div className="settings-section">
                <h3>Avaliacoes de atendimento</h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                    <thead><tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Contato</th>
                      <th style={{ textAlign: "right", padding: "0.4rem" }}>Nota</th>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Operador</th>
                      <th style={{ textAlign: "left", padding: "0.4rem" }}>Data</th>
                    </tr></thead>
                    <tbody>
                      {ratings.map((r, i) => (
                        <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "0.4rem" }}>{String(r.display_name || r.wa_id || "")}</td>
                          <td style={{ textAlign: "right", padding: "0.4rem" }}>
                            <span className="chip" style={{ fontSize: "0.75rem", background: Number(r.rating) >= 7 ? "var(--success)" : Number(r.rating) >= 4 ? "#e6a817" : "var(--danger)", color: "#fff" }}>{String(r.rating)}/10</span>
                          </td>
                          <td style={{ padding: "0.4rem" }}>{r.converted_by_user_id ? operatorName(r.converted_by_user_id) : "-"}</td>
                          <td style={{ padding: "0.4rem" }}>{String(r.rating_received_at || "").slice(0, 10)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : loading ? (
          <p className="sub">Carregando...</p>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin Settings Modal (departments, channels, system config)
// ---------------------------------------------------------------------------

function AdminSettingsModal() {
  const {
    bundle, setShowSettings, departments, channels, operators,
    systemSettings, setSystemSettings, busySettings, saveSystemSettingsAction,
    setError, setNotice,
  } = useCrm();
  const [adminTab, setAdminTab] = useState<"system" | "departments" | "channels" | "notifications">("system");

  // -- Department state --
  const [depts, setDepts] = useState<Department[]>(departments);
  const [newDeptName, setNewDeptName] = useState("");
  const [newDeptDesc, setNewDeptDesc] = useState("");
  const [newDeptBotKey, setNewDeptBotKey] = useState<string>("");
  const [editingDeptId, setEditingDeptId] = useState<number | null>(null);
  const [editDeptName, setEditDeptName] = useState("");
  const [editDeptDesc, setEditDeptDesc] = useState("");
  const [editDeptBotKey, setEditDeptBotKey] = useState<string>("");
  const [busyDept, setBusyDept] = useState(false);

  // -- Channel state --
  const [chans, setChans] = useState<Channel[]>(channels);

  useEffect(() => { setDepts(departments); }, [departments]);
  useEffect(() => { setChans(channels); }, [channels]);

  const reloadDepts = useCallback(async () => {
    if (!bundle) return;
    const res = await getJson<{ departments: Department[] }>(bundle.auth, "/api/departments");
    setDepts(res.departments);
  }, [bundle]);

  const reloadChans = useCallback(async () => {
    if (!bundle) return;
    const res = await getJson<{ channels: Channel[] }>(bundle.auth, "/api/admin/channels").catch(() => ({ channels: [] as Channel[] }));
    setChans(res.channels);
  }, [bundle]);

  const createDept = useCallback(async () => {
    if (!bundle || !newDeptName.trim()) return;
    setBusyDept(true);
    try {
      await sendJson(bundle.auth, "/api/admin/departments", {
        name: newDeptName.trim(),
        description: newDeptDesc.trim(),
        bot_key: newDeptBotKey || null,
      });
      setNewDeptName(""); setNewDeptDesc(""); setNewDeptBotKey("");
      await reloadDepts();
      setNotice("Departamento criado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, newDeptName, newDeptDesc, newDeptBotKey, reloadDepts, setError, setNotice]);

  const saveDeptEdit = useCallback(async (deptId: number) => {
    if (!bundle || !editDeptName.trim()) return;
    setBusyDept(true);
    try {
      await putJson(bundle.auth, `/api/admin/departments/${deptId}`, {
        name: editDeptName.trim(),
        description: editDeptDesc.trim(),
        bot_key: editDeptBotKey || null,
      });
      setEditingDeptId(null);
      await reloadDepts();
      setNotice("Departamento atualizado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, editDeptName, editDeptDesc, editDeptBotKey, reloadDepts, setError, setNotice]);

  const deleteDept = useCallback(async (deptId: number) => {
    if (!bundle) return;
    setBusyDept(true);
    try {
      await deleteJson(bundle.auth, `/api/admin/departments/${deptId}`);
      await reloadDepts();
      setNotice("Departamento removido");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setBusyDept(false);
  }, [bundle, reloadDepts, setError, setNotice]);

  const deactivateChannel = useCallback(async (channelId: number) => {
    if (!bundle) return;
    try {
      await deleteJson(bundle.auth, `/api/admin/channels/${channelId}`);
      await reloadChans();
      setNotice("Canal desativado");
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  }, [bundle, reloadChans, setError, setNotice]);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Administracao" onClick={() => setShowSettings(false)}>
      <button type="button" className="lightbox-close" onClick={() => setShowSettings(false)} aria-label="Fechar">Fechar</button>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <h2 style={{ margin: "0 0 1rem" }}>Administracao</h2>

        {/* Tabs */}
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.2rem", borderBottom: "1px solid var(--border)", paddingBottom: "0.5rem" }}>
          <button className={adminTab === "system" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("system")}>Sistema</button>
          <button className={adminTab === "departments" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("departments")}>Departamentos</button>
          <button className={adminTab === "channels" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("channels")}>Canais WhatsApp</button>
          <button className={adminTab === "notifications" ? "primary" : "ghost"} style={{ padding: "0.4rem 0.8rem", fontSize: "0.85rem" }} onClick={() => setAdminTab("notifications")}>Notificacoes</button>
        </div>

        {/* Tab: Sistema */}
        {adminTab === "system" && (
          <>
            <div className="settings-section">
              <h3>Prefixo de mensagem</h3>
              <div className="settings-block"><label className="settings-toggle"><input type="checkbox" checked={systemSettings.chat_prefix_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, chat_prefix_enabled: e.target.checked }))} /><span>Habilitar prefixo de mensagem (padrao do sistema)</span></label></div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Cargos que podem usar prefixo:</span>
                {["admin", "supervisor", "operador"].map((role) => (
                  <label key={role} className="settings-toggle" style={{ marginBottom: "0.25rem" }}><input type="checkbox" checked={systemSettings.chat_prefix_roles.includes(role)} onChange={(e) => setSystemSettings((prev) => ({ ...prev, chat_prefix_roles: e.target.checked ? [...prev.chat_prefix_roles, role] : prev.chat_prefix_roles.filter((r) => r !== role) }))} /><span>{role}</span></label>
                ))}
              </div>
            </div>
            <div className="settings-section" style={{ marginTop: "1.2rem" }}>
              <h3>Mensagens rapidas</h3>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Limite por usuario:</span>
                <input type="number" min={1} max={100} value={systemSettings.quick_message_max} onChange={(e) => setSystemSettings((prev) => ({ ...prev, quick_message_max: Math.max(1, Number(e.target.value) || 1) }))} style={{ width: 100 }} />
              </div>
              <div className="settings-block">
                <span className="sub" style={{ display: "block", marginBottom: "0.4rem" }}>Mensagens globais (padrao para todos):</span>
                {systemSettings.quick_messages_global.map((qm, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "0.4rem", marginBottom: "0.4rem", alignItems: "center" }}>
                    <input value={qm.shortcut} onChange={(e) => { const u = [...systemSettings.quick_messages_global]; u[idx] = { ...u[idx], shortcut: e.target.value }; setSystemSettings((prev) => ({ ...prev, quick_messages_global: u })); }} placeholder="/atalho" style={{ width: 100 }} />
                    <input value={qm.message} onChange={(e) => { const u = [...systemSettings.quick_messages_global]; u[idx] = { ...u[idx], message: e.target.value }; setSystemSettings((prev) => ({ ...prev, quick_messages_global: u })); }} placeholder="Mensagem completa" style={{ flex: 1 }} />
                    <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => setSystemSettings((prev) => ({ ...prev, quick_messages_global: prev.quick_messages_global.filter((_, i) => i !== idx) }))}>X</button>
                  </div>
                ))}
                <button className="ghost" style={{ fontSize: "0.85rem", padding: "0.5rem 0.8rem" }} onClick={() => setSystemSettings((prev) => ({ ...prev, quick_messages_global: [...prev.quick_messages_global, { shortcut: "", message: "" }] }))}>+ Adicionar mensagem global</button>
              </div>
            </div>
            <div className="settings-section" style={{ marginTop: "1.2rem" }}>
              <h3>Bot de atendimento</h3>
              <div className="settings-block">
                <label className="settings-toggle">
                  <input type="checkbox" checked={systemSettings.bot_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, bot_enabled: e.target.checked }))} />
                  <span>Habilitar bot (coleta nome, equipamento e setor antes de encaminhar)</span>
                </label>
                <p className="sub" style={{ marginTop: "0.3rem", fontSize: "0.8rem" }}>Quando desabilitado, mensagens novas caem direto para "Novos".</p>
              </div>
            </div>
            <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar configuracoes do sistema"}</button>
          </>
        )}

        {/* Tab: Departamentos */}
        {adminTab === "departments" && (
          <div className="settings-section">
            <h3>Departamentos</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {depts.map((dept) => (
                <div key={dept.id} className="admin-user-row" style={{ padding: "0.5rem 0.6rem" }}>
                  {editingDeptId === dept.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", flex: 1 }}>
                      <input value={editDeptName} onChange={(e) => setEditDeptName(e.target.value)} placeholder="Nome" />
                      <input value={editDeptDesc} onChange={(e) => setEditDeptDesc(e.target.value)} placeholder="Descricao (opcional)" />
                      <label className="sub" style={{ fontSize: "0.75rem" }}>Setor do bot (roteamento automatico):</label>
                      <select value={editDeptBotKey} onChange={(e) => setEditDeptBotKey(e.target.value)}>
                        <option value="">Nenhum (nao recebe do bot)</option>
                        <option value="comercial">Comercial</option>
                        <option value="financeiro">Financeiro</option>
                        <option value="administrativo">Administrativo</option>
                        <option value="sac">SAC</option>
                      </select>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button className="primary" style={{ flex: 1, padding: "0.4rem" }} disabled={busyDept} onClick={() => void saveDeptEdit(dept.id)}>{busyDept ? "..." : "Salvar"}</button>
                        <button className="ghost" style={{ padding: "0.4rem 0.6rem" }} onClick={() => setEditingDeptId(null)}>Cancelar</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="admin-user-info">
                        <strong>{dept.name}</strong>
                        {dept.bot_key ? <span className="chip" style={{ fontSize: "0.65rem", marginLeft: "0.3rem" }}>bot: {dept.bot_key}</span> : null}
                        {dept.description ? <span className="sub">{dept.description}</span> : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.3rem" }}>
                        <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem" }} onClick={() => { setEditingDeptId(dept.id); setEditDeptName(dept.name); setEditDeptDesc(dept.description || ""); setEditDeptBotKey(dept.bot_key || ""); }}>Editar</button>
                        <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => { if (confirm(`Remover departamento "${dept.name}"?`)) void deleteDept(dept.id); }}>Remover</button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
            <div style={{ marginTop: "1rem", display: "flex", flexDirection: "column", gap: "0.4rem", borderTop: "1px solid var(--border)", paddingTop: "0.8rem" }}>
              <span className="sub">Novo departamento:</span>
              <input value={newDeptName} onChange={(e) => setNewDeptName(e.target.value)} placeholder="Nome do departamento" />
              <input value={newDeptDesc} onChange={(e) => setNewDeptDesc(e.target.value)} placeholder="Descricao (opcional)" />
              <select value={newDeptBotKey} onChange={(e) => setNewDeptBotKey(e.target.value)}>
                <option value="">Setor do bot: Nenhum</option>
                <option value="comercial">Setor do bot: Comercial</option>
                <option value="financeiro">Setor do bot: Financeiro</option>
                <option value="administrativo">Setor do bot: Administrativo</option>
                <option value="sac">Setor do bot: SAC</option>
              </select>
              <button className="primary" style={{ padding: "0.5rem" }} disabled={!newDeptName.trim() || busyDept} onClick={() => void createDept()}>{busyDept ? "Criando..." : "Criar departamento"}</button>
            </div>
          </div>
        )}

        {/* Tab: Canais WhatsApp */}
        {adminTab === "channels" && (
          <div className="settings-section">
            <h3>Canais WhatsApp conectados</h3>
            {chans.length === 0 ? (
              <p className="sub">Nenhum canal configurado. Use o Embedded Signup para conectar um numero.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {chans.map((ch) => {
                  const owner = ch.owner_user_id ? operators.find((o) => o.id === ch.owner_user_id) : null;
                  return (
                    <div key={ch.id} className="admin-user-row" style={{ padding: "0.6rem" }}>
                      <div className="admin-user-info">
                        <strong>{ch.label}</strong>
                        <span className="sub">
                          {ch.display_phone_number || ch.phone_number_id}
                          {" | "}
                          <span className="chip" style={{ fontSize: "0.7rem" }}>{ch.channel_type === "standard" ? "Cloud API" : "Coexistence"}</span>
                          {ch.is_bot_enabled ? <span className="chip" style={{ fontSize: "0.7rem", marginLeft: "0.3rem" }}>Bot</span> : null}
                        </span>
                        {owner ? <span className="sub">Operador: {owner.display_name}</span> : null}
                      </div>
                      <div style={{ display: "flex", gap: "0.3rem", alignItems: "center" }}>
                        <span className="chip" style={{ fontSize: "0.7rem", background: ch.is_active ? "var(--success)" : "var(--danger)", color: "#fff" }}>
                          {ch.is_active ? "Ativo" : "Inativo"}
                        </span>
                        {ch.channel_type !== "standard" && (
                          <button className="ghost" style={{ padding: "0.3rem 0.5rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => { if (confirm(`Desativar canal "${ch.label}"?`)) void deactivateChannel(ch.id); }}>Desativar</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "0.8rem" }}>
              <p className="sub">Para adicionar um canal coexistence, use a opcao <strong>WhatsApp Coexistence</strong> no menu de configuracoes.</p>
            </div>
          </div>
        )}

        {/* Tab: Notificacoes */}
        {adminTab === "notifications" && (
          <NotificationsTab />
        )}
      </div>
    </div>
  );
}

function NotificationsTab() {
  const { bundle, departments, systemSettings, setSystemSettings, busySettings, saveSystemSettingsAction, setError, setNotice } = useCrm();
  const [uploadingNotif, setUploadingNotif] = useState(false);
  const [uploadingAlarm, setUploadingAlarm] = useState(false);
  const notifFileRef = useRef<HTMLInputElement | null>(null);
  const alarmFileRef = useRef<HTMLInputElement | null>(null);

  const uploadSound = useCallback(async (file: File, kind: "alarm" | "notification") => {
    if (!bundle) return;
    const setter = kind === "alarm" ? setUploadingAlarm : setUploadingNotif;
    setter(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      const res = await sendForm<{ path: string }>(bundle.auth, "/api/admin/upload-alarm-sound", form);
      setSystemSettings((prev) => ({
        ...prev,
        [kind === "alarm" ? "alarm_sound_path" : "notification_sound_path"]: res.path,
      }));
      setNotice(`Som de ${kind === "alarm" ? "alarme" : "notificacao"} atualizado`);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    setter(false);
  }, [bundle, setError, setNotice, setSystemSettings]);

  const testSound = useCallback((path: string, fallbackFreq: number) => {
    if (path) {
      const audio = new Audio(path);
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } else {
      try {
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = fallbackFreq;
        osc.type = fallbackFreq > 800 ? "sine" : "square";
        gain.gain.value = 0.3;
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.stop(ctx.currentTime + 0.4);
        setTimeout(() => ctx.close(), 600);
      } catch { /* audio not available */ }
    }
  }, []);

  return (
    <>
      <div className="settings-section">
        <h3>Notificacao de nova mensagem</h3>
        <p className="sub" style={{ marginBottom: "0.6rem" }}>Todos os usuarios ouvem um beep quando chega uma nova mensagem.</p>
        <div className="settings-block">
          <label className="settings-toggle">
            <input type="checkbox" checked={systemSettings.notification_sound_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, notification_sound_enabled: e.target.checked }))} />
            <span>Habilitar som de notificacao</span>
          </label>
        </div>
        <div className="settings-block" style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.4rem" }}>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => notifFileRef.current?.click()} disabled={uploadingNotif}>
            {uploadingNotif ? "Enviando..." : systemSettings.notification_sound_path ? "Trocar som" : "Upload som personalizado"}
          </button>
          {systemSettings.notification_sound_path && <span className="sub" style={{ fontSize: "0.75rem" }}>Personalizado ativo</span>}
          <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => testSound(systemSettings.notification_sound_path, 880)} title="Testar som">Testar</button>
          {systemSettings.notification_sound_path && (
            <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => setSystemSettings((prev) => ({ ...prev, notification_sound_path: "" }))}>Usar padrao</button>
          )}
          <input ref={notifFileRef} type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/webm,.mp3,.wav,.ogg" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadSound(f, "notification"); }} />
        </div>
      </div>

      <div className="settings-section" style={{ marginTop: "1.2rem" }}>
        <h3>Alarme de mensagens sem resposta</h3>
        <p className="sub" style={{ marginBottom: "0.6rem" }}>Alarme sonoro repetitivo para operadores dos departamentos selecionados quando ha mensagens sem visualizar.</p>
        <div className="settings-block">
          <label className="settings-toggle">
            <input type="checkbox" checked={systemSettings.alarm_enabled} onChange={(e) => setSystemSettings((prev) => ({ ...prev, alarm_enabled: e.target.checked }))} />
            <span>Habilitar alarme</span>
          </label>
        </div>
        <div className="settings-block" style={{ marginTop: "0.6rem" }}>
          <span className="sub" style={{ display: "block", marginBottom: "0.3rem" }}>Tempo sem resposta (minutos):</span>
          <input type="number" min={1} max={60} value={systemSettings.alarm_threshold_minutes} onChange={(e) => setSystemSettings((prev) => ({ ...prev, alarm_threshold_minutes: Math.max(1, Number(e.target.value) || 5) }))} style={{ width: 100 }} />
        </div>
        <div className="settings-block" style={{ marginTop: "0.6rem" }}>
          <span className="sub" style={{ display: "block", marginBottom: "0.3rem" }}>Departamentos que recebem alarme:</span>
          {departments.map((dept) => (
            <label key={dept.id} className="settings-toggle" style={{ marginBottom: "0.25rem" }}>
              <input type="checkbox" checked={(systemSettings.alarm_department_ids || []).includes(dept.id)} onChange={(e) => setSystemSettings((prev) => ({
                ...prev,
                alarm_department_ids: e.target.checked
                  ? [...(prev.alarm_department_ids || []), dept.id]
                  : (prev.alarm_department_ids || []).filter((id) => id !== dept.id),
              }))} />
              <span>{dept.name}</span>
            </label>
          ))}
          {departments.length === 0 && <span className="sub">Nenhum departamento cadastrado.</span>}
        </div>
        <div className="settings-block" style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.6rem" }}>
          <button className="ghost" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }} onClick={() => alarmFileRef.current?.click()} disabled={uploadingAlarm}>
            {uploadingAlarm ? "Enviando..." : systemSettings.alarm_sound_path ? "Trocar alarme" : "Upload alarme personalizado"}
          </button>
          {systemSettings.alarm_sound_path && <span className="sub" style={{ fontSize: "0.75rem" }}>Personalizado ativo</span>}
          <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }} onClick={() => testSound(systemSettings.alarm_sound_path, 660)} title="Testar alarme">Testar</button>
          {systemSettings.alarm_sound_path && (
            <button className="ghost" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", color: "var(--danger)" }} onClick={() => setSystemSettings((prev) => ({ ...prev, alarm_sound_path: "" }))}>Usar padrao</button>
          )}
          <input ref={alarmFileRef} type="file" accept="audio/mpeg,audio/wav,audio/ogg,audio/webm,.mp3,.wav,.ogg" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void uploadSound(f, "alarm"); }} />
        </div>
      </div>

      <button className="primary" style={{ marginTop: "1rem" }} onClick={() => void saveSystemSettingsAction()} disabled={busySettings}>{busySettings ? "Salvando..." : "Salvar configuracoes de notificacao"}</button>
    </>
  );
}

function Lightbox() {
  const { lightboxMedia, closeLightbox } = useCrm();
  if (!lightboxMedia) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Visualizacao de midia" onClick={closeLightbox}>
      <button type="button" className="lightbox-close" onClick={closeLightbox} aria-label="Fechar visualizacao">Fechar</button>
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        {lightboxMedia.kind === "image" ? <img className="lightbox-media" src={lightboxMedia.src} alt={lightboxMedia.alt} /> : <video className="lightbox-media" src={lightboxMedia.src} controls={!lightboxMedia.gifLike} autoPlay loop={lightboxMedia.gifLike} muted={lightboxMedia.gifLike} playsInline />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main CRM layout
// ---------------------------------------------------------------------------

// Fase 2.10: banner persistente que avisa admin/supervisor quando o canal
// principal nao tem metodo de pagamento configurado na Meta. Sem isso,
// envio de templates de marketing/utility falha. Apenas roles
// admin/supervisor veem o banner.
function BillingHealthBanner() {
  const { sessionUser, channels, fetchBillingStatus } = useCrm();
  const [status, setStatus] = useState<{ ok: boolean; has_payment_method: boolean; error?: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const isPrivileged = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";
  const standardChannel = channels.find((c) => c.is_active && c.channel_type === "standard");

  useEffect(() => {
    if (!isPrivileged || !standardChannel) return;
    let cancelled = false;
    void fetchBillingStatus(standardChannel.id).then((res) => {
      if (!cancelled) setStatus(res);
    });
    return () => { cancelled = true; };
  }, [isPrivileged, standardChannel, fetchBillingStatus]);

  if (!isPrivileged || !standardChannel || !status || dismissed) return null;
  if (status.ok && status.has_payment_method) return null;

  const isError = !status.ok;
  const message = isError
    ? `Nao foi possivel verificar o billing da Meta para o canal ${standardChannel.label}. ${status.error || ""}`
    : `O canal ${standardChannel.label} ainda nao tem metodo de pagamento configurado na Meta. Templates de marketing/utility nao serao entregues ate isso ser corrigido.`;

  return (
    <div style={{
      background: isError ? "#fef3c7" : "#fee2e2",
      borderBottom: `1px solid ${isError ? "#f59e0b" : "#dc2626"}`,
      color: isError ? "#92400e" : "#991b1b",
      padding: "0.6rem 1rem",
      display: "flex",
      gap: "0.8rem",
      alignItems: "center",
      justifyContent: "space-between",
      fontSize: "0.85rem",
    }}>
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <span style={{ fontSize: "1.1rem" }}>⚠</span>
        <span>{message}</span>
      </div>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <a
          href="https://business.facebook.com/wa/manage/billing/"
          target="_blank"
          rel="noreferrer"
          style={{ color: "inherit", textDecoration: "underline", fontWeight: 600 }}
        >
          Configurar agora
        </a>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          style={{ background: "transparent", border: "none", cursor: "pointer", color: "inherit", fontSize: "1rem", padding: "0 0.3rem" }}
          aria-label="Dispensar aviso"
          title="Dispensar"
        >
          ×
        </button>
      </div>
    </div>
  );
}


function CrmApp() {
  const { booting, config, firebaseUser, sessionUser, error } = useCrm();

  if (booting) return <BootScreen />;
  if (config?.auth_mode !== "firebase") return <div className="screen"><div className="hero-card"><p className="eyebrow">Configuracao invalida</p><h1>Este frontend exige Firebase Auth</h1><p>{error || "O backend deve operar em modo Firebase."}</p></div></div>;
  if (!firebaseUser || !sessionUser) return <LoginScreen />;

  return (
    <>
      <div className="crm-layout">
        <TopBar />
        <BillingHealthBanner />
        <div className="crm-grid">
          <NavBar />
          <ContactList />
          <ChatPanel />
          <DetailPanel />
        </div>
      </div>
      <SettingsModals />
      <Lightbox />
    </>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export default function App() {
  return (
    <CrmProvider>
      <CrmApp />
    </CrmProvider>
  );
}
```

## frontend/src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

## frontend/src/context/CrmContext.tsx

```tsx
import { ChangeEvent, createContext, FormEvent, KeyboardEvent, startTransition, useCallback, useContext, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { onIdTokenChanged, signInWithEmailAndPassword, signInWithPopup, signOut, type User } from "firebase/auth";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query, where } from "firebase/firestore";

import { getJson, putJson, sendForm, sendJson } from "../api";
import { initializeFirebaseBundle, type FirebaseBundle } from "../firebase";
import type {
  ActiveView, Channel, ChatMessage, ClientConfig, Contact, Conversation, Department,
  MessageReplyReference, Operator, SessionUser, SettingsPage, SystemSettings,
  TemplateSendComponent, TransportMode, UserSettings, WhatsAppTemplate,
} from "../types";
import { errorText } from "../utils/errors";
import { firebaseReady } from "../utils/firebase-helpers";
import { buildMessageReplyReference, formatRecordingTime, messageCopyText, messageMoment } from "../utils/formatting";
import { normalizeContact, normalizeConversation, normalizeMessage } from "../utils/normalization";
import { applyTheme, themePref, transportPref } from "../utils/storage";
import type { LightboxMedia } from "../utils/media";

// ---------------------------------------------------------------------------
// Context value shape
// ---------------------------------------------------------------------------

type CrmContextValue = {
  // Core
  config: ClientConfig | null;
  bundle: FirebaseBundle | null;
  firebaseUser: User | null;
  sessionUser: SessionUser | null;
  operators: Operator[];
  departments: Department[];
  channels: Channel[];
  booting: boolean;
  busyLogin: boolean;
  snapshotMode: boolean;
  isManagerRole: boolean;

  // Theme
  theme: "dark" | "light";
  toggleTheme: () => void;

  // Auth
  loginWithGoogle: () => Promise<void>;
  loginWithEmail: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;

  // Contacts
  contacts: Contact[];
  contactsById: Map<number, Contact>;
  conversations: Conversation[];
  // selectedContactId é derivado de selectedThreadId -> conversation.contact_id.
  // Para selecionar uma conversa, chame setSelectedThreadId(conversationId).
  selectedContactId: number | null;
  selectedThreadId: string | null;
  setSelectedThreadId: (id: string | null) => void;
  selectedContact: Contact | null;
  selectedConversation: Conversation | null;

  // Views
  activeView: ActiveView;
  setActiveView: (v: ActiveView) => void;
  novosConversations: Conversation[];
  meusConversations: Conversation[];
  nqConversations: Conversation[];
  equipeConversations: Conversation[];
  botConversations: Conversation[];
  novosUnread: number;
  meusUnread: number;
  nqUnread: number;
  equipeUnread: number;
  botUnread: number;
  equipeOperatorFilter: string;
  setEquipeOperatorFilter: (v: string) => void;
  equipeFiltered: Conversation[];

  // Messages
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  visibleMessages: ChatMessage[];
  messageLimit: number;
  setMessageLimit: React.Dispatch<React.SetStateAction<number>>;
  loadingMore: boolean;
  setLoadingMore: (v: boolean) => void;
  messagesRef: React.MutableRefObject<HTMLDivElement | null>;
  scrollIntentRef: React.MutableRefObject<"load_older" | "normal">;
  prevMessageCountRef: React.MutableRefObject<number>;

  // Transcription
  transcribingMessageId: number | null;
  transcribeMessage: (messageId: number) => Promise<void>;

  // Composer
  replyTarget: MessageReplyReference | null;
  startReplyToMessage: (message: ChatMessage) => void;
  cancelReply: () => void;
  copyMessageText: (message: ChatMessage) => Promise<void>;
  draft: string;
  setDraft: (v: string) => void;
  busySend: boolean;
  busyUpload: boolean;
  busyAudio: boolean;
  quickSuggestions: { shortcut: string; message: string }[];
  setQuickSuggestions: React.Dispatch<React.SetStateAction<{ shortcut: string; message: string }[]>>;
  sendTextMessage: () => Promise<void>;
  submitText: (e: FormEvent<HTMLFormElement>) => void;
  submitMedia: (file: File) => Promise<void>;
  submitFile: (file: File, label: string) => Promise<void>;
  sendLocation: () => Promise<void>;
  handleDraftKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  handleDraftChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  applyQuickMessage: (qm: { shortcut: string; message: string }) => void;
  handlePrimaryAction: () => void;
  handleImageSelected: (e: ChangeEvent<HTMLInputElement>) => void;
  composerInputRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  imageInputRef: React.MutableRefObject<HTMLInputElement | null>;
  videoInputRef: React.MutableRefObject<HTMLInputElement | null>;
  documentInputRef: React.MutableRefObject<HTMLInputElement | null>;

  // Attach menu
  showAttachMenu: boolean;
  setShowAttachMenu: (v: boolean) => void;
  toggleAttachMenu: () => void;
  openImagePicker: () => void;
  openVideoPicker: () => void;
  openDocPicker: () => void;
  attachMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Recording
  recording: boolean;
  recordingSeconds: number;
  startRecording: () => Promise<void>;
  sendRecordedAudio: () => Promise<void>;
  discardRecording: () => void;

  // Chat search
  showChatSearch: boolean;
  chatSearch: string;
  setChatSearch: (v: string) => void;
  toggleChatSearch: () => void;
  visibleMessagesFiltered: ChatMessage[] | null;

  // Dots menu
  showDotsMenu: boolean;
  toggleDotsMenu: () => void;
  closeDotsMenu: () => void;
  dotsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Lightbox
  lightboxMedia: LightboxMedia | null;
  openLightbox: (src: string, kind: "image" | "video", alt: string, gifLike?: boolean) => void;
  closeLightbox: () => void;

  // Manual contact creation
  createManualContact: (declared_name: string, phone: string, channel_id?: number) => Promise<Contact | null>;
  updateDeclaredName: (contact_id: number, declared_name: string) => Promise<void>;
  busyCreateContact: boolean;

  // Contact picker — lista TODOS contatos do tenant (inclui state_sync da agenda).
  // Cache em memoria do provider (zera no logout/fechar aba — LGPD-safe).
  loadAllContacts: (q?: string) => Promise<{ contacts: Contact[]; total: number }>;
  refreshAllContacts: () => Promise<void>;
  openConversationForContact: (contact_id: number, channel_id?: number) => Promise<string | null>;

  // Message correction
  correctMessage: (messageId: number, newContent: string) => Promise<boolean>;
  correctionTarget: ChatMessage | null;
  startCorrection: (message: ChatMessage) => void;
  cancelCorrection: () => void;

  // Templates
  fetchTemplates: (channelId?: number | null) => Promise<WhatsAppTemplate[]>;
  fetchBillingStatus: (channelId: number) => Promise<{ ok: boolean; has_payment_method: boolean; error?: string } | null>;
  sendTemplate: (params: {
    contactId: number;
    templateName: string;
    language: string;
    components?: TemplateSendComponent[];
  }) => Promise<boolean>;
  busyTemplate: boolean;

  // Detail panel
  qualification: string;
  setQualification: (v: string) => void;
  notes: string;
  setNotes: (v: string) => void;
  toUserId: number | "";
  setToUserId: (v: number | "") => void;
  toDepartmentId: number | "";
  setToDepartmentId: (v: number | "") => void;
  transferReason: string;
  setTransferReason: (v: string) => void;
  transferSummary: string;
  setTransferSummary: (v: string) => void;
  busySave: boolean;
  busyTransfer: boolean;
  busyAssume: boolean;
  saveQualification: () => Promise<void>;
  assumeContact: (contactId: number) => Promise<void>;
  transferContact: () => Promise<void>;

  // Admin users
  editingUserId: number | null;
  setEditingUserId: (v: number | null) => void;
  editRole: string;
  setEditRole: (v: string) => void;
  editDeptId: number | "";
  setEditDeptId: (v: number | "") => void;
  busyRoleUpdate: boolean;
  startEditUser: (op: Operator) => void;
  saveUserRole: (userId: number) => Promise<void>;

  // Settings
  showSettings: SettingsPage;
  setShowSettings: (v: SettingsPage) => void;
  systemSettings: SystemSettings;
  setSystemSettings: React.Dispatch<React.SetStateAction<SystemSettings>>;
  userSettings: UserSettings;
  setUserSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  busySettings: boolean;
  toggleSettingsMenu: () => void;
  openSettingsPage: (page: "chat" | "quick" | "admin" | "whatsapp" | "dashboard") => Promise<void>;
  saveSystemSettingsAction: () => Promise<void>;
  saveUserSettingsAction: () => Promise<void>;
  settingsMenuRef: React.MutableRefObject<HTMLDivElement | null>;

  // Sidebar search
  search: string;
  setSearch: (v: string) => void;
  searchText: string;
  qualificationFilter: string;
  setQualificationFilter: (v: string) => void;
  filteredConversations: Conversation[];
  viewConversations: Conversation[];

  // Notifications
  error: string;
  setError: (msg: string) => void;
  notice: string;
  setNotice: (msg: string) => void;

  refreshPollingViews: () => Promise<void>;
};

const CrmContext = createContext<CrmContextValue | null>(null);

export function useCrm() {
  const ctx = useContext(CrmContext);
  if (!ctx) throw new Error("useCrm must be used within CrmProvider");
  return ctx;
}

// ---------------------------------------------------------------------------
// Default settings
// ---------------------------------------------------------------------------

const DEFAULT_SYSTEM_SETTINGS: SystemSettings = {
  chat_prefix_enabled: false,
  chat_prefix_roles: ["admin", "supervisor", "operador"],
  quick_message_max: 20,
  quick_messages_global: [],
  notification_sound_enabled: true,
  alarm_enabled: true,
  alarm_threshold_minutes: 5,
  alarm_department_ids: [],
  alarm_sound_path: "",
  notification_sound_path: "",
  bot_enabled: false,
};

const DEFAULT_USER_SETTINGS: UserSettings = {
  chat_prefix_enabled: false,
  chat_prefix_name: "",
  quick_messages: [],
};

const CONVERSATION_OPEN_DEBOUNCE_MS = 350;
const CONVERSATION_READ_DEBOUNCE_MS = 1200;
const RECENT_CONVERSATION_CACHE_LIMIT = 12;

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function CrmProvider({ children }: { children: ReactNode }) {
  // -- Core state --
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [bundle, setBundle] = useState<FirebaseBundle | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null);
  const [operators, setOperators] = useState<Operator[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  // Fase 3: lista de conversations (sub-threads por canal). Mesmo wa_id em
  // dois canais aparece como duas entradas distintas.
  const [conversations, setConversations] = useState<Conversation[]>([]);
  // Cache em memoria de TODOS os contatos do tenant (inclui agenda
  // sincronizada via smb_app_state_sync que nao aparece na sidebar).
  // null = ainda nao carregado; array = carregado (mesmo se vazio).
  // Zera junto com o provider (logout/refresh/aba fechada) — sem
  // persistencia em localStorage por LGPD.
  const [allContactsCache, setAllContactsCache] = useState<Contact[] | null>(null);
  const contactsById = useMemo(
    () => new Map<number, Contact>(contacts.map((c) => [c.id, c])),
    [contacts],
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  // Fase 3 V2: selectedThreadId e a fonte unica de selecao na sidebar.
  // selectedContactId vira derivado de selectedThreadId -> conversation.contact_id.
  // Quando setado, ChatPanel filtra mensagens por conversation_id (nao
  // cross-channel como o legado).
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const selectedConversation = useMemo(
    () => (selectedThreadId ? conversations.find((c) => c.id === selectedThreadId) || null : null),
    [conversations, selectedThreadId],
  );
  const selectedContactId = selectedConversation?.contact_id ?? null;
  const [transportMode, setTransportMode] = useState<TransportMode>("snapshot");
  const [booting, setBooting] = useState(true);
  const [busyLogin, setBusyLogin] = useState(false);

  // -- Theme --
  const [theme, setTheme] = useState<"dark" | "light">(() => { const p = themePref(); applyTheme(p); return p; });
  const toggleTheme = useCallback(() => {
    setTheme((prev) => { const next = prev === "dark" ? "light" : "dark"; applyTheme(next); return next; });
  }, []);

  // -- Sidebar / nav --
  const [search, setSearch] = useState("");
  const [activeView, setActiveView] = useState<ActiveView>("novos");
  const [equipeOperatorFilter, setEquipeOperatorFilter] = useState("");
  const [qualificationFilter, setQualificationFilter] = useState("");
  const searchText = useDeferredValue(search.trim().toLowerCase());

  // -- Composer --
  const [draft, setDraft] = useState("");
  const [replyTarget, setReplyTarget] = useState<MessageReplyReference | null>(null);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [quickSuggestions, setQuickSuggestions] = useState<{ shortcut: string; message: string }[]>([]);
  const [busySend, setBusySend] = useState(false);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busyAudio, setBusyAudio] = useState(false);
  const [busyTemplate, setBusyTemplate] = useState(false);

  // -- Chat search --
  const [showChatSearch, setShowChatSearch] = useState(false);
  const [chatSearch, setChatSearch] = useState("");

  // -- Dots menu --
  const [showDotsMenu, setShowDotsMenu] = useState(false);

  // -- Recording --
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingTimerRef = useRef<number | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // -- Lightbox --
  const [lightboxMedia, setLightboxMedia] = useState<LightboxMedia | null>(null);

  // -- Messages --
  const [messageLimit, setMessageLimit] = useState(10);
  const [loadingMore, setLoadingMore] = useState(false);
  const [transcribingMessageId, setTranscribingMessageId] = useState<number | null>(null);

  // -- Detail panel --
  const [qualification, setQualification] = useState("");
  const [notes, setNotes] = useState("");
  const [toUserId, setToUserId] = useState<number | "">("");
  const [toDepartmentId, setToDepartmentId] = useState<number | "">("");
  const [transferReason, setTransferReason] = useState("");
  const [transferSummary, setTransferSummary] = useState("");
  const [busySave, setBusySave] = useState(false);
  const [busyTransfer, setBusyTransfer] = useState(false);
  const [busyAssume, setBusyAssume] = useState(false);
  const [busyCreateContact, setBusyCreateContact] = useState(false);
  const [correctionTarget, setCorrectionTarget] = useState<ChatMessage | null>(null);

  // -- Admin users --
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editDeptId, setEditDeptId] = useState<number | "">("");
  const [busyRoleUpdate, setBusyRoleUpdate] = useState(false);

  // -- Settings --
  const [showSettings, setShowSettings] = useState<SettingsPage>(false);
  const [systemSettings, setSystemSettings] = useState<SystemSettings>(DEFAULT_SYSTEM_SETTINGS);
  const [userSettings, setUserSettings] = useState<UserSettings>(DEFAULT_USER_SETTINGS);
  const [busySettings, setBusySettings] = useState(false);

  // -- Notifications --
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // -- Refs --
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const videoInputRef = useRef<HTMLInputElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const attachMenuRef = useRef<HTMLDivElement | null>(null);
  const dotsMenuRef = useRef<HTMLDivElement | null>(null);
  const settingsMenuRef = useRef<HTMLDivElement | null>(null);
  const prevMessageCountRef = useRef(0);
  const scrollIntentRef = useRef<"load_older" | "normal">("normal");
  const markingReadContactIdRef = useRef<number | null>(null);
  const selectedContactIdRef = useRef<number | null>(null);
  const messageCacheRef = useRef<Map<number, ChatMessage[]>>(new Map());

  // -- Derived --
  const snapshotMode = transportMode === "snapshot" && config?.data_backend === "firestore" && config?.firestore.snapshot_enabled && firebaseReady(config) && Boolean(bundle);
  const selectedContact = selectedContactId != null ? (contactsById.get(selectedContactId) || null) : null;
  const activeContact = activeConversationId != null ? (contactsById.get(activeConversationId) || null) : null;
  const isManagerRole = sessionUser?.role === "admin" || sessionUser?.role === "supervisor";

  const botEnabled = systemSettings.bot_enabled;
  // Fase 3.D: filtros operam sobre conversations (sub-threads por canal).
  // Mesmo wa_id em 2 canais = 2 entradas distintas em cada filtro. Campos
  // que pertencem ao contato (qualification, bot_completed, notes) sao
  // resolvidos via contactsById; o resto vem da propria conversation
  // (assigned_to, department_id, source_channel_type, unread_count).
  // Bot: sem atribuicao, no fluxo do bot (ainda nao completaram)
  const botConversations = useMemo(() => {
    if (!botEnabled) return [] as Conversation[];
    return conversations.filter((conv) => {
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      return c.qualification !== "nao_qualificado" && !c.bot_completed;
    });
  }, [botEnabled, conversations, contactsById]);
  // Novos: sem atribuicao. Com bot ativo, so threads que ja completaram bot.
  // Operador comum so ve threads do seu departamento (ou sem); admin/supervisor veem todas.
  const novosConversations = useMemo(() => {
    return conversations.filter((conv) => {
      if (conv.assigned_to) return false;
      const c = contactsById.get(conv.contact_id);
      if (!c) return false;
      if (c.qualification === "nao_qualificado") return false;
      if (botEnabled && !c.bot_completed) return false;
      if (!isManagerRole && conv.department_id != null && conv.department_id !== sessionUser?.department_id) return false;
      return true;
    });
  }, [conversations, contactsById, botEnabled, isManagerRole, sessionUser?.department_id]);
  // Meus: atribuidas ao usuario logado (inclui coexistence auto-atribuidas)
  const meusConversations = useMemo(
    () => conversations.filter((conv) => conv.assigned_to === sessionUser?.id),
    [conversations, sessionUser?.id],
  );
  // Nao qualificadas: qualification do contato e "nao_qualificado"
  const nqConversations = useMemo(() => {
    return conversations.filter((conv) => {
      const c = contactsById.get(conv.contact_id);
      return c?.qualification === "nao_qualificado";
    });
  }, [conversations, contactsById]);
  // Equipe: atribuidas a outros operadores. Operadores comuns nao veem
  // coexistence de outros; admin/supervisor veem tudo.
  const equipeConversations = useMemo(() => {
    return conversations.filter((conv) => {
      if (!conv.assigned_to || conv.assigned_to === sessionUser?.id) return false;
      if (!isManagerRole && conv.source_channel_type === "coexistence") return false;
      return true;
    });
  }, [conversations, isManagerRole, sessionUser?.id]);

  // Fase 3.D: unread agregado e a soma das conversations daquela view.
  // Single source of truth — coerente com mark-read otimista por thread.
  const sumUnread = (list: Conversation[]) =>
    list.reduce((s, conv) => s + (conv.unread_count ?? conv.unread ?? 0), 0);
  const botUnread = sumUnread(botConversations);
  const novosUnread = sumUnread(novosConversations);
  const meusUnread = sumUnread(meusConversations);
  const nqUnread = sumUnread(nqConversations);
  const equipeUnread = sumUnread(equipeConversations);
  const equipeFiltered = equipeOperatorFilter
    ? equipeConversations.filter((conv) => String(conv.assigned_to) === equipeOperatorFilter)
    : equipeConversations;

  const viewConversations = activeView === "bot" ? botConversations
    : activeView === "novos" ? novosConversations
    : activeView === "meus" ? meusConversations
    : activeView === "equipe" ? equipeFiltered
    : nqConversations;
  // Search e qualification filter operam no contato (denormalizado pra UX).
  const filteredConversations = viewConversations.filter((conv) => {
    const c = contactsById.get(conv.contact_id);
    const matchesSearch = !searchText || [
      c?.display_name || "",
      c?.phone_formatted || "",
      c?.department_name || "",
      c?.assigned_name || "",
    ].join(" ").toLowerCase().includes(searchText);
    const matchesQual = !qualificationFilter || c?.qualification === qualificationFilter;
    return matchesSearch && matchesQual;
  });

  const chatSearchLower = chatSearch.trim().toLowerCase();
  const visibleMessagesFiltered = chatSearchLower ? messages.filter((m) => String(m.content || "").toLowerCase().includes(chatSearchLower)) : null;
  const hasDraft = Boolean(draft.trim());
  const busyComposerAction = busyAudio || busySend;

  const visibleMessages = messages.filter((message, index, allMessages) => {
    // Filtrar mensagens admin_only para operadores comuns
    if (message.visibility === "admin_only" && !isManagerRole) return false;
    const kind = String(message.msg_type || "").trim().toLowerCase();
    if (kind !== "unsupported" && kind !== "unknown") return true;
    const nextMessage = allMessages[index + 1];
    if (!nextMessage || nextMessage.direction !== message.direction || !nextMessage.media_path) return true;
    const currentMoment = messageMoment(message.timestamp_wa || message.created_at);
    const nextMoment = messageMoment(nextMessage.timestamp_wa || nextMessage.created_at);
    if (Number.isNaN(currentMoment) || Number.isNaN(nextMoment)) return true;
    return (nextMoment - currentMoment) > 60_000;
  });

  // =========================================================================
  // Recording helpers
  // =========================================================================
  function clearRecordingTimer() {
    if (recordingTimerRef.current) { window.clearInterval(recordingTimerRef.current); recordingTimerRef.current = null; }
  }
  function releaseAudioStream() {
    if (mediaStreamRef.current) { mediaStreamRef.current.getTracks().forEach((t) => t.stop()); mediaStreamRef.current = null; }
  }
  function discardRecording() {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") { try { recorder.stop(); } catch { /* ignore */ } }
    mediaRecorderRef.current = null;
    releaseAudioStream();
    audioChunksRef.current = [];
    setRecording(false);
    setRecordingSeconds(0);
  }

  function rememberConversationMessages(contactId: number, nextMessages: ChatMessage[]) {
    const cache = messageCacheRef.current;
    if (cache.has(contactId)) cache.delete(contactId);
    cache.set(contactId, nextMessages);
    while (cache.size > RECENT_CONVERSATION_CACHE_LIMIT) {
      const oldestKey = cache.keys().next().value;
      if (oldestKey == null) break;
      cache.delete(oldestKey);
    }
  }

  function commitConversationMessages(contactId: number, nextMessages: ChatMessage[]) {
    rememberConversationMessages(contactId, nextMessages);
    if (selectedContactIdRef.current === contactId) {
      startTransition(() => setMessages(nextMessages));
    }
  }

  function restoreConversationFromCache(contactId: number | null) {
    if (!contactId) {
      startTransition(() => setMessages([]));
      return;
    }
    const cachedMessages = messageCacheRef.current.get(contactId) || [];
    startTransition(() => setMessages(cachedMessages));
  }

  function applyConversationReadLocally(contactId: number, conversationId?: string | null) {
    const cachedMessages = messageCacheRef.current.get(contactId);
    if (cachedMessages) {
      rememberConversationMessages(contactId, cachedMessages.map((message) => (
        message.direction === "inbound" && message.status === "received"
          ? { ...message, status: "read" }
          : message
      )));
    }
    startTransition(() => {
      // Fase 3: zera unread da conversation alvo (se houver), nao do contato
      // inteiro — outras threads do mesmo contato podem ter unread proprio.
      if (conversationId) {
        setConversations((prev) => prev.map((conv) => (
          conv.id === conversationId ? { ...conv, unread: 0, unread_count: 0 } : conv
        )));
      } else {
        setContacts((prev) => prev.map((contact) => (
          contact.id === contactId ? { ...contact, unread: 0, unread_count: 0 } : contact
        )));
      }
      if (selectedContactIdRef.current === contactId) {
        setMessages((prev) => {
          const nextMessages = prev.map((message) => (
            message.contact_id === contactId && message.direction === "inbound" && message.status === "received"
              ? { ...message, status: "read" }
              : message
          ));
          rememberConversationMessages(contactId, nextMessages);
          return nextMessages;
        });
      }
    });
  }

  function buildContactSnapshotTargets() {
    if (!bundle?.db || !config?.firestore.collections.wa_contacts || !sessionUser) return [];

    const waContacts = collection(bundle.db, config.firestore.collections.wa_contacts);
    const baseConstraints = [where("is_archived", "==", 0), orderBy("last_message_at", "desc"), firestoreLimit(50)] as const;

    if (sessionUser.role === "admin" || sessionUser.role === "supervisor") {
      return [{ key: "all", ref: query(waContacts, ...baseConstraints) }];
    }

    const targets: { key: string; ref: ReturnType<typeof query> }[] = [
      { key: "unassigned:blank", ref: query(waContacts, where("assigned_to_uid", "==", ""), ...baseConstraints) },
      { key: "unassigned:null", ref: query(waContacts, where("assigned_to_uid", "==", null), ...baseConstraints) },
    ];

    if (sessionUser.firebase_uid) {
      targets.push({
        key: `mine:${sessionUser.firebase_uid}`,
        ref: query(waContacts, where("assigned_to_uid", "==", sessionUser.firebase_uid), ...baseConstraints),
      });
    }

    if (sessionUser.department_id != null) {
      targets.push({
        key: `department:${sessionUser.department_id}`,
        ref: query(waContacts, where("department_id", "==", sessionUser.department_id), ...baseConstraints),
      });
    }

    return targets;
  }

  function mergeVisibleContacts(groups: Contact[][]) {
    const merged = new Map<number, Contact>();
    for (const group of groups) {
      for (const contact of group) {
        merged.set(contact.id, contact);
      }
    }
    return Array.from(merged.values())
      .sort((a, b) => (b.last_message_at || "").localeCompare(a.last_message_at || ""))
      .slice(0, 50);
  }

  // =========================================================================
  // Effects
  // =========================================================================

  // Boot
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const c = await getJson<ClientConfig>(null, "/api/client-config");
        if (cancelled) return;
        setConfig(c);
        setTransportMode(transportPref() || c.chat_delivery_mode || "snapshot");
        if (c.auth_mode === "firebase" && firebaseReady(c)) setBundle(await initializeFirebaseBundle(c.firebase_web_config));
      } catch (e) { if (!cancelled) setError(errorText(e)); }
      finally { if (!cancelled) setBooting(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // Auth listener
  useEffect(() => {
    if (!bundle) return undefined;
    return onIdTokenChanged(bundle.auth, async (user) => {
      setFirebaseUser(user);
      if (!user) { setSessionUser(null); setContacts([]); setMessages([]); return; }
      try {
        const session = await getJson<{
          user: SessionUser;
          tenant_id?: string;
          firestore_collections?: Record<string, string>;
        }>(bundle.auth, "/api/session");
        const [ops, deps, chs] = await Promise.all([
          getJson<Operator[]>(bundle.auth, "/api/operators"),
          getJson<{ departments: Department[] }>(bundle.auth, "/api/departments"),
          getJson<{ channels: Channel[] }>(bundle.auth, "/api/admin/channels").catch(() => ({ channels: [] as Channel[] })),
        ]);
        setSessionUser(session.user);
        setOperators(ops);
        setDepartments(deps.departments);
        setChannels(chs.channels);
        setError("");
        // Fase 2: sobrescreve paths das colecoes Firestore com versoes
        // scopadas ao tenant. Snapshot listeners passam a ler de
        // tenants/{tenant_id}/* em vez de colecao flat.
        if (session.firestore_collections) {
          setConfig((prev) => prev ? {
            ...prev,
            firestore: {
              ...prev.firestore,
              collections: { ...prev.firestore.collections, ...session.firestore_collections! },
            },
          } : prev);
        }
        Promise.all([
          getJson<SystemSettings>(bundle.auth, "/api/settings/system"),
          getJson<UserSettings>(bundle.auth, "/api/settings/user"),
        ]).then(([sys, usr]) => { setSystemSettings(sys); setUserSettings(usr); }).catch(() => {});
      } catch (e) { setError(errorText(e)); await signOut(bundle.auth); }
    });
  }, [bundle]);

  // Auto-select primeira conversation se nada selecionado (ou seleção orfã).
  useEffect(() => {
    if (!conversations.length) {
      if (selectedThreadId) setSelectedThreadId(null);
      return;
    }
    if (!selectedThreadId || !conversations.some((c) => c.id === selectedThreadId)) {
      setSelectedThreadId(conversations[0].id);
    }
  }, [conversations, selectedThreadId]);

  // Track the selected conversation and restore its recent in-memory cache immediately.
  useEffect(() => {
    selectedContactIdRef.current = selectedContactId;
    restoreConversationFromCache(selectedContactId);
    if (!selectedContactId) {
      setActiveConversationId(null);
      return undefined;
    }
    const timeoutId = window.setTimeout(() => setActiveConversationId(selectedContactId), CONVERSATION_OPEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [selectedContactId]);

  // Debounce equivalente para a thread selecionada (V2 Fase 3).
  useEffect(() => {
    if (!selectedThreadId) {
      setActiveThreadId(null);
      return undefined;
    }
    const timeoutId = window.setTimeout(() => setActiveThreadId(selectedThreadId), CONVERSATION_OPEN_DEBOUNCE_MS);
    return () => window.clearTimeout(timeoutId);
  }, [selectedThreadId]);

  // Reset detail state on contact change
  useEffect(() => {
    const contact = contacts.find((c) => c.id === selectedContactId) || null;
    setQualification(contact?.qualification || "");
    setNotes(contact?.notes || "");
    setToUserId(contact?.assigned_to || "");
    setToDepartmentId(contact?.department_id || "");
    setTransferReason("");
    setTransferSummary("");
    setReplyTarget(null);
    setShowAttachMenu(false);
    setLightboxMedia(null);
    setMessageLimit(10);
    setLoadingMore(false);
    prevMessageCountRef.current = 0;
    scrollIntentRef.current = "normal";
    discardRecording();
  }, [selectedContactId]);

  // Composer auto-resize
  useEffect(() => {
    const input = composerInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }, [draft, selectedContactId, recording]);

  // Attach menu click-outside
  useEffect(() => {
    if (!showAttachMenu) return undefined;
    const handler = (e: PointerEvent) => { if (!attachMenuRef.current?.contains(e.target as Node)) setShowAttachMenu(false); };
    window.addEventListener("pointerdown", handler);
    return () => window.removeEventListener("pointerdown", handler);
  }, [showAttachMenu]);

  // Lightbox escape
  useEffect(() => {
    if (!lightboxMedia) return undefined;
    const handler = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") setLightboxMedia(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightboxMedia]);

  // Cleanup recording on unmount
  useEffect(() => () => {
    clearRecordingTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") { try { recorder.stop(); } catch {} }
    releaseAudioStream();
  }, []);

  // Snapshot: contacts
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    let disposed = false;
    if (!snapshotMode || !config.firestore.collections.wa_contacts) return undefined;
    const targets = buildContactSnapshotTargets();
    const partialContacts = new Map<string, Contact[]>();

    const publish = () => {
      if (disposed) return;
      const nextContacts = mergeVisibleContacts(Array.from(partialContacts.values()));
      startTransition(() => setContacts(nextContacts));
    };

    const unsubscribers = targets.map(({ key, ref }) => onSnapshot(
      ref,
      (snap) => {
        partialContacts.set(key, snap.docs.map((doc) => normalizeContact(doc.data() as Record<string, unknown>, doc.id)));
        publish();
      },
      (e) => !disposed && setError(`Snapshot de contatos falhou: ${errorText(e)}`),
    ));

    return () => {
      disposed = true;
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
  }, [bundle, config, sessionUser, snapshotMode]);

  // Snapshot: wa_conversations (Fase 3 — sub-threads por canal)
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    if (!snapshotMode || !config.firestore.collections.wa_conversations) return undefined;
    let disposed = false;
    const ref = collection(bundle.db, config.firestore.collections.wa_conversations);
    const unsubscribe = onSnapshot(
      ref,
      (snap) => {
        if (disposed) return;
        const next = snap.docs.map((doc) => normalizeConversation(doc.data() as Record<string, unknown>, doc.id));
        startTransition(() => setConversations(next));
      },
      (e) => !disposed && setError(`Snapshot de conversations falhou: ${errorText(e)}`),
    );
    return () => { disposed = true; unsubscribe(); };
  }, [bundle, config, sessionUser, snapshotMode]);

  // Snapshot: selected conversation/thread
  // V2 Fase 3: se activeThreadId setado, filtra por conversation_id
  // (mostra so mensagens daquele canal). Senao, fallback para contact_id
  // (timeline cross-channel — comportamento legado).
  useEffect(() => {
    if (!bundle || !sessionUser || !config) return undefined;
    if (!snapshotMode) return undefined;
    if (!activeConversationId || !config.firestore.collections.wa_messages) return undefined;
    let disposed = false;
    const baseRef = collection(bundle.db, config.firestore.collections.wa_messages);
    const messagesQuery = activeThreadId
      ? query(baseRef, where("conversation_id", "==", activeThreadId), orderBy("timestamp_wa", "desc"), firestoreLimit(messageLimit))
      : query(baseRef, where("contact_id", "==", activeConversationId), orderBy("timestamp_wa", "desc"), firestoreLimit(messageLimit));
    const unsubscribe = onSnapshot(
      messagesQuery,
      (snap) => {
        // Ordena por timestamp_wa (data real da mensagem), com fallback
        // para created_at em system messages legadas sem timestamp_wa.
        const nextMessages = snap.docs.map((doc) => normalizeMessage(doc.data(), doc.id)).sort((a, b) => {
          const ta = a.timestamp_wa || a.created_at || "";
          const tb = b.timestamp_wa || b.created_at || "";
          return ta.localeCompare(tb);
        });
        commitConversationMessages(activeConversationId, nextMessages);
      },
      (e) => !disposed && setError(`Snapshot da conversa falhou: ${errorText(e)}`),
    );
    return () => { disposed = true; unsubscribe(); };
  }, [activeConversationId, activeThreadId, bundle, config, sessionUser, snapshotMode, messageLimit]);

  // Polling fallback
  useEffect(() => {
    if (!bundle || !sessionUser || !config || snapshotMode) return undefined;
    let disposed = false;
    let intervalId = 0;

    const loadContacts = async () => {
      const r = await getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts");
      if (!disposed) startTransition(() => setContacts(r.contacts));
    };
    const loadConversations = async () => {
      try {
        const r = await getJson<{ conversations: Conversation[] }>(bundle.auth, "/api/wa/conversations");
        if (!disposed) startTransition(() => setConversations(r.conversations || []));
      } catch (e) {
        // Endpoint pode nao existir em ambientes legados; fallback silencioso.
        if (!disposed) setConversations([]);
      }
    };
    const loadMessages = async (cid: number) => {
      // V2 Fase 3: se ha thread selecionada, passa conversation_id como
      // query param para filtrar mensagens daquela thread especifica.
      const threadParam = activeThreadId ? `&conversation_id=${encodeURIComponent(activeThreadId)}` : "";
      const r = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${cid}?limit=${messageLimit}${threadParam}`);
      if (!disposed) commitConversationMessages(cid, r.messages);
    };
    const tick = async () => {
      try {
        await Promise.all([loadContacts(), loadConversations()]);
        if (activeConversationId) await loadMessages(activeConversationId);
      } catch (e) {
        if (!disposed) setError(errorText(e));
      }
    };

    void tick();
    intervalId = window.setInterval(() => { void tick(); }, config.polling_interval_ms || 15000);
    return () => { disposed = true; if (intervalId) window.clearInterval(intervalId); };
  }, [activeConversationId, activeThreadId, bundle, config, sessionUser, snapshotMode, messageLimit]);

  // Mark selected conversation as read explicitly
  useEffect(() => {
    if (!bundle || !sessionUser || !activeConversationId) return undefined;
    if (selectedContactId !== activeConversationId) return undefined;
    const unreadCount = activeContact?.unread_count ?? activeContact?.unread ?? 0;
    if (markingReadContactIdRef.current && markingReadContactIdRef.current !== activeConversationId) {
      markingReadContactIdRef.current = null;
    }
    if (unreadCount <= 0) {
      if (markingReadContactIdRef.current === activeConversationId) markingReadContactIdRef.current = null;
      return undefined;
    }
    if (markingReadContactIdRef.current === activeConversationId) return undefined;

    // Fase 2C: marca thread aberta como lida (se houver). Sem thread,
    // cai no endpoint legado por contact_id (timeline cross-channel).
    const threadIdAtMark = activeThreadId;
    const readPath = threadIdAtMark
      ? `/api/wa/conversation/${encodeURIComponent(threadIdAtMark)}/read`
      : `/api/wa/contact/${activeConversationId}/read`;

    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      if (cancelled) return;
      markingReadContactIdRef.current = activeConversationId;
      void sendJson<{ status: string; updated_count: number }>(bundle.auth, readPath, {})
        .then(() => {
          if (cancelled) return;
          markingReadContactIdRef.current = null;
          applyConversationReadLocally(activeConversationId, threadIdAtMark);
        })
        .catch((e) => {
          if (cancelled) return;
          markingReadContactIdRef.current = null;
          setError(errorText(e));
        });
    }, CONVERSATION_READ_DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [activeContact?.unread, activeContact?.unread_count, activeConversationId, activeThreadId, bundle, selectedContactId, sessionUser]);

  // =========================================================================
  // Sound notifications
  // =========================================================================

  const prevTotalUnreadRef = useRef<number | null>(null);
  const alarmIntervalRef = useRef<number | null>(null);
  const alarmAudioRef = useRef<HTMLAudioElement | null>(null);

  // Beep for all users when total unread increases
  useEffect(() => {
    if (!sessionUser || !systemSettings.notification_sound_enabled) {
      prevTotalUnreadRef.current = null;
      return;
    }
    const totalUnread = contacts.reduce((s, c) => s + (c.unread || 0), 0);
    const prev = prevTotalUnreadRef.current;
    prevTotalUnreadRef.current = totalUnread;
    if (prev === null) return; // first load, don't beep
    if (totalUnread > prev) {
      // New message arrived — play notification beep
      if (systemSettings.notification_sound_path) {
        const audio = new Audio(systemSettings.notification_sound_path);
        audio.volume = 0.5;
        audio.play().catch(() => {});
      } else {
        // Default beep via Web Audio API
        try {
          const ctx = new AudioContext();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.frequency.value = 880;
          osc.type = "sine";
          gain.gain.value = 0.3;
          osc.start();
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
          osc.stop(ctx.currentTime + 0.3);
          setTimeout(() => ctx.close(), 500);
        } catch { /* audio not available */ }
      }
    }
  }, [contacts, sessionUser, systemSettings.notification_sound_enabled, systemSettings.notification_sound_path]);

  // Repeating alarm for configured departments when messages unread > threshold
  useEffect(() => {
    if (alarmIntervalRef.current) {
      window.clearInterval(alarmIntervalRef.current);
      alarmIntervalRef.current = null;
    }
    if (alarmAudioRef.current) {
      alarmAudioRef.current.pause();
      alarmAudioRef.current = null;
    }
    if (!sessionUser || !systemSettings.alarm_enabled) return undefined;
    // Check if user's department is in the alarm list
    const userDeptId = sessionUser.department_id;
    const alarmDepts = systemSettings.alarm_department_ids || [];
    if (alarmDepts.length > 0 && (!userDeptId || !alarmDepts.includes(userDeptId))) return undefined;
    // Only active if there are alarm departments configured (empty = disabled for dept filter)
    if (alarmDepts.length === 0) return undefined;

    const thresholdMs = (systemSettings.alarm_threshold_minutes || 5) * 60 * 1000;

    const checkAlarm = () => {
      const now = Date.now();
      // Check contacts assigned to this user (or unassigned in "novos") that have unread messages
      const hasOverdueUnread = contacts.some((c) => {
        if ((c.unread || 0) <= 0) return false;
        // Only alarm for contacts assigned to this user or unassigned (novos)
        if (c.assigned_to && c.assigned_to !== sessionUser.id) return false;
        // Check if last_message_at is older than threshold
        if (!c.last_message_at) return false;
        const msgTime = new Date(c.last_message_at).getTime();
        return !isNaN(msgTime) && (now - msgTime) >= thresholdMs;
      });

      if (hasOverdueUnread) {
        if (systemSettings.alarm_sound_path) {
          if (!alarmAudioRef.current) {
            alarmAudioRef.current = new Audio(systemSettings.alarm_sound_path);
            alarmAudioRef.current.volume = 0.6;
          }
          alarmAudioRef.current.currentTime = 0;
          alarmAudioRef.current.play().catch(() => {});
        } else {
          // Default alarm: two-tone beep
          try {
            const ctx = new AudioContext();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.value = 660;
            osc.type = "square";
            gain.gain.value = 0.25;
            osc.start();
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
            osc.frequency.setValueAtTime(660, ctx.currentTime + 0.3);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.45);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
            osc.stop(ctx.currentTime + 0.6);
            setTimeout(() => ctx.close(), 800);
          } catch { /* audio not available */ }
        }
      } else {
        // No overdue messages — stop alarm audio if playing
        if (alarmAudioRef.current) {
          alarmAudioRef.current.pause();
          alarmAudioRef.current = null;
        }
      }
    };

    // Check immediately and then every 30 seconds
    checkAlarm();
    alarmIntervalRef.current = window.setInterval(checkAlarm, 30_000);
    return () => {
      if (alarmIntervalRef.current) window.clearInterval(alarmIntervalRef.current);
      if (alarmAudioRef.current) { alarmAudioRef.current.pause(); alarmAudioRef.current = null; }
    };
  }, [contacts, sessionUser, systemSettings.alarm_enabled, systemSettings.alarm_threshold_minutes, systemSettings.alarm_department_ids, systemSettings.alarm_sound_path]);

  // =========================================================================
  // Actions
  // =========================================================================

  function buildReplyPayload() {
    if (!replyTarget) return {};
    return {
      reply_to_message_id: replyTarget.message_id,
      reply_to_preview: replyTarget.preview,
      reply_to_sender_name: replyTarget.sender_name,
    };
  }

  function appendReplyFields(form: FormData) {
    if (!replyTarget) return;
    form.append("reply_to_message_id", String(replyTarget.message_id));
    form.append("reply_to_preview", replyTarget.preview);
    form.append("reply_to_sender_name", replyTarget.sender_name);
  }

  function startReplyToMessage(message: ChatMessage) {
    setReplyTarget(buildMessageReplyReference(message));
    setShowAttachMenu(false);
    setQuickSuggestions([]);
    composerInputRef.current?.focus();
  }

  function cancelReply() {
    setReplyTarget(null);
  }

  async function copyMessageTextAction(message: ChatMessage) {
    const text = messageCopyText(message);
    if (!text) {
      setError("");
      setNotice("Essa mensagem nao tem texto para copiar.");
      return;
    }
    if (!navigator.clipboard?.writeText) {
      setError("Nao foi possivel copiar a mensagem neste navegador.");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setError("");
      setNotice("Texto copiado.");
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function refreshPollingViews() {
    if (!bundle) return;
    const [cr, vr] = await Promise.all([
      getJson<{ contacts: Contact[] }>(bundle.auth, "/api/wa/contacts"),
      getJson<{ conversations: Conversation[] }>(bundle.auth, "/api/wa/conversations").catch(() => ({ conversations: [] })),
    ]);
    startTransition(() => {
      setContacts(cr.contacts);
      setConversations(vr.conversations || []);
    });
    if (selectedContactId) {
      const mr = await getJson<{ messages: ChatMessage[] }>(bundle.auth, `/api/wa/messages/${selectedContactId}?limit=${messageLimit}`);
      commitConversationMessages(selectedContactId, mr.messages);
    }
  }

  async function loginWithGoogle() {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); await signInWithPopup(bundle.auth, bundle.provider); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function loginWithEmail(email: string, password: string) {
    if (!bundle) return;
    try { setBusyLogin(true); setError(""); await signInWithEmailAndPassword(bundle.auth, email, password); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyLogin(false); }
  }

  async function logout() { if (bundle) await signOut(bundle.auth); }

  // Resolve a chave de envio: preferimos conversation_id (thread atual)
  // — backend resolve canal pela thread, garantindo que mesmo wa_id em
  // 2 canais saia pelo canal correto. Se nao houver thread selecionada,
  // mandamos contact_id e o backend deriva a thread default.
  function buildSendTarget(): { conversation_id?: string; contact_id?: number } {
    if (selectedThreadId) return { conversation_id: selectedThreadId };
    if (selectedContact) return { contact_id: selectedContact.id };
    return {};
  }

  async function sendTextMessage() {
    if (!bundle || !selectedContact || !draft.trim()) return;
    try {
      setBusySend(true); setError(""); setNotice("");
      let content = draft.trim();
      if (userSettings.chat_prefix_enabled && userSettings.chat_prefix_name.trim() && systemSettings.chat_prefix_roles.includes(sessionUser?.role || "")) {
        content = `${userSettings.chat_prefix_name.trim()}: ${content}`;
      }
      await sendJson(bundle.auth, "/api/wa/send", { ...buildSendTarget(), content, ...buildReplyPayload() });
      setDraft(""); setReplyTarget(null); setNotice("Mensagem enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusySend(false); }
  }

  async function submitText(event: FormEvent<HTMLFormElement>) { event.preventDefault(); await sendTextMessage(); }

  async function submitMedia(file: File) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true); setError(""); setNotice("");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("caption", ""); form.append("file", file);
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setReplyTarget(null); setNotice("Foto enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyUpload(false); }
  }

  async function startRecording() {
    if (!selectedContact) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") { setError("O navegador nao oferece suporte para gravacao de audio."); return; }
    try {
      setError(""); setNotice(""); setShowAttachMenu(false);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];
      let recorder: MediaRecorder;
      try { recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" }); } catch { recorder = new MediaRecorder(stream); }
      recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      recorder.onstop = () => { releaseAudioStream(); mediaRecorderRef.current = null; };
      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setRecording(true); setRecordingSeconds(0); clearRecordingTimer();
      recordingTimerRef.current = window.setInterval(() => setRecordingSeconds((c) => c + 1), 1000);
    } catch (e) { setError(errorText(e)); discardRecording(); }
  }

  async function sendRecordedAudio() {
    if (!bundle || !selectedContact) return;
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    try {
      setBusyAudio(true); setError(""); setNotice(""); clearRecordingTimer();
      if (recorder.state !== "inactive") { await new Promise<void>((res) => { recorder.addEventListener("stop", () => res(), { once: true }); recorder.stop(); }); }
      const audioBlob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
      audioChunksRef.current = []; setRecording(false); setRecordingSeconds(0);
      if (!audioBlob.size) throw new Error("Nao foi possivel capturar o audio gravado.");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("file", audioBlob, "gravacao.webm");
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-audio", form);
      setReplyTarget(null); setNotice("Audio enviado.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); discardRecording(); }
    finally { releaseAudioStream(); mediaRecorderRef.current = null; audioChunksRef.current = []; setRecording(false); setRecordingSeconds(0); setBusyAudio(false); }
  }

  function handleDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!busySend && draft.trim()) void sendTextMessage(); }
  }

  function handleDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const value = event.target.value;
    setDraft(value);
    const trimmed = value.trim();
    if (trimmed.startsWith("/") && trimmed.length >= 1) {
      const typed = trimmed.toLowerCase();
      const allQuick = [...systemSettings.quick_messages_global, ...userSettings.quick_messages].filter((qm) => qm.shortcut && qm.message);
      const matches = allQuick.filter((qm) => { const s = qm.shortcut.startsWith("/") ? qm.shortcut.toLowerCase() : `/${qm.shortcut.toLowerCase()}`; return s.startsWith(typed); });
      setQuickSuggestions(matches);
    } else { setQuickSuggestions([]); }
  }

  function applyQuickMessage(qm: { shortcut: string; message: string }) {
    setDraft(qm.message); setQuickSuggestions([]); composerInputRef.current?.focus();
  }

  function toggleAttachMenu() { setShowAttachMenu((c) => !c); }
  function openImagePicker() { setShowAttachMenu(false); imageInputRef.current?.click(); }
  function openVideoPicker() { setShowAttachMenu(false); videoInputRef.current?.click(); }
  function openDocPicker() { setShowAttachMenu(false); documentInputRef.current?.click(); }

  async function submitFile(file: File, label: string) {
    if (!bundle || !selectedContact) return;
    try {
      setBusyUpload(true); setError(""); setNotice("");
      const form = new FormData();
      const target = buildSendTarget();
      if (target.conversation_id) form.append("conversation_id", target.conversation_id);
      else if (target.contact_id) form.append("contact_id", String(target.contact_id));
      form.append("caption", ""); form.append("file", file);
      appendReplyFields(form);
      await sendForm(bundle.auth, "/api/wa/send-media", form);
      setReplyTarget(null); setNotice(`${label} enviado.`);
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyUpload(false); }
  }

  async function sendLocation() {
    if (!bundle || !selectedContact) return;
    setShowAttachMenu(false);
    if (!navigator.geolocation) { setError("Geolocalização não disponível neste navegador."); return; }
    try {
      setError(""); setNotice("");
      const pos = await new Promise<GeolocationPosition>((res, rej) => navigator.geolocation.getCurrentPosition(res, rej, { timeout: 10000 }));
      await sendJson(bundle.auth, "/api/wa/send-location", { ...buildSendTarget(), latitude: pos.coords.latitude, longitude: pos.coords.longitude, ...buildReplyPayload() });
      setNotice("Localização enviada.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { const geo = e as { code?: number }; setError(geo.code ? "Permissão de localização negada ou tempo esgotado." : errorText(e)); }
  }

  async function transcribeMessage(messageId: number) {
    if (!bundle) return;
    try {
      setTranscribingMessageId(messageId); setError("");
      const result = await sendJson(bundle.auth, `/api/wa/messages/${messageId}/transcribe`, {}) as { transcription: string };
      setMessages((prev) => prev.map((m) => m.id === messageId ? { ...m, transcription: result.transcription } : m));
    } catch (e) { setError(errorText(e)); }
    finally { setTranscribingMessageId(null); }
  }

  function toggleChatSearch() { setShowChatSearch((v) => { if (v) setChatSearch(""); return !v; }); }
  function toggleDotsMenu() { setShowDotsMenu((v) => !v); }
  function closeDotsMenu() { setShowDotsMenu(false); }

  function handleImageSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return; void submitMedia(file);
  }

  function openLightbox(src: string, kind: "image" | "video", alt: string, gifLike = false) { setLightboxMedia({ src, kind, alt, gifLike }); }
  function closeLightbox() { setLightboxMedia(null); }

  function handlePrimaryAction() {
    if (busyComposerAction) return;
    if (recording) { void sendRecordedAudio(); return; }
    if (hasDraft) { void sendTextMessage(); return; }
    void startRecording();
  }

  async function saveQualification() {
    if (!bundle || !selectedContact) return;
    try { setBusySave(true); setError(""); setNotice(""); await putJson(bundle.auth, `/api/wa/contact/${selectedContact.id}/qualify`, { qualification, notes }); setNotice("Qualificacao atualizada."); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySave(false); }
  }

  function startEditUser(op: Operator) { setEditingUserId(op.id); setEditRole(op.role); setEditDeptId(op.department_id ?? ""); }

  async function saveUserRole(userId: number) {
    if (!bundle) return;
    try { setBusyRoleUpdate(true); setError(""); await putJson(bundle.auth, `/api/admin/users/${userId}`, { role: editRole, department_id: editDeptId || null }); setNotice("Usuario atualizado."); setEditingUserId(null); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyRoleUpdate(false); }
  }

  function startCorrection(message: ChatMessage) {
    setCorrectionTarget(message);
    setDraft(message.content || "");
    composerInputRef.current?.focus();
  }

  function cancelCorrection() {
    setCorrectionTarget(null);
    setDraft("");
  }

  async function correctMessage(messageId: number, newContent: string): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusySend(true); setError("");
      const res = await sendJson(bundle.auth, "/api/wa/correct-message", { message_id: messageId, new_content: newContent }) as { corrected_message_id: number };
      // Marcar mensagem original como corrigida no state local
      setMessages(prev => prev.map(m => m.id === res.corrected_message_id ? { ...m, is_corrected: true } : m));
      setCorrectionTarget(null);
      setDraft("");
      setNotice("Correcao enviada.");
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) { setError(errorText(e)); return false; }
    finally { setBusySend(false); }
  }

  async function fetchBillingStatus(channelId: number): Promise<{ ok: boolean; has_payment_method: boolean; error?: string } | null> {
    if (!bundle) return null;
    try {
      const res = await getJson<{ ok: boolean; has_payment_method: boolean; error?: string }>(
        bundle.auth,
        `/api/wa/channel/${channelId}/billing-status`,
      );
      return res;
    } catch (e) {
      return { ok: false, has_payment_method: false, error: errorText(e) };
    }
  }

  async function fetchTemplates(channelId?: number | null): Promise<WhatsAppTemplate[]> {
    if (!bundle) return [];
    const qs = channelId ? `?channel_id=${encodeURIComponent(String(channelId))}` : "";
    try {
      const res = await getJson<{ templates: WhatsAppTemplate[] }>(bundle.auth, `/api/wa/templates${qs}`);
      return res.templates || [];
    } catch (e) {
      setError(errorText(e));
      return [];
    }
  }

  async function sendTemplate(params: {
    contactId: number;
    conversationId?: string | null;
    templateName: string;
    language: string;
    components?: TemplateSendComponent[];
  }): Promise<boolean> {
    if (!bundle) return false;
    try {
      setBusyTemplate(true); setError(""); setNotice("");
      // Prefere conversation_id explicito, depois selectedThreadId, e por
      // ultimo cai em contact_id (legado pra views que ainda nao tem thread).
      const targetConv = params.conversationId || selectedThreadId || null;
      await sendJson(bundle.auth, "/api/wa/send-template", {
        ...(targetConv ? { conversation_id: targetConv } : { contact_id: params.contactId }),
        template_name: params.templateName,
        language: params.language,
        components: params.components || [],
      });
      setNotice("Template enviado.");
      if (!snapshotMode) await refreshPollingViews();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusyTemplate(false);
    }
  }

  async function createManualContact(declared_name: string, phone: string, channel_id?: number): Promise<Contact | null> {
    if (!bundle) return null;
    try {
      setBusyCreateContact(true); setError("");
      const payload: Record<string, unknown> = { declared_name, phone };
      if (channel_id) payload.channel_id = channel_id;
      const res = await sendJson(bundle.auth, "/api/wa/contact/manual", payload) as { contact: Record<string, unknown>; conversation_id?: string };
      const contact = normalizeContact(res.contact, String(res.contact.id));
      setContacts(prev => {
        const exists = prev.some(c => c.id === contact.id);
        if (exists) return prev.map(c => c.id === contact.id ? contact : c);
        return [contact, ...prev];
      });
      // Invalida cache do contact picker — novo contato precisa
      // aparecer no proximo open do modal.
      setAllContactsCache(null);
      // Backend retorna conversation_id deterministico do contato manual
      // (Fase 3). Setamos a thread direto — o snapshot listener vai trazer
      // a Conversation logo em seguida.
      if (res.conversation_id) {
        setSelectedThreadId(res.conversation_id);
      }
      setActiveView("meus");
      setNotice("Contato criado.");
      return contact;
    } catch (e) { setError(errorText(e)); return null; }
    finally { setBusyCreateContact(false); }
  }

  async function loadAllContacts(q?: string): Promise<{ contacts: Contact[]; total: number }> {
    if (!bundle) return { contacts: [], total: 0 };
    // Carrega a lista completa uma vez por sessao e cacheia em memoria.
    // Busca subsequente filtra local sobre o cache (instantanea).
    let cache = allContactsCache;
    if (!cache) {
      try {
        const res = await getJson<{ contacts: Record<string, unknown>[]; total: number; returned: number }>(
          bundle.auth, "/api/wa/contacts/all",
        );
        cache = (res.contacts || []).map((c) => normalizeContact(c, String(c.id)));
        setAllContactsCache(cache);
      } catch (e) {
        setError(errorText(e));
        return { contacts: [], total: 0 };
      }
    }
    if (q && q.trim()) {
      const needle = q.trim().toLowerCase();
      const filtered = cache.filter((c) => (
        (c.display_name || "").toLowerCase().includes(needle) ||
        (c.declared_name || "").toLowerCase().includes(needle) ||
        (c.whatsapp_profile_name || "").toLowerCase().includes(needle) ||
        (c.wa_id || "").toLowerCase().includes(needle) ||
        (c.phone_formatted || "").toLowerCase().includes(needle)
      ));
      return { contacts: filtered, total: cache.length };
    }
    return { contacts: cache, total: cache.length };
  }

  async function refreshAllContacts(): Promise<void> {
    // Forca reload do cache. Util apos criar contato manual ou
    // se admin sabe que houve sincronizacao nova.
    setAllContactsCache(null);
  }

  async function openConversationForContact(contact_id: number, channel_id?: number): Promise<string | null> {
    if (!bundle) return null;
    try {
      setError("");
      const payload: Record<string, unknown> = { contact_id };
      if (channel_id) payload.channel_id = channel_id;
      const res = await sendJson(bundle.auth, "/api/wa/conversation/open", payload) as {
        conversation_id: string; contact_id: number; channel_id: number;
      };
      // Insercao otimista no estado local pra evitar race com o snapshot
      // listener. Sem isso, o auto-select effect (que reseta seleção
      // quando selectedThreadId nao esta na lista de conversations)
      // sobrescreve nossa selecao antes do snapshot Firestore propagar.
      if (res.conversation_id) {
        setConversations((prev) => {
          if (prev.some((c) => c.id === res.conversation_id)) return prev;
          const optimistic = normalizeConversation({
            id: res.conversation_id,
            contact_id: res.contact_id,
            channel_id: res.channel_id,
            assigned_to: sessionUser?.id ?? null,
            assigned_to_uid: sessionUser?.firebase_uid ?? "",
            status: "open",
            unread_count: 0,
          }, res.conversation_id);
          return [optimistic, ...prev];
        });
        setSelectedThreadId(res.conversation_id);
        setActiveView("meus");
      }
      return res.conversation_id || null;
    } catch (e) {
      setError(errorText(e));
      return null;
    }
  }

  async function updateDeclaredName(contact_id: number, declared_name: string) {
    if (!bundle) return;
    try {
      setError("");
      const res = await putJson(bundle.auth, `/api/wa/contact/${contact_id}/declared-name`, { declared_name }) as { contact: Record<string, unknown> };
      const updated = normalizeContact(res.contact, String(res.contact.id));
      setContacts(prev => prev.map(c => c.id === updated.id ? updated : c));
      setNotice("Nome atualizado.");
    } catch (e) { setError(errorText(e)); }
  }

  async function assumeContact(contactId: number) {
    if (!bundle) return;
    try { setBusyAssume(true); setError(""); setNotice(""); await sendJson(bundle.auth, `/api/wa/assume/${contactId}`, {}); setNotice("Atendimento assumido."); if (!snapshotMode) await refreshPollingViews(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusyAssume(false); }
  }

  async function transferContact() {
    if (!bundle || !selectedContact || !toUserId || !transferSummary.trim()) return;
    try {
      setBusyTransfer(true); setError(""); setNotice("");
      await sendJson(bundle.auth, "/api/wa/transfer", { ...buildSendTarget(), to_user_id: Number(toUserId), to_department_id: toDepartmentId ? Number(toDepartmentId) : null, reason: transferReason, summary: transferSummary });
      setTransferReason(""); setTransferSummary(""); setNotice("Atendimento transferido.");
      if (!snapshotMode) await refreshPollingViews();
    } catch (e) { setError(errorText(e)); }
    finally { setBusyTransfer(false); }
  }

  function toggleSettingsMenu() { setShowSettings((prev) => prev === "menu" ? false : "menu"); }

  async function openSettingsPage(page: "chat" | "quick" | "admin" | "whatsapp" | "dashboard") {
    if (!bundle) return;
    if (page === "whatsapp") {
      setShowSettings(page);
      return;
    }
    try {
      setBusySettings(true);
      const [sys, usr] = await Promise.all([getJson<SystemSettings>(bundle.auth, "/api/settings/system"), getJson<UserSettings>(bundle.auth, "/api/settings/user")]);
      setSystemSettings(sys); setUserSettings(usr); setShowSettings(page);
    } catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveSystemSettingsAction() {
    if (!bundle) return;
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/system", systemSettings) as SystemSettings; setSystemSettings(r); setNotice("Configuracoes do sistema salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  async function saveUserSettingsAction() {
    if (!bundle) return;
    try { setBusySettings(true); const r = await putJson(bundle.auth, "/api/settings/user", userSettings) as UserSettings; setUserSettings(r); setNotice("Suas configuracoes salvas."); }
    catch (e) { setError(errorText(e)); }
    finally { setBusySettings(false); }
  }

  // =========================================================================
  // Value
  // =========================================================================

  const value: CrmContextValue = {
    config, bundle, firebaseUser, sessionUser, operators, departments, channels, booting, busyLogin, snapshotMode, isManagerRole,
    theme, toggleTheme,
    loginWithGoogle, loginWithEmail, logout,
    contacts, contactsById, conversations, selectedContactId, selectedContact, selectedConversation,
    selectedThreadId, setSelectedThreadId,
    activeView, setActiveView, novosConversations, meusConversations, nqConversations, equipeConversations, botConversations, novosUnread, meusUnread, nqUnread, equipeUnread, botUnread, equipeOperatorFilter, setEquipeOperatorFilter, equipeFiltered,
    messages, setMessages, visibleMessages, messageLimit, setMessageLimit, loadingMore, setLoadingMore, messagesRef, scrollIntentRef, prevMessageCountRef,
    transcribingMessageId, transcribeMessage,
    replyTarget, startReplyToMessage, cancelReply, copyMessageText: copyMessageTextAction,
    draft, setDraft, busySend, busyUpload, busyAudio, quickSuggestions, setQuickSuggestions,
    sendTextMessage, submitText, submitMedia, submitFile, sendLocation,
    handleDraftKeyDown, handleDraftChange, applyQuickMessage, handlePrimaryAction, handleImageSelected,
    composerInputRef, imageInputRef, videoInputRef, documentInputRef,
    showAttachMenu, setShowAttachMenu, toggleAttachMenu, openImagePicker, openVideoPicker, openDocPicker, attachMenuRef,
    recording, recordingSeconds, startRecording, sendRecordedAudio, discardRecording,
    showChatSearch, chatSearch, setChatSearch, toggleChatSearch, visibleMessagesFiltered,
    showDotsMenu, toggleDotsMenu, closeDotsMenu, dotsMenuRef,
    lightboxMedia, openLightbox, closeLightbox,
    qualification, setQualification, notes, setNotes, toUserId, setToUserId, toDepartmentId, setToDepartmentId, transferReason, setTransferReason, transferSummary, setTransferSummary,
    createManualContact, updateDeclaredName, busyCreateContact,
    loadAllContacts, refreshAllContacts, openConversationForContact,
    correctMessage, correctionTarget, startCorrection, cancelCorrection,
    fetchTemplates, sendTemplate, busyTemplate, fetchBillingStatus,
    busySave, busyTransfer, busyAssume, saveQualification, assumeContact, transferContact,
    editingUserId, setEditingUserId, editRole, setEditRole, editDeptId, setEditDeptId, busyRoleUpdate, startEditUser, saveUserRole,
    showSettings, setShowSettings, systemSettings, setSystemSettings, userSettings, setUserSettings, busySettings, toggleSettingsMenu, openSettingsPage, saveSystemSettingsAction, saveUserSettingsAction, settingsMenuRef,
    search, setSearch, searchText, qualificationFilter, setQualificationFilter, filteredConversations, viewConversations,
    error, setError, notice, setNotice,
    refreshPollingViews,
  };

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>;
}
```

## frontend/src/components/gchat/InternalChatPanel.tsx

```tsx
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { collection, limit as firestoreLimit, onSnapshot, orderBy, query } from "firebase/firestore";
import { useCrm } from "../../context/CrmContext";
import { getJson, sendJson } from "../../api";
import type { GcConversation, GcMessage } from "../../types";
import { CloseIcon, SendIcon } from "../icons";

// ---------------------------------------------------------------------------
// InternalChatPanel - Slide-in panel for Google Chat integration
// ---------------------------------------------------------------------------

type PanelView = "conversations" | "chat";

export function InternalChatPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { bundle, sessionUser, config } = useCrm();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const [view, setView] = useState<PanelView>("conversations");
  const [conversations, setConversations] = useState<GcConversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<GcConversation | null>(null);
  const [messages, setMessages] = useState<GcMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const userEmail = sessionUser?.email || "";

  // Fetch conversations on open
  useEffect(() => {
    if (!open || !bundle?.auth) return;
    setLoading(true);
    getJson<{ conversations: GcConversation[] }>(bundle.auth, "/api/gc/conversations")
      .then((r) => setConversations(r.conversations))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, bundle?.auth]);

  // Firestore real-time for conversations list
  useEffect(() => {
    if (!open || !bundle?.db || !config?.firestore?.collections?.gc_conversations) return;
    const colName = config.firestore.collections.gc_conversations;
    const q = query(collection(bundle.db, colName), orderBy("last_message_at", "desc"), firestoreLimit(50));
    const unsub = onSnapshot(q, (snap) => {
      const items: GcConversation[] = snap.docs.map((doc) => {
        const d = doc.data();
        return {
          id: d.id ?? parseInt(doc.id, 10),
          space_id: d.space_id ?? "",
          space_name: d.space_name ?? "",
          participants: d.participants ?? [],
          last_message: d.last_message ?? "",
          last_message_at: d.last_message_at?.toDate?.()?.toISOString?.() ?? d.last_message_at ?? "",
          unread_count: d.unread_count ?? {},
          created_at: d.created_at?.toDate?.()?.toISOString?.() ?? d.created_at ?? "",
        };
      });
      setConversations(items);
    });
    return () => unsub();
  }, [open, bundle?.db, config?.firestore?.collections?.gc_conversations]);

  // Firestore real-time for messages of selected conversation
  useEffect(() => {
    if (!selectedConv || !bundle?.db || !config?.firestore?.collections?.gc_messages) return;
    const colName = config.firestore.collections.gc_messages;
    const q = query(
      collection(bundle.db, colName),
      orderBy("created_at", "desc"),
      firestoreLimit(100),
    );
    const unsub = onSnapshot(q, (snap) => {
      const items: GcMessage[] = snap.docs
        .map((doc) => {
          const d = doc.data();
          return {
            id: d.id ?? parseInt(doc.id, 10),
            conversation_id: d.conversation_id,
            gchat_message_id: d.gchat_message_id ?? "",
            sender_email: d.sender_email ?? "",
            sender_name: d.sender_name ?? "",
            msg_type: d.msg_type ?? "text",
            content: d.content ?? "",
            media_path: d.media_path ?? "",
            media_mime: d.media_mime ?? "",
            source: d.source ?? "google_chat",
            create_time: d.create_time?.toDate?.()?.toISOString?.() ?? d.create_time ?? "",
            created_at: d.created_at?.toDate?.()?.toISOString?.() ?? d.created_at ?? "",
          };
        })
        .filter((m) => m.conversation_id === selectedConv.id)
        .sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
      setMessages(items);
    });
    return () => unsub();
  }, [selectedConv, bundle?.db, config?.firestore?.collections?.gc_messages]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Mark as read when opening a conversation
  useEffect(() => {
    if (!selectedConv || !bundle?.auth) return;
    sendJson(bundle.auth, `/api/gc/mark-read/${selectedConv.id}`, {}).catch(() => {});
  }, [selectedConv, bundle?.auth]);

  const openConversation = useCallback((conv: GcConversation) => {
    setSelectedConv(conv);
    setView("chat");
    setMessages([]);
  }, []);

  const goBack = useCallback(() => {
    setView("conversations");
    setSelectedConv(null);
    setMessages([]);
    setDraft("");
  }, []);

  const handleSend = useCallback(async (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || !selectedConv || busy || !bundle?.auth) return;
    setBusy(true);
    try {
      await sendJson(bundle.auth, "/api/gc/send", {
        conversation_id: selectedConv.id,
        content: draft.trim(),
      });
      setDraft("");
      inputRef.current?.focus();
    } catch {
      // Error handled silently — message won't appear in list
    } finally {
      setBusy(false);
    }
  }, [draft, selectedConv, busy, bundle?.auth]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }, [handleSend]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: PointerEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Delay to avoid closing on the same click that opened
    const timer = setTimeout(() => window.addEventListener("pointerdown", handler), 100);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("pointerdown", handler);
    };
  }, [open, onClose]);

  const getUnread = (conv: GcConversation) => {
    return conv.unread_count?.[userEmail] || 0;
  };

  const totalUnread = conversations.reduce((sum, c) => sum + getUnread(c), 0);

  const formatTime = (iso?: string) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) {
        return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
      }
      return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
    } catch { return ""; }
  };

  if (!open) return null;

  return (
    <div className={`gc-panel ${open ? "gc-panel--open" : ""}`} ref={panelRef}>
      {/* Header */}
      <div className="gc-panel__header">
        {view === "chat" && (
          <button className="gc-panel__back" onClick={goBack} title="Voltar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18"><polyline points="15 18 9 12 15 6" /></svg>
          </button>
        )}
        <h3 className="gc-panel__title">
          {view === "conversations" ? "Chat Interno" : selectedConv?.space_name || "Conversa"}
        </h3>
        <button className="gc-panel__close" onClick={onClose} title="Fechar"><CloseIcon /></button>
      </div>

      {/* Conversations list */}
      {view === "conversations" && (
        <div className="gc-panel__list">
          {loading && <div className="gc-panel__empty">Carregando...</div>}
          {!loading && conversations.length === 0 && (
            <div className="gc-panel__empty">
              Nenhuma conversa ainda.<br />
              Adicione o bot Hubloc CRM a um space no Google Chat.
            </div>
          )}
          {conversations.map((conv) => {
            const unread = getUnread(conv);
            return (
              <button key={conv.id} className="gc-conv-item" onClick={() => openConversation(conv)}>
                <div className="gc-conv-item__avatar">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="24" height="24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                </div>
                <div className="gc-conv-item__body">
                  <span className="gc-conv-item__name">{conv.space_name}</span>
                  <span className="gc-conv-item__preview">{conv.last_message || "Sem mensagens"}</span>
                </div>
                <div className="gc-conv-item__meta">
                  <span className="gc-conv-item__time">{formatTime(conv.last_message_at)}</span>
                  {unread > 0 && <span className="gc-conv-item__badge">{unread > 99 ? "99+" : unread}</span>}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Chat view */}
      {view === "chat" && selectedConv && (
        <>
          <div className="gc-panel__messages">
            {messages.length === 0 && <div className="gc-panel__empty">Nenhuma mensagem ainda.</div>}
            {messages.map((msg) => {
              const isMe = msg.source === "crm" || msg.sender_email === userEmail;
              return (
                <div key={msg.id} className={`gc-msg ${isMe ? "gc-msg--out" : "gc-msg--in"}`}>
                  {!isMe && <span className="gc-msg__sender">{msg.sender_name}</span>}
                  {msg.msg_type === "audio" && msg.media_path ? (
                    <audio controls src={msg.media_path} className="gc-msg__audio" />
                  ) : msg.msg_type === "image" && msg.media_path ? (
                    <img src={msg.media_path} alt="" className="gc-msg__image" />
                  ) : (
                    <span className="gc-msg__text">{msg.content}</span>
                  )}
                  <span className="gc-msg__time">{formatTime(msg.created_at)}</span>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          <form className="gc-panel__composer" onSubmit={(e) => void handleSend(e)}>
            <textarea
              ref={inputRef}
              className="gc-panel__input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Digite uma mensagem..."
              rows={1}
              disabled={busy}
            />
            <button type="submit" className="gc-panel__send" disabled={busy || !draft.trim()} title="Enviar">
              <SendIcon />
            </button>
          </form>
        </>
      )}
    </div>
  );
}

// Badge icon for TopBar
export function GcBadgeIcon({ totalUnread }: { totalUnread: number }) {
  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
      {totalUnread > 0 && (
        <span className="gc-topbar-badge">{totalUnread > 99 ? "99+" : totalUnread}</span>
      )}
    </span>
  );
}
```

## frontend/src/components/icons/index.tsx

```tsx
export function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  );
}

export function AddressBookIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M3 8h2M3 12h2M3 16h2" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="11" cy="11" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M7.5 17c.7-1.9 2-2.9 3.5-2.9s2.8 1 3.5 2.9" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function PhotoIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5v9A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-9Z" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="9" cy="10" r="1.5" fill="currentColor" />
      <path d="m8 16 3.2-3.2a1.2 1.2 0 0 1 1.7 0l1.1 1.1a1.2 1.2 0 0 0 1.7 0l.3-.3a1.2 1.2 0 0 1 1.7 0L20 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="3.5" width="6" height="11" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3.5M8.5 20.5h7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 19 20 12 4 5l2.7 7L4 19Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M6.7 12H20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3a7 7 0 0 0 9.79 9.79Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M16.5 16.5 21 21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function DotsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="5" r="1.5" fill="currentColor" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" />
      <circle cx="12" cy="19" r="1.5" fill="currentColor" />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function VideoIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2" y="7" width="14" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="m16 10 5-3v10l-5-3V10Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

export function FileIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M14 2v6h6M8 13h8M8 17h5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function MapPinIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="9" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
```

## scripts/_check_meta_full_status.py

```python
"""Diagnostico Meta-side completo: WABA + phones + subscribed_apps + app webhook."""
import json
import os
import urllib.error
import urllib.request

from firestore_common import collection_name, get_firestore_client


def graph_get(path, token, params=None):
    qs = "?access_token=" + token
    if params:
        for k, v in params.items():
            qs += "&{}={}".format(k, v)
    url = "https://graph.facebook.com/v22.0/{}{}".format(path, qs)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return {"_error": json.loads(body), "_status": e.code}
        except Exception:
            return {"_error_raw": body, "_status": e.code}


c = get_firestore_client()
channel = None
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    if data.get("channel_type") == "coexistence":
        channel = data
        break

if not channel:
    print("Sem canal coexistence.")
    raise SystemExit(1)

waba = channel["waba_id"]
phone_id = channel["phone_number_id"]
token = channel["access_token"]
print("Canal #{} | WABA={} | phone_id={} | webhook_sub={}".format(
    channel.get("id"), waba, phone_id, channel.get("webhook_subscribed")))
print()

print("=== GET /WABA?fields=id,name,timezone_id,account_review_status ===")
r = graph_get(waba, token, {"fields": "id,name,timezone_id,account_review_status,business_verification_status,country,creation_time"})
print(json.dumps(r, indent=2)[:1000])
print()

print("=== GET /WABA/subscribed_apps ===")
r = graph_get("{}/subscribed_apps".format(waba), token)
print(json.dumps(r, indent=2)[:1500])
print()

print("=== GET /phone_id?fields=... (sem smb_app_data) ===")
r = graph_get(phone_id, token, {
    "fields": "id,display_phone_number,verified_name,platform_type,quality_rating,status,code_verification_status,is_official_business_account,name_status,messaging_limit_tier",
})
print(json.dumps(r, indent=2)[:1500])
print()

# Tentar campos alternativos pra coexistence
print("=== GET /phone_id?fields=throughput,account_mode,certificate ===")
r = graph_get(phone_id, token, {"fields": "throughput,account_mode,certificate,health_status"})
print(json.dumps(r, indent=2)[:800])
print()

# App-level subscriptions (precisa app_token)
app_id = os.getenv("META_APP_ID", "1434723791183375")
app_secret = os.getenv("META_APP_SECRET", "")
if app_secret:
    print("=== GET /APP/subscriptions (com app_access_token) ===")
    app_token = "{}|{}".format(app_id, app_secret)
    r = graph_get("{}/subscriptions".format(app_id), app_token)
    print(json.dumps(r, indent=2)[:2000])
else:
    print("META_APP_SECRET nao no env — pula app subscriptions check.")
```

## scripts/_check_meta_subscription.py

```python
"""Verifica via Graph API se o app esta subscrito na WABA."""
import os
import urllib.request
import urllib.error
import json

from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()

channel = None
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    if data.get("channel_type") == "coexistence":
        channel = data
        break

if not channel:
    print("Nenhum canal coexistence encontrado.")
    raise SystemExit(1)

waba_id = channel.get("waba_id")
token = channel.get("access_token")
print("WABA: {} (canal #{})".format(waba_id, channel.get("id")))

url = "https://graph.facebook.com/v22.0/{}/subscribed_apps?fields=whatsapp_business_api_data,subscribed_fields,override_callback_uri&access_token={}".format(waba_id, token)
try:
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        apps = data.get("data", [])
        print("Apps subscribed: {}".format(len(apps)))
        for app in apps:
            wa_app = app.get("whatsapp_business_api_data", {})
            print("  app_id={} link={} fields={}".format(
                wa_app.get("id"),
                wa_app.get("link"),
                app.get("subscribed_fields") or app.get("override_callback_uri"),
            ))
            print("  full_app: {}".format(json.dumps(app, indent=2)[:600]))
except urllib.error.HTTPError as e:
    print("HTTP {}".format(e.code))
    err_body = e.read().decode("utf-8", errors="replace")
    print("  body: {}".format(err_body[:400]))
except Exception as e:
    print("Erro: {}".format(e))
```

## scripts/_delete_orphan_conversations.py

```python
"""Apaga wa_conversations e wa_messages cujo channel_id aponta para
um canal que nao existe mais (canal deletado).

Uso:
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._delete_orphan_conversations
  ./.venv/Scripts/python.exe -m scripts._delete_orphan_conversations --confirm
"""
import argparse
import sys

from firestore_common import get_firestore_client, collection_name


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant-id", default="hubloc")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    c = get_firestore_client()
    tenant_root = c.collection(collection_name("tenants")).document(args.tenant_id)

    existing_channel_ids = set()
    for d in c.collection(collection_name("channels")).stream():
        data = d.to_dict() or {}
        existing_channel_ids.add(data.get("id"))
    print(f"Canais existentes (flat): {sorted(existing_channel_ids)}")

    convs_to_delete = []
    msgs_to_delete_by_conv = {}

    for d in tenant_root.collection("wa_conversations").stream():
        data = d.to_dict() or {}
        ch = data.get("channel_id")
        if ch not in existing_channel_ids:
            convs_to_delete.append((d.id, ch, data.get("wa_id")))

    for cid, ch, wa in convs_to_delete:
        msgs = list(
            tenant_root.collection("wa_messages")
            .where("conversation_id", "==", cid)
            .stream()
        )
        if msgs:
            msgs_to_delete_by_conv[cid] = [m.id for m in msgs]

    print()
    print(f"=== Conversations orfas (channel deletado) ===")
    for cid, ch, wa in convs_to_delete:
        n_msgs = len(msgs_to_delete_by_conv.get(cid, []))
        print(f"  conv_id={cid} (channel_id={ch}, wa_id={wa}, msgs={n_msgs})")
    if not convs_to_delete:
        print("  (nenhuma — nada a fazer)")
        return 0

    if not args.confirm:
        print()
        print("DRY-RUN. Adicione --confirm para executar.")
        return 0

    print()
    print("=== Executando ===")
    for cid, _, _ in convs_to_delete:
        for mid in msgs_to_delete_by_conv.get(cid, []):
            tenant_root.collection("wa_messages").document(mid).delete()
        n_msgs = len(msgs_to_delete_by_conv.get(cid, []))
        tenant_root.collection("wa_conversations").document(cid).delete()
        print(f"  deletada conv_id={cid} (+{n_msgs} mensagens)")

    print()
    print("Limpeza concluida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## scripts/_diag_channels_prod.py

```python
"""Diagnostico rapido de canais e phone_routing em prod.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._diag_channels_prod
"""
import os
from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()

print("=== Canais flat castro_crm_channels (full) ===")
for d in c.collection(collection_name("channels")).stream():
    data = d.to_dict() or {}
    print(
        "doc_id={} id={} type={} phone_id={} waba={} platform={} display={} owner_uid={} expires={} created={} updated={} webhook_sub={}".format(
            d.id,
            data.get("id"),
            data.get("channel_type"),
            data.get("phone_number_id"),
            data.get("waba_id"),
            data.get("platform_type"),
            data.get("display_phone_number"),
            data.get("owner_user_id"),
            data.get("token_expires_at"),
            data.get("created_at"),
            data.get("updated_at"),
            data.get("webhook_subscribed"),
        )
    )

print()
print("=== phone_routing flat ===")
for d in c.collection(collection_name("phone_routing")).stream():
    data = d.to_dict() or {}
    print(
        "phone_id={} -> tenant={} channel_id={}".format(
            d.id, data.get("tenant_id"), data.get("channel_id")
        )
    )

print()
print("=== wa_conversations em tenants/hubloc (amostra) ===")
convs = list(
    c.collection(collection_name("tenants"))
    .document("hubloc")
    .collection("wa_conversations")
    .limit(20)
    .stream()
)
print("count_amostra={}".format(len(convs)))
for d in convs[:5]:
    data = d.to_dict() or {}
    print(
        "id={} channel={} wa_id={} last={}".format(
            d.id,
            data.get("channel_id"),
            data.get("wa_id"),
            data.get("last_message_at"),
        )
    )

print()
print("=== wa_messages em tenants/hubloc (count amostra ate 50) ===")
msgs = list(
    c.collection(collection_name("tenants"))
    .document("hubloc")
    .collection("wa_messages")
    .limit(50)
    .stream()
)
print("count_amostra={}".format(len(msgs)))
```

## scripts/_diag_send_state.py

```python
"""Diagnostico do estado pra debug do send error."""
import os
from firestore_common import get_firestore_client, collection_name

c = get_firestore_client()
hub = c.collection(collection_name("tenants")).document("hubloc")

print("=== contact wa_id=5531983440484 ===")
for d in hub.collection("wa_contacts").where("wa_id", "==", "5531983440484").stream():
    data = d.to_dict() or {}
    keys = ["id", "channel_id", "phone_number_id", "wa_id",
            "display_name", "source_channel_type"]
    for k in keys:
        print("  {}={}".format(k, data.get(k)))

print()
print("=== conversations wa_id=5531983440484 ===")
for d in hub.collection("wa_conversations").where("wa_id", "==", "5531983440484").stream():
    data = d.to_dict() or {}
    print("  conv_id={} contact={} channel={} phone={} src={}".format(
        d.id,
        data.get("contact_id"),
        data.get("channel_id"),
        data.get("phone_number_id"),
        data.get("source_channel_type"),
    ))

print()
print("=== _meta counters global ===")
doc = c.collection("castro_crm__meta").document("counters").get()
print("  {}".format(doc.to_dict()))
```

## scripts/build_sistema_completo.py

```python
#!/usr/bin/env python3
"""Gera SISTEMA_COMPLETO.md — dump unificado do codigo-fonte do projeto.

Varre o repositorio e concatena os arquivos de codigo em um unico Markdown
com sumario clicavel, para que humanos e agentes possam ler tudo de uma vez.

Uso:
    python scripts/build_sistema_completo.py

Pode ser rodado de qualquer diretorio — resolve caminhos relativo a si mesmo.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "SISTEMA_COMPLETO.md"

# Diretorios ignorados em qualquer nivel da arvore.
EXCLUDE_DIRS = {
    "docs",
    "node_modules",
    ".venv",
    "venv",
    "frontend_dist",
    "dist",
    "build",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
}

# Arquivos ignorados por nome exato (basename).
EXCLUDE_FILES = {
    ".env",
    "package-lock.json",
    "SISTEMA_COMPLETO.md",
    "CLAUDE.md",
    ".DS_Store",
    ".gitignore",
    ".dockerignore",
    ".gcloudignore",
}

# Extensao -> linguagem do fence Markdown.
LANG_BY_EXT = {
    ".py": "python",
    ".ts": "ts",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".ps1": "powershell",
    ".rules": "",
    ".txt": "text",
    ".toml": "toml",
    ".ini": "ini",
    ".sql": "sql",
}

# Nomes especiais (sem extensao ou com convencao propria).
LANG_BY_NAME = {
    "Dockerfile": "dockerfile",
    ".env.example": "bash",
    "firebase.json": "json",
}

# Prioridade de categorias dentro de cada diretorio (menor = primeiro).
# Configs/infra antes de codigo; codigo antes de testes.
CATEGORY_PRIORITY: dict[str, int] = {
    # Infra / configuracao
    ".env.example": 0,
    "Dockerfile": 1,
    "docker-compose.yml": 2,
    "requirements.txt": 3,
    "package.json": 3,
    "tsconfig.json": 4,
    "tsconfig.app.json": 4,
    "tsconfig.node.json": 4,
    "vite.config.ts": 5,
    "firebase.json": 6,
    "firestore.indexes.json": 7,
    "firestore.rules": 8,
    "storage.rules": 9,
    "deploy.ps1": 10,
    "deploy.sh": 11,
    "start.example.ps1": 12,
    "index.html": 13,
}

# Prioridade por extensao (fallback quando o nome nao esta no mapa acima).
EXT_PRIORITY: dict[str, int] = {
    ".json": 20,
    ".yml": 21,
    ".yaml": 21,
    ".rules": 22,
    ".html": 23,
    ".css": 24,
    ".ps1": 25,
    ".sh": 26,
    ".txt": 27,
    ".py": 40,
    ".ts": 50,
    ".tsx": 51,
    ".js": 52,
    ".jsx": 53,
    ".md": 80,
}


def get_lang(path: Path) -> str | None:
    """Retorna a tag de linguagem para o fence; None se o arquivo deve ser ignorado."""
    if path.name in LANG_BY_NAME:
        return LANG_BY_NAME[path.name]
    ext = path.suffix.lower()
    if ext in LANG_BY_EXT:
        return LANG_BY_EXT[ext]
    return None


def slugify(rel: str) -> str:
    """Gera ancora estilo GitHub-friendly compativel com o formato existente."""
    s = rel.lower().replace("\\", "/")
    # Remove barras e pontos; preserva hifen/underscore.
    out = []
    for ch in s:
        if ch in ("/", "."):
            continue
        out.append(ch)
    return "".join(out)


def sort_key(path: Path) -> tuple:
    """Ordem: raiz primeiro, depois subdirs alfabeticos; dentro de cada nivel,
    configs antes de codigo, depois nome."""
    rel = path.relative_to(ROOT)
    parts = rel.parts
    # Top-level bucket: "" para raiz, nome do dir caso contrario.
    top = "" if len(parts) == 1 else parts[0]
    cat = CATEGORY_PRIORITY.get(
        path.name,
        EXT_PRIORITY.get(path.suffix.lower(), 99),
    )
    # Dentro do mesmo top-level e categoria, ordenar por profundidade e nome.
    return (top, cat, len(parts), str(rel).lower())


def collect_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if get_lang(path) is None:
            continue
        files.append(path)
    files.sort(key=sort_key)
    return files


def render(files: list[Path]) -> str:
    rels = [str(p.relative_to(ROOT)).replace("\\", "/") for p in files]

    out: list[str] = []
    out.append("# Hubloc / Castro Intelligence — Sistema Completo")
    out.append("")
    out.append("Codigo-fonte completo do projeto (backend Python + frontend React/TS + configs).")
    out.append(
        "Exclui: `docs/`, `node_modules/`, `.venv/`, `frontend_dist/`, "
        "`__pycache__/`, `.env`, `package-lock.json`, `CLAUDE.md`."
    )
    out.append("")
    out.append("Gerado por `scripts/build_sistema_completo.py`. Nao editar a mao.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## Sumario")
    out.append("")
    for rel in rels:
        out.append(f"- [{rel}](#{slugify(rel)})")
    out.append("")
    out.append("---")
    out.append("")

    for path, rel in zip(files, rels):
        lang = get_lang(path) or ""
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
        # Garante newline final unica.
        content = content.rstrip("\n")
        out.append(f"## {rel}")
        out.append("")
        out.append(f"```{lang}")
        out.append(content)
        out.append("```")
        out.append("")

    return "\n".join(out) + "\n"


def main() -> None:
    files = collect_files()
    text = render(files)
    OUTPUT.write_text(text, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"OK: {OUTPUT.relative_to(ROOT)} ({len(files)} arquivos, {size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
```

## scripts/create_test_users.py

```python
# -*- coding: utf-8 -*-
"""
Cria 4 usuarios de teste no Firebase Auth via Admin SDK.

Uso:
    cd castro-intelligence
    python -m scripts.create_test_users

Requisitos:
    - Provider Email/Password ativado no Firebase Console
    - Credenciais: ou GOOGLE_APPLICATION_CREDENTIALS apontando para uma service account
      do projeto, ou `gcloud auth application-default login` ja executado.

Para remover depois, rode com --delete.
"""

import sys
from pathlib import Path

# Permite rodar de dentro de castro-intelligence/ sem setar PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from firebase_admin import auth

from firebase_admin_client import get_firebase_app


TEST_USERS = [
    {"email": "teste1@centralloc.com.br", "password": "teste1", "display_name": "Teste - Vendas"},
    {"email": "teste2@centralloc.com.br", "password": "teste2", "display_name": "Teste - Suporte"},
    {"email": "teste3@centralloc.com.br", "password": "teste3", "display_name": "Teste - Geral"},
    {"email": "teste4@centralloc.com.br", "password": "teste4", "display_name": "Teste - Financeiro"},
]


def create_users(app):
    for u in TEST_USERS:
        try:
            user = auth.create_user(
                email=u["email"],
                email_verified=False,
                password=u["password"],
                display_name=u["display_name"],
                disabled=False,
                app=app,
            )
            print(f"  [OK] Criado: {u['email']} (uid={user.uid})")
        except auth.EmailAlreadyExistsError:
            existing = auth.get_user_by_email(u["email"], app=app)
            auth.update_user(existing.uid, password=u["password"], display_name=u["display_name"], app=app)
            print(f"  [UPDATE] Ja existia, senha atualizada: {u['email']} (uid={existing.uid})")
        except Exception as e:
            print(f"  [ERRO] {u['email']}: {e}")


def delete_users(app):
    for u in TEST_USERS:
        try:
            existing = auth.get_user_by_email(u["email"], app=app)
            auth.delete_user(existing.uid, app=app)
            print(f"  [OK] Deletado: {u['email']}")
        except auth.UserNotFoundError:
            print(f"  [SKIP] Nao existia: {u['email']}")
        except Exception as e:
            print(f"  [ERRO] {u['email']}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Deleta os usuarios de teste")
    args = parser.parse_args()

    app = get_firebase_app()
    if args.delete:
        print("Deletando usuarios de teste...")
        delete_users(app)
    else:
        print("Criando usuarios de teste...")
        create_users(app)
    print("Done.")


if __name__ == "__main__":
    main()
```

## scripts/delete_channel.py

```python
"""Deleta um canal flat e limpa entries do phone_routing apontando pra ele.

Uso (PowerShell):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"  # ou "castro_crm_staging"
  ./.venv/Scripts/python.exe -m scripts.delete_channel --channel-id 1

Sem --confirm e que mostra o plano (dry-run). Com --confirm executa.
"""
import argparse
import sys

from firestore_common import get_firestore_client, collection_name


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel-id", type=int, required=True)
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    cid = args.channel_id
    c = get_firestore_client()

    ch_ref = c.collection(collection_name("channels")).document(str(cid))
    ch_doc = ch_ref.get()
    if not ch_doc.exists:
        print(f"Canal {cid} nao existe.")
        return 1

    ch_data = ch_doc.to_dict() or {}
    print("=== Canal a deletar ===")
    print(f"  doc_id={ch_doc.id}")
    print(f"  type={ch_data.get('channel_type')}")
    print(f"  phone_id={ch_data.get('phone_number_id')}")
    print(f"  waba={ch_data.get('waba_id')}")
    print(f"  display={ch_data.get('display_phone_number')}")
    print(f"  label={ch_data.get('label')}")

    routing_to_delete = []
    for d in c.collection(collection_name("phone_routing")).stream():
        data = d.to_dict() or {}
        if data.get("channel_id") == cid:
            routing_to_delete.append(d.id)

    print()
    print(f"=== phone_routing entries apontando pra channel_id={cid} ===")
    for pid in routing_to_delete:
        print(f"  {pid}")
    if not routing_to_delete:
        print("  (nenhuma)")

    if not args.confirm:
        print()
        print("DRY-RUN. Adicione --confirm para executar.")
        return 0

    print()
    print("=== Executando ===")
    for pid in routing_to_delete:
        c.collection(collection_name("phone_routing")).document(pid).delete()
        print(f"  phone_routing/{pid} deletado")

    ch_ref.delete()
    print(f"  channels/{cid} deletado")

    print()
    print("Pronto. Reinicie o backend (ou aguarde o cache TTL ~60s) "
          "para refletir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## scripts/e2e_test_staging.py

```python
# -*- coding: utf-8 -*-
"""
E2E test do cenario multi-tenant + sub-threads no staging.

Executa, em sequencia:
  1. Wipe das colecoes do tenant hubloc + canais fake (mantem channel id=1).
  2. Cria 2 canais fictícios (id=100 standard, id=200 coexistence) com
     phone_number_ids unicos.
  3. Aguarda 70s para o cache de canais reciclar no servico Cloud Run.
  4. Dispara 4 webhooks Meta-shape para o staging:
       - canal 100, wa_id X, msg "Oi do Cloud API"
       - canal 200, wa_id X, msg "Oi do coexistence" (mesmo cliente!)
       - canal 100, wa_id X, msg "segunda no Cloud API"
       - canal 200, wa_id Y (cliente diferente), msg "outro cliente"
  5. Le Firestore e valida:
       - 2 contatos (X e Y)
       - 3 conversations: 100__X, 200__X, 200__Y
       - 4 mensagens, cada uma com conversation_id correto
  6. (Cutover Fase 2C) Loga como BOOTSTRAP_ADMIN_EMAIL e exercita
     POST /api/wa/conversation/{id}/read sobre a thread 100__X.
     Valida que unread_count zera so dela; threads 200__X e 200__Y
     mantem unread; mensagens inbound da thread 100 ficam status=read,
     enquanto inbound da 200 permanece received.
  7. (Cutover Fase 2C) POST /api/wa/send com conversation_id inexistente
     espera HTTP 404 — prova que _resolve_send_target rejeita antes da
     chamada Meta (caminho feliz nao testado: tokens dos canais sao fake
     e a Graph API recusaria).
  8. (Fase 2.10.4) Valida usage_{YYYY_MM} per-tenant: le o doc Firestore
     em tenants/hubloc/audit_metrics/usage_{YYYY-MM} e tambem o endpoint
     GET /api/wa/usage/current-month. Confirma inbound_received >= 4
     (4 webhooks disparados no passo 4) e estrutura de retorno.
  9. (Fase 2.10.3) POST /api/internal/cron/health-check com header
     X-Cron-Secret. Itera tenants ativos, grava
     tenants/{tid}/health_status/current. Valida que doc do hubloc tem
     channels_total >= 2 (canais e2e 100/200) e per_channel populado.
  10. Imprime relatorio.

Uso (local com gcloud auth ja configurado):
    python -m scripts.e2e_test_staging

Variaveis de ambiente necessarias:
    FIRESTORE_PROJECT_ID         (default: project-26fb9c99-8ee9-4179-aef)
    FIRESTORE_COLLECTION_PREFIX  (default: castro_crm_staging)
    STAGING_URL                  (default: castro-crm-staging URL)
    WHATSAPP_APP_SECRET          (lido do GCP Secret Manager se ausente)
    FIREBASE_WEB_API_KEY         (lido do Cloud Run env se ausente)
    BOOTSTRAP_ADMIN_EMAIL        (lido do Cloud Run env se ausente)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

os.environ.setdefault("FIRESTORE_PROJECT_ID", "project-26fb9c99-8ee9-4179-aef")
os.environ.setdefault("FIRESTORE_COLLECTION_PREFIX", "castro_crm_staging")

STAGING_URL = os.environ.get(
    "STAGING_URL",
    "https://castro-crm-staging-286866630844.southamerica-east1.run.app",
)


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# ---------------------------------------------------------------------------
# Secret loader (Cloud Run usa GCP Secret Manager)
# ---------------------------------------------------------------------------

def get_app_secret() -> str:
    """Le WHATSAPP_APP_SECRET do GCP (mesmo do Cloud Run staging)."""
    cached = os.environ.get("WHATSAPP_APP_SECRET")
    if cached:
        return cached
    cmd = [
        "gcloud", "secrets", "versions", "access", "latest",
        "--secret=castro-crm-whatsapp-app-secret",
        "--project", os.environ["FIRESTORE_PROJECT_ID"],
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(f"Falha ao ler secret: {out.stderr}")
    return out.stdout.strip()


# ---------------------------------------------------------------------------
# Cloud Run env reader (para FIREBASE_WEB_API_KEY, BOOTSTRAP_ADMIN_EMAIL etc)
# ---------------------------------------------------------------------------

_cloud_run_env_cache: dict[str, str] | None = None


def _read_cloud_run_env() -> dict[str, str]:
    """Le todas as env vars do servico castro-crm-staging via gcloud.

    Resolve `valueFrom.secretKeyRef` chamando `gcloud secrets versions
    access` (caso o env tenha sido configurado via --update-secrets).
    Requer `roles/secretmanager.secretAccessor` no usuario corrente."""
    global _cloud_run_env_cache
    if _cloud_run_env_cache is not None:
        return _cloud_run_env_cache
    cmd = [
        "gcloud", "run", "services", "describe", "castro-crm-staging",
        "--region", "southamerica-east1",
        "--project", os.environ["FIRESTORE_PROJECT_ID"],
        "--format", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        _cloud_run_env_cache = {}
        return _cloud_run_env_cache
    try:
        data = json.loads(out.stdout)
        containers = (data.get("spec", {}).get("template", {}).get("spec", {})
                          .get("containers", []) or [])
        env_list = (containers[0].get("env", []) if containers else []) or []
        resolved: dict[str, str] = {}
        for e in env_list:
            name = e.get("name")
            if not name:
                continue
            v = e.get("value", "")
            if v:
                resolved[name] = v
                continue
            ref = (e.get("valueFrom") or {}).get("secretKeyRef") or {}
            secret_name = ref.get("name", "")
            secret_key = ref.get("key", "latest") or "latest"
            if not secret_name:
                continue
            try:
                cmd2 = [
                    "gcloud", "secrets", "versions", "access", secret_key,
                    f"--secret={secret_name}",
                    "--project", os.environ["FIRESTORE_PROJECT_ID"],
                ]
                out2 = subprocess.run(cmd2, capture_output=True, text=True, shell=True)
                if out2.returncode == 0:
                    resolved[name] = out2.stdout.rstrip("\n")
            except Exception:
                pass
        _cloud_run_env_cache = resolved
    except Exception:
        _cloud_run_env_cache = {}
    return _cloud_run_env_cache


def get_env_or_cloud_run(name: str) -> str:
    cached = os.environ.get(name, "").strip()
    if cached:
        return cached
    return (_read_cloud_run_env().get(name) or "").strip()


# ---------------------------------------------------------------------------
# Auth helper — admin idToken via Firebase custom token + REST exchange
# ---------------------------------------------------------------------------

_E2E_SIGNER_SA = (
    "castro-crm-run@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com"
)


def mint_admin_id_token() -> tuple[str, str] | None:
    """Retorna (id_token, admin_email) ou None se auth nao pode ser
    estabelecida (skip com warning amarelo nos passos 6-7).

    Cria custom token assinado pela SA do Cloud Run staging (precisa
    iam.serviceAccountTokenCreator no usuario corrente) e troca por
    idToken via REST. Evita BOOTSTRAP_ADMIN_PASSWORD (que nao existe —
    admin loga via Google SSO)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import firebase_admin
    from firebase_admin import auth as fb_auth, credentials as fb_credentials

    api_key = get_env_or_cloud_run("FIREBASE_WEB_API_KEY")
    if not api_key:
        print(_yellow("  [skip] FIREBASE_WEB_API_KEY indisponivel"))
        return None
    admin_email = get_env_or_cloud_run("BOOTSTRAP_ADMIN_EMAIL")
    if not admin_email:
        print(_yellow("  [skip] BOOTSTRAP_ADMIN_EMAIL indisponivel"))
        return None

    try:
        e2e_app = firebase_admin.get_app("e2e_signer")
    except ValueError:
        e2e_app = firebase_admin.initialize_app(
            credential=fb_credentials.ApplicationDefault(),
            options={
                "projectId": os.environ["FIRESTORE_PROJECT_ID"],
                "serviceAccountId": _E2E_SIGNER_SA,
            },
            name="e2e_signer",
        )

    try:
        user = fb_auth.get_user_by_email(admin_email, app=e2e_app)
    except Exception as exc:
        print(_yellow(f"  [skip] get_user_by_email falhou: {exc}"))
        return None
    try:
        custom_token = fb_auth.create_custom_token(
            user.uid,
            developer_claims={"tenant_id": "hubloc"},
            app=e2e_app,
        )
    except Exception as exc:
        print(_yellow(
            f"  [skip] create_custom_token falhou: {exc}\n"
            "         (usuario corrente precisa de roles/iam.serviceAccountTokenCreator "
            f"em {_E2E_SIGNER_SA})"
        ))
        return None
    if isinstance(custom_token, bytes):
        custom_token = custom_token.decode("utf-8")

    url = (
        "https://identitytoolkit.googleapis.com/v1/accounts:"
        f"signInWithCustomToken?key={api_key}"
    )
    body = json.dumps({"token": custom_token, "returnSecureToken": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(_yellow(
            f"  [skip] signInWithCustomToken falhou: {e.code} "
            f"{e.read().decode('utf-8', 'ignore')}"
        ))
        return None
    return payload["idToken"], admin_email


def http_post_authed(path: str, id_token: str, body: dict | None = None) -> tuple[int, dict | str]:
    url = STAGING_URL + path
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def http_get_authed(path: str, id_token: str) -> tuple[int, dict | str]:
    url = STAGING_URL + path
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": f"Bearer {id_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def http_post_cron(path: str, cron_secret: str, body: dict | None = None) -> tuple[int, dict | str]:
    """POST sem Firebase auth, com header X-Cron-Secret (Fase 2.10.3)."""
    url = STAGING_URL + path
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Cron-Secret": cron_secret,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


# ---------------------------------------------------------------------------
# Firestore helpers (lazy import — depende do path)
# ---------------------------------------------------------------------------

def get_clients():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from firestore_common import (
        _flat_collection,
        _flat_document,
        collection_name,
        get_firestore_client,
        utcnow,
    )
    return {
        "client": get_firestore_client(),
        "flat_coll": _flat_collection,
        "flat_doc": _flat_document,
        "coll_name": collection_name,
        "utcnow": utcnow,
    }


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_wipe(c) -> None:
    print(_bold("\n[1/9] Wipe do tenant hubloc + canais fake"))
    client = c["client"]
    coll_name = c["coll_name"]
    utcnow = c["utcnow"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    counts = {
        "contacts": 0, "conversations": 0, "messages": 0,
        "transfer_log": 0, "channels_fake": 0, "usage_current_month": 0,
    }

    for sub in ("wa_contacts", "wa_conversations", "wa_messages", "wa_transfer_log"):
        for snap in hubloc.collection(sub).stream():
            snap.reference.delete()
            counts[sub.replace("wa_", "")] = counts.get(sub.replace("wa_", ""), 0) + 1

    # Apaga canais fake (id != 1) na coleção flat
    for snap in c["flat_coll"]("channels").stream():
        data = snap.to_dict() or {}
        if data.get("id") != 1:
            snap.reference.delete()
            counts["channels_fake"] += 1

    # Limpa apenas usage_{YYYY_MM} do mes corrente (Fase 2.10.4) pra
    # garantir contagem deterministica do passo 8. Daily docs (usados
    # pelo dashboard de auditoria existente) sao preservados.
    year_month = utcnow().strftime("%Y-%m")
    try:
        usage_ref = hubloc.collection("audit_metrics").document(f"usage_{year_month}")
        if usage_ref.get().exists:
            usage_ref.delete()
            counts["usage_current_month"] = 1
    except Exception as exc:
        print(f"  aviso: falha ao limpar usage_{year_month}: {exc}")

    for k, v in counts.items():
        print(f"  removidos {k}: {v}")
    print(_green("  ✓ wipe completo"))


def step_create_channels(c) -> None:
    print(_bold("\n[2/9] Criando 2 canais ficticios para teste"))
    utcnow = c["utcnow"]
    flat_doc = c["flat_doc"]

    flat_doc("channels", 100).set({
        "id": 100,
        "channel_type": "standard",
        "label": "E2E Cloud API Test",
        "waba_id": "e2e_test_waba_standard",
        "phone_number_id": "e2e_phone_100",
        "display_phone_number": "+55 31 1000-0100",
        "access_token": "FAKE_TOKEN_E2E_100",
        "owner_user_id": None,
        "owner_firebase_uid": "",
        "is_active": True,
        "is_bot_enabled": True,
        "webhook_subscribed": True,
        "platform_type": "CLOUD_API",
        "verified_name": "E2E Standard",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    })
    print(f"  ✓ canal id=100 standard phone_id=e2e_phone_100")

    flat_doc("channels", 200).set({
        "id": 200,
        "channel_type": "coexistence",
        "label": "E2E Coexistence Test",
        "waba_id": "e2e_test_waba_coex",
        "phone_number_id": "e2e_phone_200",
        "display_phone_number": "+55 31 2000-0200",
        "access_token": "FAKE_TOKEN_E2E_200",
        "owner_user_id": None,
        "owner_firebase_uid": "",
        "is_active": True,
        "is_bot_enabled": False,
        "webhook_subscribed": True,
        "platform_type": "WHATSAPP",
        "verified_name": "E2E Coexistence",
        "created_at": utcnow(),
        "updated_at": utcnow(),
    })
    print(f"  ✓ canal id=200 coexistence phone_id=e2e_phone_200")
    print(_green("  ✓ canais criados"))


def step_wait_cache():
    print(_bold("\n[3/9] Aguardando 70s para cache de canais reciclar no Cloud Run"))
    print(f"  cache TTL = 60s; aguardamos um pouco a mais...")
    for remaining in range(70, 0, -10):
        print(f"  {remaining}s...", end="\r")
        time.sleep(10)
    print(_green("  ✓ cache reciclado"))


def post_webhook(secret: str, payload: dict) -> int:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        STAGING_URL + "/webhook",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def make_payload(phone_number_id: str, wa_id: str, profile_name: str, msg_id: str, text: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "e2e_test_waba",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "+55310000",
                        "phone_number_id": phone_number_id,
                    },
                    "contacts": [{
                        "profile": {"name": profile_name},
                        "wa_id": wa_id,
                    }],
                    "messages": [{
                        "from": wa_id,
                        "id": msg_id,
                        "timestamp": str(int(time.time())),
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
            }],
        }],
    }


def step_send_webhooks(secret: str) -> None:
    print(_bold("\n[4/9] Disparando 4 webhooks Meta-shape"))
    wa_x = "5531777771111"
    wa_y = "5531777772222"

    cases = [
        ("e2e_phone_100", wa_x, "Cliente E2E X", "wamid.e2e_X_std_1", "Oi do Cloud API standard"),
        ("e2e_phone_200", wa_x, "Cliente E2E X", "wamid.e2e_X_coex_1", "Oi do canal coexistence"),
        ("e2e_phone_100", wa_x, "Cliente E2E X", "wamid.e2e_X_std_2", "segunda mensagem no Cloud API"),
        ("e2e_phone_200", wa_y, "Cliente E2E Y", "wamid.e2e_Y_coex_1", "cliente Y, canal coexistence"),
    ]

    for phone_id, wa, name, msg_id, text in cases:
        payload = make_payload(phone_id, wa, name, msg_id, text)
        status = post_webhook(secret, payload)
        ok = status == 200
        marker = _green("✓") if ok else _red("✗")
        print(f"  {marker} {phone_id} <- {wa} ({name}) status={status}")
        if not ok:
            print(_red(f"    payload: {json.dumps(payload)}"))
    print(_green("  ✓ webhooks enviados"))


def step_verify(c) -> int:
    print(_bold("\n[5/9] Verificando estado final dos webhooks no Firestore"))
    coll_name = c["coll_name"]
    client = c["client"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    contacts = list(hubloc.collection("wa_contacts").stream())
    conversations = list(hubloc.collection("wa_conversations").stream())
    messages = list(hubloc.collection("wa_messages").stream())

    contact_ids = {(s.to_dict() or {}).get("wa_id"): (s.to_dict() or {}).get("id") for s in contacts}

    print(f"  contatos:      {len(contacts)} (esperado: 2)")
    for s in contacts:
        d = s.to_dict() or {}
        print(f"    id={d.get('id')} wa_id={d.get('wa_id')} name={d.get('display_name')}")

    print(f"  conversations: {len(conversations)} (esperado: 3)")
    for s in conversations:
        d = s.to_dict() or {}
        print(f"    id={s.id} contact_id={d.get('contact_id')} channel_id={d.get('channel_id')} unread={d.get('unread_count')}")

    print(f"  mensagens:     {len(messages)} (esperado: 4)")
    for s in messages:
        d = s.to_dict() or {}
        print(f"    id={d.get('id')} channel_id={d.get('channel_id')} conversation_id={d.get('conversation_id')} content={(d.get('content') or '')[:50]}")

    # Validacao
    failures = []
    if len(contacts) != 2:
        failures.append(f"contatos esperado=2 obtido={len(contacts)}")
    if len(conversations) != 3:
        failures.append(f"conversations esperado=3 obtido={len(conversations)}")
    if len(messages) != 4:
        failures.append(f"mensagens esperado=4 obtido={len(messages)}")

    # Cada msg deve ter conversation_id no formato {channel_id}__{wa_id}
    for s in messages:
        d = s.to_dict() or {}
        ch = d.get("channel_id")
        contact_id = d.get("contact_id")
        # Buscar wa_id do contato
        wa_id = None
        for w, cid in contact_ids.items():
            if cid == contact_id:
                wa_id = w
                break
        expected_conv = f"{ch}__{wa_id}" if wa_id else None
        if d.get("conversation_id") != expected_conv:
            failures.append(f"msg {d.get('id')} conv_id={d.get('conversation_id')} esperado={expected_conv}")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1

    print(_green("  ✓ TODAS as assercoes passaram"))
    return 0


def _conv_doc(c, conv_id: str):
    coll_name = c["coll_name"]
    client = c["client"]
    return (client.collection(coll_name("tenants")).document("hubloc")
                  .collection("wa_conversations").document(conv_id).get())


def step_post_mark_read(c, id_token: str) -> int:
    """Cutover Fase 2C: POST /api/wa/conversation/{id}/read marca leitura
    de uma thread especifica e nao das outras do mesmo contato."""
    print(_bold("\n[6/9] POST /api/wa/conversation/{id}/read (cutover Fase 2C)"))
    coll_name = c["coll_name"]
    client = c["client"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    target_conv = "100__5531777771111"

    before_target = (_conv_doc(c, target_conv).to_dict() or {}).get("unread_count")
    before_other_x = (_conv_doc(c, "200__5531777771111").to_dict() or {}).get("unread_count")
    before_y = (_conv_doc(c, "200__5531777772222").to_dict() or {}).get("unread_count")
    print(f"  antes: {target_conv}.unread={before_target}, "
          f"200__X.unread={before_other_x}, 200__Y.unread={before_y}")

    status, payload = http_post_authed(f"/api/wa/conversation/{target_conv}/read", id_token)
    if status != 200:
        print(_red(f"  ✗ POST retornou {status}: {payload}"))
        return 1
    print(f"  ✓ POST status=200 payload={payload}")

    after_target = (_conv_doc(c, target_conv).to_dict() or {}).get("unread_count")
    after_other_x = (_conv_doc(c, "200__5531777771111").to_dict() or {}).get("unread_count")
    after_y = (_conv_doc(c, "200__5531777772222").to_dict() or {}).get("unread_count")
    print(f"  depois: {target_conv}.unread={after_target}, "
          f"200__X.unread={after_other_x}, 200__Y.unread={after_y}")

    failures = []
    if after_target != 0:
        failures.append(f"{target_conv}.unread esperado=0 obtido={after_target}")
    if after_other_x != before_other_x:
        failures.append(f"200__X.unread mudou (esperado {before_other_x} estavel, obtido {after_other_x})")
    if after_y != before_y:
        failures.append(f"200__Y.unread mudou (esperado {before_y} estavel, obtido {after_y})")

    # mensagens inbound da thread alvo devem estar status=read; das outras
    # threads do MESMO contato (200__X) devem manter received.
    msgs = list(hubloc.collection("wa_messages").stream())
    for s in msgs:
        d = s.to_dict() or {}
        if d.get("direction") != "inbound":
            continue
        conv = d.get("conversation_id")
        st = d.get("status")
        if conv == target_conv and st != "read":
            failures.append(f"msg {d.get('id')} ({conv}) esperado read, obtido {st}")
        if conv == "200__5531777771111" and st == "read":
            failures.append(f"msg {d.get('id')} ({conv}) virou read sem solicitacao (cross-channel leak!)")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1
    print(_green("  ✓ mark-read isolado por thread"))
    return 0


def step_post_send_validation(c, id_token: str) -> int:
    """Cutover Fase 2C: POST /api/wa/send com conversation_id inexistente
    deve retornar 404, provando que _resolve_send_target rejeita antes de
    chamar Meta. Caminho feliz nao testado (canais fake, tokens fake)."""
    print(_bold("\n[7/9] POST /api/wa/send com conversation_id invalido (cutover Fase 2C)"))

    bad_conv = "9999__inexistente"
    status, payload = http_post_authed(
        "/api/wa/send", id_token,
        {"conversation_id": bad_conv, "content": "ignored"},
    )
    print(f"  POST conversation_id={bad_conv} -> status={status}")
    if status != 404:
        print(_red(f"  ✗ esperado 404, obtido {status}: {payload}"))
        return 1

    # Tambem valida que sem nem conversation_id nem contact_id retorna 4xx
    status2, payload2 = http_post_authed(
        "/api/wa/send", id_token, {"content": "no target"},
    )
    print(f"  POST sem target -> status={status2}")
    if status2 not in (400, 422):
        print(_red(f"  ✗ esperado 400/422, obtido {status2}: {payload2}"))
        return 1

    print(_green("  ✓ _resolve_send_target rejeita antes de chegar em Meta"))
    return 0


def step_validate_usage(c, id_token: str) -> int:
    """Fase 2.10.4: usage_{YYYY_MM} per-tenant.

    Apos os 4 webhooks inbound (passo 4), espera:
      tenants/hubloc/audit_metrics/usage_{YYYY-MM}.inbound_received >= 4
    Tambem exercita GET /api/wa/usage/current-month e compara.
    """
    print(_bold("\n[8/9] Validando usage_{YYYY_MM} per-tenant (Fase 2.10.4)"))
    coll_name = c["coll_name"]
    client = c["client"]
    utcnow = c["utcnow"]
    year_month = utcnow().strftime("%Y-%m")
    doc_id = f"usage_{year_month}"
    hubloc = client.collection(coll_name("tenants")).document("hubloc")

    snap = hubloc.collection("audit_metrics").document(doc_id).get()
    if not snap.exists:
        print(_red(f"  ✗ doc {doc_id} nao existe em tenants/hubloc/audit_metrics"))
        return 1
    data = snap.to_dict() or {}
    inbound = int(data.get("inbound_received") or 0)
    free_form = int(data.get("free_form_sent") or 0)
    templates = data.get("templates_sent") or {}
    media_bytes = int(data.get("media_uploaded_bytes") or 0)
    print(f"  doc:           tenants/hubloc/audit_metrics/{doc_id}")
    print(f"  month:         {data.get('month')}")
    print(f"  inbound_received={inbound}, free_form_sent={free_form}, "
          f"media_uploaded_bytes={media_bytes}")
    print(f"  templates_sent: {templates}")

    failures = []
    if inbound < 4:
        failures.append(f"inbound_received esperado>=4 obtido={inbound}")
    elif inbound > 4:
        print(_yellow(
            f"  [warn] inbound_received={inbound} (esperado=4) — provavel "
            "trafego paralelo no staging entre wipe e e2e"
        ))
    if data.get("month") != year_month:
        failures.append(f"month esperado={year_month} obtido={data.get('month')}")

    # Tambem exercita o endpoint REST
    status, payload = http_get_authed("/api/wa/usage/current-month", id_token)
    if status != 200:
        failures.append(f"GET /api/wa/usage/current-month status={status} payload={payload}")
    else:
        api_inbound = int((payload or {}).get("inbound_received") or 0)
        if api_inbound != inbound:
            failures.append(
                f"GET retornou inbound_received={api_inbound}, Firestore={inbound}"
            )
        print(f"  GET /api/wa/usage/current-month -> 200 inbound={api_inbound}")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1
    print(_green("  ✓ usage_{YYYY_MM} consistente com webhooks disparados"))
    return 0


def step_cron_health_check(c) -> int:
    """Fase 2.10.3: cron health-check.

    POST /api/internal/cron/health-check com header X-Cron-Secret. Itera
    tenants ativos, grava tenants/{tid}/health_status/current. Valida
    estrutura do doc do hubloc apos a chamada.
    """
    print(_bold("\n[9/9] POST /api/internal/cron/health-check (Fase 2.10.3)"))
    cron_secret = get_env_or_cloud_run("INTERNAL_CRON_SECRET")
    if not cron_secret:
        print(_yellow(
            "  [skip] INTERNAL_CRON_SECRET indisponivel no Cloud Run env nem local. "
            "Defina via gcloud run services update castro-crm-staging "
            "--update-env-vars INTERNAL_CRON_SECRET=..."
        ))
        return 0  # skip nao falha

    status, payload = http_post_cron("/api/internal/cron/health-check", cron_secret)
    if status != 200:
        print(_red(f"  ✗ POST status={status} payload={payload}"))
        return 1
    print(f"  ✓ POST status=200 tenants_processed={payload.get('tenants_processed')}")
    print(f"  summary: {payload.get('summary')}")

    coll_name = c["coll_name"]
    client = c["client"]
    hubloc = client.collection(coll_name("tenants")).document("hubloc")
    snap = hubloc.collection("health_status").document("current").get()
    if not snap.exists:
        print(_red("  ✗ tenants/hubloc/health_status/current nao existe pos-cron"))
        return 1
    data = snap.to_dict() or {}
    channels_total = int(data.get("channels_total") or 0)
    per_channel = data.get("per_channel") or []
    print(f"  doc tenants/hubloc/health_status/current:")
    print(f"    channels_total={channels_total}, "
          f"channels_pending_payment={data.get('channels_pending_payment')}, "
          f"tokens_expiring_soon={data.get('tokens_expiring_soon')}")
    for ch in per_channel:
        print(f"    channel_id={ch.get('channel_id')} type={ch.get('channel_type')} "
              f"status={ch.get('payment_method_status')} error={ch.get('error') or '-'}")

    failures = []
    if channels_total < 2:
        failures.append(
            f"channels_total esperado>=2 (canais e2e 100/200) obtido={channels_total}"
        )
    if not per_channel:
        failures.append("per_channel vazio")
    if not data.get("checked_at"):
        failures.append("checked_at ausente")

    if failures:
        print(_red("  ✗ FALHAS:"))
        for f in failures:
            print(_red(f"    - {f}"))
        return 1
    print(_green("  ✓ health_status gravado com per_channel coerente"))
    return 0


def main() -> int:
    print(_bold(f"E2E test against {STAGING_URL}"))
    secret = get_app_secret()
    if not secret:
        print(_red("WHATSAPP_APP_SECRET nao disponivel"))
        return 2

    c = get_clients()
    step_wipe(c)
    step_create_channels(c)
    step_wait_cache()
    step_send_webhooks(secret)
    rc = step_verify(c)
    if rc != 0:
        print(_red(_bold("\n✗ E2E FAILED (passos 1-5)")))
        return rc

    auth = mint_admin_id_token()
    if auth is None:
        print(_yellow(_bold("\n⚠ Passos 6-7 pulados (auth indisponivel) — passos 1-5 OK")))
        print(_green(_bold("\n✓ E2E PASSED (parcial)")))
        return 0
    id_token, admin_email = auth
    print(_bold(f"\nAuth: idToken obtido para {admin_email}"))

    rc6 = step_post_mark_read(c, id_token)
    if rc6 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 6 mark-read)")))
        return rc6

    rc7 = step_post_send_validation(c, id_token)
    if rc7 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 7 send validation)")))
        return rc7

    rc8 = step_validate_usage(c, id_token)
    if rc8 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 8 usage_{YYYY_MM})")))
        return rc8

    rc9 = step_cron_health_check(c)
    if rc9 != 0:
        print(_red(_bold("\n✗ E2E FAILED (passo 9 cron health-check)")))
        return rc9

    print(_green(_bold("\n✓ E2E PASSED")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## scripts/wipe_all_collections.py

```python
# -*- coding: utf-8 -*-
"""
Wipe controlado de um tenant em ambiente staging/prod (Fase 4).

Uso:
    # Dry-run (default — nada e apagado, so mostra o plano):
    python -m scripts.wipe_all_collections --tenant-id hubloc

    # Wipe completo do tenant (preserva users/departments por default):
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm

    # Wipe total (incluindo users/operator_profiles/departments):
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm --purge-users

    # Wipe tambem os channels flat e phone_routing relacionados ao tenant:
    python -m scripts.wipe_all_collections --tenant-id hubloc --confirm --purge-channels

NUNCA apaga:
- Doc raiz tenants/{tid} (preserva nome/plano/billing/settings).
- Colecao tenants flat (lista de tenants).
- _meta global (counters cross-tenant).
- audit_log: por default e preservado tambem (LGPD: trilha de
  auditoria sobrevive ao wipe). Use --purge-audit-log se realmente
  quiser apagar.

Variaveis de ambiente:
    FIRESTORE_PROJECT_ID         (obrigatorio)
    FIRESTORE_COLLECTION_PREFIX  (obrigatorio, default castro_crm em prod)

Confirmacao de seguranca: alem de --confirm, pede que o operador
digite "WIPE" interativamente — protege contra rerun acidental em
shell history ou CI.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Callable

# Permite rodar como `python -m scripts.wipe_all_collections` ou
# `python scripts/wipe_all_collections.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firestore_common import (  # noqa: E402
    collection_name,
    get_firestore_client,
    global_collection,
    tenant_doc_ref,
)


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# Subcolecoes preservadas por default (mesmo com --confirm). User pode
# liberar via flags --purge-users / --purge-audit-log.
DEFAULT_SKIP = frozenset()
USER_PRESERVED = frozenset({"users", "operator_profiles", "departments"})
AUDIT_PRESERVED = frozenset({"audit_log"})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Wipe controlado de um tenant (Fase 4 cutover)."
    )
    p.add_argument(
        "--tenant-id", required=True,
        help="Slug do tenant a apagar (ex: hubloc).",
    )
    p.add_argument(
        "--confirm", action="store_true",
        help="Executa de fato. Sem isso, dry-run.",
    )
    p.add_argument(
        "--purge-users", action="store_true",
        help="Tambem apaga users/operator_profiles/departments. Default: preserva.",
    )
    p.add_argument(
        "--purge-audit-log", action="store_true",
        help="Tambem apaga audit_log. Default: preserva (LGPD).",
    )
    p.add_argument(
        "--purge-channels", action="store_true",
        help="Tambem apaga channels flat + phone_routing entries do tenant.",
    )
    p.add_argument(
        "--no-interactive", action="store_true",
        help="Pula confirmacao interativa 'WIPE' (uso em CI). Cuidado.",
    )
    return p.parse_args()


def discover_tenant_subcollections(tid: str) -> list[str]:
    """Lista subcolecoes que existem em tenants/{tid}/.

    Usa list_subcollections do Admin SDK — retorna apenas as que tem
    pelo menos 1 doc.
    """
    refs = list(tenant_doc_ref(tid).collections())
    return sorted(c.id for c in refs)


def count_docs(ref) -> int:
    """Conta docs em uma colecao. Usa Aggregation (count) quando
    disponivel, senao stream-count."""
    try:
        results = ref.count().get()
        if results and results[0]:
            value = results[0][0].value
            return int(value) if value is not None else 0
    except Exception:
        pass
    return sum(1 for _ in ref.stream())


def recursive_delete_doc(doc_ref) -> int:
    """Apaga um doc + todas suas subcolecoes recursivamente. Retorna
    total de docs apagados (incluindo o proprio doc)."""
    deleted = 0
    for subcol in doc_ref.collections():
        for snap in subcol.stream():
            deleted += recursive_delete_doc(snap.reference)
    doc_ref.delete()
    deleted += 1
    return deleted


def batch_delete_collection(ref, batch_size: int = 200) -> int:
    """Apaga todos os docs de uma colecao em batches. Trata subcolecoes
    nested (recursive). Retorna total."""
    total = 0
    while True:
        batch = list(ref.limit(batch_size).stream())
        if not batch:
            break
        for snap in batch:
            total += recursive_delete_doc(snap.reference)
    return total


def collect_flat_targets(
    tenant_id: str, purge_channels: bool
) -> list[tuple[str, Callable[[dict], bool], str]]:
    """Retorna [(collection_name, predicate, description)] de colecoes flat
    cuja exclusao depende do escopo do tenant."""
    targets: list[tuple[str, Callable[[dict], bool], str]] = []
    if purge_channels:
        # Hoje channels eh single-tenant flat. Quando passar pra
        # subcolecao, este predicate precisa ajustar.
        targets.append((
            "channels",
            lambda d: True,
            "todos os canais (single-tenant flat)",
        ))
        targets.append((
            "phone_routing",
            lambda d: d.get("tenant_id") == tenant_id,
            f"entries de phone_routing apontando pra tenant_id={tenant_id}",
        ))
    return targets


def main() -> int:
    args = parse_args()
    tid = args.tenant_id

    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "<unset>")
    prefix = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "<unset>")

    print(_bold(f"\n=== WIPE TENANT: {tid} ==="))
    print(f"  project={project_id}")
    print(f"  prefix= {prefix}")
    print(f"  modo:   {'CONFIRMED (vai apagar)' if args.confirm else 'DRY-RUN (nada apagado)'}")

    # Verifica que o doc do tenant existe (sanity check)
    tenant_ref = tenant_doc_ref(tid)
    snap = tenant_ref.get()
    if not snap.exists:
        print(_red(f"\n  ✗ tenant '{tid}' nao existe no Firestore"))
        print(_red(f"    path: {prefix}_tenants/{tid}"))
        return 2
    tdata = snap.to_dict() or {}
    print(f"  tenant: name={tdata.get('name')!r} plan={tdata.get('plan')} active={tdata.get('is_active')}")

    skip = set(DEFAULT_SKIP)
    if not args.purge_users:
        skip.update(USER_PRESERVED)
    if not args.purge_audit_log:
        skip.update(AUDIT_PRESERVED)

    subcols = discover_tenant_subcollections(tid)
    flat_targets = collect_flat_targets(tid, args.purge_channels)

    # Plan output
    print(_bold(f"\n=== PLANO ==="))
    print(f"\nSubcolecoes em tenants/{tid}/:")
    if not subcols:
        print(f"  (nenhuma — tenant ja esta vazio)")
    else:
        for sc in subcols:
            ref = tenant_ref.collection(sc)
            n = count_docs(ref)
            marker = _yellow("[SKIP]") if sc in skip else _red("[WIPE]")
            note = ""
            if sc in USER_PRESERVED and not args.purge_users:
                note = "  (use --purge-users)"
            elif sc in AUDIT_PRESERVED and not args.purge_audit_log:
                note = "  (use --purge-audit-log)"
            print(f"  {marker} {sc:30s} {n:6d} docs{note}")

    print(f"\nColecoes flat (escopo {tid}):")
    if not flat_targets:
        print(f"  (nenhuma — use --purge-channels pra incluir channels/phone_routing)")
    else:
        for col_name, predicate, desc in flat_targets:
            try:
                n = sum(
                    1 for snap in global_collection(col_name).stream()
                    if predicate(snap.to_dict() or {})
                )
            except Exception as exc:
                print(f"  [WARN] count em {col_name}: {exc}")
                n = -1
            print(f"  {_red('[WIPE]')} {col_name:30s} {n:6d} docs — {desc}")

    print(f"\nNUNCA apagado:")
    print(f"  - Doc raiz tenants/{tid} (preservado)")
    print(f"  - Colecao tenants flat (preservada)")
    print(f"  - _meta global (preservado)")

    if not args.confirm:
        print(_yellow(_bold("\n[DRY-RUN] Nada foi apagado. Use --confirm para executar.")))
        return 0

    if not args.no_interactive:
        print(_red(_bold(
            f"\n!!! ATENCAO !!!\n"
            f"Esta operacao apaga PERMANENTEMENTE os dados acima do tenant '{tid}'\n"
            f"em {prefix} (project {project_id}). NAO HA UNDO.\n"
        )))
        print("Digite 'WIPE' (em maiusculas, sem aspas) pra confirmar:")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != "WIPE":
            print(_yellow("\nCancelado pelo operador."))
            return 1

    # Execute
    print(_bold(f"\n=== EXECUTANDO ==="))
    grand_total = 0
    for sc in subcols:
        if sc in skip:
            continue
        ref = tenant_ref.collection(sc)
        deleted = batch_delete_collection(ref)
        grand_total += deleted
        print(f"  apagado tenants/{tid}/{sc}: {deleted} docs")

    for col_name, predicate, desc in flat_targets:
        deleted = 0
        for snap in global_collection(col_name).stream():
            if predicate(snap.to_dict() or {}):
                snap.reference.delete()
                deleted += 1
        grand_total += deleted
        print(f"  apagado {col_name}: {deleted} docs")

    print(_green(_bold(
        f"\n✓ Wipe completo. Total apagado: {grand_total} docs.\n"
        f"  Tenant doc tenants/{tid} preservado."
    )))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

