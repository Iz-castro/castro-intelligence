$env:SECRET_KEY="troque_por_uma_chave_hex_aleatoria"
$env:WHATSAPP_TOKEN="troque_pelo_token_da_meta"
$env:WHATSAPP_PHONE_NUMBER_ID="000000000000000"
$env:WHATSAPP_VERIFY_TOKEN="troque_pelo_token_de_verificacao"
$env:WHATSAPP_APP_SECRET="troque_pelo_app_secret_da_meta"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Castro Intelligence CRM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Abrindo dois terminais:"
Write-Host "    1. Servidor FastAPI (porta 8080)"
Write-Host "    2. Tunel ngrok (HTTPS)"
Write-Host ""

# Copie este arquivo para start.ps1 e preencha os valores reais antes de rodar.

# Terminal 1: Servidor
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; .\venv\Scripts\activate; python main.py"

# Esperar servidor subir
Start-Sleep -Seconds 4

# Terminal 2: ngrok com IPv4 explicito
Start-Process powershell -ArgumentList "-NoExit", "-Command", "ngrok http 127.0.0.1:8080"

Write-Host "  Servidor e ngrok iniciados." -ForegroundColor Green
Write-Host ""
Write-Host "  Acesso local: http://127.0.0.1:8080" -ForegroundColor Yellow
Write-Host "  Copie a URL HTTPS do ngrok e atualize no painel da Meta se necessario."
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
