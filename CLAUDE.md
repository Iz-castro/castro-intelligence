# CLAUDE.md

Guia operacional do **Castro Intelligence CRM** — CRM de WhatsApp multi-tenant.
Curto e de propósito: só o que já foi verificado no código atual. Se algo aqui
divergir do código, **o código vence** — corrija este arquivo.

Cliente principal em produção: **Hubloc / Hub Loc** (locadora de equipamentos).
Tenant #2 em migração: **Varizemed** (clínica, bot Dialogflow CX).

---

## Stack e runtime

- Backend: **FastAPI 0.115 + uvicorn** (async), app único em `main.py` servido por
  `uvicorn main:app --workers 1`. Runtime **Python 3.10** (container `python:3.10-slim`).
- Dados: **Firestore Native** + **Firebase Auth** + **Google Cloud Storage** (mídia).
  `DATA_BACKEND` e `AUTH_MODE` são constantes em `config.py` (não configuráveis por env).
- `database.py` só reexporta `database_firestore.py`. **Não existe caminho SQL.**
  `POST /api/login` é legado (410 Gone); auth real = Firebase ID token.
- Frontend: **React 18 + Vite 5 + TypeScript + Firebase 11** em `frontend/`,
  compilado **dentro** da imagem Docker (`/frontend_dist`) e servido pelo backend.
- Deploy: **Google Cloud Run** (`castro-crm`), projeto Oregon (ver Deploy).

## Rodar e validar

Não há suíte de testes automatizada versionada (sem pytest/tox/conftest). Os gates são:

- **Backend:** `.venv\Scripts\python.exe -m py_compile main.py webhook.py bot_service.py lgpd_bot.py database_firestore.py config.py tenant_service.py channel_service.py`
- **Lógica do bot:** `.venv\Scripts\python.exe tools\sim_bot_flow.py` (mocka Firestore + WhatsApp
  API, exercita o código real, ~44 asserts, exit 0/1). CX: `tools\sim_cx_flow.py`.
  ⚠️ `tools\cx_smoke.py` **não é mockado** — bate no agente Dialogflow CX real (precisa ADC).
- **Frontend:** `npm run build` em `frontend/` (`tsc -b && vite build` = typecheck estrito + build).

## Deploy (produção)

Prod = projeto **`project-4a851bf9-f475-418c-800`**, região **`us-west1`** (Oregon),
prefixo de coleção `castro_crm`, tenant default `hubloc`.

**Comando de deploy de rotina** (`--source` puro **preserva** env, secrets e scaling da revisão anterior):

```powershell
gcloud run deploy castro-crm --source C:\Rafael\castro-intelligence --region us-west1 --project project-4a851bf9-f475-418c-800 --quiet
```

Três pegadinhas que **já quebraram** deploy — não esqueça nenhuma:

1. **`--project` explícito sempre.** `gcloud config` aponta pro projeto ANTIGO de SP
   (`project-26fb9c99-8ee9-4179-aef`). Sem `--project`, o deploy vai pro projeto errado.
2. **Caminho ABSOLUTO em `--source`, nunca `.`** — se o shell estiver em `frontend/`
   (ex.: após `npm run build`), o `.` cai em Buildpacks e falha.
3. **`CLOUDSDK_PYTHON` → Python312** (`C:\Users\izael\AppData\Local\Programs\Python\Python312\python.exe`);
   já setado no escopo User, mas shells que não herdam (ex.: Bash tool) precisam prefixar.

- **NUNCA** deploiar prod com `deploy.ps1` / `deploy.sh`: usam `--env-vars-file` + `--set-secrets` +
  scaling hardcoded e **clobberam** env/secrets/scaling de prod (perdem `META_APP_SECRET`,
  `FEATURE_GOOGLE_CHAT`, `CRON_OIDC_*`, `EMBEDDED_SIGNUP_CONFIG_ID`...).
- `docs/deploy/RUNBOOK_CUTOVER_PROD.md` está **STALE** (cita SP / `southamerica-east1`). O
  procedimento é útil, mas traduza projeto/região pro Oregon; não copie os `--project`/`--region` de lá.
- **Tráfego é FIXADO por revisão** (o serviço tem tag `staging` + traffic pinado, não "serve latest").
  Um `gcloud run deploy` direto na prod sobe a revisão nova **a 0%** e o gcloud ainda imprime
  "serving 100 percent" (mentira — é a revisão velha). Pior: o fluxo staging+promote **bagunça a
  numeração**, então a revisão nova pode ter número MENOR que as antigas → **`--to-latest` cai na
  errada**. **Sempre promova por NOME após o deploy:**
  `gcloud run services update-traffic castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --to-revisions <REV_NOVA>=100` e confira com `describe ... status.traffic`.
- **O NOME de revisão impresso pelo `gcloud run deploy` também pode estar ERRADO** (2026-07-29:
  imprimiu `00066-bsm`, mas a revisão criada foi `00067-frb` → promoção errada por ~2 min). Descubra
  a revisão nova com `gcloud run revisions list ... --sort-by "~metadata.creationTimestamp"` (a mais
  recente por data de criação), nunca pelo texto do deploy.
- **Smoke pós-deploy:** `GET /` → 200 e `GET /api/client-config` → 200 (confere `projectId`
  Oregon). Scaling vivo se preserva sozinho — não afirme números sem `gcloud run services describe castro-crm`.
- **Rollback:** `gcloud run services update-traffic castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --to-revisions <REV_ANTERIOR>=100`.
- **Cloud Run B** (`castro-superadmin`) tem pipeline **separado** (`cloudbuild-superadmin.yaml` +
  `Dockerfile.superadmin`); **não** use `--source` (pegaria o Dockerfile do A). Ver `docs/DEPLOY_CLOUDRUN_B.md`.

## Invariantes que NÃO podem quebrar (landmines reais)

- **`_GLOBAL_COLLECTIONS` (`firestore_common.py`)** = `channels, pending_webhook_events,
  super_admins, audit_logs_system, phone_routing, _meta, tenants`. Ficam **flat/globais** mesmo
  com tenant context ativo. Toda coleção que o webhook precisa ler **antes** de saber o tenant
  pertence aqui. Tirar `channels` daqui = refresh sob tenant monta cache vazio → `no_channel` por
  ~60s → inbound cai em pending (perda crônica de mensagens).
- **`channel_id` vem do contador GLOBAL:** `next_sequence("channels", tenant_id="")` com string
  **vazia**, nunca `None` (`None` colide ids entre tenants — incidente 2026-07-16).
- **`conversation_id` é determinístico:** `"{channel_id}__{wa_id}"`. Sem `channel_id`/`wa_id`,
  o webhook enfileira em `pending_webhook_events` (auto-id do Firestore) — nunca gera id sintético.
- **Isolamento do operador (LGPD) = 3 camadas em sincronia** (backend `get_wa_contacts_scoped_for_user`,
  frontend snapshot targets, `firestore.rules`). Operador comum vê **só próprios** (`assigned_to_uid==uid`)
  **+ pool sem dono** — **NUNCA por department_id** (query por depto vazava agenda coex pessoal pros colegas).
  `is_backup` só admin/supervisor.
- **IDOR:** endpoints por `contact_id`/`message_id` chamam `_require_contact_access` (ex.:
  `/api/wa/conversation/open`). Sem isso, operador abre/auto-atribui lead alheio por id enumerável.
- **Atribuição POR THREAD** (`assign_wa_conversation`, `assigned_to` na conversation) é **separada**
  do **Dono do Lead** (`assign_wa_contact`, `/api/admin/reassign-lead`). Revert no fechamento tem que
  gravar `assigned_to_uid` (não só `assigned_to`), senão o lead some do frontend da própria dona.
- **Whisper cold-start:** `FEATURE_AUDIO_TRANSCRIPTION=true` só é seguro porque o modelo está
  **embutido na imagem** (`HF_HUB_OFFLINE=1`). Ligar sem o modelo embutido trava o startup probe →
  cascata 500/503/429. Mudar `WHISPER_MODEL_SIZE` **exige rebuild** da imagem.
- **Bootstrap de setores:** `bootstrap_departments` roda a cada startup e só semeia defaults se o
  tenant tiver **zero** setores (inclusive inativos). Não remova o gate (setores "Vendas" duplicados
  já sequestraram roteamento). Após o seed, editar setor só pela UI.
- **Não regrida os fixes de custo:** header da sidebar usa `count_only=1` (aggregate), não o
  full-scan de `/api/wa/contacts/all`; os crons (`close_stale_attendances`, `expire_stale_takeovers`)
  usam `.where(...)` server-side, não full-scan de `wa_conversations`.
- **Resolução de canal no webhook:** `phone_number_id` sem canal **ativo** vai pra pending —
  nunca cai no canal default (número coex desconectado vazaria pro standard).

## Mapa de módulos (onde mexer)

| Assunto | Arquivos |
|---|---|
| Config / env / feature flags | `config.py` |
| App, rotas, middleware de tenant | `main.py` |
| Persistência CRM (tudo) | `database_firestore.py` (via `database.py`) |
| Acesso a dados, prefixo, tenant context, `next_sequence` | `firestore_common.py` |
| Webhook Meta (resolve tenant → canal, nunca propaga exceção) | `webhook.py` |
| Fila zero-perda de webhook | `pending_events.py` |
| Registry de canais WhatsApp (flat) | `channel_service.py` |
| Tenants, `phone_routing` global, resolução de login por domínio | `tenant_service.py` |
| Auth (Firebase ID token, resolução de tenant) | `auth.py` |
| RBAC dinâmico por tenant | `rbac.py` |
| Gate LGPD | `lgpd_bot.py` |
| Bot builtin + dispatcher builtin/CX | `bot_service.py` |
| Redação de PII em logs | `pii_redaction.py` |
| Frontend (estado central + listeners) | `frontend/src/context/CrmContext.tsx`, `App.tsx` |

Modelo de dados WhatsApp: `wa_contacts` (Lead único por `wa_id`) · `wa_conversations`
(Atendimento por canal+wa_id) · `wa_messages` (histórico por `timestamp_wa`).

## Multi-tenant

- Tenant context por request: middleware extrai `tenant_id` do claim do JWT antes do endpoint.
  Coleções roteiam para `tenants/{tid}/<name>` quando há contexto; senão, flat (compat).
- Prefixo final = `{FIRESTORE_COLLECTION_PREFIX}_{name}` (`castro_crm`; staging `castro_crm_staging`).
  Staging e prod **compartilham o mesmo Firebase/Auth**, isolados só pelo prefixo — claim de tenant
  só-de-prod dá 403 em staging.
- `allowed_email_domains` é **soft** (guarda-corpo + roteamento de login); quem autoriza é o **claim
  `tenant_id`**. Provedores públicos (gmail/outlook) nunca roteiam/auto-provisionam tenant.
- Hoje só **`hubloc`** é operacional; `"hubloc"` está hardcoded como fallback em vários pontos
  (`webhook.py`, middleware, `channel_service.py`). Ligar o tenant #2 exige revisar esses fallbacks.

## Convenções

- **Comentários e docstrings em pt-BR SEM acento** (evita encoding). Strings ao cliente final
  (respostas do WhatsApp) **mantêm** acentuação normal.
- Todo `.py` da raiz começa com `# -*- coding: utf-8 -*-`.
- Logging: um logger por módulo, `logging.getLogger("castro_crm.<modulo>")`. **Nunca** logar
  PII/tokens em claro — usar `pii_redaction.py` (`redact_phone`, `redact_name`) + `%s` lazy.
- Feature flags **env-driven**, centralizadas em `config.py`, lidas uma vez no import. Religar
  recurso = mudar env, não código. (`FEATURE_AUDIO_TRANSCRIPTION` default false — ver cold-start.)
- Branch de trabalho = **`develop`**. **Não commitar/push sem pedido explícito.**
- Decisões arquiteturais → `docs/decisions/` (ADR `NNNN-slug.md`). Diários/histórico →
  `docs/internal/` (`YYYY-MM-DD.md`).
- Nunca versionar segredos/PII (`.env`, `service-account*.json`, `media/`, `logs/` já no `.gitignore`).
