---
name: project_lead_temperature
description: "Feature temperatura do lead (quente/morno/frio) dos tenants CX — execução ADIADA (só no handoff), em prod rev 00092; + topbar com tenant.name"
metadata: 
  node_type: memory
  type: project
  originSessionId: 535f93e8-1725-4ae6-827a-2268b798f3c3
  modified: 2026-07-23T18:39:01.547Z
---

EM PROD 2026-07-21 (rev castro-crm-00092-vib; commits 8c772f3 fix visibility
isolado, b1d6348 feat temperatura, c921ac8 topbar). Plano aprovado em
[docs/PLANO_LEAD_TEMPERATURE.md](docs/PLANO_LEAD_TEMPERATURE.md).

**Arquitetura (correção CRÍTICA do PO na revisão do plano):** EXECUÇÃO ADIADA —
NENHUM write por turno. `classify_lead_temperature`
([lead_temperature.py](lead_temperature.py), módulo puro) roda UMA vez em
`_finalize_cx_handoff` sobre os session params acumulados da sessão CX (o
conector `bot_engine_dialogflow` passou a expor `queryResult.parameters`).
Batch write: contato (mesmo set do bot_completed) + conversations (mesmo set
do department) + carimbo IMUTÁVEL em `attendances_daily/{pid}`. Handoff novo
SOBRESCREVE (semântica por-atendimento: lead que volta semanas depois nasce
frio, "não fura a fila"; protocolo antigo preserva o histórico). Handoff por
falha do motor → frio.

Regra default (sinais do Router da Val): quente = wants_appointment OU
insurance_validated; morno = wants_treatment OU user_specialty/user_symptom;
frio = resto. Override parcial por tenant em `settings.ai.temperature_signals`
(`set_tenant_ai.py --temperature-signals`, preserva no re-run). Gate real =
settings.ai.bot_engine==dialogflow_cx (plano é soft — script só avisa; gate
hard por plano ficou como backlog).

UI: `LeadTemperatureDot` (App.tsx) — bolinha vermelha/amarela/branca na
sidebar (contact-meta) + chip no header; DATA-DRIVEN (campo ausente = nada;
Hubloc/professional nunca exibem — zero plumbing de modules). Campo
`lead_temperature` mapeado em types.ts + normalization.ts (whitelist!).
Sumário enriquecido na system message do handoff (`_cx_handoff_details`,
1ª linha imutável, minimização LGPD — sintoma é dado de saúde, precedente do
handoff_summary; cripto/audit ficam no gate J-3 pré-Varizemed real).

Fix acoplado (commit ISOLADO por exigência do PO): normalizeMessage não
mapeava `visibility` → filtro admin_only era inerte em snapshot mode.

**LEAD SELF-SERVICE (rev 00096-ray, 2026-07-21):** teste real expôs gap — cliente
conversou com a Val, foi agendar ONLINE, NUNCA pediu handoff → sem resumo/badge,
lead quente invisível (admin teve que assumir na mão). Fix: `/api/wa/assume`
chama `apply_cx_snapshot_on_assume` (bot_service) → classifica + emite resumo
(header próprio "Resumo do bot IA | Atendimento assumido durante a conversa"),
grava contato/conversa/protocolo. Como os params do CX não persistiam, o
`_process_cx_message` guarda um `cx_snapshot` MÍNIMO (só chaves do sumário +
`signal_keys()` do tenant) em `bot_states` — doc efêmero SEM listener no frontend
e fora do caminho quente, só quando a info MUDA → regra do PO intacta (zero
write em wa_contacts/wa_conversations durante o bot, sem write por turno).
Idempotente (consome o snapshot), no-op sem IA/hubloc, não-fatal.
`_persist_lead_temperature` extraído e compartilhado com o handoff. NÃO é
retroativo (conversa tem que ser nova). sim_cx_flow 92/92. **VALIDADO EM PROD
pelo PO 2026-07-23: ambos os caminhos (handoff E assume) funcionam — badge +
resumo aparecem.**

**Topbar por tenant (c921ac8):** eyebrow do crm-topbar consome tenant.name do
/api/session via CrmContext.tenantName (hubloc → "Hubloc Imobiliaria",
varizemed-test → "Varizemed (Teste)"); zerado no resetUserScopedState. Telas
PRÉ-login seguem literais. Backlog: editor de nome no super-admin.

Testes: sim_cx_flow 72/72 (25 casos novos), sim_bot_flow 39/39, integração
real contra Firestore staging. GOTCHA de staging: Firebase Auth é compartilhado
prod/staging (mesmo projeto) mas os DADOS têm prefixo — conta com claim de
tenant só-de-prod (ex.: contato@ → varizemed-test) toma 403 no staging (gate
tenant-aware fail-closed, by design); usar admin hubloc pra ver staging.
