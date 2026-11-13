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

> **Emenda 2026-09-23 (PO, ADR 0013):** o opt-out de reabertura do D2 **deixa de ser permanente**. Qualquer mensagem nova do
> cliente limpa `reopen_opt_out` no mesmo ponto do webhook que zera `reopen_attempts`. O clique em Encerrar continua carimbando
> o opt-out e o envio pontual continua bloqueando enquanto ele estiver ativo. Ver `docs/decisions/0013-publicos-reabertura-lote.md`.

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

## Emenda 2026-10-23: LGPD tratada pelo agente (Hubloc/Hugo)

Decisão do PO: na Hubloc, o agente de IA Hugo trata o aviso e a recusa da LGPD;
o CRM não deve mandar o próprio aviso antes dele (o cliente veria dois).

- Opção por tenant `settings.ai.lgpd_by_agent` (só vale com `true`). Com ela, o
  turno CX pula o gate local, não rebaixa nem hidrata consentimento, não grava
  prova de aceite no contato e não envia `lgpd_consent` ao agente. O buffer CX
  arma sem fase de consentimento no CRM.
- Sem a opção, nada muda: a Val segue com o gate local antes do motor.
- Consequências aceitas: a prova do aceite passa a existir só no agente (no
  Hugo, em `hugo/conversas`, banco do projeto castro-ia); a recusa dentro do
  agente não sinaliza o CRM; recursos que dependem do aceite no CRM (público
  Bot da reabertura em lote) não enxergam esses contatos. Voltar ao builtin
  (`bot_engine` vazio) restaura o gate do CRM para as mensagens seguintes.
- Validar o texto do aviso e a base legal com o jurídico da Hub Loc.

## Emenda 2026-11-13: botões do aviso depois do aceite

Decisão do PO depois da conferência dos primeiros lembretes da Varizemed (diário de 13/11): "Se o lead clicou não
então o aceite passa a não valer mais. Deve valer como recusa." E o segundo toque em "Sim" deixa de gerar resposta.

Como era: com o aceite já gravado, `handle_lgpd` devolvia `None` para qualquer mensagem, e o id técnico do botão
(`lgpd_aceitar` ou `lgpd_recusar`) seguia para o agente como se fosse texto do paciente. A Val respondia de novo ao
segundo "Sim" (26 contatos da Varizemed desde julho) e o "Não" não registrava recusa (5 contatos). A série A dos
lembretes (ADR 0015) pôs até quatro mensagens com os mesmos botões na conversa.

Regra nova, só para o gate local (CX sem `lgpd_by_agent` e builtin):

- **Só o toque conta** (id exato do botão, `lgpd_bot.botao_lgpd`). "Sim" ou "não" digitados depois do aceite
  continuam sendo fala do paciente para o agente.
- **Toque em "Não" depois do aceite = recusa.** O estado vira `refused`, sai a despedida da recusa e, no mesmo batch,
  o contato fica com `lgpd_consent=False` e `lgpd_refused_at`. `lgpd_consent_at` e `lgpd_policy_version` ficam como
  histórico do aceite anterior (nenhum leitor os usa sem `lgpd_consent` verdadeiro). Auditoria:
  `LGPD_CONSENT_REFUSED`. Sem a gravação no contato, o lote de reabertura (que lê só o contato) continuaria
  enviando, e a hidratação voltaria a valer a prova antiga assim que o `bot_states` fosse apagado.
- **Não é `lgpd_revoked`.** Aquele campo é a revogação registrada pela equipe (plano J-3, D8), definitiva, que o
  "Sim" do paciente não desfaz. A recusa pelo botão admite novo aceite, que regrava a prova.
- **Novo aceite depois dessa recusa:** sai só a confirmação. A primeira mensagem do ciclo não volta ao agente como
  replay (ele já a respondeu); volta o que o paciente digitar durante a recusa.
- **Toque repetido em "Sim" é ignorado**: sem turno do agente e sem resposta, antes da baixa dos parâmetros de um
  turno. O critério é o tempo: só é repetição o toque que chega até 5 minutos depois do aceite gravado no contato
  (`lgpd_consent_at`; os casos reais vieram em até 99 s). O critério não pode ser "há aceite em `bot_states`": o
  estado sobrevive quando a conversa é encerrada por atendente (o release faz merge e preserva `lgpd_*`), e o
  paciente que voltasse dias depois tocando "Sim" ficaria sem resposta. Fora da janela, ou quando o turno anterior
  falhou (`cx_fail_count` > 0, o paciente ainda não teve resposta do agente), o toque segue ao agente como antes.
- **Recusa gravada durante o DetectIntent de outro turno** (toque em "Não" segundos depois do "Sim"): a resposta
  atrasada do agente é descartada e o handoff daquele turno não acontece.
- **Lead fora da fase de bot** (na fila ou com atendente): o bot não roda, mas o webhook registra a recusa
  (`record_lgpd_refusal_outside_bot`), sem resposta automática no meio do atendimento humano. Se sobrou estado com
  aceite em `bot_states`, ele vira recusa no mesmo batch. Na fase de bot seguinte o aviso é mostrado de novo. O
  webhook confere em dois momentos: na chegada do toque e **depois do turno**, com o contato relido. Com o buffer
  ligado, o clique roda depois da rajada pendente; se ela termina em handoff, o turno do clique sai antes do gate e
  só essa segunda conferência registra a recusa. A segunda conferência só invalida o aceite que já existia quando o
  toque chegou (mesmo `lgpd_consent_at` na chegada e na releitura): se o paciente toca "Não" e corrige com "Sim" em
  seguida, o aceite novo, gravado durante o envio da despedida, não é derrubado.
- **Toque em botão de aviso antigo sem estado** (ex.: ciclo novo de quem recusou): o aviso é mostrado de novo e o id
  do botão não fica guardado como primeira mensagem do paciente.
- Tudo isso vale só para o gate do CRM. Tenant com `lgpd_by_agent` e motor CX não muda; no builtin (`bot_engine`
  vazio) o gate é do CRM mesmo que a opção tenha ficado ligada.

Limites aceitos:

- O toque repetido ignorado é mensagem nova: encerra o ciclo dos lembretes, que só rearma no turno seguinte do agente.
- Fora da janela de 5 minutos o toque em "Sim" chega ao agente como o texto do id, como sempre; dois toques
  seguidos nessa situação ainda geram duas respostas.
- Dentro da janela, se a resposta do turno do aceite não chegou ao paciente por falha de envio na Meta ou por
  exceção depois do aceite gravado (e não por falha do motor, que é tratada), o novo toque em "Sim" também é
  ignorado. O paciente sai disso digitando, ou tocando de novo depois dos 5 minutos.
- Aceite só com a confirmação: quando não há primeira mensagem a reenviar (aceite depois de recusa pelo botão, ou
  ciclo aberto por toque em botão antigo), o paciente recebe a confirmação e a conversa segue quando ele escrever.
- Toque em "Não" com a thread assumida por operador sem dono no contato (`human_active`), com o bot desligado ou com o
  motor pausado não é registrado.
- Fora da fase de bot o operador vê só a bolha com o texto `lgpd_recusar` (não há aviso de sistema), o "Sim" tocado
  depois não desfaz a recusa (o paciente aceita de novo no próximo ciclo com o bot) e o aviso de espera da fila
  continua saindo (ele só olha `lgpd_revoked`).
- Depois da recusa, "sim" digitado volta a valer como aceite (comportamento que o estado recusado já tinha). Com um
  turno do agente acima de 30 s, um "sim" digitado antes do toque em "Não" pode ser processado depois dele.
- O toque continua contando como mensagem nova do paciente (não-lido, reabertura do atendimento, D4 do opt-out,
  recusa comercial).
- Evento antigo reprocessado da fila de pendentes aplica a recusa com atraso.

Testes: `tools/sim_cx_flow.py` (cenário z), `tools/sim_bot_flow.py` (cenário 9) e `tools/sim_buffer_flow.py`
(cenário 23), com prova por mutação (51 mutantes do código de produção, todos pegos). Duas rodadas de revisão
independente (4 revisores e 6 céticos; depois 2 revisores e 4 céticos sobre as correções) acharam e fecharam três
defeitos de severidade média antes do commit: o "Não" perdido atrás de um handoff, o "Sim" calado em conversa nova
e a recusa gravada por cima de um aceite mais novo.
