# ADR 0006 — Fluxo de redefinicao de senha para operadores

- **Status:** Proposed (aguardando priorizacao)
- **Data:** 2026-06-03
- **Autores:** Rafa + Claude (ancoragem no codigo e na estrutura real do Firestore)
- **Relacionado:** Firebase Admin SDK em
  [firebase_admin_client.py](../../firebase_admin_client.py); endpoints admin
  `/api/admin/users` em [main.py:677](../../main.py#L677); colecao `users` via
  [firestore_common.py:94](../../firestore_common.py#L94); login no frontend em
  [CrmContext.tsx:1315](../../frontend/src/CrmContext.tsx#L1315) e
  `LoginScreen` em [App.tsx:67](../../frontend/src/App.tsx#L67).

## 1. O problema

O login no Hubloc CRM e feito via Google Auth (dominio da empresa) ou
e-mail/senha. Quando um operador esquece a senha (e-mail/senha), **nao
existe fluxo de recuperacao** — confirmado: nenhum `sendPasswordResetEmail`
no frontend, nenhuma rota de reset no backend (o `POST /api/login` legado
retorna 410). Precisamos de recuperacao segura, autonoma ou assistida pelo
Admin, mantendo conformidade LGPD e isolamento multi-tenant.

## 2. Estado atual no codigo (ancoragem)

Antes das solucoes, o que JA existe vs net-new:

| Item | Estado | Evidencia |
|---|---|---|
| Firebase Admin SDK no backend | ✅ existe | [firebase_admin_client.py](../../firebase_admin_client.py) (`verify_firebase_id_token`, `set_tenant_claims`, `get_user_claims`) |
| Backend = FastAPI no Cloud Run | ✅ | service `castro-crm`. **Nao** ha Firebase Functions no projeto |
| RBAC | ✅ inline (sem decorator) | `if current_user.get("role") not in (...)` em [main.py:679](../../main.py#L679),712,730. Roles: `admin/supervisor/operador` ([config.py:140](../../config.py#L140)) |
| Colecao de operadores | ✅ chama-se **`users`** | `create_user` [database_firestore.py:328](../../database_firestore.py#L328); path `castro_crm_tenants/{tid}/users/{user_id}` |
| Espelho por uid | ✅ `operator_profiles` (tenant-scoped, 17 docs) | campos `uid/email/role/user_id` |
| Login Google + email/senha | ✅ | `loginWithGoogle`/`loginWithEmail` [CrmContext.tsx:1315](../../frontend/src/CrmContext.tsx#L1315) |
| "Esqueci minha senha" | ❌ NET-NEW | ausente no `LoginScreen` |
| Email transacional (SendGrid/Mailgun/SMTP) | ❌ NAO existe | ausente em `requirements.txt` e `config.py` |

Pontos criticos confirmados:
- **`tenant_id` nunca vem do frontend** — e custom claim no JWT, lido pelo
  backend ([main.py:158](../../main.py#L158)). Endpoint de reset herda o
  tenant do token do admin; **nao aceitar `tenant_id` no body**.
- **`password_hash` e campo morto** — `create_user` grava, mas
  `upsert_firebase_user` sempre passa `""` ([database_firestore.py:447](../../database_firestore.py#L447)).
  A senha vive **100% no Firebase Auth**. Esta ADR **nao** propoe
  escrever/validar hash de senha no Firestore.

## 3. O que NAO fazer (antipadrao)

**Permitir que o Admin digite, defina ou visualize a nova senha de um
operador direto no painel.** Compromete a seguranca, fere a LGPD (acesso
indevido a credencial de terceiro) e destroi a auditoria (impossivel
garantir se uma acao foi do operador real ou do Admin que detem a senha).
Reforco tecnico: como a senha vive no Firebase Auth e `password_hash` e
morto, nao ha nem caminho legitimo para o backend conhecer a senha.

## 4. As solucoes (modelo recomendado: delegacao)

O unico modelo seguro: o operador define a propria senha via **link de
redefinicao** enviado ao e-mail corporativo. O backend/Admin nunca toca a
senha — apenas dispara o fluxo.

### Solucao A — Self-service (recomendacao primaria)
- **UI/UX:** link "Esqueci minha senha" abaixo do botao de login por
  e-mail/senha no `LoginScreen` ([App.tsx:67](../../frontend/src/App.tsx#L67)).
- **Execucao:** `sendPasswordResetEmail(bundle.auth, email)` do **Firebase
  Client SDK**, ao lado de `loginWithEmail`
  ([CrmContext.tsx:1315](../../frontend/src/CrmContext.tsx#L1315)). Roda
  100% client-side; **zero backend, zero provedor de email** (o Firebase
  envia).
- **Vantagem:** operador resolve sozinho, sem chamado de suporte.

### Solucao B — Gerencial (fallback assistido)
Para quando o operador nao consegue usar o self-service (bloqueado,
atendimento presencial rapido).
- **UI/UX:** no grid de equipe (`Configuracoes > Equipe`), acao **"Enviar
  link de redefinicao de senha"** na linha do operador.
- **Execucao:** o front **nao** fala com o Auth direto. Chama um **endpoint
  FastAPI** (correcao do rascunho: nao e Cloud Function):
  **`POST /api/admin/users/{user_id}/password-reset`** — aderente a familia
  `/api/admin/users` ja existente ([main.py:677](../../main.py#L677)).

## 5. Arquitetura de seguranca (Solucao B)

O endpoint segue tres protecoes:

1. **RBAC.** Guard inline no padrao atual do projeto:
   `if current_user.get("role") not in ("admin", "supervisor"): raise HTTPException(403)`
   (copia o esqueleto de `admin_revoke_coex`, [main.py:764](../../main.py#L764)).
   *Opcional/net-new:* extrair um `require_admin` reutilizavel — hoje a
   checagem e repetida inline em cada rota.

2. **Isolamento multi-tenant (estrutural, nao cross-check manual).**
   Correcao relevante: como `document("users", user_id)` roteia
   automaticamente para a subcolecao do tenant do **token do admin**
   (`castro_crm_tenants/{tid}/users/{user_id}`, via contextvar em
   [firestore_common.py:110](../../firestore_common.py#L110)), e
   **estruturalmente impossivel** o Admin do tenant A buscar um operador do
   tenant B — o `user_id` simplesmente nao existe na subcolecao dele.
   Resolver `email`/`firebase_uid` via `get_user_by_id(user_id)`
   ([database_firestore.py:286](../../database_firestore.py#L286)); abortar
   404 se nao achar. (O rascunho falava em "cross-check no Firestore"; o
   isolamento ja vem de graca pelo roteamento por contextvar.)

3. **Geracao segura e disparo.** Validado o vinculo, usar o Firebase Admin
   SDK ja inicializado ([firebase_admin_client.py](../../firebase_admin_client.py)):
   `auth.generate_password_reset_link(email)` (gera o link sem enviar) ou
   delegar o envio ao Firebase. **Net-new:** wrapper
   `generate_password_reset_link(email)` no `firebase_admin_client.py`.
   Audit obrigatorio: `log_audit(current_user["id"], "USER_PASSWORD_RESET_SENT", f"target_user={user_id}")`.

## 6. Decisao sobre envio de e-mail

| Opcao | Custo | Recomendacao |
|---|---|---|
| **Firebase Auth nativo** (`sendPasswordResetEmail` / `generate_password_reset_link`) | Zero net-new; sem secret novo | ✅ **Default.** Cobre A e B. Template editavel no Firebase Console (Authentication > Templates) |
| Provedor transacional (SendGrid/Mailgun) com template Hubloc (`nao-responda@hubloc.com.br`) | NET-NEW: lib + secret + template + var em `config.py` | So se exigir branding proprio. Documentar como trade-off, **nao** como premissa |

## 7. Net-new por solucao

- **A (self-service):** link no `LoginScreen` + metodo `resetPassword(email)`
  no `CrmContext.tsx`. Opcional: endpoint publico
  `POST /api/auth/password-reset-request` para validar dominio
  (`ALLOWED_FIREBASE_EMAIL_DOMAIN`) e registrar audit, **com rate limiting**
  (nao existe hoje).
- **B (gerencial):** endpoint `POST /api/admin/users/{user_id}/password-reset`
  + wrapper no `firebase_admin_client.py` + acao na UI de equipe + audit log.

## 8. Consequencias

### Positivas
- Recuperacao de acesso sem o Admin jamais conhecer a senha (LGPD: nao ha
  acesso indevido a credencial de terceiro; auditoria intacta).
- Isolamento multi-tenant garantido por construcao (roteamento por
  contextvar), nao por checagem manual sujeita a erro.
- Solucao A nao adiciona infra; Solucao B reusa Admin SDK e padrao de rota
  existentes.

### Negativas / atencao
- **Rate limiting** do fluxo self-service e net-new — sem ele, vira vetor de
  enumeracao de e-mail / abuso de envio.
- **Template de e-mail nativo do Firebase** tem branding limitado; branding
  Hubloc completo so com provedor transacional (net-new).
- **Whitelist de dominio:** decidir se o self-service respeita
  `ALLOWED_FIREBASE_EMAIL_DOMAIN` antes de disparar (evita reset para
  e-mail fora da empresa).

## 9. Itens dependentes (fora do escopo desta ADR)

- UX da tela `Configuracoes > Equipe` para a acao de reset (confirmacao,
  feedback de "link enviado").
- Decisao final sobre branding do e-mail (nativo vs transacional).
- `require_admin` reutilizavel (refactor do RBAC inline) — melhoria
  transversal, nao exclusiva deste fluxo.
