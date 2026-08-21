# Codebase Guide

Guia rapido para entender o repositorio sem depender de arquivos locais de contexto.

> **Status em 2026-08-21:** as "Verdades do runtime" abaixo seguem valendo, mas o
> guia e anterior a varias frentes que hoje estao EM PROD: multi-tenant real
> (tenants `hubloc`, `varizemed`, `varizemed-test`), RBAC dinamico por tenant
> (`rbac.py`), agente de IA (builtin `bot_service.py` + Dialogflow CX
> `bot_engine_dialogflow.py`), gate LGPD (`lgpd_bot.py`), horario comercial por
> tenant (`business_hours.py`), Modo Recepcao (ADR 0010) e `unread_count` do
> contato derivado das threads (ADR 0011). O mapa de modulos autoritativo hoje
> esta no [CLAUDE.md](../../CLAUDE.md) e as decisoes em `docs/decisions/`.

## Verdades do runtime

Assuma estas premissas ao ler ou alterar o sistema:

- o runtime oficial e `FastAPI + Firestore + Firebase Auth + React/Vite`
- `database.py` apenas reexporta `database_firestore.py`
- nao existe caminho real de SQL no backend atual
- nao existe fallback real para frontend legado em `static/`
- `POST /api/login` nao autentica mais e retorna `410 Gone`
- o legado principal que ainda aparece no repo e historico, nao operacional

## Ordem sugerida de leitura

1. `config.py`
2. `main.py`
3. `database.py`
4. `database_firestore.py`
5. `auth.py`
6. `webhook.py`
7. `media.py`
8. `transcription_service.py`
9. `google_chat.py`
10. `webhook_google_chat.py`
11. `frontend/src/context/CrmContext.tsx`
12. `frontend/src/App.tsx`
13. `firestore.rules`
14. `storage.rules`

## Arquivos auxiliares importantes

- `firebase_admin_client.py`: validacao de ID token do Firebase
- `firestore_common.py`: cliente Firestore, prefixos de colecao, sequencias, tenant context
- `tenant_service.py`: cache de tenants e roteamento `phone_routing/{phone_number_id}` global
- `channel_service.py`: registry de canais WhatsApp (lookup por id/phone_id; cache so-ativos), `create_channel` / `update_channel` / `rebind_channel` (Fase 1) e `deactivate_channel`
- `pending_events.py`: fila `pending_webhook_events` (zero perda de webhook da Meta quando canal nao indexado ou exception no processamento)
- `pii_redaction.py`: utilitarios `redact_phone` / `redact_name` para logs (LGPD)
- `rbac.py`: RBAC dinamico por tenant (perfis de acesso + toggles por chave)
- `bot_service.py`: bot builtin + dispatcher builtin/CX; `bot_engine_dialogflow.py`: conector do Dialogflow CX
- `lgpd_bot.py`: gate de consentimento LGPD antes do atendimento humano
- `business_hours.py`: horario comercial por tenant (aviso do builtin + params pro CX)
- `lead_temperature.py`: classificacao quente/morno/frio a partir dos params de sessao do CX (modulo puro)
- `super_admin.py` / `superadmin_main.py`: painel super-admin, servico Cloud Run B separado (ver `docs/DEPLOY_CLOUDRUN_B.md`)
- `bootstrap_data.py`: departamentos padrao
- `init_db.py`: bootstrap do Firestore e provisionamento inicial do admin
- `seed_gchat.py`: seed manual de Google Chat para teste

## Onde mexer em cada assunto

### Autenticacao

Arquivos principais:

- `auth.py`
- `firebase_admin_client.py`
- `main.py`
- `frontend/src/firebase.ts`

O que esperar:

- login via Google no Firebase
- backend validando `ID token`
- sincronizacao de usuario interno e `operator_profiles/{uid}`

### WhatsApp

Arquivos principais:

- `main.py`
- `webhook.py`
- `media.py`
- `database_firestore.py`
- `channel_service.py`

O que esperar:

- webhook da Meta (com `phone_routing` global → tenant + canal em O(1))
- envio de texto, midia, audio, localizacao e template
- modelo `Contato`/`Atendimento`/`Mensagem` = `wa_contacts` / `wa_conversations` / `wa_messages` (sub-thread por canal; `conversation_id = {channel_id}__{wa_id}`)
- atribuicao e transferencia POR THREAD (`assign_wa_conversation`); Dono do Lead separado (`assign_wa_contact`, endpoint `/api/admin/reassign-lead`)
- coexistence: Embedded Signup com rebind de canal (Fase 1 — `rebind_channel`), takeover temporario do lead-owner (`flag_conversation_takeover`, cron `castro-crm-expire-takeovers` */30)
- intervencao do supervisor — 3 modos: Sussurro (`/api/wa/internal-note`, `direction="internal"`), Co-pilotagem (texto assinado `[Supervisao - nome]:` em `/api/wa/send`), Takeover (`/api/wa/conversation/{id}/supervisor-takeover`)
- ciclo de vida do atendimento (`attendance_status` em `wa_conversations`): auto-close por inatividade plugado no mesmo cron */30, fechar/reabrir manual (`/api/wa/conversation/{id}/set-attendance`), reabre em qualquer nova mensagem
- protocolo 1 dia=1 por Lead (`attendances_daily/{YYYYMMDD-{contact_id}-{SETOR}}`): geracao silenciosa no 1o inbound (via `save_wa_message` → `ensure_daily_attendance`), envio ao cliente no fechamento como recibo, busca admin `GET /api/admin/protocol/{id}`
- painel de conflitos (`GET /api/admin/conflicts`): Leads com >=2 atendimentos ativos atribuidos a operadores distintos
- nao lidas, historico cronologico por `timestamp_wa`, idempotencia por `wa_message_id`

### Google Chat

Arquivos principais:

- `google_chat.py`
- `webhook_google_chat.py`
- `database_firestore.py`
- `frontend/src/components/gchat/InternalChatPanel.tsx`

O que esperar:

- sincronizacao de spaces, conversas e mensagens
- anexos persistidos pelo backend
- controle de `unread_count` no Firestore

### Transcricao

Arquivos principais:

- `transcription_service.py`
- `webhook.py`
- `main.py`

O que esperar:

- `faster-whisper`
- conversao com `ffmpeg`
- transcricao inbound opcional
- rota manual `POST /api/wa/messages/{message_id}/transcribe`

### Rules e acesso ao Firestore

Arquivos principais:

- `firestore.rules`
- `storage.rules`
- `main.py`

Ponto de atencao:

- `FIRESTORE_COLLECTION_PREFIX` precisa continuar alinhado com as rules atuais

## Validacao minima depois de mexer

- `python -m py_compile` nos modulos principais do backend
- `npm run build` em `frontend/`
- simuladores mockados do bot (exit 0/1): `tools/sim_bot_flow.py`,
  `tools/sim_cx_flow.py`, `tools/sim_reception_flow.py`
  (⚠️ `tools/cx_smoke.py` NAO e mockado — bate no agente Dialogflow CX real)

Observacao:

- ainda nao existe suite automatizada versionada no repo

## Como pensar ao evoluir o sistema

- trate `Firestore/Firebase/React` como plataforma definitiva
- nao recoloque compatibilidade legada sem necessidade real
- documente mudancas arquiteturais em `docs/`
- use `docs/internal/` apenas para historico de trabalho ou contexto temporario
