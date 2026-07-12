# Handoff — IAP no Cloud Run B → ligar o tenant #2

> Documento de retomada (conversa nova). Estado em 2026-07-12. Autossuficiente:
> dá pra continuar só com este doc + `docs/PLANO_OPERACAO_CLOUDRUN_B.md` +
> `docs/PLANO_RBAC_E_SUPER_ADMIN.md` + a memória `project_multitenant_fase2_roadmap`.
>
> **Próximo passo escolhido:** montar **IAP + domínio** na frente do Cloud Run B
> (2ª camada de rede) ANTES de ligar o tenant #2 real. (Alternativa ainda válida
> se faltar tempo: aceitar o v1 com a auth do app endurecida e fazer o IAP depois.)

---

## 1. Estado atual (tudo pronto e em prod)

**Projeto GCP (Oregon):** `project-4a851bf9-f475-418c-800` · região `us-west1`.

**Pré-#2 — 100% em prod:** M-A1, M-A2, M-A4, M-A4b, M-B2 (RBAC), login tenant-aware,
storage. (Detalhe no ROADMAP blocos 0d–0g.)

**Cloud Run A (CRM operacional):** serviço `castro-crm` · URL
`https://castro-crm-jdznvidcxq-uw.a.run.app` · rev atual `castro-crm-00047-sin`.

**Cloud Run B (painel super-admin):** serviço `castro-superadmin` ·
URL `https://castro-superadmin-28179318848.us-west1.run.app` · rev `00002-7pm`
(com o hardening da revisão). Deploy: imagem
`us-west1-docker.pkg.dev/project-4a851bf9-f475-418c-800/cloud-run-source-deploy/castro-superadmin:latest`,
buildada por `cloudbuild-superadmin.yaml` + `Dockerfile.superadmin` (imagem mínima,
só o fecho de imports + a página). SA dedicada
`castro-superadmin-sa@project-4a851bf9-f475-418c-800.iam.gserviceaccount.com`
(roles `datastore.user` + `firebaseauth.admin`). Hoje: `--allow-unauthenticated` +
`--ingress all` (é o que o IAP vem endurecer).

**Fundação (Sprint 0):** `super_admins/{uid}` root + `audit_logs_system/{id}` root +
`isSuperAdmin()` nas rules (ruleset **cb1bd995**). Founders com claim `super_admin`
concedido (`--allow-no-mfa`, bootstrap):
- Rafael — `rafaluisc@outlook.com` — uid `mbg9JRY86MUADtfja6pi3zxs7Az2`
- Izael  — `izaeldecastro@gmail.com` — uid `dFn2kayBsEOnS7A9BFmbBivNUGt1`

**Identity Platform:** upgradado; **TOTP habilitado** (`mfa.state=ENABLED`). Domínios
autorizados do Firebase Auth incluem a URL do B.

**M-A5 (ensaio):** VALIDADO ponta a ponta — Rafael logou no B, enrollou TOTP, criou o
tenant de teste `ensaio1`, e confirmou o isolamento por dentro (logando no CRM como
admin do ensaio). Depois o `ensaio1` foi **removido** (limpo). Rafael tem TOTP enrollado
no app; Izael provavelmente ainda não (verificar ao retomar).

**Revisão adversarial do B (2026-07-12):** 25 achados (16 confirmados). Corrigidos
(commit `a7cc82e`, rev `00002-7pm`): MFA guarda-dura (deployado sempre exige MFA), XSS
(escape), `mfa_enrolled` verificado via Admin SDK, kill switch imediato
(`check_revoked=True`), security headers/CSP, audit-after best-effort, `/healthz` sem
leak, secret TOTP limpo. Teste 18/18. **Pendente = a decisão de infra (IAP).**

**Commits locais** (todos os da Fase B — confirmar `git push origin develop`):
`a59736e` (backend), `a17d0cc` (página+MFA), `d5fc00d` (deploy artifacts),
`537fcf2` (Fase A), `a7cc82e` (hardening).

---

## 2. Por que IAP (o problema)

O B é internet-facing e nuclear: a SA lê Firestore de TODOS os tenants e seta qualquer
claim. Hoje a única trava de rede é o `require_super_admin` do app (fail-closed, MFA
sempre, revogação imediata — sólido). O IAP adiciona uma **2ª camada independente**: só
identidades Google allowlistadas (Rafael + Izael) chegam no container; o resto é barrado
no load balancer. Rafael confirmou que o outlook dele **é conta Google** → serve pro IAP
(sem precisar gmail).

---

## 3. Plano do IAP + domínio (a executar)

IAP no Cloud Run exige um **HTTPS Load Balancer** na frente (Serverless NEG) + IAP no
backend service. Passos (ajustar nomes):

**Pré-requisito — domínio:** escolher um subdomínio com DNS sob controle da Castro
(sugestão: `admin.castrointelligence.com.br`). Precisa poder criar um registro A.

1. **OAuth consent screen** (uma vez): configurar a brand no GCP (APIs & Services →
   OAuth consent screen, Internal se for Workspace).
2. **IP estático global:** `gcloud compute addresses create castro-superadmin-ip --global`.
3. **Serverless NEG** → o Cloud Run B:
   `gcloud compute network-endpoint-groups create castro-superadmin-neg --region us-west1 --network-endpoint-type serverless --cloud-run-service castro-superadmin`.
4. **Backend service** + add NEG:
   `gcloud compute backend-services create castro-superadmin-be --global --load-balancing-scheme EXTERNAL_MANAGED`; depois `... add-backend ... --network-endpoint-group castro-superadmin-neg --network-endpoint-group-region us-west1`.
5. **Cert gerenciado** (precisa do domínio):
   `gcloud compute ssl-certificates create castro-superadmin-cert --domains admin.castrointelligence.com.br --global`.
6. **URL map + target HTTPS proxy + forwarding rule** apontando pro IP estático (porta 443).
7. **DNS:** registro **A** de `admin.castrointelligence.com.br` → o IP estático. Aguardar
   o cert gerenciado ficar ACTIVE (pode levar minutos/horas após o DNS propagar).
8. **Habilitar IAP** no backend service + **allowlist**: adicionar `rafaluisc@outlook.com`
   e `izaeldecastro@gmail.com` como **IAP-secured Web App User**
   (`roles/iap.httpsResourceAccessor`). Conceder o IAP service agent como invoker no
   Cloud Run (`roles/run.invoker` ao `service-...@gcp-sa-iap.iam.gserviceaccount.com`).
9. **Trancar o ingress:** `gcloud run services update castro-superadmin --region us-west1
   --ingress internal-and-cloud-load-balancing` → a URL `.run.app` direta para de
   responder; só passa pelo LB+IAP.
10. **Testar:** abrir `https://admin.castrointelligence.com.br` → tela do Google (IAP) →
    login do painel (Firebase + TOTP) → painel. Confirmar que a URL `.run.app` direta dá 403.
11. **Atualizar domínios autorizados do Firebase Auth** com o novo domínio
    `admin.castrointelligence.com.br` (senão o login Firebase dá `auth/unauthorized-domain`).

> Nota: o `--allow-unauthenticated` do Cloud Run pode permanecer (o ingress
> internal-and-LB já impede acesso direto; o IAP gateia o LB). Rever se convém trocar
> pra `--no-allow-unauthenticated` + invoker só pro IAP.

---

## 4. Depois do IAP — ligar o tenant #2 real

1. (Se ainda não) Izael enrolla o TOTP no painel B.
2. No painel B: criar o tenant #2 com os dados reais do cliente (slug, nome, CNPJ, plano,
   email do admin do cliente, `allowed_email_domains` = domínio próprio do cliente — NUNCA
   provedor público; o sistema já ignora públicos). O `bootstrap_tenant` cria setores + 3
   perfis RBAC + admin com claim atômico, tudo auditado.
3. Provisionar o canal WhatsApp do cliente (standard, Embedded Signup — fluxo do CRM A, já
   existe). Ver ROADMAP "Fase 2 — provisionar o canal".
4. Convidar o admin do cliente (a conta Firebase nasce sem senha → link de convite/definir
   senha, ou login Google do domínio dele).

---

## 5. Follow-ups deferidos (pós-#2)
- Sessão-cookie 15min + re-MFA; sink BigQuery do `audit_logs_system`; impersonate
  read-only (M-B3) + ToS; rate-limit/Cloud Armor no LB.
- Dialog de confirmação do guarda-corpo de domínio no frontend do A.
- Fase 5 do RBAC (remover fallback de role, pós-bake-in).
- Decommission do projeto GCP antigo (SP). Quota `cpu_allocation` do Cloud Run.
- `/healthz` do B com 404 preso (cache de edge, cosmético).

---

## 6. Achados da revisão do B — aceitos/documentados (residual, baixo)
- SA `firebaseauth.admin` é necessária pro bootstrap (sem role mais fino).
- TOCTOU na criação de tenant (create_tenant re-checa; atores confiáveis; raro).
- Pré-check email-por-tenant (limitação documentada; o endpoint devolve `warning`).
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
