# Firebase Architecture

Arquitetura alvo do CRM:

- `React + Firebase Auth`
- `React -> Firestore` via `onSnapshot()` para leitura em tempo real
- `React -> FastAPI` para operacoes sensiveis: envio para Meta, webhook, handoff, Google Chat
- `Cloud Storage / Firebase Storage` para midia

## Estado atual do repo

- O backend FastAPI ja foi preparado para `Firestore + Firebase Auth + Cloud Storage`.
- As `Firestore Rules` e `Storage Rules` base ja existem neste repo.
- O arquivo [static/chat.html](/c:/Projetos/Hubloc/castro-intelligence/static/chat.html) continua sendo um cliente legado de fallback.
- Ainda nao existe um projeto React dedicado neste repositorio.

## Collections expostas ao React

### `operator_profiles/{uid}`

Espelho seguro do operador autenticado.

Campos principais:

- `uid`
- `user_id`
- `email`
- `display_name`
- `role`
- `department_id`
- `is_active`

Observacao: a colecao `users` permanece privada ao backend porque contem `password_hash` e dados internos.

### `departments/{departmentId}`

Campos:

- `id`
- `name`
- `description`
- `is_active`

### `wa_contacts/{contactId}`

Resumo de cada conversa WhatsApp.

Campos:

- `id`
- `wa_id`
- `display_name`
- `phone_formatted`
- `qualification`
- `notes`
- `assigned_to`
- `assigned_to_uid`
- `department_id`
- `unread_count`
- `is_archived`
- `first_seen_at`
- `last_message_at`
- `contact_avatar_path`

Uso no React:

- sidebar de atendimentos
- filtros por fila/departamento
- badges de nao lidas

### `wa_messages/{messageId}`

Historico de mensagens.

Campos:

- `id`
- `wa_message_id`
- `contact_id`
- `contact_doc_id`
- `direction`
- `msg_type`
- `content`
- `media_path`
- `media_mime`
- `media_id`
- `filename`
- `status`
- `operator_id`
- `assigned_to`
- `assigned_to_uid`
- `department_id`
- `timestamp_wa`
- `created_at`

Uso no React:

- query por `where("contact_id", "==", contactId)` + `orderBy("created_at")`
- `onSnapshot()` para atualizar a conversa

### `wa_transfer_log/{transferId}`

Historico de handoff.

Campos:

- `id`
- `contact_id`
- `contact_doc_id`
- `from_user_id`
- `to_user_id`
- `to_user_uid`
- `from_department_id`
- `to_department_id`
- `department_id`
- `reason`
- `summary`
- `transferred_by`
- `created_at`

## Collections privadas do backend

- `users`
- `messages`
- `internal_unread`
- `audit_log`
- `wa_message_status`
- `_meta`

## Fluxo de autenticacao

1. React autentica no Firebase Auth com Google.
2. React obtém `ID token`.
3. React chama `GET /api/session` com `Authorization: Bearer <ID_TOKEN>`.
4. FastAPI valida o token com `firebase-admin`.
5. FastAPI cria ou sincroniza o operador interno e o documento `operator_profiles/{uid}`.
6. A partir desse ponto o React pode abrir `onSnapshot()` direto nas colecoes permitidas pelas rules.

## Fluxo de midia

1. FastAPI recebe midia do WhatsApp ou upload do operador.
2. O arquivo vai para `Cloud Storage / Firebase Storage`.
3. O Firestore guarda apenas metadado e `media_path`.
4. O React renderiza a midia a partir desse path.

## Modo de entrega do front

- `snapshot`: modo principal
- `polling`: fallback de teste

O backend ainda expõe WebSocket legado, mas ele nao faz parte da arquitetura alvo.
