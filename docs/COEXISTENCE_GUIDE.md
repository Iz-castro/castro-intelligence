# WhatsApp Coexistence - Guia de Implementacao

## O que e Coexistence?

Permite que um numero de telefone opere **simultaneamente** no WhatsApp Business App (celular) e na WhatsApp Cloud API (CRM). Mensagens enviadas pelo celular aparecem no CRM e vice-versa.

---

## Arquitetura dos Portfolios Meta

| Portfolio | Papel | Status |
|---|---|---|
| **Castro Intelligence** | Tech Provider (BSP) - contem o App "Castro Intelligence CRM" | Verificado |
| **Castro Operacoes WhatsApp** | Cliente - contem a WABA e o telefone | Verificado |

> O telefone NAO pode estar no mesmo portfolio do App. Por isso existem dois.

**App ID:** `1434723791183375`
**WABA ID (Castro Test Client):** `680503338460083`
**Phone Number ID:** `1055982807598158`
**Numero:** `+55 31 7195-7758`

---

## O que ja foi feito

### 1. Portfolios Meta configurados
- [x] Portfolio **Castro Intelligence** criado e verificado (contem o App)
- [x] Portfolio **Castro Operacoes WhatsApp** criado e verificado (contem WABA + telefone)
- [x] Portfolio desnecessario "Castro CRM Provider" pode ser deletado se ainda existir

### 2. Configuracao do Embedded Signup na Meta
- [x] Config ID criado: `2785379481799560` (nome: "Castro CRM Coexistence Prod")
- [x] Permissoes: `whatsapp_business_management` + `whatsapp_business_messaging`
- [x] Dominio JSSDK configurado: `castro-crm-286866630844.southamerica-east1.run.app`
- [x] Dominio do app configurado nas Configuracoes Basicas do app

### 3. Backend implementado
- [x] Variaveis de ambiente: `META_APP_ID`, `META_APP_SECRET`, `EMBEDDED_SIGNUP_CONFIG_ID`
- [x] Endpoint `GET /api/admin/embedded-signup/config` - retorna config para o frontend
- [x] Endpoint `POST /api/admin/embedded-signup/exchange` - troca code OAuth por token + descobre WABA/Phone IDs + cria canal automaticamente no registry
- [x] Secret `castro-crm-meta-app-secret` criado no Google Secret Manager
- [x] `channel_service.py` - registry multi-canal que armazena token/phone_id por canal

### 4. Frontend implementado
- [x] Modal "WhatsApp Coexistence" no menu de configuracoes (engrenagem > admin only)
- [x] Facebook SDK carregado dinamicamente
- [x] Fluxo de Embedded Signup com `featureType: "coexistence"`
- [x] Exchange agora aceita `channel_type`, `owner_user_id`, `label` para criar canal coexistence
- [x] Canais criados aparecem em Administracao > aba Canais WhatsApp

### 5. Deploy no Cloud Run
- [x] Env vars configuradas no Cloud Run
- [x] Codigo deployado (revision `castro-crm-00041-fgd`)
- [x] URL: `https://castro-crm-286866630844.southamerica-east1.run.app`

### 6. Webhooks de Coexistence
- [x] `smb_message_echoes` - Mensagens do celular ecoadas para o CRM (outbound com source phone_app)
- [x] `smb_app_state_sync` - Contatos do celular sincronizados com wa_contacts
- [x] `history` - Importacao dos 180 dias de historico (fases, chunks, media_placeholder)
- [x] `account_update` - Eventos PARTNER_REMOVED, ACCOUNT_OFFBOARDED, ACCOUNT_RECONNECTED

---

## O QUE FALTA FAZER (nesta ordem)

### Passo 1: Deletar o numero da WABA via API

O numero `+55 31 7195-7758` esta registrado na WABA "Castro Test Client" com status **Offline**. Isso BLOQUEIA o Embedded Signup de Coexistence. Precisa deletar o numero da WABA (nao o portfolio, so o numero).

**Como fazer:**

1. Gerar um token temporario no developers.facebook.com:
   - App Castro Intelligence CRM > WhatsApp > Configuracao da API > **Gerar token de acesso**

2. Executar no terminal (substituir `TOKEN_AQUI` pelo token gerado):

```bash
curl -X DELETE "https://graph.facebook.com/v22.0/1055982807598158" \
  -H "Authorization: Bearer TOKEN_AQUI"
```

3. Resposta esperada: `{"success": true}`

4. **Aguardar 3-5 minutos** para a Meta propagar a exclusao

> **IMPORTANTE:** Apos deletar, o numero precisa de um periodo de aquecimento no WhatsApp Business App. O documento da Meta diz 7 dias minimo, ideal 1-2 meses. Porem, como o numero ja tinha uso organico antes, pode funcionar em menos tempo.

### Passo 2: Verificar que o numero esta ativo no celular

Apos deletar da WABA:
- Abrir o **WhatsApp Business App** no celular Android
- Confirmar que o numero `+55 31 7195-7758` esta logado e funcionando normalmente
- Enviar/receber algumas mensagens para garantir atividade organica
- App deve ser versao **2.24.17 ou superior**

### Passo 3: Tentar o Embedded Signup de novo

1. Acessar o CRM: `https://castro-crm-286866630844.southamerica-east1.run.app`
2. Login como admin
3. Engrenagem (canto superior) > **WhatsApp Coexistence**
4. Clicar em **Iniciar Embedded Signup**
5. No popup do Facebook:
   - Fazer login com o admin do portfolio **Castro Operacoes WhatsApp**
   - Selecionar portfolio: **Castro Operacoes WhatsApp**
   - Selecionar WABA: **Castro Test Client** (ou criar nova)
   - Na tela do numero: selecionar **"Adicionar um novo numero"**
   - Digitar o numero `553171957758`
   - **AGORA deve aparecer a opcao de QR Code** (Coexistence)
   - Escanear o QR Code no celular usando WhatsApp Business App > Configuracoes > Aparelhos Conectados

6. Se o signup completar com sucesso, o CRM vai exibir:
   - WABA ID novo
   - Phone Number ID novo
   - Access Token
   - Status do numero

### Passo 4: Canal criado automaticamente

A partir da versao multi-canal (08/04/2026), o Embedded Signup **cria o canal automaticamente** no registry do sistema (`castro_crm_channels`). Nao e mais necessario atualizar env vars manualmente para canais coexistence.

O canal novo aparece em Administracao > aba Canais WhatsApp com:
- Tipo: Coexistence
- Label: nome do operador + numero
- Token: armazenado no Firestore (por canal)
- Owner: operador dono do numero

**Nota:** As env vars `WHATSAPP_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_WABA_ID` sao usadas apenas para o canal default (standard/bot). Canais coexistence usam credenciais proprias armazenadas no Firestore.

### Passo 5: Configurar Webhook na Meta (se necessario)

Se o webhook nao foi inscrito automaticamente pelo Embedded Signup:

1. developers.facebook.com > App Castro Intelligence CRM
2. WhatsApp > Configuracao
3. Webhook URL: `https://castro-crm-286866630844.southamerica-east1.run.app/webhook`
4. Verify Token: `castro-webhook-2026`
5. Inscrever nos campos: `messages`, `smb_message_echoes`, `smb_app_state_sync`, `history`, `account_update`

### Passo 6: Rodar o diagnostico

```bash
cd castro-intelligence
python check_whatsapp_coexistence.py
```

Resultado esperado:
```
phone: status=CONNECTED platform_type=CLOUD code_verification_status=VERIFIED
diagnosis:
- o numero ja aparece como CONNECTED
```

### Passo 7: Webhooks de Coexistence - IMPLEMENTADO

Os 4 webhooks de coexistence estao implementados em `webhook.py`:

1. **`smb_message_echoes`** - Captura mensagens enviadas pelo celular e salva no Firestore como outbound
2. **`smb_app_state_sync`** - Sincroniza contatos adicionados/editados no celular com wa_contacts
3. **`history`** - Importa os 180 dias de historico de conversas (fases 0/1/2, chunks, media_placeholder)
4. **`account_update`** - Trata eventos PARTNER_REMOVED, ACCOUNT_OFFBOARDED, ACCOUNT_RECONNECTED

### Passo 8: Iniciar sincronizacao apos Embedded Signup

Apos o cliente completar o Embedded Signup, chamar os endpoints de sincronizacao:

```bash
# 1. Sincronizar contatos
curl -X POST "https://graph.facebook.com/v22.0/<PHONE_NUMBER_ID>/smb_app_data" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync"}'

# 2. Sincronizar historico de mensagens (deve ser feito em ate 24h apos integracao)
curl -X POST "https://graph.facebook.com/v22.0/<PHONE_NUMBER_ID>/smb_app_data" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"messaging_product": "whatsapp", "sync_type": "history"}'
```

---

## Troubleshooting

### Erro: "This phone number is already registered"
O numero ainda esta registrado em alguma WABA. Deletar via API (Passo 1).

### Erro: "O dominio do host JSSDK e desconhecido"
Adicionar o dominio do Cloud Run em:
- App > Configuracoes do app > Basico > Dominios do app
- Login do Facebook para Empresas > Configuracoes > Dominios permitidos para o SDK do JavaScript

### Erro: "Application has been deleted" no diagnostico
O token no `.env` esta apontando para um app Meta deletado. Atualizar o token.

### Embedded Signup nao mostra opcao de QR Code
- Verificar que o numero esta ativo no WhatsApp Business App (nao o pessoal)
- Verificar versao do app >= 2.24.17
- O numero pode precisar de mais tempo de aquecimento (7 dias minimo)
- Confirmar que `featureType: "coexistence"` esta no codigo (ja esta)

### Numero conectado mas CRM nao recebe mensagens
- Verificar webhook configurado corretamente na Meta
- Verificar `WHATSAPP_VERIFY_TOKEN` esta correto
- Verificar logs do Cloud Run: `gcloud run logs read castro-crm --region=southamerica-east1`

### Keep-Alive obrigatorio (regra dos 14 dias)
Apos conectar via Coexistence, o celular com o WhatsApp Business App DEVE ser aberto **a cada 14 dias no maximo**. Se ficar mais de 14 dias sem abrir o app, a sessao expira e precisa reconectar.

---

## Limitacoes do Coexistence (do documento tecnico)

- Rate limit: **20 MPS** (nao 80 como na API pura)
- Listas de transmissao (Broadcast): **desabilitadas** no app
- Mensagens temporarias (Disappearing): **desabilitadas**
- View Once (midia): **desabilitado**
- Localizacao ao vivo: **desabilitada**
- App Windows (Microsoft Store): **NAO funciona** como companion device
- Companion devices permitidos: WhatsApp Web (browser) + Mac app (ate 4)
- Selo verde (OBA): **incompativel** com Coexistence
- Historico importado: apenas **180 dias** e somente chats 1:1 (sem grupos)

---

## Variaveis de Ambiente Relevantes

```env
# WhatsApp Cloud API (atualizar apos Embedded Signup)
WHATSAPP_TOKEN=<token permanente>
WHATSAPP_PHONE_NUMBER_ID=<phone number id>
WHATSAPP_WABA_ID=<waba id>
WHATSAPP_VERIFY_TOKEN=castro-webhook-2026
WHATSAPP_APP_SECRET=e58bae0d5dbb76335ad29d76f5357685

# Embedded Signup (Coexistence)
META_APP_ID=1434723791183375
META_APP_SECRET=ac1949d25418a2a7eb27d8cde0fffe5b
EMBEDDED_SIGNUP_CONFIG_ID=2785379481799560
```

## Arquivos Modificados

- `config.py` - Adicionado `META_APP_ID`, `META_APP_SECRET`, `EMBEDDED_SIGNUP_CONFIG_ID`
- `main.py` - Adicionado endpoints `/api/admin/embedded-signup/config` e `/api/admin/embedded-signup/exchange`
- `frontend/src/App.tsx` - Adicionado componente `WhatsAppSignupModal` e botao no menu
- `frontend/src/types.ts` - Adicionado `"whatsapp"` ao tipo `SettingsPage`
- `frontend/src/context/CrmContext.tsx` - Atualizado `openSettingsPage` para suportar `"whatsapp"`
- `.env.example` - Adicionadas variaveis de Coexistence

---

## Pre-requisitos para onboardar um numero via Embedded Signup

Antes de clicar "Conectar WhatsApp" no CRM, valide cada item abaixo. Se algum
falhar, o popup da Meta vai recusar o numero antes mesmo de chamar nosso
backend.

### 1. Numero esta no app correto

- O numero precisa estar cadastrado no app **WhatsApp Business** (icone com
  a letra "B"), nao no WhatsApp comum.
- Se estava no WhatsApp comum, instale o WhatsApp Business e migre os dados
  pelo proprio app (oferta automatica na primeira abertura).

### 2. Numero NAO esta em outra WABA

- Um mesmo numero so pode estar em uma WABA por vez. Se o numero ja foi
  cadastrado em outra conta WhatsApp Business API (outro provedor, outro
  app, etc.), a Meta bloqueia o reuso.
- Como verificar: peca para o dono do numero abrir [business.facebook.com](https://business.facebook.com)
  e checar se aparece em "WhatsApp Accounts". Se aparecer, remova a partir
  do portfolio antigo antes de tentar o signup.

### 3. Configuracao do App Dashboard (Meta)

Em [developers.facebook.com](https://developers.facebook.com) > seu App > **WhatsApp**:

- **Configuration > Webhook**: o callback URL deve apontar para
  `https://<seu-dominio>/webhook` e o verify token bate com `WHATSAPP_VERIFY_TOKEN`.
- **Configuration > Webhook fields**: ativar todos os toggles abaixo
  (sem isso o webhook fica registrado mas nao recebe os eventos):
  - `messages`
  - `message_template_status_update`
  - `history` (coexistence)
  - `smb_message_echoes` (coexistence)
  - `smb_app_state_sync` (coexistence)
  - `account_update`
- **Embedded Signup > Configurations**: o `EMBEDDED_SIGNUP_CONFIG_ID`
  deve ter sido criado com a opcao **"WhatsApp Business App onboarding"**
  (modo Coexistence). Se o config foi criado para Cloud API padrao, o
  popup recusa numeros coexistence. Crie um novo config se necessario e
  atualize a env var.

### 4. Variaveis de ambiente do servidor

Confirme via `GET /api/admin/embedded-signup/config` (logado como admin)
que o backend retorna 200 com `app_id`, `config_id` e `graph_api_version`
preenchidos. Se retorna 503 com mensagem indicando variaveis ausentes,
configure-as no Cloud Run / `.env` antes de prosseguir.

---

## Diagnostico de falha no Embedded Signup

Se o popup retorna erro ou o backend retorna 502 apos a troca do code,
veja os logs do servidor — todas as chamadas `Graph API` agora logam
`message`, `code`, `subcode` e `fbtrace_id` da Meta. Casos comuns:

| Sintoma | Causa provavel | Acao |
|---|---|---|
| Popup fecha sem retornar code | Usuario cancelou OU `featureType` errado no FB.login | Verificar `frontend/src/App.tsx` `WhatsAppSignupModal` — deve passar `featureType: "whatsapp_business_app_onboarding"` |
| Backend 502 com `code=190` | Token invalido/expirado entre popup e exchange | Tentar de novo em janela limpa |
| Backend 502 com `code=100` em `/phone_numbers` | Token nao tem escopo para listar numeros (raro com config correto) | Validar escopos no `EMBEDDED_SIGNUP_CONFIG_ID` |
| Backend 400 "Nenhum numero encontrado" | WABA criada mas numero ainda nao adicionado | Pedir para o dono completar o flow do WhatsApp Business no celular |
| `webhook_subscribed=false` no response | POST `/subscribed_apps` falhou (logar detail) | Conferir se o app esta em modo "Live" e tem permissao no portfolio |

---

## Token expira em ~2h — agora ha refresh automatico

Tokens user-bound de coexistence vencem em ~1-2h. O backend agora salva
`token_expires_at` no documento do canal e tenta `fb_exchange_token`
automaticamente (em `_resolve_channel_creds`) quando faltam <5 min para
expirar. Quando o refresh falha, ha `WARNING` no log indicando que o
canal precisa ser re-onboardado.
