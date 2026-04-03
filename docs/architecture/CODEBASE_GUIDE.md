# Codebase Guide

Guia rapido para entender o repositorio sem depender de arquivos locais de contexto.

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
- `firestore_common.py`: cliente Firestore, prefixos de colecao e sequencias
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

O que esperar:

- webhook da Meta
- envio de texto, midia, audio, localizacao e template
- atribuicao, handoff, nao lidas e historico de mensagens

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

Observacao:

- ainda nao existe suite automatizada versionada no repo

## Como pensar ao evoluir o sistema

- trate `Firestore/Firebase/React` como plataforma definitiva
- nao recoloque compatibilidade legada sem necessidade real
- documente mudancas arquiteturais em `docs/`
- use `docs/internal/` apenas para historico de trabalho ou contexto temporario
