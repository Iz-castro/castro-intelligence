# Castro Intelligence CRM - Relatorio do Sistema

**Atualizado em:** 08/04/2026  
**Base analisada:** codigo local em `C:\Projetos\Hubloc\castro-intelligence`  
**Escopo da verificacao:** backend FastAPI multi-canal, frontend React, persistencia Firestore, midia, transcricao, deploy Cloud Run, dashboard de auditoria e integracao opcional com Google Chat

---

## 1. Resumo Executivo

O sistema evoluiu para uma arquitetura **multi-canal** com suporte simultaneo a Cloud API padrao e coexistence. O backend e o frontend compilaram sem erro, e a arquitetura esta centrada em Firestore, Firebase Auth, Cloud Run e GCS.

Pontos confirmados neste snapshot:

- Backend FastAPI com persistencia Firestore e arquitetura multi-canal (`channel_service.py`).
- Frontend React/Vite com admin panel (departamentos, canais, dashboard).
- Tempo real via Firestore Snapshot, com fallback por polling.
- 50+ endpoints REST cobrindo atendimento, admin, auditoria e export.
- Sistema de avaliacao pos-conversao (rating 1-10) com visibilidade restrita.
- Roteamento automatico de leads convertidos retornantes ao operador original.
- Dashboard de auditoria com metricas diarias, peak chart e export CSV.
- Reatribuicao em lote para quando operadores saem.
- Embedded Signup cria canais coexistence automaticamente.

Pontos de atencao:

- Token temporario no Secret Manager (precisa System User Token permanente).
- Template de avaliacao `rating_request` ainda nao criado na Meta.
- Numero de teste so envia; precisa de numero real para fluxo inbound completo.
- Nao ha suite automatizada de testes.

---

## 2. Arquitetura Atual

```text
[Cliente WhatsApp / Meta Cloud API]
        |
        | webhook + envio outbound (multi-canal)
        v
[FastAPI no Cloud Run]
  |- auth Firebase
  |- channel_service.py (registry multi-canal)
  |- endpoints /api/wa/* (envio via canal do contato)
  |- endpoints /api/admin/* (departamentos, canais, dashboard, export)
  |- endpoints /api/gc/* (Google Chat opcional)
  |- webhook Meta (resolve canal por phone_number_id)
  |- upload e entrega de midia (token por canal)
  |- transcricao de audio
  |- metricas de auditoria (audit_metrics)
        |
        +--> [Cloud Firestore]
        |      |- channels (canais WhatsApp)
        |      |- contatos (channel_id, rating, qualification)
        |      |- mensagens WA (channel_id, visibility)
        |      |- transferencias
        |      |- audit_metrics (metricas diarias)
        |      |- audit_log
        |      |- perfis de operador
        |      |- departamentos (CRUD)
        |
        +--> [Cloud Storage / Firebase Storage bucket]
        |
        +--> [Google Chat API] (opcional)

[Frontend React + Firebase Auth]
  |- login Google
  |- 4 abas: Novos / Meus / N.Q. / Equipe
  |- chat central (filtra admin_only)
  |- painel operacional (rating, devolver bot, reatribuir)
  |- admin: departamentos, canais, sistema
  |- dashboard de auditoria + export CSV
  |- embedded signup coexistence
  |- snapshots Firestore ou polling REST
```

Observacao importante sobre tempo real:

- O relatorio anterior citava WebSocket como mecanismo principal.
- No estado atual, o CRM principal trabalha com Firestore Snapshot e fallback por polling.
- O WebSocket ainda existe no backend para um subsistema legado de chat interno entre operadores, mas nao e o fluxo central do CRM atual.

---

## 3. Stack Confirmada

| Camada | Estado atual |
|---|---|
| Build frontend | Node 22 no stage de build do Docker |
| Frontend | React 18.3.1 + TypeScript 5.6.3 + Vite 5.4 |
| Backend | Python 3.10 + FastAPI + Uvicorn |
| Persistencia | Firestore via `database_firestore.py` |
| Autenticacao | Firebase Auth (Google Sign-In) |
| Midia | Cloud Storage / Firebase Storage bucket |
| Transcricao | Faster Whisper 1.2.1 + FFmpeg |
| Integracao WhatsApp | Meta Cloud API v22.0 (multi-canal via channel_service) |
| Integracao interna opcional | Google Chat API + webhook JWT validado |
| Deploy | Cloud Run via `gcloud run deploy --source .` |
| Auditoria | Dashboard com metricas diarias + export CSV |

---

## 4. Modulos Verificados

### 4.1 Backend principal

Arquivo central:

- `main.py`

Areas confirmadas:

- sessao e autenticacao
- configuracao do cliente (`/api/client-config`)
- contatos e mensagens WhatsApp
- envio de texto, midia, audio, localizacao e template
- transcricao on-demand
- qualificacao, transferencia e assumir atendimento
- configuracoes de sistema e usuario
- Google Chat opcional (`/api/gc/*`)
- webhook Meta e webhook Google Chat
- endpoint WebSocket legado (`/ws/{token}`)

### 4.2 Persistencia

Arquivo central:

- `database_firestore.py`

Conclusao:

- o modulo `database.py` apenas reexporta `database_firestore`
- nao existe backend SQL ativo no codigo atual
- o sistema esta operacionalmente orientado a Firestore

Colecoes relevantes expostas ao frontend:

- `departments` (CRUD via admin)
- `operator_profiles`
- `wa_contacts` (com channel_id, rating, source_channel_type)
- `wa_messages` (com channel_id, visibility, is_rating_message)
- `wa_transfer_log`
- `gc_conversations`
- `gc_messages`

Colecoes adicionais observadas no backend:

- `channels` (registry multi-canal)
- `users`
- `audit_log`
- `audit_metrics` (metricas diarias pre-agregadas)
- `wa_message_status`
- `system_settings`
- `user_settings`
- `_meta` (contadores)

### 4.3 Frontend

Arquivos centrais:

- `frontend/src/App.tsx`
- `frontend/src/context/CrmContext.tsx`
- `frontend/src/styles.css`

Funcionalidades confirmadas no frontend:

- login Google
- layout em tres colunas + 4 abas de navegacao (Novos, Meus, N.Q., Equipe)
- filtros por fila, busca de contatos, filtro por qualificacao
- busca dentro da conversa
- indicador de canal (badge "coex" para coexistence)
- filtragem de mensagens admin_only (rating) para operadores comuns
- contatos coexistence de outros ocultos para operadores comuns
- anexos: imagem, video, documento e localizacao
- gravacao de audio pelo navegador
- transcricao de audio inbound/on-demand
- quick messages e configuracoes de chat
- tema claro/escuro
- chat interno Google Chat em painel lateral
- resposta e copia de mensagens no chat principal
- admin: CRUD departamentos, visualizacao canais, config sistema (3 abas)
- dashboard de auditoria: metricas, grafico de pico, por operador, ratings, export CSV
- embedded signup para conectar numeros coexistence
- botao "devolver ao bot" e reatribuicao em lote
- badge de rating no painel de detalhes (color-coded, admin/supervisor)
- menu contextual com posicionamento dinamico para cima/baixo

### 4.4 Midia e transcricao

Arquivos centrais:

- `media.py`
- `transcription_service.py`

Estado atual:

- uploads de midia do CRM sao armazenados com suporte a GCS, Firestore ou disco local, conforme configuracao
- audio gravado no browser e convertido para OGG/Opus via FFmpeg antes do envio ao WhatsApp
- a transcricao atual usa Faster Whisper, nao Google Speech-to-Text
- o modelo e controlado por `WHISPER_MODEL_SIZE`, `WHISPER_DEVICE` e `WHISPER_COMPUTE_TYPE`

### 4.5 Google Chat

Arquivos centrais:

- `google_chat.py`
- `webhook_google_chat.py`
- `frontend/src/components/gchat/InternalChatPanel.tsx`

Capacidades presentes:

- listar conversas
- listar spaces
- enviar texto do CRM para um space
- marcar conversa como lida
- receber eventos do Google Chat por webhook
- persistir mensagens do Google Chat em Firestore

---

## 5. Funcionalidades de Negocio em Estado Atual

### Atendimentos WhatsApp

- fila aberta, meus atendimentos, equipe e nao qualificados
- protocolo de atendimento ao assumir conversa
- qualificacao com notas
- transferencia com motivo e resumo
- avatars de operador e de contato
- status de mensagem quando `FEATURE_MESSAGE_STATUS=true`

### Composer e bolhas

- envio de texto simples
- envio de foto, video, documento e localizacao
- envio de audio gravado no browser
- resposta a mensagem com citacao persistida
- copia de texto/transcricao para area de transferencia

### Configuracoes

- configuracoes globais e por usuario no Firestore
- prefixo opcional de mensagem
- quick messages globais e por operador

### Entrega de dados para o frontend

- modo preferencial: Firestore Snapshot
- fallback: polling REST com intervalo configuravel

---

## 6. Deploy e Infraestrutura

Arquivos inspecionados:

- `Dockerfile`
- `deploy.ps1`
- `deploy.sh`

Perfil atual de runtime no deploy PowerShell:

| Item | Valor atual |
|---|---|
| Projeto | obtido de `GCP_PROJECT_ID` |
| Regiao padrao | `southamerica-east1` |
| Servico Cloud Run | `castro-crm` |
| Build/deploy | `gcloud run deploy --source .` |
| Runtime | `python:3.10-slim` |
| Frontend build stage | `node:22-slim` |
| Memoria | `1Gi` |
| CPU | `1` |
| Min instances | `0` |
| Max instances | `3` |
| Concurrency | `1` |
| Timeout | `300s` |
| Auth publica | `--allow-unauthenticated` |

Infraestrutura que o script prepara:

- APIs GCP necessarias
- service account dedicada do Cloud Run
- bucket de midia
- permissao em Secret Manager
- permissao em Storage
- permissao em Datastore/Firestore
- secrets do app e da Meta

Observacao:

- o URL final do servico e resolvido dinamicamente pelo proprio `gcloud` no deploy
- este relatorio nao tenta afirmar uma URL publica especifica sem consulta ao ambiente

---

## 7. Variaveis e Feature Flags Relevantes

### Core

- `AUTH_MODE`
- `FIRESTORE_PROJECT_ID`
- `FIRESTORE_COLLECTION_PREFIX`
- `CHAT_DELIVERY_MODE`
- `POLLING_INTERVAL_MS`
- `MEDIA_STORAGE_BACKEND`

### Firebase

- `ALLOWED_FIREBASE_EMAIL_DOMAIN`
- `ALLOWED_FIREBASE_EMAILS`
- `AUTO_PROVISION_FIREBASE_USERS`
- `FIREBASE_STORAGE_BUCKET`
- `FIREBASE_WEB_API_KEY`
- `FIREBASE_WEB_AUTH_DOMAIN`
- `FIREBASE_WEB_APP_ID`
- `FIREBASE_WEB_MESSAGING_SENDER_ID`
- `FIREBASE_WEB_MEASUREMENT_ID`

### WhatsApp / Meta

- `WHATSAPP_TOKEN`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_WABA_ID`
- `REQUIRE_WEBHOOK_SIGNATURE`

### Audio / Whisper

- `FEATURE_AUDIO_TRANSCRIPTION`
- `STT_LANGUAGE_CODE`
- `STT_TIMEOUT_SECONDS`
- `STT_FALLBACK_TEXT`
- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`

### Google Chat

- `FEATURE_GOOGLE_CHAT`
- `GOOGLE_CHAT_PROJECT_NUMBER`
- `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE`

---

## 8. Validacoes Executadas Nesta Revisao

Validacoes feitas localmente com sucesso:

1. Build do frontend:

```powershell
cd frontend
npm run build
```

Resultado:

- build concluido
- bundles gerados em `frontend_dist`

2. Compilacao sintatica dos modulos Python principais:

```powershell
python -m py_compile auth.py bootstrap_data.py config.py database.py database_firestore.py firebase_admin_client.py firestore_common.py google_chat.py init_db.py main.py media.py seed_gchat.py transcription_service.py webhook.py webhook_google_chat.py
```

Resultado:

- sem erro de sintaxe

3. Revisao estrutural manual:

- endpoints do backend mapeados
- fluxo de persistencia revisado
- deploy scripts inspecionados
- frontend principal e painel Google Chat revisados

---

## 9. Pontos de Atencao Atuais

### 9.1 Integracao Google Chat com anexo

Ha um risco concreto no caminho de anexos do webhook Google Chat:

- `webhook_google_chat.py` chama `save_upload_media(...)` de forma inconsistente com a assinatura atual em `media.py`
- isso pode afetar o armazenamento de audio/imagem/documento vindos do Google Chat

Impacto:

- mensagens de texto do Google Chat parecem coerentes
- anexos do Google Chat precisam de correcao ou teste integrado dedicado antes de serem considerados estaveis

### 9.2 Firestore-only na pratica

Embora os scripts de deploy ainda aceitem `DATA_BACKEND=sql`, o codigo atual esta acoplado a Firestore:

- `config.py` fixa `DATA_BACKEND = "firestore"`
- `database.py` aponta somente para `database_firestore.py`

Impacto:

- o caminho SQL nao deve ser tratado como suportado neste snapshot

### 9.3 Cobertura de testes

Nao foi encontrada suite automatizada de testes de regressao para:

- webhook Meta
- envio outbound para Meta
- Google Chat webhook
- fluxo de transferencia/assumir via teste automatizado
- smoke tests de deploy

Impacto:

- a confianca atual depende mais de build, py_compile e testes manuais em ambiente real

---

## 10. Estado Recomendado do Sistema

### Pode ser considerado estavel para

- operacao principal do CRM via WhatsApp
- autenticacao Google/Firebase
- persistencia em Firestore
- upload de midia do CRM
- transcricao via Faster Whisper
- painel web do operador

### Recomendado corrigir ou validar antes de ampliar uso

- anexos do Google Chat
- smoke tests de webhook e envio outbound
- alinhamento entre documentacao de deploy e realidade Firestore-only

---

## 11. Revisoes Recentes no Codigo

Ultimos commits observados na branch local:

| Commit | Descricao |
|---|---|
| `d0e4ae4` | `chore: ignore docs in git and gcloud deploys` |
| `15af436` | `feat: add reply and copy actions to chat messages` |
| `73cd1e6` | `docs: add Google Chat integration guide and fix Firestore rules` |
| `c28ca5d` | `feat: add Google Chat integration for internal operator-supervisor communication` |
| `52e76ed` | `Implement Faster Whisper transcription` |

---

## 12. Conclusao

O sistema atual esta mais maduro e mais completo do que o relatorio anterior indicava, mas tambem mudou de forma importante:

- a transcricao agora e Faster Whisper
- o CRM principal depende de Firestore Snapshot/Polling, nao de WebSocket como mecanismo central
- o deploy atual de Cloud Run usa perfil mais conservador (`1Gi`, `concurrency=1`)
- o Google Chat existe como integracao opcional, mas o fluxo de anexo ainda precisa de validacao/correcao

Em resumo: o nucleo WhatsApp + CRM web + Firestore esta coerente; a parte opcional de Google Chat ainda merece endurecimento operacional.
