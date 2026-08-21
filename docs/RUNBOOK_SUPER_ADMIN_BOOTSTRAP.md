# Runbook — Bootstrap do Super-Admin (Sprint 0)

Fundação do painel super-admin (Cloud Run B). Ordem importa: **seed dos docs
→ Identity Platform/TOTP → enrollment do MFA → grant do claim**. O grant só
depois do MFA garante a invariante "nenhum super-admin ativo com claim sem
MFA" (PLANO_RBAC §4.5).

> Contexto: `super_admins/{uid}` (root) é a source of truth; o claim
> `super_admin: true` é só fast-path. Nenhuma operação nuclear é autorizada
> só pelo claim — o Cloud Run B revalida doc ativo **+ MFA-na-sessão** a cada
> request (Fase B).

> **Status em 2026-08-21:** os passos 1-4 **já foram executados em prod** — seed dos 2
> founders (2026-07-07), upgrade pra Identity Platform + TOTP habilitado, painel B
> (`castro-superadmin`) no ar desde 2026-07-11/12 e founders com o claim `super_admin`
> (ver `docs/HANDOFF_IAP_E_TENANT2.md` §1; ⚠ confirmar se o Izael já enrollou o TOTP).
> O runbook segue valendo para **provisionar um super-admin #3** e para o **kill
> switch**. Operação do painel: `docs/PLANO_OPERACAO_CLOUDRUN_B.md`.

---

## Pré-requisitos

- ADC autenticado com acesso ao projeto Oregon (`gcloud auth login` +
  `gcloud auth application-default login`).
- Rodar da raiz do repo com `FIRESTORE_PROJECT_ID` apontando pra prod.

```bash
export FIRESTORE_PROJECT_ID=project-4a851bf9-f475-418c-800
export CLOUDSDK_PYTHON=".../Python312/python.exe"   # quirk gcloud (ver memória)
```

---

## 1. Seed dos docs `super_admins/{uid}` (idempotente)

Cria os 2 founders (rafaluisc@outlook / izaeldecastro@gmail) com
`is_active=true`, `mfa_enrolled=false`. **Não** concede o claim ainda.

```bash
python scripts/grant_super_admin.py --seed
python scripts/grant_super_admin.py --list
```

## 2. Identity Platform + TOTP (config, 1x) — AÇÃO MANUAL

TOTP MFA exige o projeto **Firebase Authentication com Identity Platform**
(upgrade). O flip da API sozinho retorna `OPERATION_NOT_ALLOWED` até o
upgrade. Passos:

1. **Firebase Console → Authentication → Upgrade to Identity Platform**
   (ou GCP Console → Identity Platform). Gratuito abaixo de 50k MAU; TOTP
   não tem custo de SMS.
2. Depois do upgrade: **Authentication → Sign-in method → Multi-factor /
   Authenticator app (TOTP) → habilitar**. (Ou via API:
   `PATCH admin/v2/projects/{P}/config?updateMask=mfa` com
   `mfa.state=ENABLED` + `providerConfigs[].totpProviderConfig`.)

## 3. Enrollment do TOTP dos founders — via Cloud Run B (Fase B)

Não há botão de auto-enroll no Console. O enrollment acontece no **login do
Cloud Run B**: reautenticar → gerar segredo → escanear QR no autenticador
(Google Authenticator/Authy/1Password) → confirmar código → `enroll()`. O
painel marca `mfa_enrolled=true` no doc (`set_super_admin_mfa_enrolled`).

- **Cadastrar os DOIS founders** (backup mútuo de MFA).
- Guardar segredo/backup em gerenciador de senhas.

## 4. Grant do claim `super_admin` (após MFA enrolled)

```bash
python scripts/grant_super_admin.py --grant <uid>
```

Valida doc ativo + `mfa_enrolled=true`, seta o claim, revoga refresh tokens
(o founder reloga → ID token novo carrega o claim). Em bootstrap controlado
antes do enrollment: `--grant <uid> --allow-no-mfa` (o enforcement de MFA
continua no Cloud Run B a cada request — o claim sozinho é inerte no A).

## 5. Kill switch (emergência)

```bash
python scripts/grant_super_admin.py --revoke <uid>
```

Desativa o doc (`is_active=false`) + remove o claim + revoga refresh tokens.
Registra `kill_super_admin` em `audit_logs_system`.

---

## Rules

`isSuperAdmin()` + os matches de `castro_crm_super_admins/*` e
`castro_crm_audit_logs_system/*` já estão em `firestore.rules` (leitura só
super-admin; escrita sempre backend). ✅ **Publicado** — ruleset `cb1bd995` (2026-07-07).

## Provisionar super-admin #3 no futuro

Adicionar o uid/email em `FOUNDERS` (ou seed manual via `seed_super_admin`),
`--seed`, enrollment MFA no painel B, `--grant <uid>`.
