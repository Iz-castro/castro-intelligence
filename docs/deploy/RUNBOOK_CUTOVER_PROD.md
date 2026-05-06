# Runbook — Cutover prod (Fase 4)

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

# Deploy
gcloud run deploy castro-crm `
  --source . `
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

## 6. Replicar Cloud Scheduler em prod

```powershell
# Setar secret no Cloud Run prod (gerar valor novo, nao reusar staging)
$NEW_SECRET = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})

gcloud run services update castro-crm `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef `
  --update-env-vars "INTERNAL_CRON_SECRET=$NEW_SECRET"

# Idealmente, mover pra Secret Manager:
#   gcloud secrets create castro-crm-internal-cron-secret --data-file=- <<<$NEW_SECRET
#   gcloud run services update castro-crm --update-secrets INTERNAL_CRON_SECRET=castro-crm-internal-cron-secret:latest

# Criar job Cloud Scheduler em prod
gcloud scheduler jobs create http castro-crm-prod-health-check `
  --location=southamerica-east1 `
  --schedule='0 9 * * *' `
  --time-zone='America/Sao_Paulo' `
  --uri='https://<URL_PROD>/api/internal/cron/health-check' `
  --http-method=POST `
  --headers="X-Cron-Secret=$NEW_SECRET,Content-Type=application/json" `
  --message-body='{}' `
  --project=project-26fb9c99-8ee9-4179-aef

# Trigger manual pra validar
gcloud scheduler jobs run castro-crm-prod-health-check `
  --location=southamerica-east1 `
  --project=project-26fb9c99-8ee9-4179-aef
```

**TODO antes de prod real:** migrar pra OIDC token (Cloud Scheduler
suporta nativamente — endpoint validaria issuer+SA, eliminando o
header customizado).

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
