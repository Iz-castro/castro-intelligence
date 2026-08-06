# Runbook — Cutover prod (Fase 4)

> ⚠️ **STALE (marcado 2026-08-06):** escrito pra era SP (`project-26fb9c99-8ee9-4179-aef`
> / `southamerica-east1`). Prod hoje = Oregon (`project-4a851bf9-f475-418c-800` /
> `us-west1`) e o trafego e PINADO por revisao — deploy sobe a 0% e a frase
> "Default sem flag = 100%" abaixo NAO vale mais. Pra deploy de rotina use
> [DEPLOY_CLOUDRUN_A.md](DEPLOY_CLOUDRUN_A.md); este doc serve so como referencia
> do PROCEDIMENTO de cutover/wipe, traduzindo projeto/regiao.

> Procedimento de cutover do tenant default em **producao** apos
> aprovacao da Meta App Review. Apaga dados acumulados em prod (que
> hoje sao apenas dados de Fase 1, sem coexistence) e prepara o
> ambiente pra reonboarding com a arquitetura final.
>
> **Pre-requisito:** Meta App Review aprovado (BSP permission liberada
> pro app `1434723791183375`). Sem isso, channels coexistence nao
> conseguem enviar template e o reonboarding falha.

## 0. Pre-flight checklist

Antes de tocar em prod, garantir em staging:

- [ ] e2e PASSED 9/9 mais recente (`python -m scripts.e2e_test_staging`)
- [ ] Cloud Scheduler em staging rodando (`gcloud scheduler jobs describe castro-crm-staging-health-check ...`)
- [ ] Working tree em `develop` limpo
- [ ] Conta gcloud ativa: `rafaluisc@outlook.com`
  ```powershell
  gcloud config get-value account
  ```

## 1. Backup defensivo (5-15 min)

Mesmo que o wipe preserve `tenants/{tid}` e `audit_log` por default,
exporta tudo antes pra segurança:

```powershell
# Cloud Firestore export pro bucket GCS de backups
gcloud firestore export `
  gs://project-26fb9c99-8ee9-4179-aef-firestore-backups/cutover-$(Get-Date -Format yyyy-MM-dd-HHmm) `
  --project=project-26fb9c99-8ee9-4179-aef
```

Aguardar conclusão (operação assíncrona; `gcloud firestore operations
describe ...` pra acompanhar). Se algo der errado, restore via
`gcloud firestore import gs://...`.

## 2. Deploy do código mais recente em prod

```powershell
# Garantir que develop tem o que vai pra prod
git status --short  # deve estar limpo
git log --oneline -5

# Deploy — use o CAMINHO ABSOLUTO da raiz como --source. NAO use '.': se o shell
# estiver em frontend/ (ex.: apos npm run build) o gcloud cai em Buildpacks e falha.
gcloud run deploy castro-crm `
  --source C:\Rafael\castro-intelligence `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef `
  --quiet
```

A nova revision NAO recebe trafego se houver flag `--no-traffic` —
mas pra cutover queremos 100% imediato (substitui revision velha).
Default sem flag = 100%.

## 3. Wipe controlado do tenant prod

**ATENÇÃO:** este passo é destrutivo. Faça apenas após backup (passo 1).

```powershell
# 3.1 — Dry-run primeiro (SEMPRE)
$env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
$env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"

./.venv/Scripts/python.exe -m scripts.wipe_all_collections --tenant-id hubloc

# Revise o plano de cima a baixo. Numeros batem com o esperado?

# 3.2 — Wipe real (preserva users/departments/audit_log por default).
# Inclui --purge-channels pra limpar canais antigos da Fase 1
# (que serao recriados via reonboarding no passo 5).
./.venv/Scripts/python.exe -m scripts.wipe_all_collections `
  --tenant-id hubloc `
  --purge-channels `
  --confirm
# Vai pedir interativamente: digitar "WIPE" pra confirmar.
```

**Se quiser resetar tudo (incluindo users/departments — admin sera
re-bootstrap automaticamente no proximo deploy):**

```powershell
./.venv/Scripts/python.exe -m scripts.wipe_all_collections `
  --tenant-id hubloc `
  --purge-channels `
  --purge-users `
  --confirm
```

`audit_log` mantém-se por default (LGPD: trilha de auditoria sobrevive
ao wipe). Use `--purge-audit-log` apenas se realmente quiser apagar.

## 4. Re-bootstrap (automatico no proximo deploy ou primeira request)

O `@app.on_event("startup")` executa:
- `bootstrap_default_tenant()` — recria `tenants/hubloc` se foi apagado (não foi, default preserva)
- `bootstrap_departments()` — recria 4 departamentos padrão (`comercial`, `financeiro`, `administrativo`, `sac`) — só recria se foram apagados
- `bootstrap_admin_user()` — sincroniza admin Firebase (`BOOTSTRAP_ADMIN_EMAIL` vira admin do tenant)
- `bootstrap_default_channel()` — popula `phone_routing` e cria canal default flat se ausente

**Se rodou com `--purge-users`:** abrir o CRM e fazer login com
`BOOTSTRAP_ADMIN_EMAIL` — o admin é recriado automaticamente. Demais
operadores precisam ser re-cadastrados manualmente pela UI admin.

## 5. Reonboarding dos canais

### 5.1 Canal standard (Cloud API direto pela Meta)

1. Login no CRM como admin.
2. Embedded Signup pelo painel admin → escolher channel_type=`standard`.
3. Confirma webhook subscribed e WABA visivel.
4. Smoke test: enviar 1 mensagem template de teste pra um numero proprio.

### 5.2 Canal coexistence (numero ja em uso no app WhatsApp Business)

Pre-requisito: Meta App Review aprovado (BSP permission). Sem isso o
fluxo Embedded Signup coexistence retorna #131009 ou similar.

1. Embedded Signup → channel_type=`coexistence`.
2. Cliente autoriza coexistence pelo Business Manager.
3. Token coexistence salvo com `token_expires_at` (~60 dias).
4. Smoke test: aguardar mensagem inbound e verificar `channel_owner_user_id` populado em `wa_messages`.

## 6. Replicar Cloud Scheduler em prod (com OIDC + Secret Manager)

Em staging foi validado o pattern OIDC nativo (Cloud Scheduler) +
shared secret no Secret Manager (fallback pra dev/CI). Mesmo pattern
em prod.

### 6.1 SA dedicado pro Cloud Scheduler

```powershell
gcloud iam service-accounts create castro-crm-prod-scheduler `
  --display-name='Castro CRM prod scheduler invoker' `
  --project=project-26fb9c99-8ee9-4179-aef

gcloud run services add-iam-policy-binding castro-crm `
  --member='serviceAccount:castro-crm-prod-scheduler@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com' `
  --role='roles/run.invoker' `
  --region=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef
```

### 6.2 Secret Manager (shared secret, fallback)

```powershell
# Gera valor seguro (32 chars urlsafe)
$NEW_SECRET = python -c 'import secrets; print(secrets.token_urlsafe(32))'

gcloud secrets create castro-crm-prod-internal-cron-secret `
  --replication-policy='automatic' `
  --project=project-26fb9c99-8ee9-4179-aef

# Adiciona valor como version 1 (sem expor no shell history)
$NEW_SECRET | gcloud secrets versions add castro-crm-prod-internal-cron-secret `
  --data-file=- --project=project-26fb9c99-8ee9-4179-aef

# Cloud Run SA precisa de leitura
gcloud secrets add-iam-policy-binding castro-crm-prod-internal-cron-secret `
  --member='serviceAccount:castro-crm-run@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com' `
  --role='roles/secretmanager.secretAccessor' `
  --project=project-26fb9c99-8ee9-4179-aef
```

### 6.3 Configurar env vars do Cloud Run prod

```powershell
gcloud run services update castro-crm `
  --region=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef `
  --update-env-vars="CRON_OIDC_AUDIENCE=https://<URL_PROD>/api/internal/cron/health-check,CRON_OIDC_SERVICE_ACCOUNT=castro-crm-prod-scheduler@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com" `
  --update-secrets='INTERNAL_CRON_SECRET=castro-crm-prod-internal-cron-secret:latest'
```

### 6.4 Criar job Cloud Scheduler com OIDC

```powershell
gcloud scheduler jobs create http castro-crm-prod-health-check `
  --location=southamerica-east1 `
  --schedule='0 9 * * *' `
  --time-zone='America/Sao_Paulo' `
  --uri='https://<URL_PROD>/api/internal/cron/health-check' `
  --http-method=POST `
  --update-headers='Content-Type=application/json' `
  --oidc-service-account-email='castro-crm-prod-scheduler@project-26fb9c99-8ee9-4179-aef.iam.gserviceaccount.com' `
  --oidc-token-audience='https://<URL_PROD>/api/internal/cron/health-check' `
  --message-body='{}' `
  --project=project-26fb9c99-8ee9-4179-aef
```

Note: o backend aceita OIDC Bearer **OU** X-Cron-Secret (precedence:
OIDC primeiro). Configurando `--oidc-*`, o Cloud Scheduler envia
Authorization: Bearer e o backend valida via `google.oauth2.id_token`
(issuer + audience + email do SA).

### 6.5 Trigger manual pra validar

```powershell
gcloud scheduler jobs run castro-crm-prod-health-check `
  --location=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef

# Aguardar ~5s e validar Firestore
./.venv/Scripts/python.exe -c "import os; os.environ['FIRESTORE_PROJECT_ID']='project-26fb9c99-8ee9-4179-aef'; os.environ['FIRESTORE_COLLECTION_PREFIX']='castro_crm'; from firestore_common import get_firestore_client, collection_name; c=get_firestore_client(); d=c.collection(collection_name('tenants')).document('hubloc').collection('health_status').document('current').get().to_dict(); print('checked_at=', d.get('checked_at'))"
```

## 7. Smoke test final

- [ ] Dashboard de auditoria carrega sem erros (rota admin).
- [ ] `/api/wa/usage/current-month` retorna 200 com mes corrente.
- [ ] `tenants/hubloc/health_status/current` foi populado pelo cron run manual do passo 6.
- [ ] Canal standard envia template de teste com sucesso.
- [ ] Canal coexistence recebe mensagem inbound (operador manda do celular).

## 8. Rollback (se precisar)

Cenario: cutover deu errado, queremos voltar pro estado pre-wipe.

```powershell
# 1. Importa o backup feito no passo 1
gcloud firestore import `
  gs://project-26fb9c99-8ee9-4179-aef-firestore-backups/cutover-<timestamp> `
  --project=project-26fb9c99-8ee9-4179-aef

# 2. Volta a revision Cloud Run anterior
gcloud run services update-traffic castro-crm `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef `
  --to-revisions <REVISION_ANTERIOR>=100
```

## 9. Pos-cutover

- [ ] Atualizar `RETOMAR.md` (interno) com hash do commit + revision pos-cutover.
- [ ] Communicar cliente que pode usar o canal novamente.
- [ ] Monitorar logs do Cloud Run nas primeiras 24h (filtro: severity>=WARNING).
- [ ] Confirmar primeira execucao automatica do Cloud Scheduler 09:00 BRT do dia seguinte.

## Apendice — Por que NAO usar firestore.recursiveDelete()?

Firestore Admin SDK Python v2.x nao expoe recursive_delete nativamente
(existe no Node SDK e gcloud CLI). O `wipe_all_collections.py` usa
implementacao custom que percorre subcolecoes ate o fim antes de
apagar o doc parent — comportamento equivalente, com o bonus de poder
preservar coletivamente colecoes especificas (`users`, `audit_log`)
via flags.
