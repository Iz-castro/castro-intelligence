# Plano de Operação — Cloud Run B (painel super-admin) · Fase B

> **Objetivo:** subir o serviço `castro-superadmin` (mínimo) que permite a um
> super-admin criar o tenant #2 com segurança. Depois disso: M-A5 (ensaio de
> onboarding, o GATE) → ligar o tenant #2.
>
> Este doc é autossuficiente: dá pra retomar a Fase B só com ele + o
> `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` + `docs/PLANO_RBAC_E_SUPER_ADMIN.md`.

> **Status em 2026-08-21: Fase B CONCLUÍDA.** O serviço `castro-superadmin` está em prod
> desde 2026-07-11 (rev `00001-4f4`), endurecido em 12/07 pós-revisão adversarial (25
> achados, commit `a7cc82e`, rev `00002-7pm`) e com editor de tenant desde 31/07 (rev
> `00004-c8d`). Foi por ele que nasceram `varizemed-test` (14/07) e o **tenant #2 real
> `varizemed`** (28/07) — ambos em prod. Build/deploy reproduzível:
> `docs/DEPLOY_CLOUDRUN_B.md`. Segue ABERTO o §5: proteção de borda (IAP+LB vs
> Cloudflare Access — decisão em aberto, `docs/HANDOFF_IAP_E_TENANT2.md`), sessão-cookie
> de 15min, domínio próprio, sink BigQuery, impersonate e o decommission do projeto
> antigo de SP.

---

## 1. Estado atual (o que já está pronto)

**Pré-#2 100% em prod** (M-A1, M-A2, M-A4, M-A4b, M-B2 RBAC, login tenant-aware,
storage). E a **Fase A / Sprint 0** (fundação super-admin) — commit `537fcf2`:

- `super_admin.py` — camada de dados (sem FastAPI):
  - `get_super_admin(uid)`, `is_active_super_admin(uid)`, `seed_super_admin(...)`,
    `set_super_admin_mfa_enrolled(uid, True)`, `deactivate_super_admin(uid)`,
    `list_super_admins()`.
  - `log_system_audit(actor_uid, action, detail, target, target_tenant_id, ip, user_agent)`
    → grava em `audit_logs_system/{id}` (root, imutável). **PROPAGA falha** (audit-antes-da-ação).
- `firebase_admin_client.set_super_admin_claim(uid, value)` — seta/remove o claim preservando os demais.
- `scripts/grant_super_admin.py` — CLI `--seed / --list / --grant <uid> / --revoke <uid>`.
- `firestore.rules` — `isSuperAdmin()` + rules root de `super_admins/*` e `audit_logs_system/*`
  (read só super-admin, write só backend). **Publicado** (ruleset `cb1bd995`).
- `bootstrap_tenant(tenant_id, name, plan, cnpj, admin_email, admin_display_name,
  admin_department_name, allowed_email_domains)` — **a porta única de criação de tenant**,
  já endurecida (setores default + 3 perfis RBAC + admin com claim atômico + guard
  "um email = um tenant" + allowed_email_domains). Retorna
  `{tenant_id, created, admin_user_id, admin_firebase_uid}`.

**Já executado em prod:**
- Seed dos 2 founders em `super_admins/`:
  - Rafael — `rafaluisc@outlook.com` — uid `mbg9JRY86MUADtfja6pi3zxs7Az2`
  - Izael  — `izaeldecastro@gmail.com` — uid `dFn2kayBsEOnS7A9BFmbBivNUGt1`
  - Ambos `is_active=true`, `mfa_enrolled=false`, **claim NÃO concedido** (inertes).
- **Identity Platform upgradado** + **TOTP habilitado** (`mfa.state=ENABLED`,
  `totpProviderConfig`, adjacentIntervals=5). Operadores intactos.

---

## 2. Decisões de arquitetura (fechadas)

| Decisão | Escolha |
|---|---|
| Projeto GCP | **Mesmo** (Oregon `project-4a851bf9-f475-418c-800`) — B precisa do mesmo Firestore |
| Git | **Mesmo repo** — evita drift do `bootstrap_tenant` (fonte única da verdade) |
| Serviço | **Cloud Run separado** `castro-superadmin` + **service account dedicada** |
| Imagem | **`Dockerfile.superadmin` mínimo** — copia só o núcleo compartilhado + `superadmin_main` + página estática; NÃO leva `main.py`/`webhook`/`media` |
| Frontend | **Página estática única** (HTML+JS, sem Vite/npm) servida pelo próprio `superadmin_main` |
| Hardening v1 | **Enxuto seguro**: MFA-na-sessão obrigatório + audit Firestore + kill-switch via script + serviço/SA separados. DEFERIDO: sessão-cookie 15min, domínio próprio, sink BigQuery, impersonate |
| Ingress | Restringir o Cloud Run do B (ver bloco 4) |

---

## 3. Blocos de construção (✅ FEITOS em 2026-07-11/12 — histórico em `docs/DEPLOY_CLOUDRUN_B.md` §9)

### Bloco 1 — Backend do serviço B (`superadmin_main.py`)
- App FastAPI enxuto, **separado** do `main.py`.
- `require_super_admin` (dependency):
  1. `verify_firebase_id_token` (Bearer);
  2. claim `super_admin == true`;
  3. doc `super_admins/{uid}` existe + `is_active` (`is_active_super_admin`);
  4. **MFA-na-sessão**: no ID token do Firebase, checar `decoded["firebase"]["sign_in_second_factor"]`
     não-vazio (ex.: `"totp"`). *(PLANO_RBAC §4.5 fala em `amr`; no Firebase o campo real é
     `firebase.sign_in_second_factor` — CONFIRMADO: é o que o `superadmin_main.py` checa.)*
  → falhar qualquer etapa = 403.
- `POST /api/superadmin/tenants` — body: `tenant_id/slug, name, cnpj, plan, admin_email,
  allowed_email_domains`. Valida → `log_system_audit(actor, "create_tenant", ...)` **ANTES** →
  `bootstrap_tenant(...)` → retorna resultado. (Audit-antes-da-ação: se o audit falhar, aborta.)
- `GET /api/superadmin/tenants` — `list_tenants()` (só leitura).
- `POST /api/superadmin/mfa/enrolled` — marca `set_super_admin_mfa_enrolled(uid, True)` após
  o enrollment (chamado pela página).
- Health check `GET /` → serve a página estática.
- **Testável por script** antes de qualquer UI (montar TestClient + token mockado, ou curl com ID token real).

### Bloco 2 — Fluxo de MFA (na página + no backend)
- **Enrollment TOTP** (Firebase JS SDK, na página):
  ```js
  const session = await multiFactor(user).getSession();
  const secret  = await TotpMultiFactorGenerator.generateSecret(session);
  const uri     = secret.generateQrCodeUrl(email, "Castro Superadmin");  // mostrar QR
  const cred    = TotpMultiFactorGenerator.assertionForEnrollment(secret, code); // code = 6 dígitos
  await multiFactor(user).enroll(cred, "Authenticator");
  // depois: POST /api/superadmin/mfa/enrolled
  ```
- **Login com MFA**: `signIn...` lança `auth/multi-factor-auth-required` →
  `getMultiFactorResolver` → `TotpMultiFactorGenerator.assertionForSignIn(enrollmentId, code)` →
  `resolver.resolveSignIn(assertion)`.
- **Backend** já checa `sign_in_second_factor` no `require_super_admin` (bloco 1).

### Bloco 3 — Página estática única (`superadmin_web/index.html`)
- Firebase JS SDK via CDN (gstatic). Config web = a mesma do projeto (apiKey etc.).
- Telas (uma página, estados): **login** → (se preciso) **cadastrar TOTP** (QR) → **painel**:
  formulário de criar tenant (nome, CNPJ, plano, email do admin, allowed_email_domains) +
  lista de tenants. Manda o ID token no header `Authorization: Bearer`.
- Sem framework/build. Minimalista.

### Bloco 4 — Deploy isolado + SA + grant + ensaio
1. **Service account dedicada:**
   ```bash
   gcloud iam service-accounts create castro-superadmin-sa --project <oregon>
   gcloud projects add-iam-policy-binding <oregon> \
     --member serviceAccount:castro-superadmin-sa@<oregon>.iam.gserviceaccount.com \
     --role roles/datastore.user
   gcloud projects add-iam-policy-binding <oregon> \
     --member serviceAccount:castro-superadmin-sa@<oregon>.iam.gserviceaccount.com \
     --role roles/firebaseauth.admin
   ```
2. **Dockerfile.superadmin** (mínimo — COPY só os módulos usados + `superadmin_main` + `superadmin_web/`).
3. **Deploy** (build direcionado ao Dockerfile.superadmin — via `cloudbuild-superadmin.yaml` ou
   `gcloud builds submit` + `gcloud run deploy --image`):
   ```bash
   gcloud run deploy castro-superadmin --region us-west1 --project <oregon> \
     --service-account castro-superadmin-sa@<oregon>.iam.gserviceaccount.com \
     --ingress all   # (app-level auth + MFA é o portão; IAP fica como hardening fast-follow)
   ```
4. **Enrollment do TOTP** (Rafael + Izael) na URL do B → `mfa_enrolled=true`.
5. **Grant do claim:** `python scripts/grant_super_admin.py --grant <uid>` (exige mfa_enrolled).
   Relogar → ID token carrega `super_admin`.
6. **Ensaio ponta a ponta = início do M-A5 (GATE):** criar um **tenant de teste** pelo painel,
   validar que nasce isolado (setores + 3 perfis + admin com claim), e **auditar vazamento
   cross-tenant** adversarialmente (operador do teste não vê hubloc e vice-versa). Só depois: #2 real.

---

## 4. Revisão e segurança (não pular)
- **Revisão adversarial (workflow)** do serviço B antes de qualquer tráfego — mesmo padrão que
  pegou os 2 críticos no login tenant-aware e o ratchet no M-B2.
- Pontos de atenção pra revisão: bypass do `require_super_admin`; audit-antes-da-ação de fato
  abortando; a página não vazar credenciais; o Dockerfile não incluir código do A; a SA do B
  não ter permissão além do necessário; CORS/headers do serviço B.
- **Rollback:** o serviço B é novo e isolado — se der problema, `gcloud run services delete
  castro-superadmin` (ou traffic 0) não afeta o A em nada. O grant do claim é reversível
  (`--revoke <uid>`).

---

## 5. Follow-ups deferidos (pós-#2)
- Sessão-cookie 15min + re-MFA; domínio próprio `admin.castrointelligence.com.br` (DNS/cert);
  sink BigQuery do `audit_logs_system`; impersonate read-only (M-B3) + ToS; IAP na frente do B.
- Quota `cpu_allocation` do Cloud Run apertada (503 avulso em cutover) — pedir aumento antes do #2.
- Decommission do projeto GCP antigo (SP) — firestore-backups etc.

---

## 6. Ordem sugerida pra retomar
Bloco 1 (backend, testável por script) → revisão → Bloco 2+3 (MFA + página) → Bloco 4
(SA + deploy + enrollment + grant) → revisão adversarial → **ensaio/M-A5** → tenant #2.

*(Contexto vivo também na memória do projeto: `project_multitenant_fase2_roadmap`.)*
