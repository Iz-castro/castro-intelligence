# ADR 0013 — Públicos da reabertura em lote: Recepção e Bot

**Data:** 2026-09-23 · **Status:** aceito (PO, 23/09/2026) · **Contexto:** Frente C2 (reabertura em lote) em produção desde
2026-09-02 com público único (`em_atendimento`). Plano de execução: `docs/PLANO_REABERTURA_LOTE_BOT_RECEPCAO.md`.

## Decisão

1. O lote passa a ter dois públicos, escolhidos na tela: **Recepção** (atendimento humano) e **Bot** (fase de bot).
2. **Fase de bot é um estado**, não uma prova: bot disponível no tenant (motor CX ativo), contato sem dono, `bot_completed`
   falso, `human_active` falso e nenhum outbound humano depois do marco de ciclo (`bot_released_at`, gravado em
   `release_lead_to_bot`/`return_contact_to_bot`, ou `handoff_at`). Lead devolvido ao bot por fechamento automático está em
   fase de bot mesmo que tenha sido atendido antes. Quem não está em fase de bot é Recepção, inclusive lead `novo` pós-handoff
   sem atendimento. Em tenant sem motor CX, lead sem dono com `bot_completed` falso fica fora dos dois públicos.
3. **Nenhum público inclui lead sem aceite LGPD** (`lgpd_consent` verdadeiro e não revogado). Aviso pendente ou recusa ficam fora.
4. **Continuar** em lead em fase de bot dispara um turno do CX (utterance = rótulo do botão; parâmetro de sessão
   `origem=retomada_lote`) e a Val responde. Em Recepção segue abrindo para a equipe.
5. **Encerrar não é permanente:** nova mensagem do lead limpa `reopen_opt_out` (emenda do ADR 0009 D2).
6. Tetos: **250 envios por dia por portfólio** (soma dos lotes das últimas 24h nos tenants; configurável) e **2 retomadas por contato
   em 90 dias** no público Bot, sem zerar por mensagem.
7. Sem resposta ao template no público Bot: carimbo terminal e fechamento silencioso da thread da tentativa, sem devolução ao bot.
8. Mídia recebida em fase de bot vira turno do bot; a resposta é do agente.
9. Flags por tenant: `reopen_batch_enabled` (lote inteiro; Hubloc desligada até o nome de exibição do número ser aprovado),
   `reopen_bot_audience_enabled` (público Bot, default `false`) e `bot_media_turn_enabled` (turno do bot para mídia, default `false`).
   Flag do público Bot desligada não muda a classificação: lead em fase de bot não entra na Recepção.

**Complementos decididos em 24/09:** teto por contato igual nos dois públicos (2 em 90 dias, lista única por contato);
versão da política LGPD como **data** editável pelo admin — re-perguntar quando o aceite é **anterior** à data da política, e o lote exclui quem está
desatualizado (confirmado 30/09); os campos de conteúdo LGPD (data, link, aviso) saem do `settings.ai` e passam a ser editados pelo
admin do tenant na aba Sistema (`system_settings`), inclusive no bot builtin da Hubloc — a clínica é a controladora dos dados; flag da Hubloc cobre o
lote inteiro, gravada **antes** do deploy, até o nome de exibição sair do LIMITED; idade máxima de 30 dias só para `novo` pós-handoff
**na Recepção** (o público Bot não tem teto de idade), com cadência semanal pelo admin da empresa; lead com desfecho registrado
pela Val (`desfecho_bot`: agendou, recebeu o link) fica fora do público Bot.

## Consequências

- A população que o lote atende hoje na Varizemed (leads fechados e devolvidos ao bot) continua alcançável, agora pelo público Bot.
- O público Bot é vazio por construção em tenant com bot builtin (aceite LGPD já faz handoff).
- Reabertura em lote e pontual deixam de bloquear quem clicou Encerrar e depois escreveu de novo.
- O lote Bot cria conversas pagas cuja resposta é do agente; visibilidade dessas threads continua na aba Bot (admin/supervisor).

## Alternativas rejeitadas

- Definir o público Bot por prova de resposta do agente no ciclo atual (proposta de 22/09): exigia instrumentação nova e backfill,
  nascia vazio e deixava o lead devolvido ao bot sem público.
- Continuar no Bot abrir para a equipe: o lead estava com a Val; a equipe não tem contexto e a caixa de Recepção enche.
- Opt-out permanente (ADR 0009 D2 original): cliente que escreve de novo demonstrou interesse.

## Emendas

- **2026-10-29 — item 4 implementado.** O clique em Continuar de lead em fase de bot (tenant com motor CX ativo) roda um turno do agente com `REOPEN_RESUME_BOT_TEXT` (env; default "Quero continuar o atendimento.", vazio desliga) e manda `origem=retomada_lote` por UM turno (`bot_service.queue_cx_session_params` → `bot_states.pending_session_params`; `origem=None` no turno seguinte). Falha do turno, motor builtin/pausado ou lead com dono caem no caminho antigo (equipe). Quem nunca respondeu ao aviso LGPD recebe o aviso antes do turno (gate local).
- **2026-10-28/29 — item 3 flexibilizado pelo PO para a Varizemed:** o script one-off `scripts/reopen_bot_audience_once.py` ganhou `--incluir-sem-aceite` (lead que NUNCA respondeu ao aviso; recusa explícita e revogação continuam fora). A tela do lote segue com a regra do item 3.
