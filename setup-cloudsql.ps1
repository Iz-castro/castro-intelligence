$ErrorActionPreference = "Stop"

function Require-Value {
    param(
        [string]$Name,
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Defina a variavel de ambiente $Name antes de executar."
    }
}

$PROJECT_ID = if ($env:GCP_PROJECT_ID) { $env:GCP_PROJECT_ID } else { (& gcloud config get-value project 2>$null) }
$PROJECT_ID = "$PROJECT_ID".Trim()
$REGION = if ($env:GCP_REGION) { $env:GCP_REGION } else { "southamerica-east1" }
$SQL_INSTANCE_NAME = if ($env:SQL_INSTANCE_NAME) { $env:SQL_INSTANCE_NAME } else { "castro-crm-db" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "castro_crm" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "castro_app" }
$SQL_ROOT_PASSWORD = $env:SQL_ROOT_PASSWORD
$DB_PASSWORD = $env:DB_PASSWORD

Require-Value -Name "GCP_PROJECT_ID" -Value $PROJECT_ID
Require-Value -Name "SQL_ROOT_PASSWORD" -Value $SQL_ROOT_PASSWORD
Require-Value -Name "DB_PASSWORD" -Value $DB_PASSWORD

Write-Host ""
Write-Host "Projeto:  $PROJECT_ID"
Write-Host "Regiao:   $REGION"
Write-Host "Instancia $SQL_INSTANCE_NAME"
Write-Host "Banco:    $DB_NAME"
Write-Host "Usuario:  $DB_USER"
Write-Host ""

gcloud config set project $PROJECT_ID | Out-Null

gcloud services enable `
    sqladmin.googleapis.com `
    secretmanager.googleapis.com `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    --project $PROJECT_ID `
    --quiet | Out-Null

$instanceExists = $true
gcloud sql instances describe $SQL_INSTANCE_NAME --project $PROJECT_ID --format="value(name)" *> $null
if ($LASTEXITCODE -ne 0) {
    $instanceExists = $false
}

if (-not $instanceExists) {
    Write-Host "Criando instancia Cloud SQL PostgreSQL..."
    gcloud sql instances create $SQL_INSTANCE_NAME `
        --project $PROJECT_ID `
        --database-version POSTGRES_15 `
        --cpu 1 `
        --memory 3840MiB `
        --region $REGION `
        --storage-size 10 `
        --availability-type zonal `
        --root-password $SQL_ROOT_PASSWORD `
        --quiet
}
else {
    Write-Host "Instancia Cloud SQL ja existe."
}

$dbNames = @(gcloud sql databases list --instance $SQL_INSTANCE_NAME --project $PROJECT_ID --format="value(name)")
if ($dbNames -notcontains $DB_NAME) {
    Write-Host "Criando banco $DB_NAME..."
    gcloud sql databases create $DB_NAME `
        --instance $SQL_INSTANCE_NAME `
        --project $PROJECT_ID `
        --quiet | Out-Null
}
else {
    Write-Host "Banco $DB_NAME ja existe."
}

$userNames = @(gcloud sql users list --instance $SQL_INSTANCE_NAME --project $PROJECT_ID --format="value(name)")
if ($userNames -notcontains $DB_USER) {
    Write-Host "Criando usuario $DB_USER..."
    gcloud sql users create $DB_USER `
        --instance $SQL_INSTANCE_NAME `
        --project $PROJECT_ID `
        --password $DB_PASSWORD `
        --quiet | Out-Null
}
else {
    Write-Host "Usuario $DB_USER ja existe. Atualizando senha..."
    gcloud sql users set-password $DB_USER `
        --instance $SQL_INSTANCE_NAME `
        --project $PROJECT_ID `
        --password $DB_PASSWORD `
        --quiet | Out-Null
}

$CONNECTION_NAME = (& gcloud sql instances describe $SQL_INSTANCE_NAME --project $PROJECT_ID --format="value(connectionName)").Trim()

Write-Host ""
Write-Host "Cloud SQL pronto."
Write-Host "Connection name: $CONNECTION_NAME"
Write-Host ""
Write-Host "Proximo passo:"
Write-Host "  .\\deploy.ps1"
Write-Host ""
