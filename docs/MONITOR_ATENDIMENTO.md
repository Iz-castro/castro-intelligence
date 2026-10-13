# Monitor de atendimento

**Desde:** 13/10/2026 (branch `feature/painel`). **Pedido:** PO, para a Hub Loc.
**Origem:** porte do painel local do Izael ("Monitor Castro Chat v2", `painel.py` + `painel.html`),
que rodava fora do CRM, em `localhost`, com login próprio.

## O que é

Uma tela do CRM, no menu de configurações, que **substitui o item "Dashboard"** para quem tem a
permissão `ver_monitor_atendimento` num tenant com monitor. Quem não tem a permissão (supervisão,
outros tenants) continua vendo o Dashboard antigo, sem mudança.

| Seção | O que mostra |
|---|---|
| Fila de espera | Cliente que o bot entregou à fila do Comercial e está sem resposta de uma pessoa há mais de 5 min, no horário comercial. Bipe opcional, "Silenciar" por alerta, quem assumiu sem responder, quantas mensagens o cliente mandou depois. |
| Indicadores | Conversas, mensagens, protocolos novos, % que chegou à fila, % com resposta humana. |
| Gráficos | Volume por dia, atendimentos por atendente, tempo de resposta (mediana e média), equipamentos mais citados. |
| Origem | Site, Meta/Instagram ou Indeterminada por protocolo, pela 1ª fala do cliente; tabela por canal e aberturas sem marcador que se repetem. |
| Auditoria | Download .txt das conversas em que um atendente respondeu no período (até 31 dias), cliente anonimizado. Cada export vai para `log_audit` (`MONITOR_AUDITORIA_EXPORT`). |
| Resumo diário | O conteúdo do Dashboard antigo (agregado diário, avaliações, CSV). |

## Regras (do Izael) e o que mudou no porte

As regras de negócio são as do painel: classificação de mensagem (`eh_turno`,
`eh_resposta_humana`), fila só depois do handoff, palavras por número de conversas, origem por texto
e auditoria anonimizada. Mudanças:

- **Fila pelo `handoff_at`, não pelo texto "Bot finalizado".** `_finalize_bot` grava o mesmo
  `handoff_at` em todas as threads do contato, inclusive a do número pessoal (coex). Resposta humana
  (`last_human_outbound_at`) em qualquer uma delas para o relógio. O painel relia todas as mensagens
  de 12h a cada 15 s (~2.500 docs por consulta); aqui são as threads com handoff em 72h (13 em
  13/10). O cadastro do contato só é lido para quem passou nos critérios da thread.
- **Horário** do `business_hours.py` (Hub Loc 8h às 17h, seg a sex), não 7h às 17h fixo. Lead que
  chega com a loja fechada conta a partir da abertura, igual ao aviso de espera na pool.
- **Histórico importado fica de fora.** Mensagem gravada mais de 3h depois da hora real
  (`created_at - timestamp_wa`) é importação: histórico do WhatsApp ao conectar um número coex ou
  replay de backup. Em 13/10 eram 39% das mensagens de 7 dias e geravam "mídia histórico" como
  equipamento mais citado. Tempos e ordem usam a hora real (`timestamp_wa`).
- **Marcadores** (`[Midia do historico - aguardando]`, `[errors]`...) não contam como texto do
  cliente. Primeiro nome dos usuários do tenant sai do gráfico de palavras.
- **Métricas sob demanda**, com cache de 10 min no backend (`refresh=true` no "Atualizar"). O painel
  recalculava a cada 5 min com a tela aberta.
- **Exportação** vira download no navegador, auditado; o painel gravava em disco.
- Login, sessão e tenant são os do CRM. A visão de clínica do painel (Varizemed) não foi portada.

## Permissão e liga/desliga

- `ver_monitor_atendimento` (grupo Auditoria em Perfis de acesso): ligada só no perfil
  Administrador. Para liberar a uma supervisora, ligar no perfil dela; a permissão é por perfil, então
  para uma pessoa só, criar um perfil próprio a partir do Supervisor. Vale sem relogin.
- Tenant com monitor: `MONITOR_TENANTS` em `monitor_service.py` (hoje só `hubloc`; os marcadores de
  origem e os termos excluídos do gráfico são da Hub Loc). Varizemed fica fora (conversa de paciente).
- Kill-switch sem deploy: `FEATURE_MONITOR=false` volta o menu ao Dashboard.

## Custo de leitura (hubloc, 13/10/2026)

| Consulta | Docs | Quando |
|---|---|---|
| Fila | threads com handoff em 72h (13) + cadastro e últimas 25 mensagens só dos alertas | a cada 30 s com o Monitor aberto, cache de 20 s |
| Métricas 7 / 14 / 30 dias | ~8,0k / ~14,4k / ~31,4k mensagens | ao abrir, ao trocar o período, no "Atualizar"; cache de 10 min |
| Auditoria | mensagens do período escolhido | a cada download |

## Limitações conhecidas

- Origem só pelo texto da 1ª mensagem: o CRM ainda não grava o `referral` do anúncio (frente de
  origem de mídia). Quando gravar, a tag entra em `classificar_origem` e vence o texto.
- Resposta automática do app WhatsApp Business no número pessoal (saudação/ausência) chega como
  mensagem do dono do número e conta como resposta humana.
- O corte de 3h para histórico importado é heurístico: mensagem real atrasada mais de 3h (fila de
  pending muito longa) também sai das métricas.

## Validação

`tools\sim_monitor_flow.py` (69 checagens): casos A a I do modo demo do painel, horário, histórico,
custo de leitura, RBAC, rotas e export auditado. Rodado também, só leitura, contra os dados reais da
Hub Loc em 13/10.
