# Plano: modelos de CRM por vertical + gating real por plano

> **Status em 2026-08-21 — o que JÁ ESTÁ EM PRODUÇÃO (por outra porta, não por este plano):**
> - **`pool_mode` (Modo Recepção, [ADR 0010](decisions/0010-pool-mode-recepcao.md))** —
>   eixo ortogonal ao `crm_model`; `reception` ativo na varizemed real desde
>   2026-08-06 e no `varizemed-test`. Hubloc segue `legacy`.
> - **Item 6 — `release_lead_to_bot`**: fechamento (manual E cron) devolve o lead ao
>   agente de IA preservando `sale_owner`/setor/protocolo/temperatura/prova LGPD —
>   `database_firestore.py`, commit `095661d` (2026-08-05). **Gateado por
>   `is_reception_mode()`**, não por `crm_model`.
> - **Item 9 — hidratação da prova LGPD pelo CONTATO** em `_process_cx_message`
>   (com guard `lgpd_revoked`), mesmo canário de 2026-08-05.
> - **"Devolver à recepção"** (`return_contact_to_pool`) — devolve à pool SEM
>   encerrar; nasceu no ADR 0010, não estava neste plano.
> - **Horário comercial por tenant, FASE 1** (`business_hours.py`: params CX pra Val +
>   aviso do builtin), commit `5854c2c`, 2026-08-10 — **fase 2 (UI/feriados) pendente**.
>
> **O que deste plano continua NÃO implementado:** a Fase 1 inteira
> (`settings.crm_model`, `CRM_MODEL_OPTIONS`, `crm_model_from_doc`, `crm_model` no
> `/api/session`, `scripts/set_tenant_crm_model.py`) — `crm_model` só aparece hoje
> num comentário de `superadmin_main.py`; `FEATURE_CLINIC_RETURN_TO_BOT` /
> `_clinic_return_active`; item 10 (reroute de convertido gateado por modelo);
> itens 11-12 (parcialmente cobertos pelo gate de envio do reception, que já chama
> `mark_human_active`); item 14 (`scripts/rollback_clinic_return.py`); **Fase 3**
> (UI por modelo) e **Fase 4** (gating real por plano — nenhum runtime gateia por
> plano até hoje).
> ⚠ As âncoras de linha citadas adiante estão defasadas (o ADR 0010 reescreveu a
> região de `revert_lead_to_sale_owner`/`close_stale_attendances`) — confira no código.

**Status:** PROPOSTA de 2026-07-30, **parcialmente superada pela execução** — ver banner acima.
**Dono:** PO (Rafael) · **Execução:** CRM.

## O produto que o PO descreveu

> **Nota (ADR 0010, 2026-08-04):** existe um TERCEIRO eixo, ortogonal e JÁ
> IMPLEMENTADO: `system_settings/chat.pool_mode` (`legacy`|`reception`, Modo
> Recepção — pool compartilhada da varizemed). NÃO é valor de `crm_model` e
> não entra em `CRM_MODEL_OPTIONS`. Interações relevantes marcadas nos itens
> 6-8 e 11 abaixo.

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
  (⚠ Superado em 2026-08-05: com `pool_mode=reception` o fechamento chama
  `release_lead_to_bot` e o lead volta pro agente de IA — ADR 0010 / banner acima.)

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


---

<!-- ===================================================================== -->

> **Detalhamento consolidado em 2026-07-31** (workflow: 3 mapeadores do codigo real -> 2 designs independentes -> juiz). O esqueleto acima segue valendo como visao de produto; a secao abaixo e o plano de implementacao executavel das Fases 1+2 (+esboco da 3).

# PLANO FINAL CONSOLIDADO — Modelos de CRM por vertical (Fases 1+2 completas, Fase 3 esboço)

**Base:** branch `develop`, commit `c2d4f0e`. Âncoras de linha re-verificadas no HEAD em 2026-07-31 (call-sites do `revert_lead_to_sale_owner` em `database_firestore.py:1049/1078`, gate `human_active` em `bot_service.py:643`, ponto de hidratação LGPD entre `:643` e `:651`, `update_tenant` aceitando `settings` em `tenant_service.py:333`, reroute de convertido em `webhook.py:815-854`, `insert_transfer_system_message(..., advance_recency=)` em `db:1969-1971`, `crm_model` ainda inexistente no código).

## Veredito do juiz

**Espinha = Design B (MVP-first)** — menor diff, mesma mecânica central, mitigação de reabertura mais elegante (`mark_human_active` reusa o gate que os takeovers já usam) e o clear de takeover do cron sai de graça pelo dict de retorno do hook. **Enxertos do Design A (risco-first):**

1. `FEATURE_CLINIC_RETURN_TO_BOT` em `config.py` (convenção do repo: flags env-driven; 3º nível de rollback).
2. **`qualification` PRESERVADA no hook + reroute de convertido gateado por modelo** no `webhook.py` (em vez do reset `qualification="novo"` do B — não destruir dado; o reroute é semântica de locadora).
3. System message do hook ("Atendimento devolvido ao assistente virtual.", `advance_recency=False`) — observabilidade barata pra validação e pros operadores.
4. `scripts/rollback_clinic_return.py` one-off com dry-run (rollback de dados completo, não só de gate).
5. Pré-condição fail-closed no script da Fase 1 (com `--force` justificado) e casos de sim extras (sem sale_owner; builtin sem hidratação).

**Mantido do B (rejeitado do A):** mitigação de reabertura via `mark_human_active` (A re-atribuía contato + `bot_completed=True` — mais writes, mais estados; a dúvida de UX vira decisão PO D3); coex tratado por **pré-condição operacional** (guards de código do A viram follow-up obrigatório antes de clinic+coex coexistirem); clear de takeover no cron via retorno do hook (A mudava o caller); gate `_clinic_return_active()` **autocontido** (parse do tenant doc, sem import lazy de `bot_service` dentro de `database_firestore` — menos acoplamento).

**Desenho de segurança:** todo código novo é **dormante por construção** — só liga com `settings.crm_model=="medical_clinic"` E CX ativo E tenant `is_active` E flag env. Nenhum tenant terá o valor nos deploys → 2 deploys inertes; liga-se por DADO no canário (`Castro Intelligence SAC`), desliga-se por dado em ≤60s (TTL do cache de `get_tenant`, `tenant_service.py:137`).

---

## (a) Lista ordenada de mudanças por arquivo/função

### ETAPA 1 — Fase 1 (deploy inerte)

**1. `tenant_service.py`** — logo após `modules_for_plan` (~linha 100):
- `CRM_MODEL_OPTIONS = ("equipment_rental", "medical_clinic")`, `DEFAULT_CRM_MODEL = "equipment_rental"`.
- `normalize_crm_model(value) -> str`: espelho de `normalize_plan` (:91-95) — strip/lower; fora do vocabulário/None/sujo → default. **Default no READ, nunca backfill.**
- `crm_model_from_doc(tenant_doc) -> str`: guard de tipo nos 2 níveis (`settings` não-dict → `{}`, padrão `bot_service.py:518-522`) → `normalize_crm_model(settings.get("crm_model"))`. Fonte única do default, consumida por `/api/session` (F1), pelo gate de fechamento (F2) e pelo endpoint admin (F3). Doc sujo nunca quebra a sessão do tenant.
- `update_tenant` NÃO muda: `settings` já é permitido (:333) e o `set(merge=True)` (:359) faz merge profundo que preserva `settings.ai` (padrão de produção do `scripts/set_tenant_ai.py:133`).

**2. `main.py` — `session_info()` (:516-566):** import de `crm_model_from_doc` junto do existente (:543); no bloco `tenant` (:560-565) adicionar `"crm_model": crm_model_from_doc(tenant_doc)`. O try/except de `get_tenant` (:545-549) já garante default em falha. Campo aditivo — frontend atual descarta.

**3. `scripts/set_tenant_crm_model.py` (novo)** — molde de `set_tenant_ai.py`: argparse `--tenant`/`--model`, valida vocabulário, imprime before→after, confirma.
- Pré-condições fail-closed pra `medical_clinic`: (a) `settings.ai.enabled=True` + `engine=="dialogflow_cx"`; (b) `settings.ai.lgpd_policy_version` não-vazia E ≠ marcador `"{tid}-sem-versao"` (`bot_service.py:556-564` — prova fraca não sustenta clínica); (c) WARNING se o tenant tiver canal coexistence ativo. `--force` só com justificativa impressa.
- Escrita: `update_tenant(tid, settings={"crm_model": v})` — monta o dict ELE MESMO, nunca `settings` cru.
- Sob `set_tenant_context(tid)`: `log_audit(0, "CRM_MODEL_CHANGE", f"{old} -> {new} | via script")`.

**Gates E1:** `py_compile` (lista do CLAUDE.md) + `sim_bot_flow` + `sim_cx_flow` intactos + `npm run build`. Deploy A (rotina CLAUDE.md: `--source` absoluto, `--project` explícito, **promover por NOME** descoberto via `revisions list --sort-by "~metadata.creationTimestamp"`). Smoke: `GET /` 200, `GET /api/client-config` 200, `/api/session` de admin hubloc → `tenant.crm_model=="equipment_rental"` sem backfill.

### ETAPA 2 — Fase 2 (deploy inerte)

**4. `config.py`:** `FEATURE_CLINIC_RETURN_TO_BOT` (env bool, default `true`, lida no import). Freio de emergência global; o gate real é o dado do tenant.

**5. `database_firestore.py` — `_clinic_return_active() -> bool` (novo, perto de `revert_lead_to_sale_owner:1801`):**
```python
# Decide se o fechamento devolve o lead ao bot (modelo clinica).
if not FEATURE_CLINIC_RETURN_TO_BOT: return False
tid = get_tenant_context()
if not tid: return False              # flat/compat -> comportamento atual
t = get_tenant(tid) or {}             # import lazy de tenant_service (sem ciclo)
if not t.get("is_active", True): return False
if crm_model_from_doc(t) != "medical_clinic": return False
ai = (t.get("settings") or {}).get("ai") or {}   # guards de tipo nos 2 niveis
return isinstance(ai, dict) and ai.get("enabled") is True and str(ai.get("engine")) == "dialogflow_cx"
```
Qualquer exceção → `False` + warning (fechamento NUNCA falha por causa do gate). Custo: `get_tenant` cacheado 60s por instância — cron não infla reads.

**6. `database_firestore.py` — `release_lead_to_bot(contact_id, closed_conversation_id=None, close_status=None)` (novo, ao lado de `return_contact_to_bot:1829`):**
NÃO reusar `return_contact_to_bot` (clobberaria `qualification`/`attendance_protocol`/`department_id`). Ordem commit-point de `_persist_lead_temperature` (`bot_service.py:874-878`): periferia primeiro, contato POR ÚLTIMO.
- **Guards → `return None`** (caller cai no revert atual): contato inexistente; contato `is_backup`; conversa fechada `is_backup`.
- **Passo 1 — `bot_states/{contact_id}` merge** (idêntico a db:1863-1870, try/except warning): `{human_active: False, cx_snapshot: None, cx_summary_emitted: None, cx_summary_emitted_pid: None, cx_fail_count: 0}`. **Crítico:** sem zerar `human_active` (setado em `main.py:1263/2589/3610` e nunca limpo em fechamento), o CX fica mudo pra sempre (gate `bot_service.py:643`).
- **Passo 2 — threads não-backup do contato** (loop padrão db:1850-1858, pulando `is_backup`): `{assigned_to: None, assigned_to_uid: ""}`. Divergência proposital: **NÃO zerar `department_id`** (pool por setor continua; handoff novo re-carimba).
- **Passo 3 — system message** `insert_transfer_system_message(contact_id, "Atendimento devolvido ao assistente virtual.", None, conversation_id=closed_conversation_id, advance_recency=False)` — `advance_recency=False` obrigatório (memória recência inflada).
- **Passo 4 — CONTATO (commit point):** `{bot_completed: False, assigned_to: None, assigned_to_uid: ""}`. **Preservar por omissão:** `sale_owner_user_id`/`sale_owner_uid` (db:1786-1798), `lead_temperature`/`lead_temperature_at` (decisão item 12 — só handoff novo sobrescreve, `bot_service.py:1063-1065`), `lgpd_consent`/`lgpd_consent_at`/`lgpd_policy_version`, **`attendance_protocol`/`attendance_started_at`** (⚠ `_close_daily_and_send_protocol` roda DEPOIS nos 3 caminhos e lê o espelho — `main.py:3676-3682`, re-leitura :3764; limpar mata o recibo), `department_id`, **`qualification`** (enxerto do A — reroute gateado no item 10).
- **Retorno pro caller carimbar NA CONVERSA FECHADA:** `{"assigned_to": None, "assigned_to_uid": "", "takeover_status": "none", "takeover_started_at": None}`. Motivos: (a) thread fechada carimbada com dona nunca aparece na pool "novos" do frontend (exige `conv.assigned_to` vazio — racional db:1829-1833); (b) o clear de takeover conserta o gap do cron (db:1050-1053 não limpa) sem tocar caller; no manual é redundante-idempotente com `clear_takeover=True`.
- `attendances_daily`: **não tocar** (1 dia = 1 por lead segue com `ensure_daily_attendance` db:1588-1633).

**7. `database_firestore.py` — `set_attendance_status` (:1077-1080), trocar o bloco por:**
```python
if str(status).startswith("fechado"):
    _owner_fields = None
    if _clinic_return_active():
        _owner_fields = release_lead_to_bot(conv.get("contact_id"), conversation_id, status)
    if _owner_fields is None:
        _owner_fields = revert_lead_to_sale_owner(conv.get("contact_id"))
    if _owner_fields:
        updates.update(_owner_fields)
```
Cobre `fechado_manual` (main.py:3752) E `fechado_cliente` (webhook.py:339) sem tocar callers. Hubloc/`equipment_rental`: byte-idêntico ao atual.
> ⚠ **ADR 0010 (2026-08-04/05):** `revert_lead_to_sale_owner` ganhou guard no topo (`if is_reception_mode(): return None`) e `close_stale_attendances` ganhou o branch da pool — âncoras de linha deslocaram. **E o item 6 foi ANTECIPADO (PO 2026-08-05): `release_lead_to_bot` JÁ EXISTE em `database_firestore.py`** (mesmo desenho deste plano: passos 1-4, retorno pro caller, guard `lgpd_revoked` incluso), wired em `set_attendance_status` e `close_stale_attendances` com gate `is_reception_mode()`. **O item 9 (hidratação LGPD pelo CONTATO) TAMBÉM foi antecipado** (2026-08-05, desenho literal deste plano em `_process_cx_message`, com guard `lgpd_revoked` incluso — canário re-perguntava o aviso no retorno). A Fase 2 restante: trocar/compor o gate com `_clinic_return_active()` (crm_model + flag env), reroute gate (item 10), itens 11-12 (parcialmente cobertos: o gate de envio reception já chama `mark_human_active`) e rollback script (item 14). PRESERVAR os guards ao editar a região.

**8. `database_firestore.py` — `close_stale_attendances` (:1049-1053):** mesmo branch, com `_to_bot = _clinic_return_active()` calculado **UMA vez antes do loop** (tenant context já setado pelo cron, main.py:3363-3367).

**9. `bot_service.py` — hidratação LGPD em `_process_cx_message`, entre o gate `human_active` (:643-644) e `handle_lgpd` (:651):**
```python
# Retorno pos-fechamento (Fase 2): prova de consentimento no CONTATO vale
# se a policy_version bater com a vigente; recusa em bot_states tem precedencia.
if state.get("lgpd_consent") is None \
   and contact.get("lgpd_consent") is True \
   and str(contact.get("lgpd_policy_version") or "").strip() == _cx_policy_version(ai_cfg):
    state["lgpd_consent"] = True
    state["lgpd_status"] = "accepted"
```
- Custo zero de read (`contact` já carregado :632). `handle_lgpd` cai no pass-through (`lgpd_bot.py:194-196`) → turno vai DIRETO pro DetectIntent com a mensagem ATUAL (`first_cx_text` fica None → sem replay de `user_first_input` velho — por isso hidratar ANTES do handle_lgpd, nunca dentro do ramo accepted). O `_set_bot_state` de :675-678 persiste de graça.
- **Guarda `is None` inegociável:** recusa em `bot_states` (`lgpd_consent=False`, nunca vai pro contato) vence prova antiga. Versão divergente → re-pergunta com aviso vigente (fail-closed, D1). `lgpd_bot.py` NÃO muda; NÃO re-chamar `_record_lgpd_consent`.
- Efeito colateral benigno a anotar: `return_to_bot` manual do admin (main.py:3874/3926) também para de re-perguntar LGPD.

**10. `webhook.py` — reroute de convertido:** envolver SÓ o ramo de reroute (`webhook.py:838-854`, o "não é rating") com `if not _clinic_return_active():` (import via `database`). Ramo de rating (:821-836) fica — exige `rating_requested_at` pendente, que clínica não produz. Sem esse gate, `qualification=="convertido"` preservado reatribuiria o lead ao `original_operator_id` logo após o turno do bot.

**11. `main.py` — endpoint de reopen (:2200-2262):** após envio OK do template, `if _clinic_return_active(): mark_human_active(contact_id)` (`bot_service.py:904-916`). Motivo: o envio já reabre a conversa (outbound → upsert db:757-759) e em clinic o contato está sem dono e `bot_completed=False` → sem isso, a resposta em TEXTO do cliente cai no BOT e não no operador que chamou. O gate `:643` silencia o CX; qualquer fechamento posterior zera `human_active` via hook — o silêncio nunca fica preso.
> ⚠ **Buraco de UX descoberto + resolvido parcialmente (ADR 0010):** em clinic o contato pós-fechamento fica SEM dono → `_check_conv_send_permission` daria 403 no reopen (e na resposta) de operador comum. Com `pool_mode=reception` (caso varizemed) o gate libera órfã standard e o buraco some. Clinic com `pool_mode=legacy` AINDA tem o 403 — se algum tenant operar nessa combinação, tratar aqui na Fase 2.

**12. `webhook.py` — `_handle_reopen_button` ramo RETOMAR (:354-371):** mesma chamada gated (`mark_human_active`) — idempotente com o item 11, cobre template enviado por outra instância/antes do deploy. Ramo ENCERRAR: nada a fazer — passa por `set_attendance_status("fechado_cliente")` → hook zera `human_active` → bot disponível. Consistente.

**13. Simuladores** — seção (c).

**14. `scripts/rollback_clinic_return.py` (novo, entregue junto):** no tenant, query `wa_contacts` com `bot_completed==False` E `sale_owner_user_id` presente (lead novo genuíno não tem sale_owner → intocado) → re-carimbar `{bot_completed: True, assigned_to: sale_owner_user_id, assigned_to_uid: sale_owner_uid}`. **Dry-run por default**, log por contato.

**Gates E2:** `py_compile` + sims (velhos E novos) exit 0 + `npm run build`. Deploy B inerte. Regressão manual hubloc: fechar 1 atendimento de teste → lead volta pra vendedora.

### ETAPA 3 — canário e sign-off
`set_tenant_crm_model.py --tenant <castro-sac> --model medical_clinic` → checklist da seção (d) → 48h de observação → PO sign-off + ADRs (seção f) → Fase 3 (UI) → Varizemed real só após J-3 + migração.

Sem commit/push sem pedido explícito (convenção do repo).

### FASE 3 — ESBOÇO (UI por modelo + escolha do admin do tenant)

**Backend (`main.py`):** `GET/PUT /api/settings/tenant` com body/retorno `{crm_model}` (padrão do PUT /api/settings/system, main.py:1039-1045).
- Gate: **role `admin` estrita** (padrão main.py:677) — NÃO `ensure_permission("gerenciar_config_sistema")` (supervisor teria o toggle; PO pediu "só admin"). Front esconde a seção por `sessionUser.role` pra não gerar 403 visível (D6).
- Valida vocabulário; pré-condições `medical_clinic` iguais ao script (CX ativo + policy_version real + **erro** se canal coex ativo); **monta ele mesmo** `settings={"crm_model": v}` — NUNCA repassar `settings` cru do body (`update_tenant` não valida shape; repassar = admin de tenant sobrescreve `settings.ai` via REST — escalada de privilégio).
- `log_audit(uid, "CRM_MODEL_CHANGE", "old=x new=y")` (padrão diff legível de `_perfil_toggle_diff` main.py:915-921); retorna o valor salvo (evita flicker do cache 60s).
- Sem conflito com painel B: `UpdateTenantBody` exclui `settings` de propósito (superadmin_main.py:164-172); merge profundo em campos disjuntos.

**Frontend:**
- `CrmContext.tsx`: tipo do contexto (:34-35) ganha `crmModel`; state default `equipment_rental` ao lado de `tenantName` (:361); tipo inline da sessão (:1090) ganha `crm_model?`; `setCrmModel(session.tenant?.crm_model || "equipment_rental")` junto da :1102; **reset em `resetUserScopedState` (:1037-1070)** — PC compartilhado Rafael/Izael; export no value (:2421); derivar `isClinicModel`; action de save com refetch de `/api/session`.
- `App.tsx` — `AdminSettingsModal` (2236+): nova `settings-section` "Modelo de CRM" na tab Sistema (:2340-2382), visível só role admin, save próprio chamando o PUT + atualização do contexto + aviso "demais operadores verão após recarregar" (sessão só refaz no onIdTokenChanged ~1h; onSnapshot no tenant doc fica como follow-up — rules já permitem read, firestore.rules:214-216, mas o doc não está no mapa `firestore_collections` da sessão).
- Condicionais `isClinicModel`: rótulos Paciente/Lead (App.tsx:167/169/378/501/643/920/2140-2141); esconder chip/select/filtro de `qualification` (:625/:891/:1440-1451/:584) e aba "N/Q" (:177-179); temperatura em destaque (`LeadTemperatureDot` :460-480 maior + resumo do handoff CX no lugar do chip); revisar saudação de takeover (:771).
- ⚠ Fase 3 é só UI: `qualification` continua gravada no backend; revisar com o PO o que dashboard/N-Q significam na clínica antes de esconder.

---

## (b) Modelo de dados exato

| Coleção/doc | Campo | Valor/tipo | Default/compat |
|---|---|---|---|
| `tenants/{tid}.settings` | `crm_model` | `"equipment_rental"` \| `"medical_clinic"` | **Default aplicado no READ** (`crm_model_from_doc`); hubloc/varizemed/`create_tenant` (semeia `settings={}`, ts:320) NUNCA precisam de backfill. Escrito só por script (F1) e endpoint admin (F3), sempre via `update_tenant(tid, settings={"crm_model": v})` — merge profundo preserva `settings.ai`. |
| `/api/session` → `tenant` | `crm_model` | string normalizada | Aditivo; frontend atual descarta. |
| `config.py` | `FEATURE_CLINIC_RETURN_TO_BOT` | env bool | default `true` (inerte — gate real é o dado). |
| `wa_contacts` (fechamento clinic) | `bot_completed=False`, `assigned_to=None`, `assigned_to_uid=""` | — | **Preservados:** `sale_owner_user_id/uid`, `lead_temperature(_at)`, `lgpd_consent(_at)`, `lgpd_policy_version`, `attendance_protocol`, `attendance_started_at`, `department_id`, `qualification`. Nenhum campo novo. |
| `wa_conversations` (a fechada) | `assigned_to=None`, `assigned_to_uid=""`, `takeover_status="none"`, `takeover_started_at=None` | via retorno do hook | junto do `attendance_status` já gravado pelo caller. |
| `wa_conversations` (demais threads não-backup) | `assigned_to=None`, `assigned_to_uid=""` | — | `department_id` mantido (difere do `return_contact_to_bot`). |
| `bot_states/{contact_id}` | merge `{human_active:False, cx_snapshot:None, cx_summary_emitted:None, cx_summary_emitted_pid:None, cx_fail_count:0}` no fechamento; hidratação grava `lgpd_consent=True`+`lgpd_status="accepted"` via `_set_bot_state` existente | — | doc nunca deletado pelo hook; tenant-scoped, id = contact_id. |
| `audit_log` (tenant-scoped) | action nova `CRM_MODEL_CHANGE` (detail `old=x new=y \| via script/endpoint`) | best-effort | padrão `log_audit`. |
| `attendances_daily`, `wa_messages` | **sem mudança** | — | regra 1 dia = 1 por lead intacta; nenhum índice novo (todas as queries já existem). |

---

## (c) Casos de simulador novos

**`tools/sim_cx_flow.py`** (harness: estender o stub de `tenant_service.get_tenant` pra servir `settings.crm_model` além do `_AI_CFG`; exercitar `set_attendance_status`/`close_stale_attendances` REAIS sobre o STORE mockado):
1. **clinic_fecha_manual_volta_pro_bot** — seed pós-handoff (bot_completed=True, assigned, sale_owner=5, lead_temperature="quente", prova LGPD vigente no contato) → `set_attendance_status(conv,"fechado_manual",clear_takeover=True)` → asserts: contato `bot_completed=False`, sem dono, `sale_owner_user_id==5`/temperatura/protocolo/`lgpd_*`/`qualification` PRESERVADOS; conversa fechada `assigned_to=None`; `bot_states.human_active=False`; msg nova → 1 chamada CX com a mensagem atual (não `user_first_input`), SEM botões LGPD.
2. **clinic_fecha_inatividade** — `close_stale_attendances` → mesmos asserts + `takeover_status=="none"` na conversa fechada.
3. **clinic_fechado_cliente** — botão "encerrar" → hook aplica → msg seguinte cai no CX.
4. **policy_version_divergente_repergunta** — prova com versão antiga → retorno re-pergunta com aviso vigente; `len(CX_CALLS)` não cresce.
5. **recusa_vence_prova** — `bot_states.lgpd_consent=False` + prova True no contato → hidratação NÃO acontece, re-prompt de recusa, CX não chamado.
6. **human_active_zerado** — `mark_human_active` + fechamento → msg nova → CX responde (regressão do gate :643).
7. **handoff_novo_sobrescreve_temperatura** — retorno → novo ciclo → handoff "frio" → contato/daily novo = frio; daily antigo preserva quente.
8. **reopen_silencia_bot** — clinic pós-retorno → `mark_human_active` (simulando reopen/retomar) → texto do cliente NÃO gera resposta CX; fechamento seguinte re-arma.
9. **convertido_nao_rerouta_em_clinic** — contato `qualification="convertido"` pós-retorno → msg nova → CX responde e lead NÃO é reatribuído ao `original_operator_id` (gate do item 10); espelho rental: reroute continua funcionando.
10. **sem_sale_owner** — clinic fecha contato sem sale_owner → hook roda sem erro, contato limpo, pool ok.
11. **rental_regressao** — tenant sem `crm_model` → fechamento reverte pro sale_owner, `bot_completed` continua True, CX não chamado (proteção Hubloc).

**`tools/sim_bot_flow.py`** (builtin/Hubloc):
12. **cenario_fechamento_rental** — fluxo feliz → `_finalize_bot` → fechamento manual → `assigned_to==sale_owner`, `bot_completed=True` (bot mudo no gate do webhook).
13. **cenario_builtin_sem_hidratacao** — contato com prova LGPD no doc, `bot_states` vazio → builtin AINDA mostra o aviso (hidratação é só CX) — trava contra escopo-creep.

---

## (d) Roteiro de validação — tenant "Castro Intelligence SAC" (prod) e rollout Varizemed

**Pré:** Deploy B promovido por NOME (descoberto via `revisions list --sort-by "~metadata.creationTimestamp"`) e conferido com `describe status.traffic`; `settings.ai.lgpd_policy_version` REAL configurada no tenant de teste.

1. **Ligar:** `set_tenant_crm_model.py` → `GET /api/session` (admin do tenant) mostra `medical_clinic`; audit `CRM_MODEL_CHANGE` gravado.
2. **T1 ciclo completo:** número novo → LGPD → aceite → Val (CX) qualifica → handoff (pool Comercial + temperatura + `bot_completed=True`) → operador assume (vira sale_owner) → **fechar manual** → conferir no console Firestore: contato `bot_completed=False`, sem dono, `sale_owner_*`/`lead_temperature`/`attendance_protocol` intactos; conversa fechada `assigned_to` vazio; `bot_states.human_active=False`; system message "devolvido ao assistente" presente SEM subir a thread; recibo de protocolo chegou no WhatsApp.
3. **T2 retorno:** "qual o endereço mesmo?" → Val responde SEM re-perguntar LGPD; atendimento reaberto; lead na pool "Novos".
4. **T3 novo handoff:** temperatura sobrescrita (item 12).
5. **T4 takeover/picker:** abrir via picker (`human_active=True`) → fechar → msg nova → Val responde.
6. **T5 inatividade:** retro-datar `last_message_at` (só no tenant de teste; NÃO mexer em `ATTENDANCE_AUTOCLOSE_HOURS`) → `POST /api/internal/cron/expire-takeovers` (OIDC) → mesmos efeitos de T1 + `takeover_status="none"` + recência NÃO inflada.
7. **T6 reabertura:** enviar template → resposta em TEXTO cai no operador (bot mudo por `human_active`) → "Retomar" mantém humano → "Encerrar" fecha e a msg seguinte volta pra Val.
8. **T7 policy version:** trocar `settings.ai.lgpd_policy_version` do tenant de teste → retorno re-pergunta (fail-closed) → aceite grava prova nova + audit `LGPD_CONSENT_ACCEPTED`; restaurar.
9. **T8 regressão Hubloc (mesmo deploy):** fechar 1 atendimento real → lead volta pra vendedora; recorrente cai direto com ela.
10. **Monitorar 48h:** `pending_webhook_events` (~0, tripwire), logs `[BOT-CX]` e `no_channel`, warnings de `_record_lgpd_consent`, contagem de reads (cron não pode inflar).

**Critério:** 100% dos itens + 48h sem anomalia → evidências ao PO.

**Rollout Varizemed (após sign-off + Fase 3 + gate J-3 + migração/import):** (1) confirmar `settings.ai` da varizemed (CX ativo, `lgpd_policy_version` real, sem coex); (2) ligar `medical_clinic` (script ou endpoint F3) fora de horário de pico; (3) repetir T2/T5/T6 com paciente de teste; (4) avisar a clínica do churn one-time: pacientes importados sem prova re-perguntam LGPD 1x (D7); (5) monitorar 48h; rollback = seção abaixo.

**Rollback (3 níveis):**
- **Dado (imediato, sem deploy):** `set_tenant_crm_model.py <tid> --model equipment_rental` → desarma em ≤60s. Remediação: `scripts/rollback_clinic_return.py` (dry-run default) re-carimba os contatos já devolvidos ao bot.
- **Código:** repromover revisão anterior por NOME (`update-traffic --to-revisions <REV>=100`, nunca `--to-latest`).
- **Env:** `FEATURE_CLINIC_RETURN_TO_BOT=false` (gera revisão nova; congela o comportamento em todos os tenants mantendo o código).
- Hidratação LGPD: sem rollback de dados (não grava prova nova) — revert de código basta.

---

## (e) Riscos aceitos e mitigados

**Mitigados (no código deste plano):**
| Risco | Mitigação |
|---|---|
| `human_active` órfão pós-takeover → CX mudo pra sempre | hook zera sempre (passo 1) |
| Thread fechada carimbada com dona → lead nunca aparece na pool | retorno do hook grava `assigned_to=None` na conversa fechada |
| Protocolo do dia não sai | hook preserva `attendance_protocol/started_at`; `_close_daily_and_send_protocol` intacto |
| Template de reabertura × bot | `mark_human_active` no envio e no "retomar" |
| Reroute de convertido rouba o lead da IA | gate por modelo no webhook (:838-854) |
| Takeover ativo + fechamento por cron | clear de takeover no dict de retorno do hook |
| Recência inflada por system message | `advance_recency=False` |
| Recusa LGPD atropelada por prova antiga | guarda `is None` na hidratação |
| Versão de política mudou | igualdade estrita → re-pergunta fail-closed |
| Replay de `user_first_input` velho | hidratação ANTES do `handle_lgpd`, nunca no ramo accepted |
| Reads do cron | boolean 1x/função + cache 60s do `get_tenant` |
| Corrida cron × inbound | ordem commit-point (contato por último) → degrada pra "1ª msg sem resposta, autocorrige" |
| Backup volta pro bot | guards `is_backup` (contato e conversa) → fallback no revert |
| Escalada via `settings` cru no endpoint F3 | endpoint monta `settings={"crm_model": v}` ele mesmo |
| Doc de tenant sujo quebra `/api/session` | guards de tipo + default no read |
| Deploy acidentalmente ativo | dormante por dado; 2 deploys inertes; canário antes da Varizemed |

**Aceitos (documentados, sem código agora):**
1. **Coex re-captura / bot em número pessoal:** mitigado por PRÉ-CONDIÇÃO operacional (`medical_clinic` só em tenant sem canal coexistence — warning no script, erro no endpoint F3). Guards de código (auto_assign=None + bot não roda em coex quando clinic) são **follow-up obrigatório** antes de qualquer tenant clinic ganhar coex. Exposição hoje: zero (Varizemed = standard único).
2. **Corrida fechamento × mensagem em voo:** 1ª mensagem do retorno pode ficar sem resposta do bot (contact_row lido antes do commit, webhook.py:708); autocorrige na seguinte.
3. **`_record_lgpd_consent` é best-effort:** prova pode não existir no contato mesmo com aceite → re-pergunta é o fallback permanente e não pode ser removida.
4. **Cron não limpa takeover no rental:** inconsistência pré-existente mantida (mudança mínima) — follow-up.
5. **Propagação do `crm_model` a operadores logados:** até reload/refresh de token (~1h); aviso na UI; onSnapshot no tenant doc é follow-up.
6. **Skip da re-pergunta aumenta dependência da prova gravada** (sem cripto de campo/TTL/audit de leitura): tenant de TESTE liberado; go-live Varizemed real segue gateado pelo J-3.

**Follow-ups fora de escopo:** guards coex de código; hidratação LGPD no builtin; onSnapshot no tenant doc (incluir no `firestore_collections` da sessão); takeover-clear no cron pro rental; gating real por plano (Fase 4); significado de dashboard/N-Q/convertido no vertical clínica.

---

## (f) DECISÕES PENDENTES DO PO (registrar como ADR em `docs/decisions/`)

> **D1-D3 DECIDIDAS em 2026-08-01 — ver `docs/decisions/0009-modelos-crm-d1-d3-retorno-ao-bot.md`.**
> D1=SIM (bump manual de `lgpd_policy_version` dispara re-aceite); D2=SIM
> (+ requisito novo: "Encerrar" do cliente vira opt-out de template de
> retomada — campanhas devem filtrar); D3=pontual mantém comportamento
> atual (pool "Meus" do operador), em massa exige confirmação do
> departamento-destino no disparo. D4-D8 seguem pendentes.

1. **D1 — policy_version mudou → re-perguntar LGPD (fail-closed)?** Recomendação: SIM (dado de saúde, art. 11; política nova = novo aceite com prova nova). Corolários da mesma decisão: prova builtin `"hubloc-2026-06"` em tenant CX re-pergunta; contatos com marcador `"{tid}-sem-versao"` re-perguntam 1x quando a versão real for configurada; exigir policy_version real ANTES de ligar `medical_clinic` (já embutido em script/endpoint).
2. **D2 — `fechado_cliente` (botão Encerrar) também devolve ao bot?** Recomendação: SIM (uniforme com "QUALQUER fechamento"; o botão curto-circuita o bot no clique — sem ping-pong imediato). Alternativa: `client_requested_close` veta.
3. **D3 — reabertura humana:** com `mark_human_active`, a resposta do cliente ao template cai na POOL (sem dono, bot mudo). Alternativa (Design A): re-atribuir ao sale_owner/remetente pra cair no "Meus" dele. Recomendação: pool + `human_active` (menor diff); confirmar UX.
4. **D4 — `qualification` preservada + reroute de convertido gateado por modelo** (recomendado) vs resetar pra "novo" no hook (perde o carimbo). Ligado: o que "convertido"/dashboard significam na clínica (Fase 3).
5. **D5 — pré-condição coex:** `medical_clinic` só em tenant sem canal coexistence. Confirmar como default (Varizemed não é afetada).
6. **D6 — gate do seletor (Fase 3):** role `admin` estrita (recomendado; supervisor com `gerenciar_config_sistema` NÃO vê/troca) vs permissão RBAC.
7. **D7 — import Varizemed:** pacientes migrados sem prova re-perguntam LGPD 1x (recomendado). Carimbar "prova legada" só com decisão jurídica explícita.
8. **D8 — revogação de consentimento:** não existe campo/fluxo pro titular que revoga via atendente — gap permanece no J-3; go-live Varizemed real segue gateado por ele.
