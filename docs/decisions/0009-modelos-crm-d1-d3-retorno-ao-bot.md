# ADR 0009 — Modelos de CRM: decisões D1-D3 do retorno-ao-bot (clínica)

> **Status em 2026-08-21:** o retorno-ao-bot **está em produção**, mas ligado pelo
> `pool_mode=reception` ([ADR 0010](0010-pool-mode-recepcao.md) — Fase 2 do
> PLANO_MODELOS antecipada em 2026-08-05, commits `095661d`/`ee1e4cc`), **não** pelo
> `crm_model`: esse eixo ainda NÃO existe no código (só aparece como "futuro" num
> comentário de `superadmin_main.py`).
> **D1 — FEITA:** a hidratação da prova pelo CONTATO compara
> `contact.lgpd_policy_version` com a vigente (`_cx_policy_version`) e re-pergunta
> quando diverge; recusa no `bot_states` tem precedência e `lgpd_revoked` nunca
> hidrata (`bot_service._process_cx_message`).
> **D2 — PARCIAL:** o botão "Encerrar" fecha o atendimento e grava
> `reopen_response`/`client_requested_close` **na conversation** (`webhook.py`),
> mas nenhum disparo consome esse opt-out — o envio em lote
> (`scripts/send_template_bulk.py`) não filtra hoje. Requisito do motor de
> campanhas segue ABERTO.
> **D3 — atenção:** desde a emenda de 2026-08-19 do ADR 0010 (commit `3aa9d05`),
> abrir pelo picker só auto-atribui a thread se o LEAD já for do operador — a
> retomada pontual só cai no "Meus" de quem já é dono.

- **Status:** aceito (PO, 2026-08-01)
- **Contexto:** `docs/PLANO_MODELOS_CRM_E_PLANOS.md` (Fases 1+2 — modelo
  `medical_clinic` devolve o lead ao agente de IA após QUALQUER fechamento,
  decisão de 2026-07-31). Três decisões estavam pendentes do PO.

## D1 — Política de privacidade mudou ⇒ re-perguntar o aceite: SIM

Quando a versão vigente da política do tenant for diferente da versão
carimbada na prova de consentimento do contato, o gate LGPD re-pergunta.
Corolários aceitos: prova antiga do builtin (`hubloc-2026-06`) em tenant CX
re-pergunta; contatos com marcador `{tid}-sem-versao` re-perguntam 1x quando
a versão real for configurada.

**Mecânica (não é detecção automática):** a "mudança" é um ato operacional —
quem atualiza o texto da política TEM que atualizar junto o campo
`settings.ai.lgpd_policy_version` do tenant (ex.: `varizemed-2026-07` →
`varizemed-2027-01`). O sistema compara `contact.lgpd_policy_version` com a
vigente; divergiu ⇒ re-pergunta e re-carimba. Regra operacional a documentar
pro cliente: texto novo sem bump de versão = ninguém re-aceita; bump sem
texto novo = todo mundo re-aceita à toa.

## D2 — Fechamento pelo cliente (botão "Encerrar") também devolve ao bot: SIM

Uniforme com "vale para todo fechamento". O clique curto-circuita o bot no
próprio turno, então não há ping-pong.

**Detalhe NOVO do PO (vira requisito do motor de campanhas, ADR 0005):** a
Varizemed fará campanhas de retomada por template. Cliente que responder
**Encerrar** entra em opt-out de reabertura: NENHUM template de retomada
pode mais ser enviado a ele (campanha em massa DEVE filtrar; envio manual
deve avisar/bloquear). Implementação prevista: flag no contato (ex.:
`reopen_opt_out=True` carimbado quando `reopen_response=="encerrar"`),
consumida pelo disparo em lote e pela UI de template. Opt-out de retomada ≠
revogação LGPD (D8/J-3) — são registros distintos.

## D3 — Reabertura: pontual vs em massa

- **Pontual (operador manda o template manualmente):** comportamento atual
  mantido — a conversa retomada volta pra pool "Meus" do operador, com
  recência e badge.
- **Em massa (recurso futuro de reabertura em lote):** ANTES de disparar, o
  sistema informa ao admin/operador autorizado **em qual departamento** as
  retomadas vão cair (Geral — todos veem — ou Comercial, etc.), como parte da
  confirmação do disparo. Vira requisito do motor de campanhas (ADR 0005).

## Consequências

- Fase 2 do plano dos modelos pode ser implementada (D1-D3 fechadas).
- O gate de consentimento por CONTATO (Fase 2) compara versão, não só o
  booleano — implementação deve seguir o desenho do PLANO_MODELOS.
- ADR 0005 (campanhas) ganha dois requisitos: filtro de opt-out (D2) e
  confirmação de departamento-destino no disparo em massa (D3).
