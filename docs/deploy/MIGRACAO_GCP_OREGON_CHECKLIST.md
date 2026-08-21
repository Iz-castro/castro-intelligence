# Checklist de migração — GCP/Firebase para conta Castro Intelligence (Oregon / us-west1)

> ✅ **HISTÓRICO (marcado 2026-08-06):** a migração TÉCNICA foi concluída — prod
> roda no Oregon desde 2026-06. Mantido como registro. Para deploy de rotina ver
> [DEPLOY_CLOUDRUN_A.md](DEPLOY_CLOUDRUN_A.md). Os itens jurídicos/LGPD abaixo
> têm status próprio — conferir antes de assumir que seguem pendentes.
>
> ⚠️ **Status em 2026-08-21:** todo item que cita `deploy.ps1`/`deploy.sh` ou
> flags de scaling no deploy está **SUPERADO** (Fases 8 e 9) — os scripts foram
> removidos do repo em 2026-08-06 e o deploy de rotina é `--source` puro.

> **Decisão:** mover o projeto da conta pessoal `rafaluisc@outlook.com`
> (projeto `project-26fb9c99-8ee9-4179-aef`, região `southamerica-east1`)
> para a conta **`castrointelligence@gmail.com`**, em **projeto NOVO**, com
> **Cloud Run + Firestore em `us-west1` (Oregon)**.
>
> Estratégia = **Opção C** (rebuild + migração completa de dados + nova
> região). Firestore é imutável por projeto, então não há "mover" — é
> criar novo e migrar.
>
> ⚠️ **LGPD:** Oregon move PII (inclui dados sensíveis de clínicas) do
> Brasil para os EUA → **transferência internacional (art. 33 LGPD)**. A
> frente jurídica abaixo é **obrigatória** e roda em paralelo à técnica.

---

## ⛔ Fase 0 — Decisões e pré-requisitos — RESOLVIDO (2026-06-10)

- [x] **Billing:** conta Castro já tem billing account ativa.
- [x] **Projeto novo criado:** "Castro CRM" — Project ID
      `project-4a851bf9-f475-418c-800`, Project Number `28179318848`.
      ⚠️ **CONFIRMAR que ID e número estão completos** (copiar exato do
      Console / `gcloud projects list` — o copy-paste parece cortado no fim;
      número costuma ter 12 dígitos).
- [x] **Firestore location** = `us-west1` (regional). ⚠️ imutável.
- [x] **Prefixo de coleção** = `castro_crm` (mantém).
- [x] **Tenant default** = `hubloc` (mantém).
- [x] **Login** = Google sign-in + Email (sem migração de senha).
- [x] **Dados/mídia:** começar **VAZIO** — nada de prod a migrar.
- [x] **App Meta:** reusar a existente (App ID `1434723791183375`,
      Business `877897608035564`, WABA `1633469507697155`) — só reaponta
      webhook, não cria app nova.
- [ ] **`BOOTSTRAP_ADMIN_EMAIL`** definitivo: qual conta Castro vira o 1º
      admin? (pendente)

---

## ⚖️ Fase 1 — LGPD / Compliance (começar JÁ, corre em paralelo) — OBRIGATÓRIA

- [ ] **Base legal de transferência internacional (art. 33):** confirmar
      aceite do **Google Cloud Data Processing Addendum + SCCs** e o adendo
      de transferência internacional (cobre Brasil→EUA). Idem com a Meta.
- [ ] **Reescrever RoPA** ([docs/compliance/LGPD_RoPA_RIPD_INTERNO.md](../compliance/LGPD_RoPA_RIPD_INTERNO.md)
      e `_CLIENTE.md`): mudar residência de dados p/ EUA, recategorizar
      risco, atualizar medidas. Fechar os gaps §1.3 e §6.
- [ ] **Reescrever RIPD** (relatório de impacto) à luz da nova residência.
- [ ] **Comunicar/obter anuência do cliente controlador (Hubloc)** —
      aditivo contratual + atualização da política de privacidade aos
      titulares.
- [ ] **Nova ADR** documentando a decisão Brasil→Oregon (motivo, custo,
      proporcionalidade) + revisar ADR 0002 (LGPD coex) e 0007 (isolamento).
- [ ] Confirmar que **criptografia em repouso** (default Firestore) e
      **audit_log** continuam garantidos no novo banco.

---

## 🏗️ Fase 2 — Provisionar o novo projeto (Castro / Oregon) — ✅ executado 2026-06-10

- [x] Projeto `project-4a851bf9-f475-418c-800` (Castro CRM) + billing vinculada.
- [x] Habilitar APIs: run, firestore, firebase, firebasestorage, storage,
      secretmanager, cloudscheduler, artifactregistry, cloudbuild, iam,
      identitytoolkit.
- [ ] Criar **app Firebase (web)** → coletar `apiKey`, `authDomain`,
      `appId`, `messagingSenderId`, `measurementId`. **(PRÓXIMO — Fase 2b)**
- [x] Criar **Firestore Native em `us-west1`** (location imutável confirmada).
- [x] **PITR ON** (7 dias).
- [x] Criar **bucket de mídia** (`...-castro-crm-media`) vazio em us-west1.
- [x] Criar **bucket de backups** (`...-firestore-backups`) em us-west1.

---

## 🔐 Fase 3 — Identidade & IAM — ✅ parcial 2026-06-10

- [x] SA `castro-crm-run@project-4a851bf9-f475-418c-800.iam...` + roles:
      `datastore.user`, `secretmanager.secretAccessor`, `storage.objectAdmin`,
      `logging.logWriter`, **`firebaseauth.admin`** (⚠️ esquecido no 1º grant —
      sem ele o backend não grava custom claims; o SA antigo tinha. Adicionado).
- ⚠️ SA antigo tinha também `roles/speech.client` (Google Cloud Speech) — NÃO
      replicado. Transcrição usa Whisper local/offline, então provável que não
      precise; se áudio falhar, conceder `speech.client`.
- [x] SA `castro-crm-prod-scheduler@...` criada.
      - [ ] `run.invoker` (OIDC) — aplicar **após** o Cloud Run existir (Fase 9/10).
- [ ] Compute default SA: `storage.objectViewer`, `artifactregistry.writer`,
      `logging.logWriter` (p/ Cloud Build) — aplicar antes do 1º deploy.
- [x] Owner do projeto = `rafaluisc@outlook.com` (aceito) sob conta Castro.

---

## 🗝️ Fase 4 — Secrets — ✅ copiados e verificados 2026-06-10

Copiados VERBATIM old→new via pipe byte-clean (`access | add --data-file=-`),
verificados por tamanho de bytes (idênticos). São **6** (não 4):

- [x] `castro-crm-secret-key` (64 bytes)
- [x] `castro-crm-whatsapp-token` (203 bytes)
- [x] `castro-crm-whatsapp-verify-token` (19 bytes)
- [x] `castro-crm-whatsapp-app-secret` (32 bytes — **copiado da versão 16**, que prod usa)
- [x] `castro-crm-meta-app-secret` (32 bytes)
- [x] `castro-crm-system-user-token` (205 bytes)

SA `castro-crm-run` lê todos via `secretmanager.secretAccessor` no nível do
projeto (Fase 3). `INTERNAL_CRON_SECRET` não é necessário (prod usa OIDC).
⚠️ Incidente de leak `META_APP_SECRET` em logs httpx — manter httpx silenciado.

---

## 📦 Fase 5 — Firestore: COMEÇAR VAZIO (sem migração de dados)

> Decisão (2026-06-10): não há dado real de prod no projeto atual (é tudo
> QA/teste). Não migramos nada — banco novo nasce vazio. Projeto antigo
> fica intacto como rede de segurança.

- [x] Criar Firestore (Native) em `us-west1` + **PITR ON** (Fase 2).
- [x] Deploy de **índices**: `firebase deploy --only firestore:indexes` ✅
- [x] Deploy de **rules**: `firestore.rules` (whitelist + `castrointelligence@gmail.com`) ✅
      — `storage.rules` pulado (sem bucket Firebase Storage; mídia é backend/GCS).
- [x] Bootstrap do tenant `hubloc` + admin no 1º startup do Cloud Run.
- [ ] `phone_routing`: validar no 1º inbound (Firestore vazio → fallback `hubloc`).
- [x] (Sem export/import e sem reimport de backup.)

---

## 🖼️ Fase 6 — Mídia: PULAR (começar vazio)

> Decisão (2026-06-10): não transferir mídia. Bucket novo nasce vazio em
> `us-west1`; mídia nova entra a partir do 1º webhook no projeto novo.

- [ ] Apenas **criar o bucket vazio** em us-west1 (feito na Fase 2).
- [ ] Sem `gsutil cp`. Mídia antiga fica no projeto antigo (consistente,
      pois o Firestore novo também nasce vazio — sem refs penduradas).

---

## 👤 Fase 7 — Firebase Auth — ✅ login funcionando 2026-06-10

- [x] Email + Google sign-in habilitados; authorized domain
      `castro-crm-28179318848.us-west1.run.app` adicionado.
- [x] Whitelist `ALLOWED_FIREBASE_EMAILS` (+`castrointelligence@gmail.com`)
      no env e em [firestore.rules](../../firestore.rules) (publicada).
- [x] Login validado (rafaluisc) — snapshot de conversations/contacts OK.
- ⚠️ **GOTCHA (gap da Fase 3):** a SA de runtime `castro-crm-run` PRECISA de
      `roles/firebaseauth.admin` p/ o backend gravar custom claims
      (`set_tenant_claims`). Sem ela → `INSUFFICIENT_PERMISSION`, claims não
      setam, e o frontend nega os snapshots. **Corrigido** (role concedida).
- ⚠️ O app só sincroniza claims no 1º provisionamento; usuários criados
      ANTES do fix precisam de **1 logout/login** (token novo p/ refletir os
      claims já gravados). storage.rules pulado (sem Firebase Storage).

---

## ⚙️ Fase 8 — Config da aplicação (.env / Cloud Run env)

- [ ] Novo `.env` (gitignored) com: `FIRESTORE_PROJECT_ID`, `FIREBASE_WEB_*`
      (novos), `FIREBASE_STORAGE_BUCKET`, `GCS_MEDIA_BUCKET`,
      `BOOTSTRAP_ADMIN_EMAIL`, `CORS_ORIGINS` (nova URL),
      `CRON_OIDC_AUDIENCE` (nova URL), `CRON_OIDC_SERVICE_ACCOUNT` (novo SA),
      `GOOGLE_CHAT_PROJECT_NUMBER` (novo).
- [x] ~~Atualizar **região default** em `deploy.sh` / `deploy.ps1`~~ —
      **SUPERADO (2026-08-06):** os dois scripts foram **REMOVIDOS do repo**
      (clobberavam env/secrets/scaling de prod). Deploy hoje = `gcloud run deploy
      --source <caminho absoluto>` puro → [DEPLOY_CLOUDRUN_A.md](DEPLOY_CLOUDRUN_A.md).
- [ ] Atualizar scripts e2e/diag com nova URL/project
      (`scripts/e2e_test_staging.py`, `check_whatsapp_coexistence.py`).

---

## 🚀 Fase 9 — Deploy Cloud Run (Oregon) — ✅ 1º deploy OK 2026-06-10

- [x] Deploy `castro-crm` em `us-west1` via `gcloud run deploy --source`
      (env-vars-file `env.oregon.yaml` + `--set-secrets` p/ os 6 secrets).
      Revisão inicial `castro-crm-00001-h6d`.
      ⚠️ **Scaling: copiar do PROD LIVE, não do deploy.ps1** (que é stale). Eu
      deployei errado (1Gi/1cpu/max3/**conc1**) → "Rate exceeded"/"no available
      instance" na abertura do CRM. Prod live = **2Gi / cpu 2 / max 5 / conc 8 /
      cpu-boost / 300s**. Corrigido na rev `00004-9w5`. Deploy futuro DEVE incluir
      `--memory=2Gi --cpu=2 --concurrency=8 --min-instances=1 --max-instances=5 --cpu-boost`.
      ⚠️ **SUPERADO (2026-08-06) só a última frase:** deploy de ROTINA não leva
      flag nenhuma de scaling/env/secret — `--source` puro **preserva** a config
      da revisão anterior, e repassar as flags é justamente o que clobbera prod.
      As flags acima valem apenas pra **bootstrap de um serviço novo**.
- [x] **URL nova:** `https://castro-crm-28179318848.us-west1.run.app`
- [x] Health-check OK: `GET /` 200, `GET /api/client-config` 200 (env e
      firebase_web_config do projeto novo carregados, prefixo castro_crm).
- [ ] `castro-crm-staging` — depois (após validar prod).
- Gotcha resolvido: `--set-secrets` precisa de **aspas** no PowerShell
      (vírgula é operador de array → quebra o arg).

---

## ⏰ Fase 10 — Cloud Scheduler — ✅ 2026-06-10

- [x] `CRON_OIDC_AUDIENCE` setado no serviço (rev `castro-crm-00002-sls`).
- [x] `run.invoker` concedido à SA `castro-crm-prod-scheduler`.
- [x] Job `castro-crm-expire-takeovers` (*/30, America/Sao_Paulo) criado em
      us-west1 c/ OIDC. **Validado: force-run → HTTP 200.**
- Nota: prod só tinha 1 job real (o `health-check` antigo era de staging).
      `INTERNAL_CRON_SECRET` não usado (OIDC).

---

## 📲 Fase 11 — Meta / WhatsApp — ✅ webhook repontado 2026-06-10 (cutover FEITO)

- [x] **Webhook repontado via Graph API** → `https://castro-crm-28179318848.us-west1.run.app/webhook`.
      Meta retornou `{"success":true}` (handshake validado). Campos preservados:
      messages, smb_message_echoes, smb_app_state_sync, history, account_update,
      message_template_status_update. ⚠️ App antigo NÃO recebe mais (1 callback só).
- [x] **Teste e2e VALIDADO (coex) 2026-06-10:** ES do número +55 31 9934-6195 →
      WABA lida da **session-info** (granular voltou só `public_profile` — o fix
      v4 salvou) → canal coex criado (id=1, waba=985540003931801) → subscription
      OK → smb_app_state_sync + 2 contatos importados → **inbound POST /webhook 200
      + troca de mensagens funcionando**. ✅
- [x] **Embedded Signup:** nova URL nos App Domains / login-para-empresas.
- [ ] **Standard:** está em OUTRA WABA (SAC `1573507174381657`, Castro Operações)
      que os tokens não acessam → re-onboardar via ES standard quando precisar.

---

## 💬 Fase 12 — Google Chat (se em uso)

- [ ] Atualizar webhook URL + `GOOGLE_CHAT_PROJECT_NUMBER`; reinvitar bot
      se necessário.

---

## 🌐 Fase 13 — DNS / domínio customizado (se houver)

- [ ] Apontar domínio/CNAME p/ o novo Cloud Run (us-west1).

---

## ✅ Fase 14 — Validação pós-cutover

- [ ] Login com conta Castro + acesso admin OK.
- [ ] WhatsApp inbound chega / outbound envia / mídia carrega.
- [ ] Listeners realtime OK; **medir latência do Brasil** (esperar +~150-180ms).
- [ ] Cloud Scheduler rodando (`health_status` populando).
- [ ] PITR ativo no banco novo.
- [ ] Contagem de dados confere.
- [ ] **Isolamento multi-tenant / rules reconfirmado** (gates LGPD).

---

## 🔁 Fase 15 — Cutover & rollback

- [ ] Janela de baixa demanda (madrugada BRT).
- [ ] **Não deletar** o projeto antigo — manter por N dias como rollback +
      PITR.
- [ ] Plano de reversão escrito (reapontar webhook Meta de volta).

---

## 🧹 Fase 16 — Decomissionar o antigo (após dias de validação)

- [ ] Exportar **logs históricos** (Cloud Logging é por projeto, não migra).
- [ ] Preservar backups/audit pela retenção legal.
- [ ] Remover acessos da conta pessoal `rafaluisc@outlook.com`.

---

## 📝 Fase 17 — Docs & housekeeping

- [x] Atualizar [CLAUDE.md](../../CLAUDE.md) (região, project) e runbooks —
      **FEITO**; o runbook de deploy vigente é
      [DEPLOY_CLOUDRUN_A.md](DEPLOY_CLOUDRUN_A.md) (2026-08-06).
      ⚠ `.env.example` / scripts: verificar caso a caso.
- [ ] Reescrever/atualizar [RUNBOOK_CUTOVER_PROD.md](RUNBOOK_CUTOVER_PROD.md)
      com novo project/região — **não reescrito**; recebeu banner **STALE** em
      2026-08-06 e no dia a dia foi substituído por DEPLOY_CLOUDRUN_A.md.
- [ ] Diário de migração em `docs/internal/`.

---

### Itens de maior risco (não erre nestes)
1. **Firestore location** us-west1 é imutável — confirme antes de criar.
2. **Webhook Meta** reapontado — senão o CRM para de receber mensagens.
3. **Secrets da Meta** copiados verbatim (token/app_secret/verify são reais
   da Meta, mesmo sem "dado de prod") — senão envio/validação quebra.
4. **Whitelist de emails** (rules + .env) — trocar conta pessoal pela Castro.
5. **LGPD** — dados de prod nascerão em Oregon (EUA): RoPA/RIPD + DPA +
   cliente continuam obrigatórios mesmo começando vazio.
