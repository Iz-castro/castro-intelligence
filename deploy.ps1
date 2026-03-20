$ErrorActionPreference = "Stop"

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
        gcloud secrets describe $Name --project $ProjectId *> $null
        if ($LASTEXITCODE -ne 0) {
            gcloud secrets create $Name `
                --project $ProjectId `
                --data-file=$tmpFile `
                --replication-policy=automatic | Out-Null
            Write-Host "Secret criado: $Name"
        }
        else {
            gcloud secrets versions add $Name `
                --project $ProjectId `
                --data-file=$tmpFile | Out-Null
            Write-Host "Nova versao adicionada ao secret: $Name"
        }
    }
    finally {
        Remove-Item $tmpFile -ErrorAction SilentlyContinue
    }
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
$AUTO_PROVISION_FIREBASE_USERS = if ($env:AUTO_PROVISION_FIREBASE_USERS) { $env:AUTO_PROVISION_FIREBASE_USERS } else { "true" }
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

$serviceEnableArgs = @("services", "enable")
$serviceEnableArgs += $services
$serviceEnableArgs += @("--project", $PROJECT_ID, "--quiet")
& gcloud @serviceEnableArgs | Out-Null

$SERVICE_ACCOUNT_EMAIL = "$SERVICE_NAME-run@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts describe $SERVICE_ACCOUNT_EMAIL --project $PROJECT_ID *> $null
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create "$SERVICE_NAME-run" `
        --project $PROJECT_ID `
        --display-name "$SERVICE_NAME runtime" | Out-Null
}

gcloud storage buckets describe "gs://$MEDIA_BUCKET" --project $PROJECT_ID *> $null
if ($LASTEXITCODE -ne 0) {
    gcloud storage buckets create "gs://$MEDIA_BUCKET" `
        --project $PROJECT_ID `
        --location $REGION `
        --uniform-bucket-level-access `
        --public-access-prevention=enforced | Out-Null
}

gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
    --role "roles/secretmanager.secretAccessor" `
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
$envVars.Add("AUTO_PROVISION_FIREBASE_USERS=$AUTO_PROVISION_FIREBASE_USERS")

if ($AUTH_MODE -eq "firebase") {
    $envVars.Add("BOOTSTRAP_ADMIN_EMAIL=$BOOTSTRAP_ADMIN_EMAIL")
}
else {
    $envVars.Add("BOOTSTRAP_ADMIN_USERNAME=$BOOTSTRAP_ADMIN_USERNAME")
}

Write-Host ""
Write-Host "Iniciando deploy no Cloud Run..."

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
    "--max-instances", "1",
    "--timeout", "300",
    "--set-env-vars", ($envVars -join ","),
    "--set-secrets", ($secretMappings -join ",")
)

if ($deployArgs.Count -gt 0) {
    $gcloudArgs += $deployArgs
}

& gcloud @gcloudArgs

$SERVICE_URL = (& gcloud run services describe $SERVICE_NAME --project $PROJECT_ID --region $REGION --format="value(status.url)").Trim()

Write-Host ""
Write-Host "Deploy concluido."
Write-Host "URL do servico: $SERVICE_URL"
Write-Host "Webhook:         $SERVICE_URL/webhook"
Write-Host "Bucket de media: gs://$MEDIA_BUCKET"
Write-Host ""
