---
name: project_channel_filter_meus
description: "Filtro por canal (standard/coex) no Meus Atendimentos — em prod 2026-07-17 (rev d20260717-1257); sem opcao \"Todos\"; follow-up de UX de transferencia coex em aberto"
metadata: 
  node_type: memory
  type: project
  originSessionId: 350b14c8-c4e7-4e4e-9523-6f865d4e3b43
---

Em 2026-07-17 entrou em prod (commit be99be9, rev `castro-crm-d20260717-1257`,
100% trafego) o select de canal no "Meus Atendimentos", a esquerda do filtro
de qualificacao:

- Opcoes derivadas das conversas do operador (channel_id/type/phone denorm);
  so aparece com 2+ canais; standard primeiro; rotulo "Standard - <numero>".
- SEM opcao "Todos" (decisao do Rafael via AskUserQuestion): abre ja
  filtrado no primeiro standard. Com 0-1 canal, caixa some e nada filtra.
- Zero backend. Fallback de channel_id via prefixo do id deterministico
  da thread ("{channel_id}__{wa_id}").
- Consequencia correta mas que surpreendeu: operador ve opcao "Coex" de
  numero de OUTRO operador quando atende thread que mora la (transferencia
  coex / devolucao no fechamento — lead gruda na vendedora devolve a thread
  fechada a dona de origem, [[project_bot_flow_e_pool_setor]]).

**Follow-up em aberto:** Rafael vai estudar o caso da thread coex de
terceiro no Meus (ex.: Aline dona de atendimento em numero da Danielle,
takeover pendente) pra "ver se chegamos numa solucao melhor" — possivel
mudanca futura no fluxo de transferencia/devolucao coex.

Primeira revisao com o sufixo de data `--revision-suffix dYYYYMMDD-HHmm`
(fix da numeracao fora de ordem, ver [[project_oregon_prod_cutover]]).
