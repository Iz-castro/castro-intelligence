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
$DATA_BACKEND = if ($env:DATA_BACKEND) { $env:DATA_BACKEND.Trim().ToLowerInvariant() } else { "firestore" }
$AUTH_MODE = if ($env:AUTH_MODE) { $env:AUTH_MODE.Trim().ToLowerInvariant() } else { "firebase" }
$SQL_INSTANCE_NAME = if ($env:SQL_INSTANCE_NAME) { $env:SQL_INSTANCE_NAME } else { "castro-crm-db" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "castro_crm" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "castro_app" }
$DB_PASSWORD = $env:DB_PASSWORD
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
$SECRET_KEY = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { New-HexSecret }
$WHATSAPP_TOKEN = $env:WHATSAPP_TOKEN
$WHATSAPP_VERIFY_TOKEN = $env:WHATSAPP_VERIFY_TOKEN
$WHATSAPP_APP_SECRET = $env:WHATSAPP_APP_SECRET
$WHATSAPP_PHONE_NUMBER_ID = $env:WHATSAPP_PHONE_NUMBER_ID
$WHATSAPP_WABA_ID = $env:WHATSAPP_WABA_ID
$BOOTSTRAP_ADMIN_EMAIL = if ($env:BOOTSTRAP_ADMIN_EMAIL) { $env:BOOTSTRAP_ADMIN_EMAIL } else { "" }
$BOOTSTRAP_ADMIN_USERNAME = if ($env:BOOTSTRAP_ADMIN_USERNAME) { $env:BOOTSTRAP_ADMIN_USERNAME } else { "admin" }
$BOOTSTRAP_ADMIN_PASSWORD = $env:BOOTSTRAP_ADMIN_PASSWORD
$BOOTSTRAP_ADMIN_DISPLAY_NAME = if ($env:BOOTSTRAP_ADMIN_DISPLAY_NAME) { $env:BOOTSTRAP_ADMIN_DISPLAY_NAME } else { "Administrador" }
$BOOTSTRAP_ADMIN_DEPARTMENT = if ($env:BOOTSTRAP_ADMIN_DEPARTMENT) { $env:BOOTSTRAP_ADMIN_DEPARTMENT } else { "Geral" }
$JWT_EXPIRATION_MINUTES = if ($env:JWT_EXPIRATION_MINUTES) { $env:JWT_EXPIRATION_MINUTES } else { "480" }
$LOG_LEVEL = if ($env:LOG_LEVEL) { $env:LOG_LEVEL } else { "INFO" }
$CORS_ORIGINS = if ($env:CORS_ORIGINS) { $env:CORS_ORIGINS } else { "" }
$REQUIRE_WEBHOOK_SIGNATURE = if ($env:REQUIRE_WEBHOOK_SIGNATURE) { $env:REQUIRE_WEBHOOK_SIGNATURE } else { "true" }
$CHAT_DELIVERY_MODE = if ($env:CHAT_DELIVERY_MODE) { $env:CHAT_DELIVERY_MODE.Trim().ToLowerInvariant() } else { "snapshot" }
$POLLING_INTERVAL_MS = if ($env:POLLING_INTERVAL_MS) { $env:POLLING_INTERVAL_MS } else { "5000" }
$ENABLE_AUDIO_TRANSCRIPTION = $FEATURE_AUDIO_TRANSCRIPTION.Trim().ToLowerInvariant() -in @("1", "true", "yes", "on")

if ($DATA_BACKEND -notin @("firestore", "sql")) {
    throw "DATA_BACKEND deve ser 'firestore' ou 'sql'."
}

if ($AUTH_MODE -notin @("firebase", "legacy")) {
    throw "AUTH_MODE deve ser 'firebase' ou 'legacy'."
}

if ($CHAT_DELIVERY_MODE -notin @("snapshot", "polling")) {
    throw "CHAT_DELIVERY_MODE deve ser 'snapshot' ou 'polling'."
}

Require-Value -Name "GCP_PROJECT_ID" -Value $PROJECT_ID
Require-Value -Name "WHATSAPP_TOKEN" -Value $WHATSAPP_TOKEN
Require-Value -Name "WHATSAPP_VERIFY_TOKEN" -Value $WHATSAPP_VERIFY_TOKEN
Require-Value -Name "WHATSAPP_APP_SECRET" -Value $WHATSAPP_APP_SECRET
Require-Value -Name "WHATSAPP_PHONE_NUMBER_ID" -Value $WHATSAPP_PHONE_NUMBER_ID

if ($DATA_BACKEND -eq "sql") {
    Require-Value -Name "DB_PASSWORD" -Value $DB_PASSWORD
}

if ($AUTH_MODE -eq "legacy") {
    Require-Value -Name "BOOTSTRAP_ADMIN_PASSWORD" -Value $BOOTSTRAP_ADMIN_PASSWORD
}

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

if ($DATA_BACKEND -eq "sql") {
    $services += "sqladmin.googleapis.com"
}

if ($ENABLE_AUDIO_TRANSCRIPTION) {
    $services += "speech.googleapis.com"
}

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

if ($DATA_BACKEND -eq "sql") {
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
        --role "roles/cloudsql.client" `
        --quiet | Out-Null
}
else {
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
        --role "roles/datastore.user" `
        --quiet | Out-Null
}

if ($ENABLE_AUDIO_TRANSCRIPTION) {
    gcloud projects add-iam-policy-binding $PROJECT_ID `
        --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
        --role "roles/speech.client" `
        --quiet | Out-Null
}

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

if ($DATA_BACKEND -eq "sql") {
    $INSTANCE_CONNECTION_NAME = (& gcloud sql instances describe $SQL_INSTANCE_NAME --project $PROJECT_ID --format="value(connectionName)").Trim()
    Require-Value -Name "SQL_INSTANCE_NAME" -Value $INSTANCE_CONNECTION_NAME

    $DB_USER_ENCODED = [System.Uri]::EscapeDataString($DB_USER)
    $DB_PASSWORD_ENCODED = [System.Uri]::EscapeDataString($DB_PASSWORD)
    $DATABASE_URL = "postgresql+pg8000://${DB_USER_ENCODED}:${DB_PASSWORD_ENCODED}@/$DB_NAME?unix_sock=/cloudsql/$INSTANCE_CONNECTION_NAME/.s.PGSQL.5432"
    $DB_SECRET_NAME = "$SERVICE_NAME-database-url"
    Set-GcpSecret -ProjectId $PROJECT_ID -Name $DB_SECRET_NAME -Value $DATABASE_URL
    $secretMappings.Add("DATABASE_URL=${DB_SECRET_NAME}:latest")
    $deployArgs.Add("--add-cloudsql-instances")
    $deployArgs.Add($INSTANCE_CONNECTION_NAME)
}

if ($AUTH_MODE -eq "legacy") {
    $BOOTSTRAP_PASSWORD_SECRET_NAME = "$SERVICE_NAME-bootstrap-admin-password"
    Set-GcpSecret -ProjectId $PROJECT_ID -Name $BOOTSTRAP_PASSWORD_SECRET_NAME -Value $BOOTSTRAP_ADMIN_PASSWORD
    $secretMappings.Add("BOOTSTRAP_ADMIN_PASSWORD=${BOOTSTRAP_PASSWORD_SECRET_NAME}:latest")
}

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

if ($AUTH_MODE -eq "firebase") {
    $envVars.Add("BOOTSTRAP_ADMIN_EMAIL=$BOOTSTRAP_ADMIN_EMAIL")
}
else {
    $envVars.Add("BOOTSTRAP_ADMIN_USERNAME=$BOOTSTRAP_ADMIN_USERNAME")
}

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
        "--memory", "512Mi",
        "--cpu", "1",
        "--min-instances", "0",
        "--max-instances", "3",
        "--concurrency", "40",
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
