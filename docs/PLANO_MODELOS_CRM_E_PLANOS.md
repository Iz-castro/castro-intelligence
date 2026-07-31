# Plano: modelos de CRM por vertical + gating real por plano

**Status:** PROPOSTA (PO descreveu o produto em 2026-07-30; nada implementado).
**Dono:** PO (Rafael) · **Execução:** CRM.

## O produto que o PO descreveu

Dois eixos INDEPENDENTES por tenant:

1. **Modelo de CRM (vertical de UI)** — define COMO a interface se comporta.
   Escolhido pelo **admin do tenant, na UI do CRM** (não pelo super-admin):
   - `equipment_rental` (locadora de equipamentos — comportamento atual da Hubloc):
     lead recorrente fala DIRETO com o vendedor que o atendeu (`sale_owner`);
     fechamento devolve lead+thread pra dona de origem.
   - `medical_clinic` (clínica médica — comportamento desejado pra Varizemed):
     cliente recorrente que manda mensagem DEPOIS do fechamento (manual ou por
     inatividade) **volta pro agente de IA** (ex.: "qual o endereço mesmo?" no
     dia da consulta → a Val responde sozinha). A temperatura NÃO é limpa no
     fechamento; só um NOVO handoff a sobrescreve (decisão PO 2026-07-30,
     resposta ao item 12 da auditoria).

2. **Plano comercial** — define O QUE o tenant pode usar. Registrado por NÓS
   (super-admin) conforme o que o cliente comprou:
   - `professional`: bot builtin (LGPD → direto pro Comercial). Futuro: bot
     configurável na UI pelo admin do tenant.
   - `ai_custom`: + agente de IA customizado qualificando leads (CX).
   - `enterprise_ai`: ai_custom + especificações sob medida. **AINDA NÃO
     IMPLEMENTADO** — decisão PO 2026-07-30: tirar da UI de criação de tenant
     até existir (o valor continua aceito no backend p/ compat).

## Estado atual (verificado 2026-07-29/30)

- `plan` é rótulo: NENHUM runtime gateia por plano. IA liga por `settings.ai` +
  `system_settings.bot_enabled`. Frontend descarta `tenant.plan/modules` do
  `/api/session` (só usa `tenant.name`).
- Vertical de UI NÃO existe como conceito. As diferenças Hubloc×Varizemed são
  data-driven (bolinha aparece se o campo existir).
- **Retorno-ao-bot pós-fechamento NÃO existe**: `set_attendance_status`/
  `close_stale_attendances` mantêm `bot_completed=True` e revertem o dono pro
  `sale_owner`; o gate do bot no webhook exige contato sem dono E sem
  `bot_completed`. Ou seja, hoje NENHUM tenant tem o comportamento "clínica".

## Execução proposta (fases pequenas, cada uma deployável)

### Fase 1 — persistir os dois eixos
- Tenant doc ganha `settings.crm_model` (`equipment_rental` | `medical_clinic`;
  default `equipment_rental` = zero mudança pros tenants atuais).
- `/api/session` já expõe `plan`+`modules`; passa a expor `crm_model`.
- Editor de tenant no painel B (JÁ IMPLEMENTADO no branch, item 9 da rodada
  2026-07-30) cobre `plan`/`name`/`is_active`/domínios. `crm_model` fica FORA
  do painel B — é escolha do admin do TENANT (Fase 3).

### Fase 2 — comportamento "clínica": retorno ao bot pós-fechamento
O coração do modelo `medical_clinic`. **Decisão PO 2026-07-31: vale para TODO
fechamento** (manual E por inatividade). SE o tenant é `medical_clinic` E tem
motor CX ativo:
- limpar `bot_completed` (contato) e devolver threads sem dono (como o
  `return_contact_to_bot` faz), MAS **preservando** `sale_owner`/histórico e
  **sem** limpar `lead_temperature` (decisão do item 12);
- **pular a re-pergunta da LGPD**: `handle_lgpd` hoje lê o `bot_states` (que é
  limpo no handoff) — precisa aceitar prova de consentimento já gravada no
  CONTATO (`lgpd_consent=True` + policy_version igual à vigente) e ir direto
  pro CX. Sem isso, o cliente recorrente tomaria o aviso LGPD de novo a cada
  retorno;
- o protocolo do dia continua com a regra atual (1 dia = 1 por lead).
Gate de qualidade: casos novos no `sim_cx_flow` (fechar → mensagem nova →
bot responde; handoff novo sobrescreve temperatura antiga).

### Fase 3 — UI por modelo + escolha pelo admin do tenant
- Config do CRM (aba admin): seletor "Modelo de CRM" (só `admin` do tenant;
  auditado). Grava `settings.crm_model` via endpoint novo no CRM A.
- Frontend consome `session.tenant.crm_model` no `CrmContext` e deriva flags
  de UI (ex.: `medical_clinic` mostra bolinha/resumo com destaque; rótulos
  "Paciente" vs "Lead"; esconder o que não faz sentido no vertical).

### Fase 4 — gating REAL por plano
- Backend: motor CX exige `ai_agent` em `modules_for_plan(plan)` (além do
  `settings.ai` atual) — um `professional` com `settings.ai` sobrando deixa de
  rodar IA por acidente.
- Frontend: `CrmContext` passa a guardar `plan`/`modules` e esconde features
  de IA quando o módulo não existe.
- `scripts/set_tenant_ai.py`: o aviso de plano vira ERRO (hoje grava mesmo assim).

### Follow-up herdado da revisão de 2026-07-30
**`is_active` do tenant é um kill switch PARCIAL.** Hoje ele: (a) silencia o bot
do tenant (implementado em `bot_service._tenant_is_active`), (b) tira o tenant do
roteamento de login por domínio e da rede de transição. **NÃO** desconecta quem já
tem o claim `tenant_id` — `auth.py` autoriza por claim e as `firestore.rules`
também. O editor do painel B já diz isso na UI. Fechar o buraco de verdade exige
um gate no `auth.py` (negar login se o tenant estiver inativo) — mudança com
blast radius alto (um bug ali tranca todo mundo fora), então ficou como item
próprio, a ser feito com canário e rollback pronto.

### Fora de escopo por ora
- `enterprise_ai` como produto (spec sob medida) — o PO mencionou um doc antigo
  sobre isso que não foi localizado; procurar/reescrever quando a fase chegar.
- Bot builtin configurável na UI (citado como futuro do `professional`).

## Riscos/lembretes
- Fase 2 mexe no ciclo de vida de atendimento — validar com os fluxos de
  reabertura (template de reabertura/botões) pra não criar corrida bot×botão.
- `varizemed-test` (renomeado "Castro Intelligence SAC") usa o MESMO agente CX
  do tenant real; quando a Fase 2 entrar, testar lá primeiro.
- LGPD: retorno ao bot reabre coleta de dado de saúde — a prova de consentimento
  por CONTATO (não por sessão) vira peça central; alinhar com o gate J-3.
