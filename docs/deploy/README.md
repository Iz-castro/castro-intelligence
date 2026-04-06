# Deploy Docs

Esta pasta concentra deploy, configuracao de ambiente e operacao.

## Premissas atuais

- o runtime oficial e `Firestore + Firebase Auth`
- o frontend React precisa estar compilado em `frontend_dist/`
- `docs/` fica fora do deploy por causa do `.gcloudignore`

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

WhatsApp:

- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_WABA_ID`
- `WHATSAPP_TOKEN`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`

Observacao:

- `WHATSAPP_WABA_ID` identifica a conta do WhatsApp Business no Meta.
- `WHATSAPP_PHONE_NUMBER_ID` identifica o numero conectado e e o valor usado nas rotas `/messages` e `/media`.
- Em cenarios de `coexistence`, nao confundir os dois ids durante o provisionamento.
- No Cloud Run atual, `WHATSAPP_PHONE_NUMBER_ID` e `WHATSAPP_WABA_ID` entram como variaveis de ambiente.
- No Cloud Run atual, `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN` e `WHATSAPP_APP_SECRET` entram via Secret Manager.

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
