# Checklist de Configuracao na Meta — Coexistence

## A. Pre-requisitos (verificar se ja esta feito)

- [ ] **Portfolio "Castro Intelligence"** (Tech Provider) — verificado, contem o App
- [ ] **Portfolio "Castro Operacoes WhatsApp"** (Cliente) — verificado, contem WABA + telefone
- [ ] **App "Castro Intelligence CRM"** criado no App Dashboard (App ID: `1434723791183375`)
- [ ] Permissoes do App: `whatsapp_business_management` + `whatsapp_business_messaging`

## B. Configuracoes do App (developers.facebook.com)

- [ ] **App Dashboard > Configuracoes > Basico**
  - [ ] Dominio do app adicionado: `castro-crm-286866630844.southamerica-east1.run.app`
  - [ ] App Secret anotado (para validacao HMAC do webhook)

- [ ] **Login do Facebook para Empresas > Configuracoes**
  - [ ] Dominio permitido para SDK JavaScript: `castro-crm-286866630844.southamerica-east1.run.app`

## C. Configuracao do Embedded Signup

- [ ] **App Dashboard > WhatsApp > Embedded Signup**
  - [ ] Config ID criado: `2785379481799560`
  - [ ] Permissoes marcadas: `whatsapp_business_management` + `whatsapp_business_messaging`

## D. Webhook — CRITICO

- [ ] **App Dashboard > WhatsApp > Configuracao > Webhook**
  - [ ] URL do callback: `https://castro-crm-286866630844.southamerica-east1.run.app/webhook`
  - [ ] Verify Token: `castro-webhook-2026`
  - [ ] **Inscrever nos campos (todos obrigatorios para coexistence):**
    - [ ] `messages` (mensagens inbound padrao)
    - [ ] `smb_message_echoes` (mensagens enviadas pelo celular)
    - [ ] `smb_app_state_sync` (sincronizacao de contatos)
    - [ ] `history` (importacao de historico 180 dias)
    - [ ] `account_update` (desconexao, offboarding, reconexao)
    - [ ] `message_template_status_update` (opcional, para templates)

## E. Preparar o Numero de Telefone

- [ ] **Deletar o numero da WABA atual** (esta com status Offline, bloqueia o signup):
  ```bash
  curl -X DELETE "https://graph.facebook.com/v22.0/1055982807598158" \
    -H "Authorization: Bearer TOKEN_AQUI"
  ```
- [ ] **Aguardar 3-5 minutos** para a Meta propagar
- [ ] **No celular Android**, confirmar que o WhatsApp Business App esta:
  - [ ] Logado com o numero `+55 31 7195-7758`
  - [ ] Versao **2.24.17 ou superior**
  - [ ] Enviando/recebendo mensagens normalmente (atividade organica recente)

## F. Executar o Embedded Signup (no CRM)

- [ ] Acessar o CRM como admin
- [ ] Engrenagem > **WhatsApp Coexistence**
- [ ] Clicar **Iniciar Embedded Signup**
- [ ] No popup do Facebook:
  - [ ] Login com o admin do portfolio **Castro Operacoes WhatsApp**
  - [ ] Selecionar portfolio: **Castro Operacoes WhatsApp**
  - [ ] Selecionar/criar WABA
  - [ ] Selecionar **"Adicionar um novo numero"**
  - [ ] Digitar `553171957758`
  - [ ] **Escanear o QR Code** no celular (WhatsApp Business App > Configuracoes > Aparelhos Conectados)
  - [ ] Opcionalmente: autorizar compartilhamento de historico
- [ ] Anotar os dados retornados: **WABA ID**, **Phone Number ID**, **Token**

## G. Atualizar Variaveis de Ambiente

- [ ] Atualizar `.env` local:
  ```
  WHATSAPP_TOKEN=<token retornado>
  WHATSAPP_PHONE_NUMBER_ID=<phone_number_id retornado>
  WHATSAPP_WABA_ID=<waba_id retornado>
  ```
- [ ] Atualizar no **Cloud Run / Secret Manager**:
  ```bash
  echo -n "NOVO_TOKEN" | gcloud secrets versions add castro-crm-whatsapp-token \
    --data-file=- --project=project-26fb9c99-8ee9-4179-aef

  gcloud run services update castro-crm \
    --region=southamerica-east1 \
    --project=project-26fb9c99-8ee9-4179-aef \
    --update-env-vars="WHATSAPP_PHONE_NUMBER_ID=NOVO_ID,WHATSAPP_WABA_ID=NOVO_WABA_ID"
  ```

## H. Pos-Signup — Iniciar Sincronizacao (em ate 24h!)

- [ ] **Sincronizar contatos:**
  ```bash
  curl -X POST "https://graph.facebook.com/v22.0/<PHONE_NUMBER_ID>/smb_app_data" \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync"}'
  ```
- [ ] **Sincronizar historico de mensagens:**
  ```bash
  curl -X POST "https://graph.facebook.com/v22.0/<PHONE_NUMBER_ID>/smb_app_data" \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"messaging_product": "whatsapp", "sync_type": "history"}'
  ```

## I. Validacao Final

- [ ] Rodar diagnostico: `python check_whatsapp_coexistence.py`
- [ ] Resultado esperado: `status=CONNECTED platform_type=CLOUD_API is_on_biz_app=true`
- [ ] Enviar mensagem do celular -> verificar se aparece no CRM
- [ ] Enviar mensagem pelo CRM -> verificar se aparece no celular
- [ ] Verificar logs: `gcloud run logs read castro-crm --region=southamerica-east1`

## J. Regra Permanente

- [ ] **O celular deve abrir o WhatsApp Business App pelo menos a cada 14 dias**, senao a sessao expira e precisa reconectar

---

> **Secao D (Webhooks)** e a mais importante — sem inscrever nos 5 campos, o CRM nao recebe os eventos de coexistence.
> **Secao H** tem prazo de 24h apos o signup.
