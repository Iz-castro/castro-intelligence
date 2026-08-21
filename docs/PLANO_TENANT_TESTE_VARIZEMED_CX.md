# Plano — Tenant de teste "Varizemed" + motor de IA Dialogflow CX por tenant

> **Status em 2026-08-21:** plano **executado**. O `varizemed-test` e o tenant
> real `varizemed` estão em produção (CX ponta a ponta desde 29/07/2026, hoje
> com Modo Recepção — ADR 0010). Dois acertos de fato no corpo abaixo:
> o handoff usa **`bot_key=sac`** (corrigido nas duas ocorrências — `atendimento`
> NÃO é bot_key válido: `VALID_BOT_KEYS = {comercial, financeiro,
> administrativo, sac}` em `database_firestore.py`), e a location do agente é
> **`us-central1`** (vale a tabela do CONTRATO; o JSON de exemplo e a URL do
> DetectIntent mais abaixo ainda dizem `global`).
> ⚠ A "pegadinha do deploy" logo abaixo está desatualizada: `--source .`
> (caminho relativo) é proibido — use caminho **absoluto** — e o tráfego é
> **pinado por revisão**, então a revisão nova sobe a 0% e precisa ser promovida
> **por NOME** (`update-traffic --to-revisions <REV>=100`). Ver CLAUDE.md e
> `docs/deploy/DEPLOY_CLOUDRUN_A.md`. Troca de versão da Val:
> `docs/deploy/TROCAR_ENVIRONMENT_VAL.md` (hoje environment
> `22390163-6bbc-47b5-a25a-e53eb3363d8f`, `val-5.0.3`).

> Data: 2026-07-13 · Aprovado pelo PO. Organização: **2 trilhas paralelas**
> (Dev IA e Dev CRM) com contrato compartilhado. Este doc é a fonte única do
> contrato entre as trilhas — mudou algo aqui, avisa o outro dev.
>
> **Dev IA: sua parte é a "TRILHA IA" + o "CONTRATO COMPARTILHADO".**
> Entregável final da sua trilha (SYNC-1): `AI_PROJECT` real, `AGENT_ID` do
> agente restaurado e as URLs das 2 functions.
>
> ⚠️ **PEGADINHA DO DEPLOY (staging tag → prod):** o staging roda como revisão
> com tag `staging` + `--no-traffic` + `--update-env-vars FIRESTORE_COLLECTION_PREFIX=castro_crm_staging`.
> Como a revisão staging fica com esse prefixo, o deploy de PROMOÇÃO pra prod
> DEVE setar o prefixo de volta EXPLICITAMENTE, senão a prod herda `castro_crm_staging`:
> ```
> gcloud run deploy castro-crm --source . --region us-west1 \
>   --project project-4a851bf9-f475-418c-800 \
>   --update-env-vars FIRESTORE_COLLECTION_PREFIX=castro_crm
> ```

## Contexto (resumo)

A Varizemed (clínica) será o tenant #2 do Castro CRM, plano **ai_custom**.
O agente dela (`val-05`) é Dialogflow CX **generativo** (Gemini 2.5 Flash,
playbooks + 2 Cloud Functions como tools). Temos o export completo
(`docs/agenteval05/`) e os fontes das functions (`docs/valmr/`).
Curto prazo: tenant de TESTE no CRM com número próprio (DDD 71) respondendo
pelo agente CX via novo motor de bot por tenant. O banco do agente fica em
**banco Firestore nomeado separado** no projeto de IA — zero colisão com o CRM.

---

## CONTRATO COMPARTILHADO (fonte única — as 2 trilhas usam ESTES nomes)

### Identificadores GCP

| Recurso | Nome padronizado | Dono |
|---|---|---|
| Projeto de IA | `AI_PROJECT` = **`castro-ia`** ✅ (confirmado Dev IA 2026-07-13; billing ativo) | Dev IA |
| Projeto do CRM | `CRM_PROJECT` = `project-4a851bf9-f475-418c-800` (Oregon) | Dev CRM |
| Location do agente CX | **`us-central1`** ✅ (NAO global — o val-05 era global; DetectIntent usa host regional `us-central1-dialogflow.googleapis.com`, o conector ja trata). Functions/banco: co-locar em `us-central1` (Dev IA) | — |
| Banco Firestore do agente | **`castro-ai-test`** (nomeado; NUNCA o default — o Router ignora FIRESTORE_PREFIX, isolamento é só por banco) | Dev IA |
| Function router | **`varizemed-router`** (entry `varizemed_router_endpoint`) | Dev IA |
| Function memória | **`val-memory`** (entry `val_memory_endpoint`) | Dev IA |
| Agente CX | display **`val`** · **AGENT_ID `5fa69ea1-bc68-445b-9d20-d72265aaaf36`** ✅ (criado; language `pt-br`) | Dev IA |
| SA runtime das functions | `val-agent-fn@AI_PROJECT.iam.gserviceaccount.com` | Dev IA |
| SA do CRM (existente) | `CRM_SA` = SA do Cloud Run castro-crm (`gcloud run services describe castro-crm --region us-west1 --project CRM_PROJECT --format 'value(spec.template.spec.serviceAccountName)'`) | Dev CRM |
| Service agent Dialogflow | `service-{PROJECT_NUMBER}@gcp-sa-dialogflow.iam.gserviceaccount.com` (nasce ao habilitar a API) | — |

### Env vars

- **Lado IA (functions):** `FIRESTORE_DATABASE=castro-ai-test` (obrigatória nas
  2); `FIRESTORE_PREFIX` SEMPRE vazia/ausente. Nada mais.
- **Lado CRM:** NENHUMA env var nova. Toda config do motor é por tenant em
  `tenants/{tid}.settings.ai`. ADC resolve credenciais.

### Config por tenant (doc `tenants/{tid}.settings.ai`) — Dev CRM grava

```json
{
  "bot_engine": "dialogflow_cx",
  "gcp_project_id": "<AI_PROJECT>",
  "location": "global",
  "agent_id": "<AGENT_ID do restore>",
  "environment_id": "",
  "language_code": "pt-br",
  "handoff_bot_key": "sac",
  "lgpd_notice": "<aviso LGPD da clinica>",
  "lgpd_privacy_url": "https://...",
  "lgpd_policy_version": "varizemed-test-2026-07",
  "core_version": "val-05",
  "customization_version": "1",
  "status": "active"
}
```

### Parâmetros de sessão do CX (grafia EXATA; quem escreve → quem lê)

| Parâmetro | Escreve | Lê | Semântica |
|---|---|---|---|
| `user_id` | CRM (todo DetectIntent) | agente/ValMemory | `+` + dígitos E.164 do contato |
| `tenant_id` | CRM (todo DetectIntent) | (futuro multi-tenant das functions) | id do tenant |
| `lgpd_consent` | CRM (sempre `true` — gate local já passou) | flow lgpd do agente (bypass) | consentimento |
| `handoff_request` | agente (Atomic Closure) | CRM (conector) | true → transferir p/ humano |
| `conversation_complete` | agente | CRM (conector) | fim de sessão sem handoff |
| `handoff_summary` | agente | CRM (system message) | resumo p/ o atendente |
| `user_name` | agente | CRM (opcional) | nome declarado |

- **Session ID** = dígitos do wa_id do contato (10-15 dígitos, sem `+`) —
  formato que a ValMemory valida (rejeita sessões não-numéricas por design).
- **Endpoint DetectIntent** (CRM → agente): REST v3
  `https://dialogflow.googleapis.com/v3/projects/{AI_PROJECT}/locations/global/agents/{AGENT_ID}[/environments/{env}]/sessions/{session_id}:detectIntent`

### IAM entre projetos (quem concede o quê)

| Concessão | Onde | Quem executa |
|---|---|---|
| `roles/datastore.user` p/ `val-agent-fn@` | AI_PROJECT | Dev IA |
| `roles/run.invoker` nas 2 functions p/ service agent Dialogflow | AI_PROJECT | Dev IA |
| `roles/dialogflow.client` p/ `CRM_SA` (e SA do staging) | AI_PROJECT | Dev IA (após Dev CRM informar a SA) |

### Decisões de desenho já tomadas (não rediscutir)

- **LGPD**: o gate local do CRM (`lgpd_bot.py`) é a ÚNICA fonte de consentimento.
  O flow `lgpd_intro_flow` do agente é neutralizado no restore (remover o webhook
  `check_lgpd_consent` do `entryFulfillment` de `pagina_verificacao_lgpd`) e
  `lgpd_consent=true` é injetado em todo DetectIntent. A function
  `check-lgpd-consent` NÃO é portada.
- **Transporte**: REST `:detectIntent` com httpx + token ADC. Sem lib gRPC.
- **Sem debounce na v1**. NÃO copiar o debounce do Flask antigo (exige instância
  única + race de snapshot).
- **Dispatch**: fachada única `process_bot_message_async()` no CRM decide
  builtin × CX.

---

## TRILHA IA (Dev IA — autocontida)

### IA-1. Projeto, APIs, banco, seed

```bash
gcloud services enable dialogflow.googleapis.com cloudfunctions.googleapis.com \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com --project AI_PROJECT

gcloud firestore databases create --database=castro-ai-test \
  --location=us-west1 --type=firestore-native --project=AI_PROJECT

# SEED OBRIGATORIO: o fallback local insurance_plans.json da function e VAZIO
# (0 bytes); sem seed no Firestore, validate_insurance QUEBRA (JSONDecodeError).
python docs/valmr/upload_firestore_val.py --project AI_PROJECT \
  --database castro-ai-test --prefix "" --dir docs/valmr --dry-run   # conferir
python docs/valmr/upload_firestore_val.py --project AI_PROJECT \
  --database castro-ai-test --prefix "" --dir docs/valmr
```

Aceite: banco `castro-ai-test` com `config/insurance_plans` (schema 3.0),
`config/clinic_info`, `specialties/*` (5 docs).

### IA-2. Deploy das 2 functions (AUTENTICADAS — obrigatório; não têm auth própria)

Patch mínimo antes do deploy (nos fontes copiados de `docs/valmr/` — ver IA-5):
mascarar telefone nos logs (últimos 4 dígitos) e remover
`Access-Control-Allow-Origin: *` da ValMemory.

```bash
gcloud iam service-accounts create val-agent-fn --project AI_PROJECT
gcloud projects add-iam-policy-binding AI_PROJECT \
  --member serviceAccount:val-agent-fn@AI_PROJECT.iam.gserviceaccount.com \
  --role roles/datastore.user

gcloud functions deploy varizemed-router --gen2 --runtime python311 --region us-west1 \
  --source <fonte val-4> --entry-point varizemed_router_endpoint \
  --trigger-http --no-allow-unauthenticated \
  --set-env-vars FIRESTORE_DATABASE=castro-ai-test \
  --service-account val-agent-fn@AI_PROJECT.iam.gserviceaccount.com --project AI_PROJECT

gcloud functions deploy val-memory --gen2 --runtime python311 --region us-west1 \
  --source <fonte val_memory-4> --entry-point val_memory_endpoint \
  --trigger-http --no-allow-unauthenticated \
  --set-env-vars FIRESTORE_DATABASE=castro-ai-test \
  --service-account val-agent-fn@AI_PROJECT.iam.gserviceaccount.com --project AI_PROJECT

PROJECT_NUMBER=$(gcloud projects describe AI_PROJECT --format 'value(projectNumber)')
for FN in varizemed-router val-memory; do
  gcloud run services add-iam-policy-binding $FN --region us-west1 --project AI_PROJECT \
    --member serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-dialogflow.iam.gserviceaccount.com \
    --role roles/run.invoker
done
```

Aceite: curl anônimo → 403; curl com identity token → 200 JSON.

### IA-3. Restore do agente val-05 (patchado)

Preparar CÓPIA do `docs/agenteval05/` num diretório de build (NÃO alterar `docs/`):

1. `tools/VarizemdRouter/schema.yaml` + `tools/ValMemory/schema.yaml`:
   `servers.url` → URLs das functions novas.
2. `flows/lgpd_intro_flow/pages/pagina_verificacao_lgpd.json`: remover
   `"webhook"`/`"tag"` do `entryFulfillment` (decisão LGPD do contrato).
3. Zipar preservando estrutura → GCS → criar agente vazio (`displayName:
   "varizemed-test"`, `defaultLanguageCode: "pt-br"`) → `:restore` via REST v3:

```bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" -H "x-goog-user-project: AI_PROJECT" \
  "https://dialogflow.googleapis.com/v3/projects/AI_PROJECT/locations/global/agents" \
  -d '{"displayName":"varizemed-test","defaultLanguageCode":"pt-br","timeZone":"America/Buenos_Aires"}'
# guardar o AGENT_ID retornado

gsutil mb -p AI_PROJECT -l us-west1 gs://AI_PROJECT-agents || true
gsutil cp val05_patched.zip gs://AI_PROJECT-agents/

curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" -H "x-goog-user-project: AI_PROJECT" \
  "https://dialogflow.googleapis.com/v3/projects/AI_PROJECT/locations/global/agents/AGENT_ID:restore" \
  -d '{"agentUri":"gs://AI_PROJECT-agents/val05_patched.zip"}'
```

4. Console CX: configurar auth das 2 tools como **Service Agent ID Token**
   (o export não carrega auth config) e conferir que o Knowledge Connector ficou
   sem data store (esperado — data store não vem no export; recriar = deferido).
5. Revisar filtros RAI (o export veio com BLOCK_NONE nas 4 categorias) —
   manter só se for decisão consciente.

Aceite: simulador do console conversa com a Val e as tools respondem
(ex.: convênio Unimed → resposta correta do router, prova seed+function).

### IA-4. IAM cross-project p/ o CRM

```bash
gcloud projects add-iam-policy-binding AI_PROJECT \
  --member serviceAccount:CRM_SA --role roles/dialogflow.client
# idem SA do castro-crm-staging
```

**SYNC-1 (IA → CRM):** entregar `AI_PROJECT` real, `AGENT_ID`, URLs das functions.

### IA-5. Código-fonte definitivo

Mover os fontes das functions de `docs/valmr/` para diretório deployável
(sugestão: `agents/varizemed/` neste repo, ou repo próprio — decisão do Dev IA),
com os patches de log/CORS commitados. `docs/valmr/` vira artefato histórico.

---

## TRILHA CRM (Dev CRM — resumo; detalhe no plano interno)

- **Rollout**: staging primeiro (`castro-crm-staging` — recriar no projeto
  Oregon, pendência da migração), tag git, depois prod. Tenant de teste vive no
  banco de PROD.
- **CRM-0**: fix `get_send_credentials` (override env só pro próprio número —
  evita envio cross-tenant pelo número do Hubloc).
- **CRM-1**: planos `professional/ai_custom/enterprise_ai` + `_LEGACY_PLAN_MAP`
  + `PLAN_MODULES` derivado em código + `/api/session` com `tenant.plan/modules`
  + `scripts/migrate_plans.py`.
- **CRM-2**: `bot_engine_dialogflow.py` (conector REST DetectIntent) + dispatcher
  `process_bot_message_async` em `bot_service.py` (gate LGPD local ANTES do
  motor; handoff via `handoff_bot_key`→department; fallback educado na 1ª falha,
  handoff na 2ª) + guard de redelivery no webhook + `tools/sim_cx_flow.py`.

## FASE CONJUNTA (após SYNC-1)

1. Tenant `varizemed-test` (plano `ai_custom`) via painel super-admin.
2. Setor "Recepção" com `bot_key=sac`.
3. `scripts/set_tenant_ai.py` grava `settings.ai`; ligar `bot_enabled` do tenant.
4. **Gate staging**: canal fake + webhook simulado → DetectIntent real → resposta
   da Val gravada (envio Meta falha por token fake — esperado).
5. Número DDD 71 real: adicionar na WABA, registrar (PIN), `subscribed_apps`.
6. Canal standard no CRM (prod) com access_token do canal → `phone_routing` automático.
7. E2E real: LGPD → Val → convênio → handoff → pool Recepção → operador responde.

## Hardening antes da Varizemed REAL (gate de go-live)

TTL nas coleções da ValMemory; máscara de PII em todos os logs; criptografia
extra de campos sensíveis + audit de leitura; residência de dados (avaliar
southamerica-east1); token Meta via secret/KMS; aviso/política LGPD da própria
Varizemed + DPA; CI das functions.

## Pendências de input do PO

1. ID real do `AI_PROJECT` + billing.
2. Número DDD 71 completo (E.164) + em qual WABA entra + quem tem o PIN.
3. Email do admin do tenant `varizemed-test`.
4. Texto do aviso LGPD + URL de política pro teste.
5. Confirmar mapa de planos legados (`enterprise→enterprise_ai`, `premium→ai_custom`).
