# Roadmap Multi-Tenant (Fase 2) — Decisões fechadas + Ordem de execução

> **Decisões D1-D6 FECHADAS em 2026-07-01. Execução iniciada.**
> Documento vivo — atualizar conforme os milestones forem entregues.

## Contexto

O CRM (FastAPI + Firestore + React, Cloud Run Oregon) opera hoje **single-tenant**
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
     Drift: repo tem castrointelligence@gmail.com no emailAllowed() que o publicado não tem → republicar.

PRÉ-#2 (tudo validado no hubloc antes de ligar o cliente novo):
  A. Isolamento de canais
     M-A1  ADR 0007 Fase 1 (filtro lógico + id UUID na fila)   [S, baixo risco]  ← COMEÇANDO
     M-B1  ADR 0007 Fase 2 (migração estrutural dos 4 canais)  [L, alto risco]   (D2)
  B. Onboarding
     M-A2  bootstrap_tenant(tid) + claim atômico (D6)          [M]
     Sprint 0 RBAC/super-admin (§6 PLANO_RBAC — fundação)      [S]
     Cloud Run B mínimo (só criar tenant, D3)                  [L, front-load segurança]
  C. RBAC dinâmico no hubloc (D4 — antes do #2)
     M-B2  seed perfis + require_permission/useCan dual-check + ondas + UI toggles  [L]
  D. Rules + gate
     M-A4  rules multi-tenant: remover emailAllowed() do ownsTenant (isolar por
           claim + operator_profile) + endurecer rules de STAGING            [M]
     M-A5  ensaio de onboarding + auditoria de vazamento (GATE)

LIGAR TENANT #2 (standard) pela UI do Cloud Run B.

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
2. Formulário: nome, CNPJ, plano, email do admin do cliente.
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
| **M-A1** | ADR 0007 Fase 1: filtro por `get_tenant_context()` em `get_all_active_channels`/`get_channels_for_user`; `_default_channel_id` vira `dict[tid]`; UUID em `enqueue_pending_event`. | S | `channel_service.py`, `pending_events.py`, `main.py` |
| **M-A2** | `bootstrap_tenant(tid)`: `create_tenant` + `bootstrap_departments` + admin com `set_tenant_claims`+`revokeRefreshTokens` na criação (D6). Refatorar startup do hubloc pra usar. | M | `main.py`, `tenant_service.py`, `firebase_admin_client.py` |
| **M-B2** | RBAC dinâmico (D4, antes do #2): `perfis_acesso` por tenant, 3 seed = comportamento atual, `require_permission`/`useCan` dual-check, ondas, UI toggles. | L | backend + rules + frontend (PLANO_RBAC §3) |
| **Cloud Run B** | Sprint 0 (§6) + serviço mínimo com criação de tenant (D3). | L | novo serviço |
| **M-B1** | ADR 0007 Fase 2: migrar canais → `tenants/{tid}/channels`, cache por tenant, backfill `phone_routing`, preservar `channel_id`. | L | `channel_service.py` |
| **M-A4/A5** | **Rules multi-tenant:** tirar `emailAllowed()` do `ownsTenant`/`tenantOperatorActive` (isolar por claim `tenant_id` + `operator_profile` ativo — hoje a whitelist hubloc BARRARIA operador do #2); endurecer rules de STAGING (espelhar PROD); ensaio de onboarding (GATE). | M | `firestore.rules` |

---

# PARTE 2 — INVENTÁRIO DE OUTRAS PENDÊNCIAS (fora do caminho do #2)

### LGPD / Segurança
- **Rules de `wa_messages` por dono** (denormalizar `assigned_to_uid` + backfill) — camada mais fraca; verificar escopo atual.
- Backfill de conversas órfãs coex — parcial, monitorar.
- **ADR 0001** — evitar Embedded Signup duplicado (409 + transferir posse) — proposto.
- **Oregon LGPD** — DPA/SCCs + RoPA/RIPD (Brasil→EUA) — pendente.

### Custo Firestore (write-side)
- Unificar 2× `.set` em `wa_contacts`; `skip_metrics` p/ `direction='system'`; coalescing de `update_wa_message_status`.
- Recência inflada por msg de sistema — deployado, monitorar.

### Lead/Atendimento (Fase 5B+)
- Categorização obrigatória no fechamento; resumo IA (Vertex); read-only pós-takeover; sticky-routing TTL; painel de agenda por operador.

### Billing / Onboarding UI
- `<TenantHealthBanner/>` completo; página `/setup`; modal 402; card "Uso este mês".

### Canais / Embedded Signup
- 2º número standard (3351-7604) — bloqueado em hardware; Método B (signup standard na UI); import real do Backup (~500 JSONs).

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
