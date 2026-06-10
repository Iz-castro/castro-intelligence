# Diário 2026-06-10 — Migração GCP → Oregon (conta Castro)

## Resumo

Migramos toda a infra do CRM da **conta pessoal** `rafaluisc@outlook.com`
(projeto `project-26fb9c99-8ee9-4179-aef`, `southamerica-east1`) para a
**conta Castro** (`castrointelligence@gmail.com`), em **projeto novo** com
**Cloud Run + Firestore em `us-west1` (Oregon)**. Decisão: começar com
**Firestore VAZIO** (sem migração de dados — era QA, nada real de prod).
**Validado end-to-end via coex.** Runbook completo: [docs/deploy/MIGRACAO_GCP_OREGON_CHECKLIST.md](../deploy/MIGRACAO_GCP_OREGON_CHECKLIST.md).

## Estado atual (FUNCIONANDO ✅)

- **URL:** https://castro-crm-28179318848.us-west1.run.app
- **Projeto:** `project-4a851bf9-f475-418c-800` (number `28179318848`), `us-west1`
- **Firestore** us-west1 (Native) + **PITR**; prefixo `castro_crm`; tenant `hubloc`
- **Login** Email + Google OK; **rules + indexes** publicados (whitelist inclui `castrointelligence@gmail.com`)
- **Coex Embedded Signup** validado (número +55 31 9934-6195) → **inbound + troca de mensagens OK** (fix ES v4 leu a WABA da session-info, granular voltou só `public_profile`)
- **Webhook Meta repontado** pra nova URL (cutover de mensagens feito — app antigo não recebe mais)
- **Cloud Scheduler** `castro-crm-expire-takeovers` (*/30, OIDC) validado (200)
- **Scaling** rev `castro-crm-00004-9w5`: 2Gi / cpu 2 / **conc 8** / min 1 / max 5 / cpu-boost

## IAM (projeto novo)

- SA runtime `castro-crm-run@...`: `datastore.user`, `secretmanager.secretAccessor`, `storage.objectAdmin`, `logging.logWriter`, **`firebaseauth.admin`**
- SA scheduler `castro-crm-prod-scheduler@...`: `run.invoker`
- SA Cloud Build (`28179318848-compute@developer...`): `cloudbuild.builds.builder`, `artifactregistry.writer`, `logging.logWriter`
- Owners: `rafaluisc@outlook.com` + `izaeldecastro@gmail.com`; `izaeldecastro` tem `firebase.admin`

## Secrets (Secret Manager, copiados VERBATIM do projeto antigo)

`castro-crm-secret-key`, `castro-crm-whatsapp-token`, `castro-crm-whatsapp-verify-token`,
`castro-crm-whatsapp-app-secret` (origem v16), `castro-crm-meta-app-secret`, `castro-crm-system-user-token`.
Config de env (não-secreto) em [docs/deploy/env.oregon.yaml](../deploy/env.oregon.yaml).

## ⚠️ Gotchas / lições (LER)

1. **`firebaseauth.admin` na SA runtime:** o SA antigo tinha; eu esqueci no 1º grant.
   Sem ele o backend não grava custom claims (`set_tenant_claims` → `INSUFFICIENT_PERMISSION`)
   → claims não setam → frontend nega TODOS os snapshots. **Corrigido.**
2. **Scaling: copiar do PROD LIVE, não do `deploy.ps1`** (stale). Eu deployei
   1Gi/cpu1/**conc1**/max3 → "Rate exceeded"/"no available instance". Prod live =
   **2Gi/cpu2/conc8/max5/cpu-boost**. Corrigido.
3. **Token staleness (PENDENTE — fix amanhã):** 1º login E troca de papel exigem
   re-login pro claim novo entrar no TOKEN (o claim é setado no servidor durante o
   login, mas o token daquele login foi emitido antes). Comportamento do app
   (mesmo código do prod), só dói porque TODOS são novos de uma vez.
   **Fix planejado:** frontend chama `getIdToken(true)` após o provisionamento,
   antes de montar os listeners. Mitigação manual hoje = setar claim via Identity
   Toolkit API (ver "Comandos úteis").
4. **ES coex v4 ESTÁ commitado** (webhook.py + App.tsx leem WABA da session-info) —
   confirmado funcionando. A nota de memória "falta commitar" estava desatualizada.
5. **STANDARD está em OUTRA WABA:** o env `WHATSAPP_PHONE_NUMBER_ID=1070927076104221` /
   `WHATSAPP_WABA_ID=1633469507697155` ("Castro Intelligence Chat") são **STALE** —
   essa WABA tem **0 números**. O standard REAL é **phone_number_id `1199019616617623`**
   na WABA **`1573507174381657` ("Castro Intelligence SAC", portfólio Castro Operações)**,
   que os tokens do app **não acessam**. → re-onboardar o standard via **ES standard**.
   O canal standard `id=1` que o bootstrap criou (phone `1070927076104221`) é **bogus**
   (não roteia) — limpar.

## Pendente / próximos passos

1. **[EMPRESA, hoje]** Onboardar o número **STANDARD** via ES standard (Rafal foi presencialmente).
2. **[amanhã]** Fix do **token-refresh** (1º login seamless, sem re-login manual).
3. **Re-onboardar os DEMAIS operadores (coex)** — Firestore vazio; eventos de números
   não onboardados chegam como `no_channel_for_phone` e ficam **enfileirados** (não perdem),
   processam quando o número é onboardado.
4. **Limpar** canal standard bogus (`id=1`, phone `1070927076104221`) + remover
   `WHATSAPP_PHONE_NUMBER_ID/WABA_ID` do env (standard vem por ES, não por bootstrap).
5. **Frente LGPD** (transferência internacional Brasil→EUA): RoPA/RIPD + DPA Google/Meta + comunicar cliente.
6. Migrar **staging**; **desativar projeto antigo** (após validar); atualizar `CLAUDE.md` (região/projeto) no cutover final.
7. Verificar: **media placeholders** do histórico resolvendo (o fix de scaling deve ajudar — webhooks de mídia estavam sendo derrubados); reconciliar o `channel id=1` (standard bootstrap vs coex).

## Comandos úteis

**Deploy (do diretório do repo, conta Castro ativa no gcloud):**
```
gcloud run deploy castro-crm --source . --project project-4a851bf9-f475-418c-800 `
  --region us-west1 `
  --service-account castro-crm-run@project-4a851bf9-f475-418c-800.iam.gserviceaccount.com `
  --allow-unauthenticated `
  --memory=2Gi --cpu=2 --concurrency=8 --min-instances=1 --max-instances=5 --cpu-boost --timeout=300 `
  --env-vars-file docs/deploy/env.oregon.yaml `
  --set-secrets "SECRET_KEY=castro-crm-secret-key:latest,WHATSAPP_TOKEN=castro-crm-whatsapp-token:latest,WHATSAPP_VERIFY_TOKEN=castro-crm-whatsapp-verify-token:latest,WHATSAPP_APP_SECRET=castro-crm-whatsapp-app-secret:latest,META_APP_SECRET=castro-crm-meta-app-secret:latest,WHATSAPP_SYSTEM_USER_TOKEN=castro-crm-system-user-token:latest"
```
(⚠️ `--set-secrets` precisa de aspas no PowerShell — vírgula é operador de array.)

**Setar claim de um usuário manualmente (mitigação do token staleness), via bash:**
```
PROJECT=project-4a851bf9-f475-418c-800
TOKEN=$(gcloud auth print-access-token)
# achar uid:
curl -s -X POST "https://identitytoolkit.googleapis.com/v1/projects/$PROJECT/accounts:lookup" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  -d '{"email":["EMAIL_AQUI"]}'
# setar (trocar UID e role):
curl -s -X POST "https://identitytoolkit.googleapis.com/v1/projects/$PROJECT/accounts:update" \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: $PROJECT" -H "Content-Type: application/json" \
  -d '{"localId":"UID_AQUI","customAttributes":"{\"tenant_id\":\"hubloc\",\"role\":\"admin\"}"}'
# depois o usuário faz 1 logout/login. (x-goog-user-project e obrigatorio senao da quota error)
```

**Ver logs do webhook / erros:**
```
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="castro-crm"' --project project-4a851bf9-f475-418c-800 --freshness=15m --order=desc --limit=40 --format="value(timestamp, httpRequest.status, httpRequest.requestUrl, textPayload)"
```
