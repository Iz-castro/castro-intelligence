# Plano RBAC Dinâmico + Painel Super Admin

> **Source of truth** para controle de acesso configurável (RBAC) e
> arquitetura do painel super admin do Castro Intelligence CRM.
>
> **Substitui:** rascunho original `plano020626.md` (mantido apenas
> local, não versionado; conteúdo absorvido aqui).
> **Absorve:** roadmap pós-Fase 2 do
> [PLANO_COEXISTENCE_REFATORACAO.md](PLANO_COEXISTENCE_REFATORACAO.md)
> relativo a tenant onboarding, cross-tenant analytics e backup/export.
> **Não substitui:** PLANO_COEXISTENCE_REFATORACAO (Fases 1-4 de
> multi-tenant + sub-threads continuam válidas) nem
> PLANO_LEAD_ATENDIMENTO_E_REGRAS (regras de Lead/Atendimento continuam
> válidas; modos supervisor continuam funcionando e vão migrar pra
> toggles RBAC quando este plano rodar).

---

## 0. Status e decisões tomadas

| Data | Decisão | Estado |
|---|---|---|
| 2026-06-02 | Doc primeiro, código depois | aprovado |
| 2026-06-02 | Dois Cloud Run separados — A operacional + B super admin | aprovado |
| 2026-06-02 | Abandonar prefixo `/api/platform/` em Cloud Run A (era reserva no PLANO_COEXISTENCE §2.4) | aprovado |
| 2026-06-02 | Impersonate read-only (modo B) — sem opção full | aprovado |
| 2026-06-02 | Super admins iniciais: `rafaluisc@outlook.com` + `izaeldecastro@gmail.com` | aprovado |
| 2026-06-02 | Modelo de identidade super admin: híbrido (claim `super_admin: true` fast-path + doc `super_admins/{uid}` source of truth) | aprovado |
| 2026-06-02 | Termos de Uso devem cobrir suporte/debug com impersonate read-only | aprovado |
| 2026-06-02 | RBAC dinâmico via perfis em subcoleção por tenant + claim leva `perfil_acesso_id` | aprovado |
| 2026-07-04 | §10.1 resolvida: catálogo de toggles é FIXO da plataforma; admin escolhe perfis/valores | aprovado |
| 2026-07-04 | Catálogo enxuto: só toggles com enforcement real no código (ver §3.4.1) | aprovado |
| 2026-07-04 | **M-B2 IMPLEMENTADO** (fases 1–4 do §3.8 de uma vez, dual-check ativo; fase 5 pendente). Código: `rbac.py` + migração `main.py`/`App.tsx`/`CrmContext.tsx` + rules `perfis_acesso` + UI master-detail. Pendente: staging → prod. | implementado |

Decisões em aberto listadas em §10.

---

## 1. Contexto e motivação

### 1.1 Estado atual do controle de acesso

O sistema hoje opera com 3 roles hardcoded (`admin`, `supervisor`,
`operador`) gravadas em duas fontes:

- Firebase custom claim `role` no JWT (lida por rules + backend)
- Documento `tenants/{tid}/operator_profiles/{uid}.role` (espelho)

A verificação é feita por `if user["role"] in (...)` espalhado em endpoints
FastAPI e por `role === "admin"` espalhado em componentes React.
Mapeamento atual em
[`database_firestore.py:1332`](../database_firestore.py#L1332)
(visibilidade) e [`firestore.rules`](../firestore.rules) (helpers
`tokenRole()`, `isPrivilegedInTenant()`, `canSeeContactScoped()`).

### 1.2 Por que mudar

- Não escala para autonomia do administrador de cada tenant — hoje só
  Castro Intelligence consegue ajustar política.
- Não expressa nuances já implementadas em produção: Sussurro,
  Co-pilotagem, Takeover supervisor (ver
  [PLANO_LEAD_ATENDIMENTO_E_REGRAS.md](PLANO_LEAD_ATENDIMENTO_E_REGRAS.md)
  §3.2) hoje são checks role-hardcoded.
- Mudar política exige mexer em código backend, rules e frontend
  simultaneamente — alto risco, lento.
- Pendente histórica conhecida: "read-only operador pós-takeover v2"
  (PLANO_LEAD_ATENDIMENTO §3.2.3) — encaixa naturalmente como toggle.

### 1.3 Estado atual do super admin

**Nada concreto.** Os planos antigos só reservaram pedaços soltos:

- PLANO_COEXISTENCE §2.1 — `_meta/system_metrics` "agregações
  cross-tenant (super-admin Castro Intelligence)"
- PLANO_COEXISTENCE §2.4 — prefixo `/api/platform/...` reservado **no
  Cloud Run A**, não implementado (esta decisão é **revertida** aqui)
- PLANO_COEXISTENCE §2.9 — rules `tenants/{tenantId}` write `if false`
  com comentário "só super-admin via Admin SDK"
- PLANO_COEXISTENCE roadmap pós-Fase 2 — tenant onboarding UI,
  cross-tenant analytics, backup/export, white-label

Faltava: identidade dedicada, MFA específico, audit imutável,
separação física, impersonate.

### 1.4 Resultado pretendido

- Admin de tenant edita política do próprio tenant via UI master-detail
  de toggles, sem deploy.
- Painel super admin separado (Cloud Run B) com identidade hardened
  para operações cross-tenant.
- Impersonate read-only auditado para suporte sem risco LGPD de "agir
  como o operador".
- Modos supervisor existentes (Sussurro/Co-pilotagem/Takeover) virem
  toggles, sem regressão de comportamento.

---

## 2. Arquitetura geral

```
                  ┌──────────────────────────────────────┐
                  │     Firestore + Auth + Storage       │
                  │     (banco único, multi-tenant)      │
                  └──────┬───────────────────────┬───────┘
                         │                       │
                rules    │                       │ Admin SDK
                scoped   │                       │ (bypassa rules)
                         │                       │
        ┌────────────────┴───────────┐  ┌────────┴────────────────────┐
        │  Cloud Run A — castro-crm  │  │  Cloud Run B — castro-      │
        │  (existe)                  │  │  superadmin (a criar)        │
        ├────────────────────────────┤  ├──────────────────────────────┤
        │ • Webhook Meta             │  │ • Criar/desativar tenant     │
        │ • Frontend operador        │  │ • Seed perfis RBAC inicial   │
        │ • Send mensagem            │  │ • Kill switch operador       │
        │ • Dashboard tenant         │  │ • Cross-tenant analytics     │
        │ • Sussurro/co-pilotagem/   │  │ • Backup/export tenant       │
        │   takeover supervisor      │  │ • Impersonate read-only      │
        │ • RBAC dentro do tenant    │  │   (gerador de token)          │
        ├────────────────────────────┤  ├──────────────────────────────┤
        │ DB scope: tenants/{tid}/*  │  │ DB scope: tudo (root + all)  │
        │ Auth: Firebase + claims    │  │ Auth: Firebase + MFA real    │
        │   (tenant_id, role,        │  │   + claim super_admin: true  │
        │   perfil_acesso_id)        │  │ Sessão: 15min cookie         │
        │ Sessão: ~1h ID token       │  │ Domínio: admin.castro...     │
        │ Domínio: crm.hubloc...     │  │                              │
        ├────────────────────────────┤  ├──────────────────────────────┤
        │ Service Account: scoped    │  │ Service Account: Admin SDK   │
        │ Usado por: centenas de     │  │ Usado por: 2-3 humanos       │
        │   operadores/tenants       │  │   (Castro Intelligence)      │
        └────────────────────────────┘  └──────────────────────────────┘
```

**Princípio:** Cloud Run A nunca tem permissão cross-tenant, nem mesmo
para super admin. Se super admin precisa fazer algo cross-tenant, usa
Cloud Run B. Comprometer A → não compromete Castro Intelligence.

---

## 3. RBAC Dinâmico (dentro do tenant)

### 3.1. Estrutura de Dados (Firestore)

> Preservado do rascunho original.

- **Localização:** Os perfis não são globais. Eles residem em uma
  subcoleção dentro de cada Tenant:
  `tenants/{tenant_id}/perfis_acesso/{perfil_id}`.
  (Fisicamente, com o prefix do ambiente:
  `castro_crm_tenants/{tenant_id}/perfis_acesso/{perfil_id}`.)
- **Desacoplamento:** O documento individual do usuário (operador)
  não carrega uma árvore de permissões, apenas uma referência direta
  ao perfil. Hoje vive em
  `tenants/{tid}/operator_profiles/{firebase_uid}` — adiciona-se um
  campo:

```json
{
  "firebase_uid": "abc123",
  "display_name": "Maria",
  "role": "operador",
  "perfil_acesso_id": "perfil_operador_padrao"
}
```

O campo `role` é mantido por compatibilidade durante a migração
(§3.8). Após a migração, `role` vira só rótulo de UI, sem semântica.

### 3.2. Interface Administrativa (Master-Detail)

> Preservado do rascunho original.

- **Layout:** Navegação no padrão "WhatsApp Web".
  - **Painel Esquerdo (Mestre):** Lista de cartões dos perfis de
    acesso existentes na empresa e botão para criação de novos
    perfis.
  - **Painel Direito (Detalhe):** Formulário de edição composto
    exclusivamente por *Toggle Switches* (chaves booleanas) para
    evitar confusão cognitiva.
- **Agrupamento Lógico das Regras:** Visibilidade, Atendimento, Lead,
  Conteúdo, Auditoria, Gestão. Catálogo completo em §3.4.

### 3.3. Proteção Arquitetural (Lock)

> Preservado do rascunho original.

- O documento `perfil_admin` base de cada tenant recebe uma flag
  nativa: `is_system_locked: true`.
- O front-end (React) lê essa flag e **desabilita** a edição dos
  toggles críticos e a exclusão deste perfil específico. Isso previne
  que o administrador da locadora retire seus próprios acessos por
  acidente (autossabotagem).
- Lista mínima de toggles travados no `perfil_admin`:
  `gerenciar_usuarios`, `gerenciar_perfis_acesso`, `ver_todos_leads`.
- Backend também valida: PUT em perfil com `is_system_locked: true`
  rejeita mudanças nos toggles travados (defense-in-depth — UI
  desabilita, backend reforça).

### 3.4. Catálogo inicial de toggles

Lista derivada do código atual (`main.py`, `database_firestore.py`,
`firestore.rules`, `App.tsx`, `CrmContext.tsx`) e dos comportamentos
descritos no PLANO_LEAD_ATENDIMENTO. Identificadores em snake_case
estável (entram em `perfis_acesso/{id}.toggles.<chave>`).

#### 3.4.1. Catálogo REAL implementado (M-B2, 2026-07-04)

> A fonte da verdade do catálogo é `PERMISSION_CATALOG` em `rbac.py`
> (28 chaves). O inventário 1:1 dos checks reais divergiu do rascunho
> abaixo em pontos importantes — regra aplicada: **só entra no catálogo
> chave com ponto de enforcement real**; toggle sem efeito enganaria o
> admin do tenant (LGPD: pareceria mudar escopo de dados sem mudar).
>
> **Removidos do rascunho** (sem check de código controlável): 
> `ver_proprios_leads`, `ver_leads_sem_dono`, `ver_leads_setor`,
> `ver_canal_coex_proprio` (escopo do operador é estrutural — queries
> scoped + rules por claim `role`), `ver_audit_log`, `ver_transfer_log`
> (enforcement só nas rules, que não leem toggles — §3.6),
> `re_onboarding_coex` (não há fluxo distinto no código).
> **Adicionados** (ações destrutivas eram só-admin no código):
> `desativar_usuarios`, `desativar_canais`, `desativar_departamentos`,
> `gerenciar_config_sistema`.
> **Divergências 1:1 vs rascunho §3.5** (o código venceu): supervisor
> TEM `exportar_contatos`, `autorizar_coex_para_operador` e
> `gerenciar_canais`; operador TEM `transferir_atendimento` (o
> `/api/wa/transfer` nunca teve gate de role — o fluxo do bot depende).
>
> **Teto das rules:** rules seguem autorizando leitura ampla pelo claim
> `role` (§3.6). Perfil customizado que AMPLIE visibilidade além da
> role vale só no caminho REST/backend; snapshot continua limitado. No
> frontend, `canSeeAll = toggle && role privilegiada` protege os
> listeners. Visibilidade fina por toggle exige redesenho das rules
> (fora do M-B2).
>
> **Guards de escalação** (follow-up M-A4b absorvido): criar/promover
> admin exige caller admin; ninguém altera o próprio cargo/perfil;
> não-admin não rebaixa admin (`main.py` admin_create_user /
> admin_update_user — mudança consciente de comportamento).
>
> **Endurecimento pós-canário (2026-07-05):** o lock do §3.3 passou de
> "3 toggles críticos" para **TODOS os toggles do perfil de sistema
> travados em ligado** — o `perfil_admin` é o teto do tenant. Motivo:
> no canário, desligar toggles do `perfil_admin` (o modal abre com ele
> selecionado) + guard anti-amplificação criou um **ratchet
> irreversível pela UI** (o admin "perdia" o toggle e não podia mais
> religá-lo em perfil nenhum; reparo exigiu Admin SDK). Junto:
> `toggles_beyond_user` faz **bypass para role admin** (a role é o teto
> duro; o guard morde quem está abaixo, ex. supervisor delegado).
> Perfil administrativo limitado = perfil customizado com base admin.

#### Visibilidade

| Chave | Comportamento |
|---|---|
| `ver_proprios_leads` | Vê leads com `assigned_to == self` |
| `ver_leads_sem_dono` | Vê leads com `assigned_to ∈ {None, ""}` |
| `ver_leads_setor` | Vê leads com `department_id == self.department_id` |
| `ver_todos_leads` | Vê todos os leads do tenant |
| `ver_canal_coex_proprio` | Operador dono de número coex vê threads desse canal mesmo se atribuídas a outro operador |

#### Atendimento (thread)

| Chave | Comportamento |
|---|---|
| `enviar_mensagem_propria_thread` | Enviar mensagem em thread atribuída a si |
| `enviar_mensagem_qualquer_thread` | Co-pilotagem — enviar `[Supervisao - X]:` sem assumir |
| `assumir_coex_proprio` | Takeover operador dono coex (`/api/wa/conversation/{id}/takeover`) |
| `assumir_supervisor` | Takeover supervisor (`/api/wa/conversation/{id}/supervisor-takeover`) |
| `transferir_atendimento` | `POST /api/wa/transfer` |
| `fechar_atendimento_manual` | `POST /api/wa/conversation/{id}/set-attendance` close |
| `reabrir_atendimento_manual` | `POST /api/wa/conversation/{id}/set-attendance` reopen |
| `enviar_nota_interna` | Sussurro (`POST /api/wa/internal-note`) |
| `enviar_template` | `POST /api/wa/send-template` |

#### Lead (cliente)

| Chave | Comportamento |
|---|---|
| `editar_dono_lead` | `wa_contacts.assigned_to` |
| `qualificar_lead` | `PUT /api/wa/contact/{id}/qualify` |
| `editar_declared_name` | `PUT /api/wa/contact/{id}/declared-name` |
| `arquivar_lead` | Arquivar contato |
| `adicionar_contato_manual` | `POST /api/wa/contact/manual` |
| `exportar_contatos` | Export massivo (LGPD — atenção §8) |

#### Canais e templates

| Chave | Comportamento |
|---|---|
| `gerenciar_canais` | Criar/desativar canal, refresh token coex |
| `autorizar_coex_para_operador` | `POST /api/admin/users/{id}/coex` |
| `re_onboarding_coex` | Acionar fluxo Embedded Signup pós-revogação |

#### Auditoria e visualizações

| Chave | Comportamento |
|---|---|
| `ver_painel_conflitos` | Lista leads com ≥2 atendimentos ativos com operadores distintos |
| `ver_audit_log` | Acesso ao `tenants/{tid}/audit_log/*` |
| `ver_transfer_log` | Acesso ao `tenants/{tid}/wa_transfer_log/*` |
| `ver_dashboard_uso` | `tenants/{tid}/audit_metrics/usage_*` |
| `buscar_protocolo` | `GET /api/admin/protocol/{id}` |

#### Gestão de pessoas

| Chave | Comportamento |
|---|---|
| `gerenciar_usuarios` | Criar/editar/desativar operadores do tenant |
| `gerenciar_perfis_acesso` | CRUD em `perfis_acesso/*` (auto-lock em `perfil_admin`) |
| `gerenciar_departamentos` | CRUD em `departments/*` |

### 3.5. Perfis seed iniciais (reproduzem comportamento atual)

Quando RBAC dinâmico for ativado, todo tenant recebe 3 perfis seed que
**replicam o comportamento atual**. Garantia: dia 0 do RBAC = mesmo
comportamento do dia anterior.

#### `perfil_admin` (system_locked)

Todos os toggles `true`. Lock impede que o próprio admin desative
`gerenciar_usuarios`, `gerenciar_perfis_acesso`, `ver_todos_leads`.

#### `perfil_supervisor`

| Grupo | Toggles `true` |
|---|---|
| Visibilidade | `ver_proprios_leads`, `ver_leads_sem_dono`, `ver_leads_setor`, `ver_todos_leads`, `ver_canal_coex_proprio` |
| Atendimento | todos exceto `assumir_coex_proprio` (esse é exclusivo do dono) |
| Lead | todos exceto `exportar_contatos` |
| Canais | nenhum (canais hoje só admin) |
| Auditoria | todos |
| Gestão | `gerenciar_usuarios` (matches `main.py:677,710` hoje), `gerenciar_departamentos`. **NÃO** `gerenciar_perfis_acesso` |

#### `perfil_operador`

| Grupo | Toggles `true` |
|---|---|
| Visibilidade | `ver_proprios_leads`, `ver_leads_sem_dono`, `ver_leads_setor`, `ver_canal_coex_proprio` |
| Atendimento | `enviar_mensagem_propria_thread`, `assumir_coex_proprio` (se for dono), `fechar_atendimento_manual`, `reabrir_atendimento_manual`, `enviar_template` |
| Lead | `qualificar_lead`, `editar_declared_name`, `arquivar_lead`, `adicionar_contato_manual` |
| Canais | nenhum |
| Auditoria | nenhum |
| Gestão | nenhum |

**Validar antes de seedar:** rodar grep nos checks atuais e confirmar
1:1 com a tabela acima. Qualquer divergência = decisão consciente
documentada como mudança de comportamento.

### 3.6. Split claim vs Firestore

Decisão arquitetural: **claim leva apenas o ID do perfil**, perfil
fica em Firestore como source of truth, backend cacheia.

| Camada | Lê | Não lê |
|---|---|---|
| **Firebase claim** | `tenant_id`, `role` (rótulo), `perfil_acesso_id` | (não carrega toggles individuais — estouro de 1KB) |
| **Firestore rules** | claim apenas (`role` grosso para autorizar acesso amplo às subcoleções do tenant) | nunca faz `get(perfis_acesso/...)` em rule (custo) |
| **Backend FastAPI** | claim + cache em memória do perfil (LRU 5min) | fallback: lê Firestore se cache miss/invalidação |
| **Frontend** | snapshot Firestore do perfil + claim | nunca confia só em claim — usa estado React do perfil |

#### Por que (b) e não (a)/(c)

Alternativas descartadas:

- **(a) Claim guarda só `role`, perfil resolvido a cada request via
  `role → toggles` server-side.** Funciona mas gruda a política à
  estrutura de roles atual; perfil deixa de ser configurável.
- **(c) Claim expande toggles inteiros (`can_takeover: true`, etc).**
  Estoura limite de 1KB combinado de claims rápido (já temos
  `tenant_id`, `role`, futuro `super_admin`); custódia de
  versionamento vira pesadelo.

Vence **(b)**: claim cresce 1 campo (`perfil_acesso_id` ≈ 30B),
toggles vivem onde podem evoluir, cache evita custo de read.

#### Invalidação do cache

- PUT em perfil → endpoint backend invalida cache local + emite mensagem
  para outras réplicas (Pub/Sub ou polling de versão no doc).
- Mudança de `operator_profiles/{uid}.perfil_acesso_id` → backend
  invalida cache do uid e força refresh do ID token (`revokeRefreshTokens`)
  para propagar o novo `perfil_acesso_id` no claim.

### 3.7. Primitivos `require_permission` e `useCan`

#### Backend (FastAPI)

```python
# auth.py
def require_permission(perm: str):
    async def _dep(user: dict = Depends(get_current_user)):
        toggles = await get_perfil_toggles(user["tenant_id"], user["perfil_acesso_id"])
        if not toggles.get(perm, False):
            raise HTTPException(403, f"Permissão {perm} negada")
        return user
    return _dep

# uso em endpoint:
@app.post("/api/wa/transfer")
async def transfer(
    body: TransferBody,
    user: dict = Depends(require_permission("transferir_atendimento")),
):
    ...
```

`get_perfil_toggles(tenant_id, perfil_id)` lê do cache (LRU 5min) ou
Firestore.

#### Frontend (React)

```typescript
// hooks/useCan.ts
export function useCan(perm: PermissionKey): boolean {
  const { perfil } = useContext(CrmContext);
  return perfil?.toggles?.[perm] ?? false;
}

// uso em componente:
const canTransfer = useCan("transferir_atendimento");
return canTransfer ? <TransferButton /> : null;
```

`perfil` é injetado no `CrmContext` via snapshot Firestore do
`perfis_acesso/{perfil_acesso_id}` do usuário corrente.

### 3.8. Migração do estado atual (sem regressão dia 0)

Fases ordenadas. Cada uma é um deploy independente reversível:

1. **Schema + seed.** Criar `perfis_acesso/{id}` em cada tenant com os
   3 perfis seed (§3.5). Backfill
   `operator_profiles/{uid}.perfil_acesso_id` baseado em `role` atual.
   Sem mudança de comportamento — nenhum código consulta ainda.
2. **Primitivos disponíveis.** Adicionar `require_permission` e
   `useCan` na codebase. **Modo dual-check:** `require_permission(perm)`
   internamente verifica primeiro o toggle; se toggle ausente,
   fallback para o check antigo de `role`. Permite usar nos endpoints
   sem migrar todos.
3. **Migrar endpoints/UI** em ondas:
   - Onda 1: Atendimento (takeover, transferir, fechar, sussurro,
     co-pilotagem) — mais sensível, mais visível
   - Onda 2: Lead (qualificar, editar, arquivar)
   - Onda 3: Auditoria (conflitos, audit log, dashboard)
   - Onda 4: Gestão (usuários, canais, departments, perfis_acesso)
4. **Painel UI de edição de perfis** (no CRM, para admin do tenant).
   Master-detail conforme §3.2.
5. **Remover fallback de role.** Quando todos os checks foram
   migrados, `require_permission` para de olhar `role`. `role` vira
   só rótulo de UI.

Cada onda valida em staging antes de prod (gate atual:
`gcloud run deploy castro-crm-staging ... && ... castro-crm ...`).

### 3.9. Audit de mudanças de perfil

Toda criação/alteração/exclusão de perfil ou alteração de
`operator_profiles/{uid}.perfil_acesso_id` gera entry em
`tenants/{tid}/audit_log/`:

```python
log_audit(
    actor_uid=current_user["firebase_uid"],
    action="permission_change",
    detail={
        "perfil_id": "perfil_supervisor",
        "before": {"transferir_atendimento": True},
        "after": {"transferir_atendimento": False},
        "scope": "perfil",  # ou "user" se foi mudança de perfil_acesso_id de um user
    },
)
```

Inalterável pelo admin do tenant (rules: `audit_log` é write-only via
Admin SDK do backend).

---

## 4. Painel Super Admin (Cloud Run B)

### 4.1. Separação de Serviços e Infraestrutura

> Preservado do rascunho original, com ajustes.

- **Serviço CRM (Cloud Run A — `castro-crm`):**
  - Lida com webhooks da Meta, front-end do cliente e IA de resumo.
  - Escopo confinado: Regras de segurança rigorosas garantem que o
    serviço só leia e escreva dados dentro do caminho
    `tenants/{tenant_id_da_requisicao}`. Cego para o resto do banco.
  - **Mesmo com claim `super_admin: true`**, rules de A não liberam
    operações cross-tenant. Defense-in-depth: comprometer claim ≠
    atacar via A.
- **Serviço Super Admin (Cloud Run B — `castro-superadmin`, a criar):**
  - Aplicação web completamente separada (domínio próprio
    `admin.castrointelligence.com.br`).
  - Utiliza Firebase Admin SDK com privilégios totais de sistema.
  - Responsável exclusivo pela criação de novos Tenants, faturamento,
    injeção da seed de Perfis de Acesso (RBAC) durante o onboarding
    de uma nova empresa, gerador de token de impersonate (§5),
    métricas cross-tenant, kill switch.

### 4.2. Gestão de Identidade do Super Admin (Modelo Híbrido)

> Preservado do rascunho original.

A validação de quem é o dono do SaaS utiliza a abordagem de maior
performance e segurança no Firebase:

- **Custom Claims (O "Fast-path"):** A variável `super_admin: true`
  é injetada no JWT (token) via Firebase Auth. Utilizada para liberar
  acessos amplos em rules **globais** (não em rules de A) sem gerar
  custos de leitura no Firestore.
- **Firestore Base (Source of Truth):** Um documento em
  `super_admins/{uid}` (coleção root, não tenant-scoped). É utilizado
  pelo backend (Cloud Run B) para validação profunda em rotas
  sensíveis (escrita, leitura cross-tenant e exportação de dados).
  **O Claim sozinho não autoriza operações nucleares.**

Schema do doc:

```json
{
  "email": "rafaluisc@outlook.com",
  "display_name": "Rafael Castro",
  "granted_by": "bootstrap",
  "granted_at": "2026-06-02T...",
  "reason": "founder",
  "mfa_enrolled": true,
  "is_active": true,
  "last_seen_at": "...",
  "scopes": ["create_tenant", "read_cross_tenant", "kill_switch", "impersonate"]
}
```

`scopes` permite no futuro super admin "junior" com subset (ex.: só
suporte com impersonate, sem criar tenant). Por hora, todos os 2
super admins iniciais têm o array completo.

### 4.3. Checklist Rigoroso de Segurança e LGPD

> Preservado do rascunho original, expandido.

Para evitar o "cenário nuclear" (vazamento de dados pessoais de
múltiplos tenants), o serviço Super Admin obedece a quatro leis:

1. **MFA Obrigatório.** O acesso ao painel do Cloud Run B exige
   Autenticação de Dois Fatores (TOTP/SMS) habilitada no Firebase
   Auth. O backend exige `mfa_enrolled: true` no doc **E** valida que
   a sessão atual veio de um sign-in com MFA real — não basta o flag
   estar ligado no enrollment (§4.5).
2. **Audit Trail Intocável.** Qualquer ação realizada pelo Super
   Admin (criar tenant, ler logs, alterar permissões, iniciar
   impersonate) gera uma gravação automática na coleção global
   `audit_logs_system` contendo: *quem fez*, *quando*, *IP*, *user
   agent* e o *motivo da operação*. Replicado para BigQuery como
   source of truth imutável (§4.6).
3. **Revogação Instantânea (Kill Switch).** Em caso de
   comprometimento, a exclusão do documento `super_admins/{uid}`
   somada ao comando `admin.auth().revokeRefreshTokens(uid)` invalida
   instantaneamente a sessão ativa, anulando o acesso antes que o TTL
   do token expire (§4.8).
4. **Sessão Curta.** TTL de 15 minutos via Firebase session cookies
   custom (`admin.auth().createSessionCookie(idToken, { expiresIn })`).
   Reduz janela de exposição mesmo sem kill switch (§4.7).

### 4.4. Bootstrap: super admins iniciais

| UID/Email | Origem | Papel |
|---|---|---|
| `rafaluisc@outlook.com` | já é owner do projeto GCP (ver memória `reference-gcp-accounts`) | primary — recovery, billing GCP |
| `izaeldecastro@gmail.com` | email operacional dia-a-dia | secondary — suporte ativo |

**Por que 2 e não 1:** backup mútuo de MFA (se um perder TOTP, o
outro destrava), kill switch recíproco (se um for comprometido, o
outro revoga), separação de papéis (primary = governance, secondary =
operações). Custo zero — são só 2 docs.

#### Procedimento de bootstrap (manual, executado 1x)

Como o Cloud Run B ainda não existe na hora do bootstrap, todo passo é
**manual via gcloud/Firebase Console**:

1. Criar contas Firebase Auth para os 2 emails (signup normal).
2. Habilitar MFA TOTP em cada conta (via Firebase Console ou
   `gcloud firebase auth ...`). Guardar codes de backup em
   gerenciador de senhas.
3. Criar docs em `super_admins/{uid}` via Firestore Console com
   `mfa_enrolled: true`, `is_active: true`, `scopes` completos.
4. Rodar `scripts/grant_super_admin.py <uid>` (a criar — Sprint 0)
   que:
   - Valida o doc existe e está `is_active && mfa_enrolled`.
   - Seta claim `super_admin: true` via Admin SDK.
   - Chama `revokeRefreshTokens(uid)` para forçar reissue do ID token.
5. Login no painel (quando existir) força reautenticação + MFA
   → ID token novo já carrega `super_admin: true`.

Documentar bootstrap em `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md`
(Sprint 0 cria essa runbook).

### 4.5. MFA: enrolled E usado-na-sessão

Distinção crítica:

- **`mfa_enrolled: true` no doc** = usuário tem MFA configurado no
  Firebase. Não diz nada sobre a sessão atual.
- **MFA usado na sessão** = o ID token atual foi obtido via fluxo que
  exigiu segundo fator.

**Implementação no backend Cloud Run B:**

```python
def require_super_admin(decoded_token: dict, request: Request):
    uid = decoded_token["uid"]
    if not decoded_token.get("super_admin"):
        raise HTTPException(403)
    # Source of truth check
    doc = firestore.collection("super_admins").document(uid).get()
    if not (doc.exists and doc.get("is_active") and doc.get("mfa_enrolled")):
        raise HTTPException(403)
    # Session MFA check — verifica que a sessão veio de MFA real
    amr = decoded_token.get("firebase", {}).get("sign_in_attributes", {}).get("amr", [])
    if "mfa" not in amr:
        raise HTTPException(401, "MFA exigido nesta sessão")
    return doc.to_dict()
```

`amr` (Authentication Method References) é populado pelo Firebase
quando o login envolve segundo fator.

### 4.6. Audit imutável — Firestore + BigQuery export

- **Tier 1 — Firestore (`audit_logs_system/{entry_id}`):** escrita em
  tempo real pelo Cloud Run B. Mutável tecnicamente (super admin com
  Admin SDK poderia adulterar via console), serve para queries de UI.
- **Tier 2 — BigQuery (dataset `audit_imutavel`):** export via Cloud
  Logging sink com retenção de 7 anos. Source of truth para
  investigação. Configurado via Terraform/gcloud na infra (não é
  código de aplicação).

**Setup BigQuery export (1x, post-Sprint 0):**

```
1. Criar dataset BQ "audit_imutavel" região southamerica-east1
2. Configurar log sink: logName=projects/.../logs/super_admin_audit
   → dataset BQ
3. No log_system_audit() do backend, emitir também via
   google-cloud-logging com structured log
4. Política de retenção BQ table: 7 anos (LGPD)
```

Audit Firestore continua existindo para query de UI rápida; BigQuery
é a versão imutável usada se houver suspeita de adulteração.

### 4.7. Sessão curta + domínio próprio

- **TTL 15min** via Firebase session cookies:
  `admin.auth().createSessionCookie(idToken, { expiresIn: 15 * 60 * 1000 })`.
- Cookie `HttpOnly`, `Secure`, `SameSite=Strict`,
  `domain=admin.castrointelligence.com.br`.
- **Renovação:** cookie expira → frontend força re-login + MFA. Sem
  auto-renew silencioso (decisão para reduzir surface — ver §10).
- **Domínio próprio** isola cookie scope: comprometer XSS no CRM
  (`crm.hubloc.com.br`) não vaza cookie do painel
  (`admin.castrointelligence.com.br`).
- **CSP estrito** no painel: sem inline scripts, sem inline styles,
  CSRF token em toda mutação.

### 4.8. Kill switch — sequência completa

Operação executada via Cloud Run B (ou script gcloud em emergência):

```python
def kill_super_admin(uid: str, actor_uid: str, reason: str):
    # 1. Audit ANTES (evita lacuna se algo falhar)
    log_system_audit(actor_uid, "kill_super_admin", target=uid, reason=reason)
    # 2. Marca doc inativo (não deleta — preserva auditoria histórica)
    firestore.collection("super_admins").document(uid).update({"is_active": False})
    # 3. Remove claim
    firebase_admin.auth.set_custom_user_claims(uid, {"super_admin": False})
    # 4. Revoga refresh tokens (sessão atual morre na próxima validação)
    firebase_admin.auth.revoke_refresh_tokens(uid)
    # 5. Notifica os outros super admins via email/Push
    notify_other_super_admins(uid, actor_uid, reason)
```

**Tempo máximo de exposição depois do kill:** TTL do ID token (até 1h
para tokens já emitidos; sessão Cloud Run B = 15min). Cookie de
sessão expira em ≤15min.

---

## 5. Impersonate Read-Only

### 5.1. Mecanismo

Operação executada via Cloud Run B em UI dedicada ("Ver como
operador X — apenas leitura"):

```python
@app.post("/api/admin/impersonate/start")
async def start_impersonate(
    body: ImpersonateRequest,
    super_admin: dict = Depends(require_super_admin),
):
    target_uid = body.target_uid
    target_tenant = body.target_tenant_id
    reason = body.reason  # OBRIGATÓRIO, não-vazio, mín 20 chars
    if not reason or len(reason.strip()) < 20:
        raise HTTPException(400, "Motivo obrigatório (mín 20 chars)")

    # Audit ANTES de emitir o token
    session_id = log_system_audit(
        actor_uid=super_admin["uid"],
        action="impersonate_start",
        target=target_uid,
        target_tenant_id=target_tenant,
        reason=reason,
    )

    # Custom token com claims escopadas
    additional_claims = {
        "impersonating": target_uid,
        "impersonator_uid": super_admin["uid"],
        "read_only": True,
        "impersonate_session_id": session_id,
        "exp_override": now() + 15*60,  # 15min absoluto
        "tenant_id": target_tenant,  # frontend vê dados do tenant alvo
        "role": "operador",  # rótulo — toggles vêm do perfil real do target
        "perfil_acesso_id": load_target_perfil(target_uid),
    }
    token = firebase_admin.auth.create_custom_token(
        super_admin["uid"], additional_claims
    )
    # Notificação ao operador impersonado (assíncrona)
    enqueue_notify_impersonated(target_uid, super_admin["uid"], reason)
    return {"custom_token": token, "session_id": session_id, "expires_in": 900}
```

Frontend troca a sessão atual pelo token retornado e renderiza painel
do operador alvo (com banner e botões desabilitados — §5.3).

**Fim da sessão:**

```python
@app.post("/api/admin/impersonate/end")
async def end_impersonate(
    body: ImpersonateEndRequest,
    super_admin: dict = Depends(require_super_admin),
):
    log_system_audit(
        actor_uid=super_admin["uid"],
        action="impersonate_end",
        target=body.target_uid,
        impersonate_session_id=body.session_id,
        duration_seconds=...,
    )
    firebase_admin.auth.revoke_refresh_tokens(super_admin["uid"])
    # Força super admin a fazer login normal de novo
```

### 5.2. Travas de escrita (Rules)

Toda rule de escrita ganha verificação que **rejeita** tokens com
`impersonating` ou `read_only`:

```javascript
function isReadOnlyImpersonate() {
  return request.auth != null
    && (request.auth.token.read_only == true
        || request.auth.token.impersonating != null);
}

match /tenants/{tenantId}/{document=**} {
  allow read: if request.auth != null
    && request.auth.token.tenant_id == tenantId;
  allow write: if request.auth != null
    && request.auth.token.tenant_id == tenantId
    && !isReadOnlyImpersonate();  // ← bloqueio
}
```

**Backend também valida** (defense-in-depth):

```python
def require_not_impersonate(user: dict = Depends(get_current_user)):
    if user.get("impersonating") or user.get("read_only"):
        raise HTTPException(403, "Operação bloqueada em modo impersonate read-only")
    return user

# em endpoints de escrita:
@app.post("/api/wa/send")
async def send(..., user: dict = Depends(require_not_impersonate)):
    ...
```

### 5.3. UX — Faixa de quarentena (Frontend)

Componente `<ImpersonateBanner />` montado no nível root da app
(acima do TopBar). Ativa quando claim `impersonating != null`:

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠ MODO DE DEBUG — VOCÊ ESTÁ VENDO COMO Maria do SAC          │
│   Apenas leitura. Ações bloqueadas. Sessão termina em 12:34. │
│   Motivo: "Investigar reclamação ticket #1234"               │
│                                              [Sair do modo]  │
└─────────────────────────────────────────────────────────────┘
```

Cor: amarelo/laranja sustentado durante toda a sessão. Botão "Sair do
modo" chama `/api/admin/impersonate/end`.

**Botões desabilitados ao detectar claim:**

- Composer de mensagem (placeholder "Leitura — não é possível enviar")
- Enviar template, enviar mídia, enviar nota interna
- Transferir, fechar/reabrir atendimento, assumir
- Editar contato (qualificar, declared_name, arquivar)
- Tudo que é mutação

`useCan(perm)` retorna `false` automaticamente para qualquer `perm`
quando claim `read_only == true` — primitivo único cuida disso, não
precisa esqualecer toggle a toggle.

### 5.4. Audit obrigatório com motivo

Cada sessão impersonate gera 2 entries em `audit_logs_system`:

```json
{
  "id": "audit_abc",
  "action": "impersonate_start",
  "actor_uid": "rafal_uid",
  "actor_email": "rafaluisc@outlook.com",
  "target_uid": "maria_uid",
  "target_email": "maria@hubloc.com.br",
  "target_tenant_id": "hubloc",
  "reason": "Investigar reclamação ticket #1234 — operadora não consegue enviar template",
  "ip": "189.x.x.x",
  "user_agent": "...",
  "started_at": "2026-06-02T14:30:00Z",
  "session_id": "imp_session_xyz",
  "expires_at": "2026-06-02T14:45:00Z"
}
```

```json
{
  "id": "audit_def",
  "action": "impersonate_end",
  "actor_uid": "rafal_uid",
  "target_uid": "maria_uid",
  "session_id": "imp_session_xyz",
  "started_at": "2026-06-02T14:30:00Z",
  "ended_at": "2026-06-02T14:42:13Z",
  "duration_seconds": 733,
  "end_reason": "manual" | "ttl_expired" | "kill_switch"
}
```

Replicados para BigQuery (§4.6) — investigação posterior usa BQ.

### 5.5. TTL e notificação ao operador

- **TTL: 15min absoluto.** Não há renovação dentro da mesma sessão.
  Se super admin precisa mais tempo, encerra e abre nova sessão (gera
  novo audit com motivo atualizado).
- **Notificação ao operador impersonado:** assíncrona, enviada após
  início:
  - Email: "Super admin X acessou sua conta em modo debug (apenas
    leitura) por Y minutos em ZZ/MM às HH:MM. Motivo: '...'."
  - Push no app (se existir notificação push): banner persistente até
    operador dismiss.
- Operador **não pode** bloquear a operação (super admin tem
  precedência), mas tem visibilidade total.

### 5.6. Termos de Uso — draft pt-BR

Bloco a incluir no ToS do CRM (revisar com jurídico antes de
publicar):

```
SUPORTE TÉCNICO E ACESSO PARA DEBUG

Para garantir a continuidade do serviço e resolver questões técnicas
reportadas pelo usuário ou identificadas pela equipe Castro
Intelligence, técnicos autorizados (Super Administradores) podem,
em casos justificados, visualizar a tela do CRM como se fossem o
usuário ("modo de debug"). Esse acesso é estritamente de leitura —
nenhuma ação (envio de mensagens, alteração de dados, transferências,
etc.) pode ser executada pelo Super Administrador em nome do usuário
durante o modo de debug.

Cada acesso de debug é:
- Justificado: o Super Administrador deve registrar o motivo do
  acesso (ex.: chamado de suporte, investigação de incidente).
- Auditado: data, hora, técnico responsável, duração e motivo ficam
  registrados em log imutável.
- Notificado: o usuário cuja tela foi acessada recebe notificação
  por email após o término da sessão, contendo as informações
  acima.
- Temporário: cada sessão dura no máximo 15 minutos.

O usuário pode solicitar a qualquer momento o histórico de acessos
em modo de debug à sua conta, exercendo seu direito de acesso
previsto na LGPD.
```

---

## 6. Sprint 0 — Fundação executável

Cinco entregas pequenas que destravam todo o resto, **sem tocar
nenhum endpoint operacional do CRM**. Tudo reversível via `git revert`
ou deleção de doc/coleção.

### 6.1 Entregáveis

| # | Entregável | Toca |
|---|---|---|
| 1 | Schema `super_admins/{uid}` documentado + seed manual dos 2 founders via Firestore Console | Firestore (doc novo, coleção root nova) |
| 2 | `scripts/grant_super_admin.py` — lê doc, valida, seta claim, revoga refresh tokens | novo arquivo Python |
| 3 | Helper `isSuperAdmin()` em `firestore.rules` (lê claim — fast-path). **Não remove** nenhuma rule existente, só adiciona capacidade futura | `firestore.rules` |
| 4 | Schema `audit_logs_system/{entry_id}` (root) + função `log_system_audit()` no backend (escreve em Firestore; BigQuery sink fica para depois) | novo módulo Python |
| 5 | Draft do Termo de Uso pt-BR (§5.6) + runbook bootstrap em `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` | docs novos |

### 6.2 O que NÃO entra no Sprint 0

- UI do painel super admin (depende de Cloud Run B existir)
- Endpoint `POST /api/admin/impersonate/start` (depende de B)
- Subdomínio `admin.castrointelligence.com.br` (config DNS + cert)
- BigQuery export de `audit_logs_system` (config GCP)
- MFA enforcement no Firebase Auth (config console — fazer junto com
  enrollment manual dos 2 founders, fora do código)
- Catálogo de toggles em código (entra na Onda 1 da migração RBAC,
  Sprint 1)
- `require_permission`/`useCan` (idem)

### 6.3 Critério de aceite Sprint 0

- 2 docs em `super_admins/` com `is_active && mfa_enrolled`.
- `scripts/grant_super_admin.py rafaluisc_uid` roda e o ID token de
  Rafael passa a carregar `super_admin: true` (verificar com
  `gcloud auth print-identity-token` + decode JWT).
- `firestore.rules` deploya sem regressão (testes existentes passam).
- `log_system_audit("test", ...)` chamado de um endpoint protegido
  grava em `audit_logs_system/`.
- Runbook bootstrap descreve passos para provisionar super admin #3
  no futuro.

---

## 7. Roadmap absorvido do PLANO_COEXISTENCE pós-Fase 2

Itens que estavam no roadmap pós-Fase 2 do PLANO_COEXISTENCE e
**migram para Cloud Run B**:

| Item original | Onde vive agora |
|---|---|
| Tenant onboarding UI (super-admin cria tenant) | Cloud Run B — §4.1 (criação de tenants) |
| Self-service signup do cliente | Cloud Run B (futuro — landing → cartão → tenant) |
| Cross-tenant analytics (`_meta/system_metrics`) | Cloud Run B — leitura cross-tenant via Admin SDK |
| Backup/export por tenant | Cloud Run B — endpoint dedicado, com audit |
| White-label (sub-domínio próprio do tenant) | Cloud Run B configura DNS/cert (futuro) |
| Cross-tenant analytics agregada | Cloud Run B |
| Limites enforced por plano | Cloud Run B (config de tenant) + Cloud Run A enforce |

Itens que **continuam no PLANO_COEXISTENCE** (não migram):

- Billing automation (Stripe/Asaas) — integração de cobrança da
  mensalidade SaaS, não é super admin
- Importação de histórico WhatsApp Business App — feature do CRM
  operacional, fica em A
- `docs/ONBOARDING_TENANT.md` (guia pro admin do tenant) — documento
  de produto, não código

---

## 8. Compliance LGPD — pontos específicos

Este plano introduz 3 novos tratamentos de dados pessoais que exigem
atenção LGPD além do que CLAUDE.md §2 já cobre:

1. **Impersonate read-only.** Super admin **lê** conversas WhatsApp e
   dados de cliente final em nome de operador. Mitigações: motivo
   obrigatório, audit em Firestore + BigQuery, notificação ao
   operador, sem capacidade de ação, sessão 15min. Cobertura no ToS
   (§5.6).
2. **Audit cross-tenant.** `audit_logs_system` registra ações em
   múltiplos tenants. Acesso restrito a super admins ativos. BigQuery
   sink com retenção 7 anos para investigação.
3. **Mudança de perfil RBAC.** Governance de acesso a dados pessoais
   (quem pode ver quê) é dado de auditoria crítica. `audit_log` do
   tenant registra todas as mudanças (§3.9).

**Itens não-negociáveis pré-produção:**

- RoPA/RIPD atualizado com os 3 tratamentos acima
- ToS atualizado e publicado antes do primeiro impersonate em prod
- Retenção BQ definida (7 anos para LGPD; permanente para audit é
  vedado por princípio de necessidade)
- Resposta a pedido LGPD do titular: como recuperar histórico de
  quem acessou os dados do operador X? Endpoint dedicado em Cloud
  Run B (futuro — §10)

---

## 9. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Claim out-of-sync com perfil (sessão antiga ainda autoriza após mudança) | `revokeRefreshTokens(uid)` no PUT do `perfil_acesso_id` do user; cache backend curto |
| Super admin comprometido (phishing) | Kill switch via outro super admin (§4.8); MFA obrigatório; sessão 15min |
| Bootstrap perde MFA dos 2 founders ao mesmo tempo | Códigos de backup em 2 gerenciadores de senhas separados; SA owner GCP pode usar `firebase_admin.auth.update_user` em emergência |
| Audit Firestore adulterado | BigQuery sink imutável (§4.6) — investigação séria usa BQ |
| RBAC seed quebra comportamento atual | Validar 1:1 com checks atuais antes de seedar; modo dual-check na migração (§3.8) |
| Impersonate vira atalho preguiçoso de suporte | Motivo obrigatório com 20+ chars + audit + notificação ao operador desincentiva uso casual |
| Frontend RBAC fica permissivo se `useCan` falhar (retorna `true` no fallback) | `useCan` default = `false`; só retorna `true` com toggle explicitamente lido do perfil |

---

## 10. Decisões em aberto

| # | Decisão | Notas |
|---|---|---|
| 1 | Catálogo de toggles é editável pelo admin do tenant ou fixo da plataforma? | Recomendação: fixo da plataforma (toggles são contrato com o código). Admin escolhe **quais perfis e quais valores**, não inventa toggle novo. Confirmar antes de Sprint 1. |
| 2 | BigQuery sink ativa no Sprint 0 ou quando Cloud Run B nascer? | Recomendação: quando B nascer. Sprint 0 só Firestore. |
| 3 | Cookie de sessão Cloud Run B auto-renova com motivo ou força re-MFA total a cada 15min? | Recomendação: re-MFA total (mais seguro; pouca fricção pra 2-3 humanos). |
| 4 | Endpoint LGPD "histórico de impersonate na minha conta" — Cloud Run A ou B? | Recomendação: A (operador acessa). B só **escreve**; A faz query do `audit_logs_system` filtrado pelo `target_uid == self`. |
| 5 | Painel UI de impersonate fica dentro do painel admin geral ou em rota separada `/impersonate`? | Decidir junto com escopo do painel B. |
| 6 | Renomear `castro-crm-staging` → `castro-crm-staging-a`? (preparação para `castro-superadmin-staging-b`) | Cosmético. Fazer junto com criação do B. |

---

## 11. Fora de escopo

- **Impersonate full** (super admin agindo como operador) — acordado:
  só read-only.
- **SSO/SAML** para super admin — Firebase MFA + TOTP suficiente
  agora; SSO entra quando equipe Castro Intelligence crescer.
- **Self-service signup de tenant** — fica no roadmap pós-Cloud Run B.
- **Billing UI / cobrança automática** — PLANO_COEXISTENCE §2.10
  cobre o que existe hoje (health check + erro 402). Cobrança Stripe
  fica fora.
- **Multi-region** — não mencionado nos planos atuais.
- **Customer-managed encryption keys (CMEK)** — não necessário no
  plano atual; Firestore encryption default + audit cobre LGPD.

---

## 12. Glossário rápido

| Termo | Significado |
|---|---|
| **claim** | Campo no JWT do Firebase Auth, lido por rules e backend sem precisar de read de DB |
| **Admin SDK** | SDK Firebase com permissão total que bypassa rules — usado pelo backend |
| **source of truth** | Documento Firestore que é a verdade absoluta — claim é cache, doc decide |
| **fast-path** | Caminho otimizado (claim) que evita reads em rules |
| **kill switch** | Mecanismo de revogação imediata de acesso (delete doc + clear claim + revoke tokens) |
| **Cloud Run A** | Serviço CRM operacional (`castro-crm`) — existe hoje |
| **Cloud Run B** | Serviço super admin (`castro-superadmin`) — a criar |
| **perfil seed** | Perfil RBAC default criado em todo tenant (`perfil_admin`, `perfil_supervisor`, `perfil_operador`) |
| **dual-check** | Durante migração, `require_permission` aceita toggle novo OU role antigo |
| **impersonate read-only** | Super admin vê tela do operador, não pode agir; banner amarelo + audit |
| **amr** | Authentication Method References no JWT — comprova MFA usado nesta sessão |
