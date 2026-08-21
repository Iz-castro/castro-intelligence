# Plano — Temperatura do lead (motor CX / castro-ia) — v2 pós-revisão do PO

> **Status em 2026-08-21: ENTREGUE E EM PRODUÇÃO.** Commit `b1d6348` (2026-07-21):
> `lead_temperature.py`, bolinha na sidebar/header e handoff enriquecido; commit
> `c58c4f9` (2026-07-22): segundo ponto de cálculo no assume do lead self-service
> (`apply_cx_snapshot_on_assume`, hoje também em takeover, supervisor-takeover e
> abertura pelo picker) — a regra "zero write por turno" segue intacta.
> **Correção posterior obrigatória:** o agente CX passou a devolver parâmetros em
> struct (`{chave: valor}`), o que sujava o resumo do operador e tornava o estado
> QUENTE inalcançável — unwrap dos params em `c2d4f0e` (2026-07-31). A regressão
> entrou sem aviso porque `settings.ai.environment_id` vazio faz a produção bater no
> **DRAFT** do agente; desde 2026-08-16 existem script + runbook para fixar o
> environment (`docs/deploy/TROCAR_ENVIRONMENT_VAL.md`, commit `80073b1`).
> ℹ Revisão registrada na memória do agente: `castro-crm-00092-vib` (2026-07-21). A numeração do Cloud Run
> fica fora de ordem pelo fluxo staging+promote (ver CLAUDE.md) — confira sempre por `creationTimestamp`.
> Segue **pendente** o que o próprio plano deixou fora do v1 (override manual do
> operador, temperatura no builtin, badge ao vivo durante o bot).

> Passo 0 da execução: salvar este plano em `docs/PLANO_LEAD_TEMPERATURE.md`
> e referenciá-lo no commit.

## Context

Tenants com o motor Dialogflow CX (plano ai_custom) qualificam leads pela Val,
mas o operador não vê a intenção ao assumir. Feature: classificar
**quente / morno / frio** a partir dos parâmetros de sessão do DetectIntent
(zero mudança no agente), exibir como **bolinha** (vermelha/amarela/branca) na
sidebar e no header, e **enriquecer a system message do handoff** com o que foi
coletado (interna ao CRM; cliente nunca vê).

**Decisões do PO (2026-07-21, revisão aplicada):**
- Regra: QUENTE = `wants_appointment` OU `insurance_validated`; MORNO =
  `wants_treatment` OU `user_specialty`/`user_symptom`; FRIO = resto.
  Override por tenant em `settings.ai.temperature_signals`.
- **EXECUÇÃO ADIADA (correção crítica do PO):** NENHUM write por turno.
  O cálculo roda UMA vez, no handoff (`_finalize_cx_handoff`), usando os
  params finais acumulados da sessão CX ("a IA já guarda o estado da
  sessão"). *(Atualização 2026-07-22, commit `c58c4f9`: existe um SEGUNDO
  ponto de cálculo — `apply_cx_snapshot_on_assume`, para o lead self-service
  que nunca pediu handoff; disparado no `/api/wa/assume` e, desde 2026-07-30,
  também em takeover, supervisor-takeover e abertura pelo picker. A regra
  "zero write por turno" segue intacta: o bot só persiste um snapshot mínimo
  em `bot_states` quando a informação coletada muda.)* Batch write: contato +
  conversas + protocolo. O operador só precisa da classificação consolidada
  quando o protocolo cai na fila
  humana — sem bolinha mudando ao vivo, sem listeners disparando à toa, sem
  race condition de writes concorrentes.
- Cada engajamento nasce limpo (1 dia = 1 protocolo): classificação sai só dos
  params DAQUELE engajamento; handoff novo SOBRESCREVE incondicional (sem
  ratchet — desnecessário com cálculo único). Histórico não suja a fila do dia.
- Registro **imutável no protocolo**: `attendances_daily/{pid}.lead_temperature`.
- Contexto histórico: sumários enriquecidos anteriores ficam no thread.
- Fix do visibility em **commit isolado** (exigência do PO: rollback da feature
  não pode levar a correção de segurança junto).

## Backend

**1. `lead_temperature.py` (NOVO, raiz)** — módulo puro (sem deps → sims intactos):
- `DEFAULT_TEMPERATURE_SIGNALS` = {quente_bool_any: [wants_appointment,
  insurance_validated], morno_bool_any: [wants_treatment], morno_nonempty_any:
  [user_specialty, user_symptom]} (sinais do Router da Val — não usar os
  "Provável—playbook").
- `classify_lead_temperature(params, signals=None) -> "quente"|"morno"|"frio"`
  com coerção bool/string "true" (precedente `_coerce_bool`) e override
  PARCIAL por chave.

**2. [bot_engine_dialogflow.py](../../../Rafael/castro-intelligence/bot_engine_dialogflow.py)**:
`_normalize_response` (L111-121) e `_FAILURE` (L124-131) ganham
`"parameters": {}` (dict bruto no sucesso; extraído na L113 e hoje descartado).
Docstring atualizada. Nunca logar conteúdo.

**3. [bot_service.py](../../../Rafael/castro-intelligence/bot_service.py)** — TUDO no handoff:
- `_cx_handoff_details(summary, user_name, cx_params, temperature) -> str`
  (pura, testável): 1ª linha IMUTÁVEL "Bot IA finalizado | Transferido para
  atendimento humano", depois só linhas preenchidas (minimização):
  `Temperatura do lead: QUENTE`, `Nome:`, `Sintoma:`, `Convênio: X (validado)`,
  `Especialidade:`, `Quer agendar: sim`, `Quer tratamento: sim`, `Resumo:`.
- `_finalizecx_handoff(contact_id, ai_cfg, summary="", user_name="",
  cx_params=None, contact=None)`:
  - `temperature = classify_lead_temperature(cx_params or {},
    ai_cfg.get("temperature_signals"))` — calculada AQUI, única vez.
  - Contato: `lead_temperature`+`lead_temperature_at` entram no MESMO
    `set(merge)` existente de bot_completed/department (L736-742) — zero
    write extra. Sobrescreve incondicional (per-atendimento).
  - Conversations: loop existente (L744-751) grava department+temperatura num
    único `set(merge)` por doc (pula `is_backup`).
  - Protocolo: `document("attendances_daily", contact.attendance_protocol)
    .set({"lead_temperature": t}, merge=True)` quando houver (+1 write).
  - System message: `save_wa_message(direction="system",
    content=_cx_handoff_details(...))` — visibility default "all" (operador
    vê; cliente nunca recebe).
  - Log: só a temperatura (sem PII).
- `_process_cx_message`: única mudança = passar `cx_params=
  result.get("parameters")` e `contact=contact` nos DOIS call sites de
  `_finalize_cx_handoff` (handoff normal L695-699 e por falha L667-670; na
  falha cx_params vazio → classifica FRIO + sumário "Bot IA indisponivel",
  sem detalhes — aceito pelo desenho). **NENHUM outro código por turno.**

**4. [scripts/set_tenant_ai.py](../../../Rafael/castro-intelligence/scripts/set_tenant_ai.py)**: arg opcional
`--temperature-signals '<json>'`; sem o arg, PRESERVAR o valor existente no
re-run (o script reescreve settings.ai inteiro).

## Frontend (inalterado da v1 — badge aparece quando o protocolo cai na fila)

**5. [types.ts](../../../Rafael/castro-intelligence/frontend/src/types.ts)**: `lead_temperature?:
"quente"|"morno"|"frio"|string` em `Contact` (~L143) e `Conversation` (~L213).

**6. [normalization.ts](../../../Rafael/castro-intelligence/frontend/src/utils/normalization.ts)** (whitelist dropa
campo novo): mapear em `normalizeContact` e `normalizeConversation`.
**Commit ISOLADO `fix:`** (exigência do PO): `normalizeMessage` mapear
`visibility: String(record.visibility || "all")` — filtro `admin_only`
(CrmContext.tsx:776) está inerte em snapshot mode.

**7. [App.tsx](../../../Rafael/castro-intelligence/frontend/src/App.tsx)**: `LeadTemperatureDot` (bolinha ~10px
inline, padrão `contact-operator-dot`): quente `#dc2626`, morno `#f59e0b`,
frio branco borda `#94a3b8`, `title` com legenda. Data-driven (sem campo →
null). Sidebar: `contact-meta` (L574-586), fonte
`conversation.lead_temperature || contact.lead_temperature`. Header: chip
dot+texto no `.chips` (L851-854). `firestore.rules`: nenhuma mudança.

## Testes ([tools/sim_cx_flow.py](../../../Rafael/castro-intelligence/tools/sim_cx_flow.py); 47 atuais seguem verdes)

- Durante o bot: turnos com params quentes NÃO geram write de temperatura
  (contato sem o campo até o handoff) — prova da execução adiada.
- Handoff quente (params acumulados, coerção "true" string) → contato/
  conversas/protocolo carimbados + system message com todas as linhas.
- Handoff frio (params vazios) → "frio" + minimização (sem Nome/Sintoma).
- Handoff por falha do motor → frio + "Bot IA indisponivel".
- Re-handoff (novo engajamento) sobrescreve temperatura anterior (quente→frio
  permitido — per-atendimento).
- Override `temperature_signals` parcial por tenant.
- Builtin hubloc: contato NUNCA ganha o campo.
- Regressão: `tools/sim_bot_flow.py` + `npm run build`.

## LGPD (registrar no commit — CLAUDE.md §2)

Finalidade: priorização de atendimento. Temperatura = derivado não-sensível;
sumário inclui `user_symptom` (SAÚDE): precedente do handoff_summary
existente, minimização, params crus nunca persistidos. Consentimento: gate
LGPD roda antes de todo turno CX. Cripto/audit/TTL: gate J-3 pré-go-live da
Varizemed real. Logs: só a temperatura.

## Deploy e verificação E2E

1. Local: sims + npm build. 2. Commits: `fix:` visibility (isolado) →
`feat:` temperatura (corpo com registro LGPD). 3. Staging (tag staging,
prefixo `castro_crm_staging`): webhook simulado → DetectIntent real → conferir
que DURANTE o bot não há campo; após handoff: contato/conversa/protocolo
carimbados + sumário na UI da tag. 4. Prod (revisão 0% → valida prefixo/
minScale/health → cutover). 5. E2E número real varizemed-test: conversa
completa ("dores...", "quero agendar, tenho Unimed") → SEM badge durante o
bot → handoff → badge VERMELHO na sidebar/header + sumário enriquecido no
thread + `attendances_daily` carimbado. 6. Regressão Hubloc: nada muda.
Rollback: revisão anterior (campos inertes nos dois sentidos; fix de
visibility sobrevive em commit próprio).

## Fora de escopo v1

Painel de contexto histórico dedicado; override manual pelo operador;
temperatura no bot builtin; badge ao vivo durante o bot (decisão explícita
do PO — execução adiada).
