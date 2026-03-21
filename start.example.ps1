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
