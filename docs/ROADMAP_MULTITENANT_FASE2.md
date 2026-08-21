# Roadmap Multi-Tenant (Fase 2) — Decisões fechadas + Ordem de execução

> **Decisões D1-D6 FECHADAS em 2026-07-01. Execução iniciada.**
> Documento vivo — atualizar conforme os milestones forem entregues.

> **Status em 2026-08-21:** o caminho do tenant #2 FECHOU. **Pré-#2 100% em prod**
> (M-A1, M-A2, M-A4, M-A4b, M-B2 RBAC, login tenant-aware, storage) e o **Cloud Run B
> (`castro-superadmin`) está em prod desde 2026-07-11/12** — foi por ele que nasceram
> `varizemed-test` (14/07) e o **tenant #2 real `varizemed`** (28/07, plano `ai_custom`),
> hoje com bot Dialogflow CX e Modo Recepção (ADR 0010) em produção. São **3 tenants
> ativos** (`hubloc`, `varizemed`, `varizemed-test`). Continuam ABERTOS: **M-B1** (ADR 0007
> Fase 2), a proteção de borda do painel B (IAP+LB vs Cloudflare Access — decisão em
> aberto, `docs/HANDOFF_IAP_E_TENANT2.md`), a Fase 5 do RBAC (pós-bake-in) e o
> decommission do projeto antigo de SP. Execução/deploy do B:
> `docs/PLANO_OPERACAO_CLOUDRUN_B.md` + `docs/DEPLOY_CLOUDRUN_B.md`.

## Contexto

O CRM (FastAPI + Firestore + React, Cloud Run Oregon) operava **single-tenant** em 2026-07-01
(só `hubloc`). Objetivo: habilitar **multi-tenant** para onboarding de novos clientes sob
a mesma infra, no modelo **managed billing** (Castro fronta a Meta e re-fatura — CLAUDE.md §1).

**Releitura-chave:** boa parte do "Fase 2" **já está em produção** (context machinery,
roteamento `tenants/{tid}/`, resolução por JWT, `tenant_service`, `phone_routing`, rules PROD
estritas, auditoria coex). O que falta pro 2º tenant é pequeno e localizado — o gargalo real
é **um só: os canais ainda são coleção flat** (ADR 0007).

---

## STATUS DAS DECISÕES (fechadas 2026-07-01)

| # | Decisão | **Escolha final** | Nota |
|---|---|---|---|
| **D1** | Modelo do 1º cliente novo | **STANDARD** | Coex continua **disponível** (arquitetura já suporta os dois). Coex p/ novos tenants só após ADR 0002 (jurídico). |
| **D2** | ADR 0007: filtro lógico vs migração estrutural | **Fase 1 E Fase 2** | Fase 1 (lógico) destrava já; Fase 2 (estrutural) **logo em seguida**, sem ninguém esperando. |
| **D3** | Criar tenant via script vs UI | **UI super-admin (Cloud Run B)**, incremental | Sprint 0 → B mínimo só-criar-tenant → crescer. Criar tenant é operação de root; o "grande" do B é a superfície de segurança, não o formulário. Não pode ser botão no A (isolamento §4.1). |
| **D4** | RBAC dinâmico antes ou depois do #2 | **ANTES do #2** | Migrar RBAC no hubloc (tenant que controlamos) enquanto só há 1 tenant → o #2 **nasce** no modelo dinâmico. Custo: mais escopo antes do #2. |
| **D5** | Estratégia de teste | **Agentes de teste** (orçamento alto autorizado) | Por milestone: workflow que gera casos + roda em staging + verifica isolamento adversarialmente. |
| **D6** | Propagação do claim | **Atômico na criação** | `set_tenant_claims` + `revokeRefreshTokens` no `bootstrap_tenant` → 1º login do admin já vem com `tenant_id`/`perfil_acesso_id`. Evita "admin novo não enxerga o tenant". |

**Trilha legal (paralela, dona = jurídico):** Oregon/us-west1 → DPA/SCCs + RoPA/RIPD
(Brasil→EUA). Coex p/ novos tenants → ADR 0002 (política + cláusulas). Não bloqueia o dev em
staging; bloqueia go-live em prod.

---

## ORDEM DE EXECUÇÃO (começando hoje)

```
0. VERIFY-FIRST ✅ FEITO 2026-07-01 — rules estritas de PROD CONFIRMADAS publicadas (console).
     ACHADO: ownsTenant() depende de emailAllowed() (whitelist hubloc) → operador de
     tenant #2 (email não-hubloc) seria BARRADO nas rules. Vira item obrigatório pré-#2 (M-A4).
     [CORRIGIDO 2026-07-03: o "drift" do castrointelligence@gmail.com era FALSO — leitura via
     API (fonte autoritativa) confirmou publicado ≡ repo HEAD, zero diferença.]

0b. NOVO BLOQUEADOR (achado no M-A4, 2026-07-03): o gate de LOGIN do backend
     (auth._firebase_email_allowed + env ALLOWED_FIREBASE_EMAIL_DOMAIN=hubloc.com.br,
     ALLOWED_FIREBASE_EMAILS=founders, AUTO_PROVISION=true) é OUTRA whitelist hubloc-only.
     Operador do #2 passaria nas rules pós-M-A4 mas levaria 403 NO LOGIN. Precisa evoluir pro
     design soft allowed_email_domains por tenant (usuário PROVISIONADO loga independente de
     domínio; auto-provision só para domínio de algum tenant). Item "M-A4b", escopo próprio —
     mexe no caminho de login de prod. (Hoje esse gate é o que impede estranho de auto-provisionar
     → é pré-requisito ele continuar equivalente ao evoluir.)

0c. M-A4 ✅ PUBLICADO EM PROD 2026-07-03 — ownsTenant() autoriza SÓ por claim tenant_id
     (removido `emailAllowed() &&`). Ruleset ativo `faa492f1-c3c7-45d9-b5b3-8f141af2a1c9`
     (createTime 21:34:18Z; backup do anterior em firestore.rules.bak-publicado-20260703 +
     rollback via scratchpad publish_ma4_rules.py --rollback). Revisão adversarial (18 agentes,
     0 erros): veredito SHIP, 0 bloqueadores — para a população viva do hubloc é NO-OP byte-a-byte
     (13/13 ativos com claim; o termo removido era redundante com deter o claim, que só é emitido
     após passar o mesmo gate de email do backend). Canário OK (operador comum + admin enviam/recebem).
     4 FOLLOW-UPS pré-existentes (NÃO bloquearam este deploy; são PRÉ-REQUISITO do #2 — grupo "M-A4b"):
       (i)  OFFBOARDING ⭐ — deactivate_user (database_firestore.py:393) só grava is_active=0;
            falta revoke_refresh_tokens + remover claim tenant_id/role + invalidar cache. As ~11
            subcoleções gateadas SÓ por ownsTenant (departments:204, wa_contacts/wa_conversations
            via canSeeContactScoped:209/213, wa_messages não-backup:221, system_settings:240,
            health_status:259, gc_*:264/269, messages:274, media_assets:291) não checam
            operator_profile ativo → desativado com claim residual lê PII do próprio tenant por
            ~1h (TTL do ID token) até revogar. Alternativa/complemento: trocar essas subcoleções
            para tenantOperatorActive (que exige profile ativo).
       (ii) ROLE STALE — troca de cargo na UI (main.py:666) não reescreve o claim role
            (auth._resolve_tenant_id early-return em auth.py:114); admin rebaixado mantém leitura
            privilegiada direta (tokenRole em isPrivilegedInTenant). Reemitir claim role +
            revoke_refresh_tokens na troca, ou rules privilegiadas consultarem operator_profile.
       (iii) MIS-PROVISIONAMENTO cross-tenant ao abrir o gate — _resolve_tenant_id faz fallback
            cego p/ _DEFAULT_TENANT=hubloc (auth.py:172) e admin_create_user (main.py:640) cria
            operador SEM claim. Antes de ampliar ALLOWED_FIREBASE_EMAIL_DOMAIN p/ o #2: setar
            claim atômico na criação (como ensure_tenant_admin) e remover o default cego p/ hubloc.
       (iv) storage.rules (LOW) — ainda whitelist single-tenant hubloc (falta até
            castrointelligence@gmail.com); inócuo hoje (mídia via backend Admin SDK main.py:448,
            sem Storage client-side). Migrar p/ claim tenant_id antes de ligar leitura client-side.

0d. M-A4b (lifecycle de claims) ✅ EM PROD 2026-07-04 — commit 1dbb752, rev castro-crm-00041-rij.
     Fecha 0c(i) OFFBOARDING e 0c(ii) ROLE STALE, mais o guard anti-ressurreição:
     - DELETE /api/admin/users/{id}: limpa claim (clear_tenant_claims, preserva extras;
       UserNotFound=ok) + revoke + invalida cache; guard em auth.authenticate_firebase_token
       nega login de conta DESATIVADA (403) ANTES do auto-provision → offboarding TERMINAL
       mesmo com AUTO_PROVISION=true (não depende mais de flipar o flag); DELETE idempotente
       (get_user_raw_by_id → retry do clear em vez de 404); retorna claims_cleared.
     - PUT /api/admin/users/{id}: reemite claim role por divergência do CLAIM (re-salvar = retry)
       + revoke + invalida cache; guard cross-tenant.
     - POST /api/admin/users: provision_operator (tenant_bootstrap) — lookup-only da conta
       Firebase (não pré-cria: 8/13 usam senha), claim atômico se conta existe, guard
       "um email=um tenant" (409); recusa recriar sobre desativado (DeactivatedUserError→409,
       evita gêmeo ativo+inativo que sombrearia o guard). Helpers: clear_tenant_claims,
       get_firebase_uid_by_email, get_user_raw_by_firebase_uid_or_email, get_user_raw_by_id.
     Revisões: core SHIP (22 ag) + delta SHIP (gate pré-deploy de duplicatas PASSOU: 13 docs, 0
     gêmeos). Testes: 44 (claims) + 11 (guard) em memória + integração ponta-a-ponta em teste@
     contra Firebase real (restaurada). Rollback: update-traffic p/ rev anterior 00040-*.
     PENDENTE do grupo M-A4b (NÃO shipado; pré-#2): 0c(iii-parcial) matar fallback cego
     _DEFAULT_TENANT=hubloc + AUTO_PROVISION tenant-aware; 0b gate de login por domínio
     (allowed_email_domains soft); 0c(iv) storage.rules. Follow-ups: disabled=True na conta
     Firebase ao desativar (belt-and-suspenders — fecha 100% o resíduo client-SDK se o clear
     falhar; muda reativação p/ exigir re-habilitar); guards de escalação (supervisor não
     cria/promove admin, ninguém muda próprio cargo) → M-B2 RBAC.

0f. LOGIN TENANT-AWARE (mata _DEFAULT_TENANT cego + gate 0b) ✅ EM PROD 2026-07-06 —
     rev castro-crm-00047-sin (rollback = update-traffic p/ 00045-xim). Fecha os
     bloqueadores 0b (gate de login hubloc-only) e 0c(iii) (mis-provisionamento cego).
     Resolução de tenant no login (auth.py): claim → domínio (allowed_email_domains do
     tenant) → rede de transição (single_active_tenant, só enquanto 1 tenant; desarma ao
     criar o #2). Login que não resolve tenant = NEGADO (sem default cego). Gate tenant-
     aware (_login_gate): founder OU claim OU domínio casa tenant. AUTO_PROVISION só por
     domínio + email_verified. tenant_service: allowed_email_domains (create/update),
     resolve_by_domain (None se ambíguo), single_active_tenant; hubloc backfillado +
     reconciliado no boot (durável). REVISÃO ADVERSARIAL (workflow 5-dim → verify) achou
     20 sobreviventes/14 confirmados; corrigidos os críticos em commit 3732ccc: (1)
     provedor público (gmail/outlook) NUNCA vira allowed_email_domains — senão bootstrap
     derivava do email founder e qualquer conta do provedor auto-provisionava (PII cross-
     tenant); (2) email_verified obrigatório no auto-provision; (3) env-domain belt-and-
     suspenders era ilusório (autorizava sem resolver) — aposentado, robustez vem do
     reconcile no boot; (4) refresh_tenants resiliente a falha (roda no login path); (5)
     colisão de domínio rejeitada. Matriz em memória 13/13. CANÁRIO staging (dados reais):
     admin 200 sem churn, operador 200 escopo próprio, ESTRANHO gmail 403 + zero doc criado.
     Follow-ups conhecidos (não bloqueiam): founder cross-tenant sem claim + 2 tenants →
     403 (intencional: Cloud Run A exige tenant concreto; cross-tenant = Cloud Run B);
     cache cross-instance 60s ao criar #2 (janela transiente); guarda-corpo de domínio na
     UI (backend devolve domain_warning; falta dialog de confirmação no frontend).

0g. STORAGE (0c(iv)) ✅ RESOLVIDO 2026-07-06 — o "bloqueador" não existia na prod nova.
     Investigação (a pergunta "está usando storage antigo?" destravou): a prod Oregon usa
     um bucket GCS PURO `...-castro-crm-media` (não Firebase Storage), servido 100% pelo
     backend via Admin SDK (serve_media → download_as_bytes); o frontend NÃO usa Storage
     SDK. Não existe release `firebase.storage/...` no projeto novo — o storage.rules do
     repo (whitelist hubloc) estava publicado SÓ no projeto ANTIGO (SP). Logo, sem
     whitelist em vigor pra travar o #2. Ações: (1) storage.rules reescrito deny-all
     (backend-only) como backstop documentado — se um dia linkar Firebase Storage, o
     default do Firebase é permissivo; (2) PAP `enforced` no bucket novo (higiene LGPD;
     mídia segue 200); (3) bucket Firebase ANTIGO (SP, `.firebasestorage.app`, 1487 objs
     de mídia duplicada) LIMPO — prova de completude confirmou que nada que a prod
     referencia vive só lá (2487/2532 mídias no bucket novo; 45 refs órfãs de 10/jun
     tarde = dado de teste do cutover, sumido de AMBOS os buckets, sem importância);
     soft-delete 7 dias como rede. Follow-up cosmético: 45 mensagens de 10/jun com
     media_path apontando pra mídia inexistente (404 nesses anexos; não vale limpar).
     Decommission do projeto antigo (firestore-backups etc.) fica como item à parte.
     >>> PRÉ-#2 COMPLETO. Próximo: Cloud Run B mínimo (Sprint 0 + criar-tenant) → M-A5 GATE.

0h. CLOUD RUN B — FASE A / SPRINT 0 (fundação super-admin) ✅ FEITO 2026-07-07.
     Fundação (não toca Cloud Run A operacional; escopo enxuto seguro aprovado):
     - `super_admin.py` (camada de dados, sem FastAPI): super_admins/{uid} (root, source
       of truth) — get/is_active/seed/list/mfa_enrolled/deactivate; log_system_audit()
       em audit_logs_system/{id} (root, imutável; PROPAGA falha ≠ log_audit best-effort,
       pra audit-antes-da-ação nas ops nucleares).
     - firebase_admin_client.set_super_admin_claim (preserva demais claims, leitura estrita).
     - `scripts/grant_super_admin.py` — CLI --seed/--list/--grant/--revoke; grant exige doc
       ativo + mfa_enrolled (--allow-no-mfa p/ bootstrap). SEED JÁ RODADO EM PROD: 2 docs
       (rafa uid mbg9..., izael uid dFn2...), is_active=true, mfa_enrolled=false, claim NÃO
       concedido (espera MFA). Inertes até o grant.
     - firestore.rules: isSuperAdmin() (claim fast-path; CEGO a tenant-scoped — §4.1) +
       castro_crm_super_admins/* e castro_crm_audit_logs_system/* (read só super-admin,
       write false). PUBLICADO ruleset cb1bd995 (aditivo puro vs 21cf3d0c; backup
       firestore.rules.bak-publicado-20260705). Diff = só o bloco super-admin.
     - docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md (ordem: seed→IP/TOTP→enroll→grant→kill).
     BLOQUEIO PRA FASE B (ação manual do usuário): TOTP MFA exige UPGRADE do projeto p/
     Identity Platform (a API retornou OPERATION_NOT_ALLOWED — precisa "aligned product").
     Grátis abaixo de 50k MAU, TOTP sem custo de SMS. Enrollment vem no login do Cloud Run
     B (não há auto-enroll no Console). PRÓXIMO: Fase B (serviço castro-superadmin: login+
     enroll MFA + require_super_admin + POST criar-tenant→bootstrap_tenant+audit + UI mínima).

0e. M-B2 (RBAC dinâmico) ✅ EM PROD 2026-07-06 — rev castro-crm-00045-xim (100% via
     update-traffic; rollback = update-traffic p/ 00041-rij). Staging tagged validado
     2026-07-05 (boot: seed 3 perfis + backfill 13 users, ninguém deslogado; matriz de
     rules 23/23 no motor real; canário manual admin+operador). Rules ruleset 21cf3d0c
     (perfis_acesso; backup faa492f1 no repo). CANÁRIO ACHOU 1 BUG DE DESIGN (corrigido
     em f671f88 + redeploy 00045-xim): desligar toggles do perfil_admin + guard
     anti-amplificação criava ratchet irreversível pela UI → agora perfil de sistema tem
     TODOS os toggles travados em ligado (teto do tenant) e o guard faz bypass p/ role
     admin (segue mordendo supervisor delegado); dados reparados via Admin SDK com audit
     op=repair. Único 503 no cutover = blip de quota cpu_allocation (follow-up: quota
     Cloud Run apertada p/ revisões staging+prod simultâneas).
     Fases 1–4 do PLANO_RBAC §3.8 numa tacada, com dual-check (dia 0 = comportamento
     idêntico; fallback = seed da role):
     - `rbac.py`: catálogo FIXO de 28 toggles (só chaves com enforcement real — ver
       PLANO_RBAC §3.4.1), 3 perfis seed validados 1:1 contra o inventário dos ~46
       checks de main.py + 30 do frontend; cache TTL 60s (RBAC_PERFIL_CACHE_TTL_SECONDS);
       has_permission/ensure_permission/effective_toggles; CRUD com lock do perfil_admin.
     - Seed + backfill perfil_acesso_id no bootstrap_tenant (idempotente, não sobrescreve);
       claim perfil_acesso_id em set_tenant_claims (derivado da role se não explícito);
       clear_tenant_claims limpa também o perfil.
     - main.py: 46 checks de role migrados p/ ensure_permission/has_permission + novos
       enforcements (transfer, template, qualify, declared-name, arquivar, contato manual,
       envio própria thread, fechar/reabrir, assumir_coex) — todos true nos seeds = sem
       regressão dia 0. CRUD /api/admin/perfis-acesso (audit permission_change §3.9,
       delete bloqueado se em uso/seed). GUARDS DE ESCALAÇÃO (follow-up M-A4b): supervisor
       não cria/promove/rebaixa admin; ninguém muda o próprio cargo/perfil.
     - Frontend: perfil efetivo via /api/session + snapshot ao vivo de perfis_acesso;
       can()/useCan (deny-by-default) + canSeeAll (toggle E role — teto das rules);
       UI master-detail "Perfis de acesso" (admin) + select de perfil no editor de usuário.
     - Rules: perfis_acesso read p/ membros do tenant, write só backend. Rules seguem
       autorizando por claim role (PLANO_RBAC §3.6) — perfil ampliado além da role só
       vale no REST.
     Fase 5 (matar fallback de role) fica pós-bake-in. Divergências 1:1 documentadas no
     PLANO_RBAC §3.4.1.
     REVISÃO ADVERSARIAL (8 finders → verify) rodada 2026-07-04: 10 findings, todos
     corrigidos no commit de fixes — destaques: anti-amplificação por NÍVEL ("não concede
     o que não tem", cobre perfil-clone de admin e auto-edição de perfil), teto de role
     também no REST (can_see_all_tenant — 3 camadas em sincronia), update_user só re-deriva
     perfil quando a role MUDA (payload que ecoa role não reseta perfil custom), sem
     fallback hubloc no _resolve_tenant, claim churn zerado p/ usuários pré-M-B2, cache
     curto de falha de leitura (anti retry-storm; fallback de role cobre a janela).

0i. CLOUD RUN B — FASE B (painel super-admin) ✅ EM PROD 2026-07-11/12 — serviço
     `castro-superadmin` com imagem/SA/auth separados (rev 00001-4f4 em 11/07; rev
     00002-7pm em 12/07 com o hardening pós-revisão adversarial, 25 achados, commit
     a7cc82e). Login Firebase + TOTP obrigatório NA SESSÃO + audit-antes-da-ação +
     kill-switch por script. Editor de tenant (PATCH) na rev 00004-c8d (2026-07-31,
     commit c2d4f0e). Pipeline reproduzível: docs/DEPLOY_CLOUDRUN_B.md. DEFERIDOS:
     sessão-cookie 15min, domínio próprio, sink BigQuery, impersonate, IAP/borda.

0j. TENANT #2 LIGADO ✅ — `varizemed-test` (14/07) e o real `varizemed` (28/07, plano
     ai_custom) foram criados PELO painel B (prova no audit imutável audit_logs_system);
     fluxo CX ponta a ponta em prod desde 29/07 e Modo Recepção (ADR 0010) desde 06/08.
     Com 3 tenants ativos, single_active_tenant() retorna None => login sem claim e sem
     domínio casado é 403 (rede de transição desarmada, by design).

PRÉ-#2 (tudo validado no hubloc antes de ligar o cliente novo):
  A. Isolamento de canais
     M-A1  ADR 0007 Fase 1 (filtro lógico + id UUID na fila)   [S, baixo risco]  ✅ EM PROD
     M-B1  ADR 0007 Fase 2 (migração estrutural dos 4 canais)  [L, alto risco]   (D2)
           ⚠ ABERTO em 2026-08-21 — reavaliar antes de executar: hoje `channels` é
           invariante GLOBAL (_GLOBAL_COLLECTIONS, ver CLAUDE.md); tirar de lá já
           causou perda crônica de inbound (fix em prod rev 00065-zif, 2026-07-16).
  B. Onboarding
     M-A2  bootstrap_tenant(tid) + claim atômico (D6)          [M]  ✅ EM PROD
     Sprint 0 RBAC/super-admin (§6 PLANO_RBAC — fundação)      [S]  ✅ 2026-07-07 (0h)
     Cloud Run B mínimo (só criar tenant, D3)                  [L]  ✅ EM PROD (0i)
  C. RBAC dinâmico no hubloc (D4 — antes do #2)
     M-B2  ✅ EM PROD 2026-07-06 (ver bloco 0e)
  D. Rules + gate
     M-A4  ✅ FEITO 2026-07-03 — removido emailAllowed() do ownsTenant (isolar por
           claim tenant_id). Publicado + canário OK. Ver bloco 0c. Falta: endurecer
           rules de STAGING (espelhar PROD) — pendente, baixo risco (staging vazio em Oregon).
     M-A5  ensaio de onboarding + auditoria de vazamento (GATE) — ensaio FEITO no
           painel B (tenant de ensaio criado/limpo + isolamento, 07/2026) e o #2 real
           nasceu por lá em 28/07. Auditoria formal de vazamento: ⚠ verificar.

LIGAR TENANT #2 pela UI do Cloud Run B.  ✅ FEITO — ver blocos 0i/0j.

PÓS-#2:
  M-B3 (crescer Cloud Run B: impersonate/analytics/kill-switch)
  M-B4 (billing enforcement) → M-B5 (self-service + white-label)
```

**Fluxo de cada milestone:** implementar → **revisão adversarial (Workflow)** → **staging**
(tagged, no-traffic) → **testes por agentes (D5)** → aprovação → **prod** (`update-traffic`).

---

## FLUXO DE ONBOARDING DO TENANT #2 (criação → operador atendendo)

> Modelo **standard** (D1). Cada passo marca **[hoje]** (já existe) ou **[milestone]** (falta construir).

**Fase 0 — Pré-requisitos (uma vez):** ADR 0007 Fase 1 no ar **[M-A1]**; rules PROD publicadas
**[verify-first]**; RBAC dinâmico migrado no hubloc **[M-B2/D4]**; Cloud Run B mínimo +
super-admins provisionados **[Sprint 0 + D3]**.

**Fase 1 — Criar o tenant (super-admin, Cloud Run B):**
1. Super-admin loga no painel B (MFA) **[Cloud Run B]**.
2. Formulário: nome, CNPJ, plano, email do admin do cliente, **`allowed_email_domains`**
   (ver "Identidade/domínio do tenant" abaixo — default = domínio do email do admin).
3. B chama `bootstrap_tenant(tid,...)` (Admin SDK) **[M-A2]**: `create_tenant` → `tenants/{tid}`
   (metadata/billing) **[hoje: tenant_service]**; semeia setores default; semeia 3 perfis RBAC
   **[M-B2]**; cria admin do cliente; `set_tenant_claims`+`revokeRefreshTokens` (D6).
4. Audit em `audit_logs_system` **[Sprint 0]**; convite por email ao admin do cliente.

**Fase 2 — Provisionar o canal WhatsApp (standard):**
5. Número WABA da empresa do cliente no portfólio **Castro Operações** (managed billing);
   método de pagamento Meta configurado lá.
6. **Self-service via Embedded Signup standard [HOJE — Método B já feito]:** botão
   "☁️ Conectar numero (Cloud API)" (admin/sup) → ES com `EMBEDDED_SIGNUP_CONFIG_ID_STANDARD`
   (2342621062931210, plugado em prod) → `exchange` → `create_channel` carimba `tenant_id` do
   **contexto** (claim do admin) + `upsert_phone_routing(phone_id, tid, channel_id)`. O webhook
   passa a rotear. (Meta exige verificação SMS/ligação do número — passo de hardware, não código.)

**Fase 3 — Admin do cliente configura (Cloud Run A / CRM):**
7. Admin loga no CRM; JWT já traz `tenant_id` → vê só o próprio tenant **[hoje + D6]**.
8. Ajusta setores (renomear/deletar — seguro pós-hardening) **[hoje]**; cria operadores
   (`gerenciar_usuarios`) — cada um com claim atômico **[M-A2/D6]**; ajusta perfis RBAC se
   quiser **[M-B2]**; configura bot (LGPD→setor), templates **[hoje]**.

**Fase 4 — Operador atende:**
9. Operador loga; JWT: `tenant_id` + `role`/`perfil` → vê só o tenant e só o que o perfil permite
   (próprios + pool sem dono) **[hoje + M-B2]**.
10. Cliente final manda msg → webhook Meta → `phone_routing[phone_id]` → tenant → `set_tenant_context`
    → grava em `tenants/{tid}/wa_*` **[hoje]**. Bot roteia por setor → pool "Novos" → operador assume.

**Transversal:** isolamento em 3 camadas (rules por path/claim + backend por contexto + frontend);
billing managed (health-cron monitora pagamento por canal); LGPD (Oregon DPA/SCCs; coex→ADR 0002).

### Identidade/domínio do tenant — decisão SOFT (fechada 2026-07-03)

**O domínio NÃO autoriza acesso — o claim `tenant_id` autoriza** (setado no provisionamento;
o M-A4 remove a whitelist de email de propósito). Um operador pode ter qualquer email (domínio
do cliente, gmail, etc.); o que vale é ter sido provisionado (claim).

Mesmo assim, guardar o domínio no tenant (`allowed_email_domains: ["clientenovo.com.br"]`, LISTA,
default = domínio do email do admin, **editável** pelo admin do tenant e/ou super-admin) por 2 usos:
- **Guarda-corpo:** ao criar um operador com email fora do(s) domínio(s), o sistema **avisa**
  ("fora dos domínios, adicionar mesmo assim?") — evita botar operador no tenant errado. Combina
  com o guard "um email = um tenant" já no `bootstrap_tenant`.
- **Self-service / roteamento:** login Google novo (sem claim ainda) de um domínio conhecido →
  roteia pro tenant certo, em vez do fallback "hubloc" errado do `auth._resolve_tenant_id`.

**Modelo SOFT (Forma A — escolhida):** o domínio é guarda-corpo + roteamento, **nunca a trava**.
Exceção (operador de fora do domínio, ex: contratado gmail) **não é um campo/allowlist** — é só
o admin criar o operador mesmo assim (com o aviso). Os "de fora" são deriváveis (operadores cujo
email não bate com nenhum domínio) sem campo extra. Rejeitada a Forma B (campo `extra_allowed_emails`
explícito) por adicionar manutenção sem ganho de acesso.

**Pré-requisito técnico:** criar operador pela UI deve **setar o claim** (igual o `bootstrap_tenant`
faz pro admin) — senão o operador loga sem claim e o domínio vira NECESSÁRIO pra rotear. Ideal:
criar operador já seta o claim (dispensa o domínio) E guardamos o domínio como guarda-corpo/self-service.

---

# PARTE 1 — DETALHE DO MULTI-TENANT

## 1.1 Já pronto (não refazer)

- Context machinery (`firestore_common.py`), resolução por request (`auth.py` + middleware
  `main.py:160-188`), `tenant_service.py` CRUD + `phone_routing`, webhook O(1) (`webhook.py:47-67`),
  `wa_conversations` + auditoria coex, usage/402/health-cron per-tenant, **rules PROD estritas**
  (`firestore.rules:177-287`).

## 1.2 O gargalo — ADR 0007 (canais flat)

`castro_crm_channels` (4 docs) e `castro_crm_pending_webhook_events` estão flat, fora de
`tenants/{tid}/`. Riscos no 2º tenant: (1) READ cross-tenant em `GET /api/admin/channels`;
(2) WRITE cross-tenant gravíssimo — `_default_channel_id` é int global, envio sem `channel_id`
sai pela WABA do outro tenant; (3) colisão de `event_id` na fila. **Bloqueante, não teórico.**

## 1.3 Milestones do caminho crítico

| Milestone | O quê | Esforço | Arquivos |
|---|---|---|---|
| **M-A1** | ✅ EM PROD — ADR 0007 Fase 1: filtro por `get_tenant_context()` em `get_all_active_channels`/`get_channels_for_user`; `_default_channel_id` vira `dict[tid]`; UUID em `enqueue_pending_event`. | S | `channel_service.py`, `pending_events.py`, `main.py` |
| **M-A2** | ✅ EM PROD — `bootstrap_tenant(tid)`: `create_tenant` + `bootstrap_departments` + admin com `set_tenant_claims`+`revokeRefreshTokens` na criação (D6). Refatorar startup do hubloc pra usar. | M | `main.py`, `tenant_service.py`, `firebase_admin_client.py` |
| **M-B2** | ✅ EM PROD 2026-07-06 — RBAC dinâmico (D4, antes do #2): `perfis_acesso` por tenant, 3 seed = comportamento atual, `require_permission`/`useCan` dual-check, ondas, UI toggles. | L | backend + rules + frontend (PLANO_RBAC §3) |
| **Cloud Run B** | ✅ EM PROD 2026-07-11/12 (`castro-superadmin`) — Sprint 0 (§6) + serviço mínimo com criação de tenant (D3). | L | novo serviço |
| **M-B1** | ⚠ **ABERTO** (reavaliar: `channels` é hoje invariante global) — ADR 0007 Fase 2: migrar canais → `tenants/{tid}/channels`, cache por tenant, backfill `phone_routing`, preservar `channel_id`. | L | `channel_service.py` |
| **M-A4/A5** | ✅ **M-A4 FEITO (2026-07-03):** removido `emailAllowed()` do `ownsTenant` (isolar por claim `tenant_id`) — publicado em prod, canário OK, veredito de revisão SHIP (ver bloco 0c + 4 follow-ups pré-#2). Pendente: endurecer rules de STAGING (espelhar PROD, baixo risco); M-A5 ensaio de onboarding (GATE). | M | `firestore.rules` |

---

# PARTE 2 — INVENTÁRIO DE OUTRAS PENDÊNCIAS (fora do caminho do #2)

### LGPD / Segurança
- **Rules de `wa_messages` por dono** (denormalizar `assigned_to_uid` + backfill) — camada mais fraca; virou a **fase F4** do `docs/PLANO_J3_LGPD_E_REVOGACAO.md`.
- Backfill de conversas órfãs coex — parcial, monitorar.
- **ADR 0001** — evitar Embedded Signup duplicado (409 + transferir posse) — proposto.
- **Oregon LGPD** — DPA/SCCs + RoPA/RIPD (Brasil→EUA) — pendente (o DPA entrou como frente do `docs/PLANO_J3_LGPD_E_REVOGACAO.md`).

### Custo Firestore (write-side)
- Unificar 2× `.set` em `wa_contacts`; `skip_metrics` p/ `direction='system'`; coalescing de `update_wa_message_status`.
- Recência inflada por msg de sistema — deployado, monitorar.

### Lead/Atendimento (Fase 5B+)
- Categorização obrigatória no fechamento; resumo IA (Vertex); read-only pós-takeover; sticky-routing TTL; painel de agenda por operador.

### Billing / Onboarding UI
- `<TenantHealthBanner/>` completo; página `/setup`; modal 402; card "Uso este mês".

### Canais / Embedded Signup
- 2º número standard — bloqueado em hardware. Método B (signup standard na UI) ✅ em prod; import real do Backup ✅ (`scripts/import_backup_hubloc.py`, aba Caixa Backup em prod).

### Infra / Tech-debt
- Google Chat; Python 3.8 EOL (2026-10-04); re-submeter screencast App Review; pinning de tráfego Oregon (`update-traffic` manual).

---

## Como validar (por milestone — D5, agentes)

- **M-A1:** 2 canais fake com `tenant_id` distintos → `get_all_active_channels()`/`get_default_channel()` diferem por contexto; 2 pending events em contextos distintos → ids distintos.
- **M-A2:** `bootstrap_tenant('teste-x')` em staging → subcoleções semeadas, admin com claim, admin loga e vê só o próprio tenant; hubloc no startup inalterado.
- **M-B2 (RBAC):** dia 0 = comportamento idêntico ao anterior (grep 1:1 dos checks); dual-check não regride; UI de toggles reflete o perfil.
- **Rules (M-A4):** simulador → operador de A negado em `tenants/B/...`, permitido no próprio.
- **Gate (M-A5):** onboarding completo + checklist de vazamento cross-tenant.

## Mapa de fontes

- `docs/PLANO_COEXISTENCE_REFATORACAO.md` — plano Fases 1-4.
- `docs/decisions/0007-...md` — **ADR do gargalo de canais** ⭐ · `0002` (LGPD coex) · `0001` (signup duplicado).
- `docs/PLANO_RBAC_E_SUPER_ADMIN.md` — RBAC dinâmico (§3) + Cloud Run B (§4-6, Sprint 0).
- Código: `firestore_common.py`, `tenant_service.py`, `channel_service.py`, `pending_events.py`, `auth.py`, `webhook.py`, `firestore.rules`, `main.py`.
