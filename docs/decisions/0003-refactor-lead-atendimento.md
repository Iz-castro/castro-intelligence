# ADR 0003 — Refactor Lead/Atendimento/Mensagem + regras coex hibrido (Fases 1-5A)

- **Data:** 2026-05-28
- **Status:** ✅ Implementado em prod (revisao `castro-crm-00124-298`)
- **Relacionado:** [PLANO_LEAD_ATENDIMENTO_E_REGRAS.md](../PLANO_LEAD_ATENDIMENTO_E_REGRAS.md), [ADR 0001](0001-prevenir-coex-signup-duplicado.md), [ADR 0002](0002-lgpd-canal-coex-compartilhado.md), dailies [2026-05-27](../internal/2026-05-27.md) + [2026-05-28](../internal/2026-05-28.md)

> **Status em 2026-08-21:** segue vigente, mas **emendado** por ADRs posteriores — leia
> junto com: [ADR 0008](0008-lead-gruda-na-vendedora.md) (dona de origem + revert no
> fechamento), [ADR 0009](0009-modelos-crm-d1-d3-retorno-ao-bot.md) e
> [ADR 0010](0010-pool-mode-recepcao.md) (Modo Recepcao: em tenant
> `pool_mode=reception` o fechamento do atendimento **devolve o lead ao agente de IA**
> em vez de so encerrar, e ha "Devolver a recepcao"). ⚠ As revisoes `castro-crm-001xx`
> da tabela no fim deste ADR sao do **projeto ANTIGO de Sao Paulo** — a prod migrou pro
> projeto de Oregon (`us-west1`) no cutover de 2026-06-10 e a numeracao do servico
> recomecou; nao procurar essas revisoes no ambiente atual.

## Contexto

Conforme o produto avancou para coexistence multi-operador, sintomas reais
em prod evidenciaram limitacoes do modelo `Contato/Atendimento/Mensagem`
original:

- Re-signup do mesmo numero coex criava canais duplicados (1/4/5 do
  `7195-7758`), com threads orfas no canal antigo → 503 "Nenhum canal
  configurado" no envio.
- Faixa de contexto exibia `Conversa no numero: —` em snapshot mode pq o
  frontend nao tinha join com canal.
- Transferencia de thread movia o **Lead** inteiro (espelho legado),
  apagando o conceito de "Dono do Atendimento" distinto do "Dono do Lead".
- Painel admin nao tinha visao de **conflitos** (Leads tocados por varios
  operadores no mesmo dia).
- Supervisao precisava de uma forma estruturada de **intervir**
  (orientar/responder/assumir) sem o ad-hoc "admin envia direto" cego.
- Atendimentos abertos indefinidamente — sem ciclo de vida nem fechamento
  automatico.
- Protocolo (`ATD-YYYYMMDDHHMMSS-id5`) era gerado no `assume`, por-contato,
  nao por-dia-por-Lead, e sem semaforo p/ retorno-zumbi.

## Decisao

Refactor faseado, em ondas que poderiam ser deployadas/validadas
isoladamente:

### Fase 1 — Re-login coex = rebind do canal existente
- Detectar canal por `phone_number_id` (decidido com base em evidencia:
  `phone_number_id` + `waba_id` sao **estaveis** entre re-signups do
  mesmo numero) e dar UPDATE no canal existente, em vez de criar
  duplicata.
- `phone_number_id` vira a chave primaria de dedup; `phone_routing` global
  segue inalterado entre re-signups.
- **Mantem o `channel_id` reaproveitado** — `conversation_id = {channel_id}__{wa_id}`
  segue valido, threads sobrevivem ao rebind sem migracao.

### Fase 2a — Apresentacao honesta por Atendimento
- Denormalizar `channel_phone_number`/`channel_label`/`channel_active`/`channel_type`
  no doc da conversation (preenchimento via `upsert_wa_conversation` +
  script `backfill_conversation_channel_denorm`).
- REST cai no denorm quando canal esta inativo (em vez de zerar campos).
- Composer fica **somente leitura** quando canal inativo, com mensagem
  clara, evitando 503 cru.
- **Fase 2b (abas por canal na ChatPanel) ADIADA** — sidebar ja lista
  cada canal como linha distinta. Reabre se navegacao por pessoa virar
  dor concreta.

### Fase 3 — Dono do Atendimento × Dono do Lead + Conflitos + Supervisor

**3A — Painel de Conflitos** (`GET /api/admin/conflicts`): lista Leads com
>=2 atendimentos ativos atribuidos a operadores distintos.

**3B — Desacople Dono Atendimento × Dono Lead:**
- `assign_wa_conversation` deixa de espelhar `assigned_to` no contato
  (param `also_lead=False` por default; espelho vira opt-in).
- Novo `POST /api/admin/reassign-lead` (admin/sup): muda **so** o Dono
  do Lead, sem mover threads.
- Frontend separa cards "Transferir atendimento" (todos) e "Reatribuir
  Lead (dono)" (admin).

**3 modos de intervencao do supervisor** (substitui o "bypass admin" cego
por modos com intencao + auditoria):
- **Modo 1 — Sussurro (nota interna):** `direction="internal"` em
  `wa_messages`, NAO vai pra Meta; orienta o operador, cliente nao ve.
- **Modo 2 — Co-pilotagem (assinada, automatica):** admin/sup envia ao
  lead **sem assumir**; backend faz prepend `[Supervisao - {1o nome}]:`
  no texto + `sender_user_id=supervisor` (thread owner intacto).
  `_check_conv_send_permission` retorna `"intervention"` p/ admin/sup
  nao-dono — operador comum segue estrito (standard) / via takeover (coex).
- **Modo 3 — Takeover do supervisor:** `POST /api/wa/conversation/{id}/supervisor-takeover`
  assume a thread (3B desacoplado: muda so o Dono do Atendimento) e
  avisa o lead com texto livre se <=24h (sem template aprovado fora da
  janela — assume silencioso).

### Fase 4 — Ciclo de vida do Atendimento
- Novo campo `attendance_status` em `wa_conversations`
  (`aberto`/`fechado_inatividade`/`fechado_manual`; ausente = aberto).
- Reabre em **qualquer mensagem** (inbound ou outbound).
- `close_stale_attendances(horas)` fecha apenas atendimentos **atribuidos**
  ociosos > `ATTENDANCE_AUTOCLOSE_HOURS` (default 24h; prod: **6h** via
  env, encaixa no fechamento operacional 17h da Hubloc).
- Plugado no cron `*/30` existente (`castro-crm-expire-takeovers`) —
  **sem job novo**.
- `POST /api/wa/conversation/{id}/set-attendance` (dono/admin/sup) p/
  fechar/reabrir manual; fechar manual zera takeover.

### Fase 5A — Protocolo 1 dia = 1 por Lead
- Nova colecao tenant-scoped
  `attendances_daily/{YYYYMMDD-{contact_id}-{SETOR}}` (TZ Brasil -3
  fixo; SETOR = 3 letras ASCII upper do dept, fallback `GERAL`).
- **Geracao silenciosa** no 1o inbound do dia (via `save_wa_message`
  → `ensure_daily_attendance` → denormaliza `protocol_id` na mensagem).
- **Envio ao cliente SO no fechamento** (manual + cron) como recibo:
  `"Seu protocolo de hoje e {id}. Agradecemos pela confianca em nossa empresa."`
  Texto livre se <=24h; fora, fecha sem enviar.
- **Semaforo `protocolo_informado`** bloqueia reenvio em retorno-zumbi
  no mesmo dia (idempotente entre threads do mesmo Lead).
- Busca admin `GET /api/admin/protocol/{id}` + card "Buscar protocolo"
  no detail-panel.
- `/api/wa/assume` **NAO** gera mais protocolo — alinhado a spec do PO
  (so o webhook na 1a inbound do dia).

## Alternativas consideradas

- **Wipe Firestore antes do refactor** (decisao #7 do plano): autorizado
  pelo PO, mas **nao executado** — as fases foram entregues evoluindo a
  base viva (backfills/scripts), o que se mostrou viavel. Wipe segue
  como higiene opcional antes do 1o cliente real pago.
- **Modelo de protocolo no contato** (Fase 5A, alternativa simples):
  campo `attendance_protocol` regenerado por dia. Rejeitado — perde
  historico, dificulta busca/auditoria por protocolo. Optou-se pela
  colecao dedicada (`attendances_daily`).
- **Tabs por canal na ChatPanel (Fase 2b)**: avaliadas em 2 sabores
  (light = aditivo no frontend; full = mexe nos filtros das views).
  **Adiada** — sidebar ja separa canais por linha distinta.
- **Operador read-only pos-takeover do supervisor (v2 do Modo 3):**
  adiado — thread sai da view do operador antigo como em transferencia
  comum. Reabre se necessario.

## Consequencias

### Positivas
- Re-onboarding coex deixa de criar duplicatas; threads sobrevivem.
- Operador / supervisor / admin tem afordancias claras pra cada cenario.
- Auditoria coex/supervisao usa o par `sender_user_id` ×
  `channel_owner_user_id` ja existente (Fase 2C anterior).
- Protocolo gera "carimbo do dia" automaticamente ao fechar — sem
  operador precisar lembrar.
- Cron unico (`*/30`) cobre takeover-expire + auto-close + envio de
  protocolo (mesmo job, sem infra nova).
- Fim do `Conversa no numero: —`, do 503 cru e do banner stale apos
  reatribuir Lead.

### Negativas / atencoes
- **Cron envia mensagens automaticas ao cliente** (protocolo) — superficie
  monitorar via `audit_log/ATTENDANCE_AUTO_CLOSE` + rate de protocolos.
  Salvaguarda: helper so envia se pid no formato novo
  (`YYYYMMDD-{contact_id}-SETOR`), evitando spam em threads pre-Fase-5A.
- `attendances_daily` cresce ~N_Leads × N_dias-com-inbound. Em escala BR
  ainda OK (Firestore aguenta); planejar TTL/expurgo se virar prioridade
  de retencao LGPD.
- Mudanca de comportamento: `/api/wa/assume` nao gera mais protocolo. Se
  algum fluxo dependia disso, vira no-op silencioso.
- TZ Brasil **hardcoded -3**: parametrizar por tenant quando o produto
  for alem do BR.

### Pendencias do plano
- **Fase 5B** tipificacao obrigatoria no fechamento + **5C** resumo IA
  Vertex em background (exige update RoPA/RIPD por LGPD).
- **Fase 2b** abas por atendimento, se a navegacao por pessoa virar dor.
- **Read-only do operador antigo** pos-takeover do supervisor (v2 do
  Modo 3).
- **Sticky routing TTL** (§3.4 do plano).
- **Decisoes do plano ainda abertas:** #3 agenda por-operador vs
  compartilhada, #4 TTL do sticky, #6 catalogo de tipificacao.

## Commits e revisoes

| Fase | Commit | Revisao prod |
|------|--------|--------------|
| 1 — rebind | `0a13d62` | `castro-crm-00116-slp` |
| 2a — apresentacao | `957cef2` | `castro-crm-00117-z4n` |
| 3A — conflitos | `5b121e2` | `castro-crm-00118-jtw` |
| 3B + Modo 1 | `0409857` | `castro-crm-00119-8g2` |
| fix takeover preso | `8c1ff70` | `castro-crm-00120-bmc` |
| Modos 2 + 3 | `9d609de` | `castro-crm-00121-zqx` |
| 4 + icone Sussurro | `ea2cbbc` | `castro-crm-00122-zkn` |
| env `ATTENDANCE_AUTOCLOSE_HOURS=6` | (mesmo build) | `castro-crm-00123-qb5` |
| 5A — protocolo | `15b4c7a` | `castro-crm-00124-298` |
