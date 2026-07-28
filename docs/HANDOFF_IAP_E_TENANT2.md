# Handoff — IAP no Cloud Run B (hardening do painel super-admin)

> **Doc de retomada (conversa nova). Estado em 2026-07-23.** Autossuficiente:
> dá pra continuar só com este doc + `docs/PLANO_OPERACAO_CLOUDRUN_B.md` +
> `docs/PLANO_RBAC_E_SUPER_ADMIN.md` + as memórias `project_multitenant_fase2_roadmap`
> e `project_oregon_prod_cutover`.
>
> **O que é:** montar **IAP + domínio** na frente do **Cloud Run B** (painel
> super-admin `castro-superadmin`) — uma 2ª camada de rede, independente da auth
> do app, pra proteger o serviço mais sensível do sistema.
>
> **Status:** NÃO iniciado. Além disso, surgiu um **fork de arquitetura** (2026-07-23):
> o gate de borda pode ser o **IAP+LB do GCP** (plano original, agora "Opção A" na
> Seção 3) OU o **Cloudflare Access (Zero Trust)** — mais barato e sem load balancer.
> Ver a nova seção "⚖️ Decisão de borda em aberto". Continua sendo **hardening
> recomendada ANTES de provisionar CLIENTES REAIS pelo painel B**, não urgente.
>
> **Dependência crítica única:** o DNS de `castrointelligence.com.br` já está no
> **Cloudflare** (descoberto 2026-07-23; ver seção de decisão) — então criar o
> subdomínio `admin.castrointelligence.com.br` é fácil em qualquer dos caminhos.
> Falta **decidir IAP+LB vs. Cloudflare Access** e ter acesso à conta Cloudflare na
> hora de executar.

---

## 0. Mudança de contexto desde 2026-07-12 (LEIA ISTO)

O doc original tratava o IAP como **gate pra "ligar o tenant #2 real"**. Isso
mudou — o produto evoluiu por outro caminho:

- O **tenant #2 virou a Varizemed** (clínica), atacada como **motor de bot
  Dialogflow CX por tenant**, não via criação de tenant pelo painel B. O tenant
  de teste **`varizemed-test` foi criado DIRETO no banco de prod** (o webhook da
  Meta aponta pra prod; isolamento é estrutural por path), com número real DDD 71,
  bot da Val respondendo, handoff, e a feature de **temperatura do lead**
  (quente/morno/frio) — tudo em prod e validado. Ver memórias
  `project_varizemed_migration`, `project_lead_temperature`.
- Logo, **o IAP não bloqueia mais nada do que já foi entregue.** Ele volta a ser
  o que sempre foi na essência: **endurecer o painel B** pro dia em que a Castro
  for provisionar tenants de **clientes reais** por lá (fluxo self-service do
  super-admin), OU simplesmente pra fechar a superfície de ataque do serviço mais
  poderoso do sistema. Recomendável, não urgente.
- A **Varizemed REAL** (go-live com pacientes de verdade) tem o **seu próprio
  gate — J-3 hardening LGPD** (cripto de campo sensível, audit de leitura, TTL/
  retenção, DPA; clínica = dado de saúde), que é **separado** do IAP. Ver
  `docs/PLANO_LEAD_TEMPERATURE.md` e `docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md` (J-3).

---

## ⚖️ Decisão de borda em aberto (NOVO 2026-07-23): IAP+LB (GCP) vs. Cloudflare Access

Ao investigar "de onde vem o IP fixo", descobrimos o DNS real de vocês — e isso abriu
um caminho mais barato que o LB. **As duas opções entregam a mesma proteção essencial**
(só Rafael + Izael chegam no painel B); o que muda é custo, complexidade e uma
propriedade de rede. Este doc registra as **duas posições**; a decisão segue em aberto.

### Fatos de DNS descobertos (via `nslookup`, 2026-07-23)
- **Registro do domínio:** `registro.br` (obrigatório pra `.com.br`). GitHub **não**
  registra domínio — a confusão veio de o **site institucional estar no GitHub Pages**.
- **DNS gerenciado no Cloudflare** (`archer.ns.cloudflare.com` / `laila.ns.cloudflare.com`).
- `www` e raiz → **GitHub Pages** (institucional). Só vamos **adicionar** subdomínios,
  sem tocar no site atual.

### Layout de subdomínios alvo
| Hostname | Aponta pra | Papel |
|---|---|---|
| `castrointelligence.com.br` / `www` | GitHub Pages | institucional (fica como está) |
| `crm.castrointelligence.com.br` | Cloud Run `castro-crm` | app dos clientes |
| `admin.castrointelligence.com.br` | Cloud Run `castro-superadmin` | painel super-admin |

> **Correção crítica:** o gate de identidade (IAP OU Cloudflare Access) vai **SÓ no
> `admin`**. No `crm` ele NÃO pode existir — trancaria os próprios clientes
> (operadores da Hubloc, Varizemed…) do lado de fora. No `crm`, o Cloudflare faz só
> **DNS + proxy + WAF/rate-limit**; quem controla o acesso continua sendo o login do
> app (Firebase + claim de tenant).

### Opção A — IAP + HTTPS Load Balancer (GCP) — o plano da Seção 3
- **Identidade:** IAP (Google) com allowlist (Rafael + Izael).
- **Mata a `.run.app` direta:** SIM (ingress `internal-and-cloud-load-balancing`).
- **Custo:** ~US$20/mês (regra de encaminhamento do LB) + tráfego; IP e cert
  gerenciado inclusos/grátis.
- **WAF:** via Cloud Armor (config e custo à parte).
- **Complexidade:** alta (Compute API, Serverless NEG, backend service, cert, url map,
  forwarding rule, DNS).
- **Webhook Meta:** no `admin` não há webhook. Se um dia aplicar o mesmo esquema no
  `crm`, trancar o ingress **obriga a migrar o callback da Meta** (risco de derrubar o
  WhatsApp dos clientes).

### Opção B — Cloudflare Access (Zero Trust) — novo, recomendado
- **Identidade:** Cloudflare Access com allowlist (grátis até 50 usuários).
- **Mata a `.run.app` direta:** NÃO por padrão. Fecha-se com um **header secreto** que
  o Cloudflare injeta e o app exige (barato, defesa em profundidade).
- **Custo:** US$0 (Access free + WAF/rate-limit básico do Cloudflare incluído).
- **Complexidade:** baixa/média — tudo no painel Cloudflare, sobre um DNS que **já é deles**.
- **Webhook Meta:** **intocado** — como não se tranca o ingress, o webhook do CRM segue
  na `.run.app` sem migração. Some o passo perigoso do plano do LB.

### Em ambas, a trava real do painel B continua a mesma
A auth do app (`require_super_admin` + MFA sempre + `check_revoked`) é o gate
fail-closed já validado pela revisão adversarial (commit `a7cc82e`). IAP/Access é a
**2ª camada** por cima — a diferença entre A e B é *como* se monta essa 2ª camada e se
a `.run.app` morre no nível de rede (A) ou via header secreto (B).

### Recomendação
Como o DNS já está no Cloudflare, o custo é US$0 e o webhook fica intocado, a
**Opção B** (Cloudflare Access no `admin`, Cloudflare proxy+WAF no `crm`) é o caminho
mais simples e barato. A **Opção A** fica documentada como alternativa caso um dia se
queira matar a `.run.app` no nível de rede sem header secreto, ou consolidar tudo no
GCP. **Decisão ainda em aberto** — Rafael pediu as duas posições registradas.

### Evolução: domínio personalizado por cliente (`crm.hubloc.com.br`)
Recurso de white-label, viável via **Cloudflare for SaaS / Custom Hostnames** (TLS por
cliente automático; camada grátis ~100 hostnames). O cliente cria um `CNAME` no DNS
dele. **Regra de ouro LGPD:** o isolamento entre tenants **nunca** depende do hostname
(falsificável) — segue no **claim de tenant** (fonte da verdade estrutural). O domínio
bonito é entrada + branding (o topbar já mostra `tenant.name`). Feature de venda/plano
premium, não urgente; Hubloc é candidata natural a piloto.

---

## 1. Estado atual da infra (Oregon)

**Projeto GCP:** `project-4a851bf9-f475-418c-800` · região `us-west1` · Firestore
`(default)` Native · banco de prod = prefixo `castro_crm` (staging = tagged
revision, prefixo `castro_crm_staging`). ⚠ `gcloud config` pode apontar pro
projeto ANTIGO (SP) — passar `--project` explícito sempre
(ver `project_oregon_prod_cutover`).

**Cloud Run A (CRM operacional):** serviço `castro-crm` · URL
`https://castro-crm-jdznvidcxq-uw.a.run.app` · **rev atual `castro-crm-00096-ray`**
(saltou de 00047 em 12/07 — CX bot engine, recuperação do incidente de colisão de
canal, fix channels-global, dieta de reads, temperatura do lead, branding topbar).
minScale=1. NÃO é alvo do IAP (é o app dos operadores, internet-facing por design).

**Cloud Run B (painel super-admin) — ALVO DO IAP:** serviço `castro-superadmin` ·
URL `https://castro-superadmin-jdznvidcxq-uw.a.run.app` · **rev `castro-superadmin-00003-lsw`**.
Deploy: imagem `.../cloud-run-source-deploy/castro-superadmin:latest`, buildada por
`cloudbuild-superadmin.yaml` + `Dockerfile.superadmin` (imagem mínima). SA dedicada
`castro-superadmin-sa@project-4a851bf9-f475-418c-800.iam.gserviceaccount.com`
(roles `datastore.user` + `firebaseauth.admin`). **Hoje: internet-facing**
(`--allow-unauthenticated`, ingress default `all`) — é exatamente o que o IAP vem
endurecer.

**IAP/LB: ZERO.** `compute.googleapis.com` não está habilitada no projeto →
nenhum IP estático, NEG, backend service ou LB existe. Habilitar a Compute API é
o passo 0 de fato.

**Fundação super-admin (pronta e em prod):** `super_admins/{uid}` root +
`audit_logs_system/{id}` root + `isSuperAdmin()` nas rules. Founders com claim
`super_admin`:
- Rafael — `rafaluisc@outlook.com` — uid `mbg9JRY86MUADtfja6pi3zxs7Az2`
- Izael  — `izaeldecastro@gmail.com` — uid `dFn2kayBsEOnS7A9BFmbBivNUGt1`

**Identity Platform:** upgradado; TOTP habilitado (`mfa.state=ENABLED`). Rafael
validou o painel B ponta a ponta (login + TOTP + criar/limpar tenant de ensaio +
isolamento). Izael: confirmar se já enrollou TOTP no painel B ao retomar.

**Hardening do B (revisão adversarial 2026-07-12, commit `a7cc82e`):** 25 achados,
16 corrigidos — MFA guarda-dura, XSS escapado, `mfa_enrolled` via Admin SDK, kill
switch `check_revoked=True`, security headers/CSP, `/healthz` sem leak. A auth do
app (`require_super_admin`) é sólida e fail-closed. O IAP é a 2ª camada por cima
dela, não a única.

---

## 2. Por que IAP (o problema)

O B é internet-facing e nuclear: a SA lê Firestore de TODOS os tenants e seta
qualquer claim. Hoje a única trava de rede é o `require_super_admin` do app (MFA
sempre, revogação imediata — sólido). O IAP adiciona uma **2ª camada independente**:
só identidades Google allowlistadas (Rafael + Izael) chegam no container; o resto é
barrado no load balancer. O outlook do Rafael **é conta Google** → serve pro IAP
(sem precisar gmail).

---

## 3. Plano da OPÇÃO A — IAP + domínio (comandos GCP, ainda válidos)

> Este é o caminho da **Opção A** (ver seção de decisão acima). Para a **Opção B
> (Cloudflare Access)**, os passos são no painel Cloudflare + Zero Trust, não aqui —
> a detalhar quando a decisão fechar nesse caminho.

IAP no Cloud Run exige um **HTTPS Load Balancer** na frente (Serverless NEG) + IAP
no backend service. Passos (ajustar nomes):

**Passo 0 — Compute API:** `gcloud services enable compute.googleapis.com --project project-4a851bf9-f475-418c-800`.

**Pré-requisito — domínio:** escolher um subdomínio com DNS sob controle da Castro
(sugestão: `admin.castrointelligence.com.br`). Precisa poder criar um registro A.

1. **OAuth consent screen** (uma vez): APIs & Services → OAuth consent screen
   (Internal se for Workspace).
2. **IP estático global:** `gcloud compute addresses create castro-superadmin-ip --global`.
3. **Serverless NEG** → o Cloud Run B:
   `gcloud compute network-endpoint-groups create castro-superadmin-neg --region us-west1 --network-endpoint-type serverless --cloud-run-service castro-superadmin`.
4. **Backend service** + add NEG:
   `gcloud compute backend-services create castro-superadmin-be --global --load-balancing-scheme EXTERNAL_MANAGED`; depois `... add-backend ... --network-endpoint-group castro-superadmin-neg --network-endpoint-group-region us-west1`.
5. **Cert gerenciado** (precisa do domínio):
   `gcloud compute ssl-certificates create castro-superadmin-cert --domains admin.castrointelligence.com.br --global`.
6. **URL map + target HTTPS proxy + forwarding rule** apontando pro IP estático (porta 443).
7. **DNS:** registro **A** de `admin.castrointelligence.com.br` → o IP estático.
   Aguardar o cert gerenciado ficar ACTIVE (minutos/horas após o DNS propagar).
8. **Habilitar IAP** no backend service + **allowlist**: `rafaluisc@outlook.com` e
   `izaeldecastro@gmail.com` como **IAP-secured Web App User**
   (`roles/iap.httpsResourceAccessor`). Conceder o IAP service agent como invoker no
   Cloud Run (`roles/run.invoker` ao `service-...@gcp-sa-iap.iam.gserviceaccount.com`).
9. **Trancar o ingress:** `gcloud run services update castro-superadmin --region us-west1 --ingress internal-and-cloud-load-balancing` → a URL `.run.app` direta para de responder; só passa pelo LB+IAP.
10. **Testar:** abrir `https://admin.castrointelligence.com.br` → tela do Google (IAP)
    → login do painel (Firebase + TOTP) → painel. Confirmar que a `.run.app` direta dá 403.
11. **Domínios autorizados do Firebase Auth:** adicionar `admin.castrointelligence.com.br`
    (senão o login Firebase dá `auth/unauthorized-domain`).

> Nota: o `--allow-unauthenticated` pode permanecer (o ingress internal-and-LB já
> impede acesso direto; o IAP gateia o LB). Rever se convém trocar pra
> `--no-allow-unauthenticated` + invoker só pro IAP.

---

## 4. Depois do IAP — criar tenant de CLIENTE REAL pelo painel B

(Fluxo self-service do super-admin. Distinto do `varizemed-test`, que foi criado
direto no banco por script.)

1. (Se ainda não) Izael enrolla o TOTP no painel B.
2. No painel B: criar o tenant com dados reais (slug, nome, CNPJ, plano, email do
   admin do cliente, `allowed_email_domains` = domínio próprio do cliente — NUNCA
   provedor público; o sistema já ignora públicos). O `bootstrap_tenant` cria
   setores + 3 perfis RBAC + admin com claim atômico, tudo auditado.
3. Provisionar o canal WhatsApp (standard via Embedded Signup, fluxo do CRM A).
   ⚠ Colisão de channel_id JÁ CORRIGIDA (contador global; ver
   `project_channel_id_collision`).
4. Convidar o admin do cliente (conta Firebase nasce sem senha → link/definir
   senha, ou login Google do domínio dele).
5. Se for **clínica** (dado de saúde): cumprir o **gate J-3 LGPD** antes do
   go-live (fora deste doc).

---

## 5. Follow-ups deferidos (pós-IAP)
- Sessão-cookie 15min + re-MFA; sink BigQuery do `audit_logs_system`; impersonate
  read-only (M-B3) + ToS; rate-limit/Cloud Armor no LB.
- Diálogo de confirmação do guarda-corpo de domínio no frontend do A.
- Fase 5 do RBAC (remover fallback de role, pós-bake-in).
- Decommission do projeto GCP antigo (SP). Quota `cpu_allocation` do Cloud Run.

---

## 6. Achados da revisão do B — aceitos/documentados (residual, baixo)
- SA `firebaseauth.admin` necessária pro bootstrap (sem role mais fino).
- TOCTOU na criação de tenant (create_tenant re-checa; atores confiáveis; raro).
- Pré-check email-por-tenant (limitação documentada; endpoint devolve `warning`).
- `isSuperAdmin` por claim no path client-SDK de `super_admins`/`audit_logs_system`
  (ninguém lê essas coleções pelo client SDK; o backend já é `check_revoked`).

---

## 7. Arquivos-chave
- `superadmin_main.py` — backend do B (require_super_admin, criar-tenant, MFA).
- `superadmin_web/index.html` — página estática (login + enroll TOTP + painel).
- `super_admin.py` — super_admins + `log_system_audit`.
- `scripts/grant_super_admin.py` — `--seed/--list/--grant/--revoke`.
- `Dockerfile.superadmin`, `cloudbuild-superadmin.yaml`, `requirements-superadmin.txt`.
- `docs/PLANO_OPERACAO_CLOUDRUN_B.md`, `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md`,
  `docs/PLANO_RBAC_E_SUPER_ADMIN.md`, `docs/ROADMAP_MULTITENANT_FASE2.md`.
