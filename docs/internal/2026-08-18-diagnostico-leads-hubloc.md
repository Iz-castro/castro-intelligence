# Diagnóstico — "não está chegando lead no bot" (Hubloc)

**Data:** 18/08/2026, 09h–10h (BRT) · **Pedido por:** Rafael · **Executado por:** Claude (Castro Intelligence)
**Escopo:** descartar falha do CRM/bot antes de atribuir a queda ao marketing. Toda a verificação foi **somente leitura** em produção (Cloud Run `castro-crm`, projeto Oregon, Firestore `castro_crm`), exceto o item 7 (limpeza de dois números de teste, a pedido).

---

## Resumo executivo

1. **O serviço está entregando e o bot está respondendo.** Nos últimos 14 dias, 100% das chamadas da Meta ao webhook receberam `200`; a fila de eventos pendentes está zerada; e dos **189 leads novos** que chegaram no número do bot em 21 dias, **187 receberam a resposta do bot em ≤10 min (mediana 4 s)** — os 2 restantes são casos em que o bot não deve rodar (1º contato não-texto / criado por mensagem de sistema).
2. **O que caiu foi o volume de gente nova escrevendo pro número do bot** — de ~60–90 leads/semana para **6 na segunda-feira 17/08** e **0 até 09h27 de hoje**. O sinal mais claro: as mensagens com o texto pré-preenchido do **botão do site** ("Olá! Vim pelo site da Hub Loc…") foram de **9/dia (10–11/08) para 0 em 14, 15 e 16/08** e ~2/dia desde então, enquanto o inbound de clientes já existentes seguiu normal (164 mensagens no dia 17).
3. **O botão do site aponta pro número certo** (`wa.me/553133517604`, 23 links na home; site respondendo). Portanto a queda está **antes** do WhatsApp/CRM: menos cliques/tráfego chegando ao botão (mídia paga, SEO, campanha, página de destino).
4. **Teste ao vivo às 09h38 confirmou** (seção 7): dois números zerados escreveram pro +55 31 3351-7604 — um deles pelo próprio botão do site — e em **2 s** receberam o aviso LGPD do bot; após o aceite, caíram no pool do Comercial e foram assumidos com protocolo em menos de 30 s.

Há dois pontos de configuração na Meta que **não explicam a queixa**, mas merecem correção (seção 6).

---

## 1. Canais WhatsApp cadastrados (CRM × Meta)

Cadastro do CRM (`channels` + `phone_routing`) está íntegro e consistente 1:1. Estado na Meta consultado via Graph API com o token de cada canal (`subscribed_apps`, `phone`, `WABA`, `health_status`).

| Canal | Tenant | Tipo | Número | `phone_number_id` | WABA | Meta hoje |
|---|---|---|---|---|---|---|
| 1 | hubloc | coexistência (Izael) | +55 31 9934-6195 | 1093519330516990 | 985540003931801 | ⚠️ token **não acessa mais** WABA/telefone ("does not exist / missing permissions") — provavelmente desconectado na Meta, mas segue `active` no cadastro |
| 2 | hubloc | coexistência (Aline) | +55 31 9833-5187 | 841410913287143 | 1237692759946280 | app inscrito ✅ · CONNECTED · qualidade GREEN · nome de exibição não aprovado (`NON_EXISTS`) → envio `LIMITED` |
| 3 | hubloc | coexistência (Danielle) | +55 31 8979-3089 | 2768278269960685 | 263297655079710 | app inscrito ✅ · CONNECTED · GREEN · nome não aprovado (`NON_EXISTS`) → `LIMITED` |
| **4** | **hubloc** | **standard — número do bot** | **+55 31 3351-7604** | 1118622994671651 | 1548003596823528 | app inscrito ✅ · CONNECTED · GREEN · WABA APPROVED · **`name_status = DECLINED`** ("HUBCLOC COMERCIAL" recusado) → envio `LIMITED` |
| 6 | varizemed-test | standard | +55 31 7195-7758 | 1199019616617623 | 1573507174381657 | app inscrito ✅ · tudo AVAILABLE |
| 7 | varizemed | standard | +55 31 9979-4546 | 1257632794095120 | 28119031584452691 | app inscrito ✅ · tudo AVAILABLE |

Configuração do bot da Hubloc: `system_settings/chat.bot_enabled = true`, tenant ativo, motor builtin (sem Dialogflow). O gate LGPD → pool do Comercial está do jeito que foi desenhado.

---

## 2. Entrega da Meta → nosso webhook (14 dias)

| Verificação | Resultado |
|---|---|
| `POST /webhook` com status ≠ 200 desde 10/08 | **1** (um `429` isolado em 10/08 18:59Z). Todo o resto `200`. |
| Volume de `POST /webhook` por dia (todos os tenants) | 06/08: 1.851 · 07: 1.879 · sáb 08: 353 · dom 09: 222 · 10: 2.390 · 11: 2.277 · 12: 2.751 · 13: 2.014 · 14: 1.633 · sáb 15: 159 · dom 16: 188 · 17: 2.473 · 18 (até ~09h40): 459 |
| `pending_webhook_events` recebidos na janela | **0** (nenhum `no_channel`, nenhuma exceção enfileirada). Total histórico pendente: 1 (antigo). |
| Buracos de recepção (inbound por hora, 12–18/08) | Nenhum em dias úteis 7h–17h. No fim de semana 15–16 a Hubloc recebeu 4 e 6 mensagens, mas a **Varizemed recebeu 41 e 46 no mesmo período pelo mesmo serviço** → a plataforma esteve no ar. |
| Erros no Cloud Run | 14/08 18:56Z: rajada de ~20 `GET /api/wa/contact/{id}` do frontend abortados ("no available instance") — **não** era webhook. 14/08 14:08Z: 1 falha transitória de conexão ao enviar resposta do bot (auto-recupera na mensagem seguinte). |
| Revisão em produção | `castro-crm-00081-swz` (100% do tráfego), min 1 / max 10 instâncias, concorrência 8. |

---

## 3. O bot está respondendo?

Método: para cada contato **novo** criado pelo webhook no canal 4 (últimos 21 dias), procurar a primeira mensagem inbound e uma resposta do bot em até 10 min.

| Métrica | Valor |
|---|---|
| Leads novos no canal 4 (21 dias) | 189 |
| Receberam resposta do bot em ≤10 min | **187** |
| Latência da resposta (s) | mín 2,1 · p50 4,0 · p90 5,0 · máx 15,9 |
| Não cobertos | 1 lead cujo 1º inbound foi `unsupported` (não-texto — o bot só roda em texto) e 1 contato criado por mensagem de sistema (sem inbound). Comportamento esperado. |
| Status das mensagens do bot no canal 4 (21 d) | 243 lidas · 136 entregues · 11 enviadas · 9 falhas de envio (transitórias) |
| Simulador do fluxo builtin (`tools/sim_bot_flow.py`, código real com mocks) | 56/56 checagens ✅ |

Exemplo real de 17/08 00h47 (BRT): lead escreve "Olá, quero alugar uma ferramenta!" → **3 s** depois o bot envia o aviso LGPD → lead manda áudio (bot não trata) → supervisora reatribui à operadora às 07h27 → operadora responde 07h30.

Observação: **todos os 124 leads novos do canal 4 dos últimos 14 dias têm dono** hoje (91 passaram pelo bot até o fim; os demais foram assumidos/reatribuídos por operadora antes de concluir o LGPD). Ou seja, os leads que chegam estão sendo vistos e trabalhados.

**Roteamento pro setor certo:** dos 143 leads novos que concluíram o bot em 21 dias, **137 foram para o Comercial** (setor id 2, `bot_key = comercial`, ativo) — tanto no contato quanto na conversa `4__<wa_id>`, que é o campo que segmenta o pool "Novos Leads". Os 6 restantes (4 Suporte, 2 Financeiro) foram **movidos por operadora depois de assumidos** (transferências entre setores), não pelo bot. Os setores duplicados "Vendas" (ids 7 e 8) e "Geral" (id 6) estão inativos — nenhum sequestro de roteamento.

---

## 4. Volume — onde está a queda

### 4.1 Leads novos por semana (canal 4 = número do bot; `wa_contacts` criados pelo webhook)

| Semana ISO | Período | Canal 4 (bot) | Coex (1+2+3) |
|---|---|---|---|
| 26 | 22–28/06 | 97 | 38 |
| 27 | 29/06–05/07 | 64 | 32 |
| 28 | 06–12/07 | 83 | 12 |
| 29 | 13–19/07 | 90 | 39 |
| 30 | 20–26/07 | 88 | 23 |
| 31 | 27/07–02/08 | 79 | 25 |
| 32 | 03–09/08 | 70 | 26 |
| 33 | 10–16/08 | 58 | 24 |
| 34 | 17/08 (só segunda) | **6** | 7 |

### 4.2 Últimos 14 dias, por dia (BRT)

| Dia | Leads novos canal 4 | Inbound canal 4 (todas as msgs) | "Vim pelo site" (canal 4) |
|---|---|---|---|
| ter 04/08 | 18 | 70 | 12 |
| qua 05 | 13 | 127 | 6 |
| qui 06 | 7 | 140 | 1 |
| sex 07 | 10 | 144 | 5 |
| sáb 08 | 7 | 22 | 4 |
| dom 09 | 4 | 6 | 2 |
| seg 10 | 13 | 120 | 9 |
| ter 11 | 18 | 178 | 9 |
| qua 12 | 9 | 123 | 2 |
| qui 13 | 4 | 59 | 2 |
| sex 14 | 9 | 71 | **0** |
| sáb 15 | 2 | 4 | **0** |
| dom 16 | 3 | 6 | **0** |
| seg 17 | 6 | 164 | 2 |
| ter 18 (até 09h27) | **0** | 21 | 2 |

Leitura: o inbound de **clientes já existentes** continua (164 msgs na segunda), as operadoras seguem trocando mensagens normalmente nos coex, mas a entrada de **gente nova** — em especial a que vem do botão do site — despencou a partir de 13–14/08. Para referência, em dias úteis normalmente 0–7 leads novos chegam antes das 09h30 (mediana 3); hoje, 0.

### 4.3 O botão do site

`https://hubloc.com.br/` respondeu 200 (90 KB). Todos os 23 links de WhatsApp da home apontam para
`https://wa.me/553133517604?text=Olá! Vim pelo site da Hub Loc e gostaria de um orçamento de locação.` — ou seja, **o número certo (canal 4)** e o texto que usamos como marcador. Não há links para outros números. As mensagens com esse texto **não migraram** para nenhum outro canal (busca em todos os canais da Hubloc, 12 dias).

Conclusão: a redução é de **cliques/tráfego** chegando ao botão (ou de leads via anúncio click-to-WhatsApp, que não usam texto pré-preenchido), não de entrega ou de resposta.

---

## 5. O que foi descartado do nosso lado (checklist)

- [x] Cadastro de canais e roteamento por `phone_number_id` (todos os canais ativos batem com `phone_routing`)
- [x] Assinatura do nosso app nas WABAs da Hubloc (canais 2, 3 e 4) — inscrito
- [x] Webhook respondendo `200` (sem 4xx/5xx relevantes, sem timeouts)
- [x] Fila de eventos pendentes vazia (nenhuma mensagem "presa" por canal não resolvido)
- [x] Recepção contínua por hora em dias úteis; plataforma no ar no fim de semana (Varizemed normal)
- [x] Bot habilitado, respondendo a 187/189 leads novos, latência mediana 4 s
- [x] Leads novos com dono/atendidos (nenhum lead "invisível" preso no gate LGPD)
- [x] Site aponta para o número correto; nenhuma migração de mensagens para outro canal
- [x] Sem deploy suspeito: última revisão 17/08 15h28Z; comportamento do bot igual antes/depois
- [x] Teste controlado ao vivo (2 números novos, um via botão do site): bot em 2 s, aceite LGPD, pool do Comercial, assumido com protocolo

---

## 6. Pendências (não causam a queixa, mas vale corrigir)

1. **Nome de exibição do canal 4 recusado pela Meta** (`name_status = DECLINED`, "HUBCLOC COMERCIAL"). Consequência: `can_send_message = LIMITED` — teto baixo de conversas **iniciadas pela empresa** (templates de retomada, campanhas). Não afeta receber nem responder dentro de 24 h. Ação: submeter um nome de exibição válido no WhatsApp Manager (ex.: "Hub Loc" / "Hub Loc Comercial", conforme a política de nomes). Canais 2 e 3 estão na mesma situação (`NON_EXISTS`).
2. **Canal 1 (coex do Izael)** aparece desconectado na Meta (token sem acesso à WABA/telefone) mas continua ativo no cadastro e no `phone_routing`. Ação: confirmar no WhatsApp Manager e desativar o canal no CRM se for o caso.

---

## 7. Teste controlado (a pedido do Rafael)

Para reproduzir o caminho de um lead 100% novo, os contatos de teste do Rafael e do Izael foram **removidos do tenant hubloc** (contato + índice de `wa_id` + conversas em todos os canais + mensagens e índices + atendimentos diários + logs de transferência; resíduo verificado = 0). Roteiro:

1. Enviar uma mensagem de **texto** para **+55 31 3351-7604**.
2. Esperado em segundos: aviso LGPD com botões (mensagem do bot).
3. Tocar em "aceitar": mensagem de confirmação e o lead entra no pool do **Comercial** ("Novos Leads") sem dono, para uma operadora assumir.

### Resultado (18/08/2026, 09h38 BRT) — ✅ os dois passaram ponta a ponta

Timeline real lida em produção (`tenants/hubloc/wa_messages`), horários em BRT:

| Passo | Rafael (contato novo #8215) | Izael (contato novo #8216) |
|---|---|---|
| 1º inbound (texto) | 09:38:11 — "Ola bom dia" | 09:38:40 — "Olá! Vim pelo site da Hub Loc e quero um orçamento de locação de Martelo Rompedor 10 Kg…" (texto vindo do **botão do site**) |
| Bot envia aviso LGPD | **09:38:13 (2 s)** | **09:38:42 (2 s)** |
| Lead toca "aceitar" (`lgpd_aceitar`) | 09:38:23 | 09:39:02 |
| Sistema: "Bot finalizado · Setor=Comercial · Encaminhado para Comercial" | 09:38:24 | 09:39:03 |
| Bot confirma ("Certo, seus dados serão tratados…") | 09:38:25 | 09:39:04 |
| Lead visível no pool e **assumido** por operador (protocolo gerado) | 09:38:39 — protocolo 20260818-8215-GERAL | 09:39:07 — protocolo 20260818-8216-GERAL |
| Conversa humana segue normalmente | ✅ (mensagens lidas/entregues) | ✅ (mensagens lidas/entregues) |

Estado final dos dois contatos: `bot_completed = true`, `lgpd_consent = true`, `department_id = 2` (Comercial), canal 4, com dono. O teste do Izael saiu pelo próprio botão do site (texto pré-preenchido), fechando o circuito **site → WhatsApp → webhook → bot → pool → operador** em menos de 30 segundos.

---

## Método (reprodutibilidade)

- Firestore de produção, somente leitura: `castro_crm_channels`, `castro_crm_phone_routing`, `castro_crm_tenants`, `tenants/hubloc/{system_settings, wa_contacts, wa_conversations, wa_messages}`, `castro_crm_pending_webhook_events`.
- Cloud Logging: `run.googleapis.com/requests` (status/volume de `POST /webhook`), logs de aplicação (severity ≥ ERROR, `[BOT]`, `[PENDING]`).
- Meta Graph API v22 com o token de cada canal: `/{waba}/subscribed_apps`, `/{phone_id}` (status, qualidade, `name_status`, `health_status`), `/{waba}` (review/verificação). Tokens nunca foram exibidos.
- Site: `GET https://hubloc.com.br/` e extração dos links `wa.me`/`tel:`.
