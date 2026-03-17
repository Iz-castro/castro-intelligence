$env:SECRET_KEY="castro_intel_2026_chave_fixa"
$env:WHATSAPP_TOKEN="EAALBK2KV99sBQZCwHhZBiiL3BFQoW7FZBeIxZAYWDhZAQIVZCKDhGNZABztEjHH5Due2xZCArZAZBXOj4DjTHZCyy651OLu2RxTlSSDhDnlp3Ho58ipdxnmFIUTetlXVlkzNZAFqZCdxov8j8n0dCZAaskxaCNBkUcjdNIkpFZBZACFRjXCBcVEdy5g9KZBVoCc9tNSloTax3cAZDZD"
$env:WHATSAPP_PHONE_NUMBER_ID="983401388192837"
$env:WHATSAPP_VERIFY_TOKEN="hubloc2024"
$env:WHATSAPP_APP_SECRET=""

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Castro Intelligence CRM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Abrindo dois terminais:"
Write-Host "    1. Servidor FastAPI (porta 8080)"
Write-Host "    2. Tunel ngrok (HTTPS)"
Write-Host ""

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