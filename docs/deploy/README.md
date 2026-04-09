# Deploy Docs

Esta pasta concentra deploy, configuracao de ambiente e operacao.

## Premissas atuais

- o runtime oficial e `Firestore + Firebase Auth`
- o sistema suporta multi-canal (standard + coexistence) via `channel_service.py`
- o frontend React precisa estar compilado em `frontend_dist/`
- `docs/` fica fora do deploy por causa do `.gcloudignore`
- no startup, o sistema cria automaticamente o canal default a partir das env vars

## Variaveis de ambiente mais importantes

Base do runtime:

- `FIRESTORE_PROJECT_ID`
- `FIRESTORE_COLLECTION_PREFIX`
- `CHAT_DELIVERY_MODE=snapshot|polling`
- `MEDIA_STORAGE_BACKEND=local|gcs|firestore`
- `FEATURE_MESSAGE_STATUS`
- `FEATURE_AUDIO_TRANSCRIPTION`
- `FEATURE_GOOGLE_CHAT`

Firebase:

- `ALLOWED_FIREBASE_EMAIL_DOMAIN`
- `ALLOWED_FIREBASE_EMAILS`
- `AUTO_PROVISION_FIREBASE_USERS`
- `FIREBASE_WEB_API_KEY`
- `FIREBASE_WEB_AUTH_DOMAIN`
- `FIREBASE_WEB_APP_ID`
- `FIREBASE_WEB_MESSAGING_SENDER_ID`
- `FIREBASE_WEB_MEASUREMENT_ID`
- `FIREBASE_STORAGE_BUCKET`
- `BOOTSTRAP_ADMIN_EMAIL`

Midia:

- `GCS_MEDIA_BUCKET`
- `GCS_MEDIA_PREFIX`

Transcricao:

- `STT_LANGUAGE_CODE`
- `STT_TIMEOUT_SECONDS`
- `STT_FALLBACK_TEXT`
- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`

WhatsApp (canal default / standard):

- `WHATSAPP_PHONE_NUMBER_ID` — ID do numero padrao (bootstrap do canal default)
- `WHATSAPP_WABA_ID` — ID da WABA padrao
- `WHATSAPP_TOKEN` — token do canal default (via Secret Manager)
- `WHATSAPP_VERIFY_TOKEN` — token de verificacao do webhook
- `WHATSAPP_APP_SECRET` — secret do app Meta (validacao HMAC)

Meta Embedded Signup (Coexistence):

- `META_APP_ID` — App ID na Meta
- `META_APP_SECRET` — App Secret (via Secret Manager ou env)
- `EMBEDDED_SIGNUP_CONFIG_ID` — Config ID do Embedded Signup

Observacao sobre multi-canal:

- As env vars `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_WABA_ID` sao usadas apenas para criar o **canal default** no startup (bootstrap).
- Canais adicionais (coexistence) armazenam seus proprios tokens na colecao `castro_crm_channels` do Firestore.
- O modulo `channel_service.py` resolve credenciais dinamicamente por canal.
- Cada endpoint de envio busca token/phone_id do canal associado ao contato.
- No Cloud Run, `WHATSAPP_TOKEN` e `WHATSAPP_APP_SECRET` entram via Secret Manager.

## Diagnostico de coexistence

Para validar rapidamente se o bloqueio esta no token ou no provisionamento do numero:

- ambiente local / `.env`: `python check_whatsapp_coexistence.py`
- secret de producao no GCP: `python check_whatsapp_coexistence.py --token-source gcloud-secret --gcloud-project <project-id>`
- comparar local x producao: `python check_whatsapp_coexistence.py --token-source both --gcloud-project <project-id>`

Sinais mais comuns:

- `OAuthException code=190` com `Application has been deleted`: token local preso em uma app Meta removida
- `status=DISCONNECTED` + `platform_type=ON_PREMISE` + `code_verification_status=NOT_VERIFIED`: a coexistence ainda nao terminou de registrar o numero para Cloud API
- `CONNECTED`: o numero ja esta provisionado do lado da Meta e o proximo teste deve ser envio real por `/messages`

Google Chat:

- `GOOGLE_CHAT_PROJECT_NUMBER`
- `GOOGLE_CHAT_SERVICE_ACCOUNT_FILE`

## Validacao minima antes de deploy

- `python -m py_compile` nos modulos principais
- `npm run build` dentro de `frontend/`

## Observacoes operacionais

- as rules atuais do Firestore ainda sao amplas e precisam continuar alinhadas com `FIRESTORE_COLLECTION_PREFIX`
- o bootstrap inicial do primeiro admin depende de `BOOTSTRAP_ADMIN_EMAIL`
- o login legado nao faz mais parte do deploy nem do runtime atual
