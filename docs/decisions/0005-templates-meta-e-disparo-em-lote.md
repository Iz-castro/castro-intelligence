# ADR 0005 — Padronizacao de templates Meta e arquitetura de disparo em lote

- **Status:** Proposed (estudo registrado, aguardando priorizacao)
- **Data:** 2026-06-03
- **Autores:** Rafa + Gemini (estudo) + Claude (registro e ancoragem no codigo)
- **Relacionado:** envio de template em `/api/wa/send-template`
  ([main.py:1609](../../main.py#L1609), guard de billing em
  [main.py:1743](../../main.py#L1743)); protocolo de atendimento (Fase 5A)
  em [database_firestore.py:1364](../../database_firestore.py#L1364);
  ADR [0004](0004-falha-billing-assincrona-webhook.md) (falha de billing
  assincrona).

## Contexto

Estudo de estrategia (feito com apoio do Gemini) para dois temas que se
reforcam num CRM SaaS multi-tenant de locadora: (1) **padronizacao dos
templates** da Meta para previsibilidade operacional e evitar banimento
de WABA; (2) **arquitetura de disparo em lote** (bulk) para cobrancas e
avisos operacionais.

Estado atual no codigo:
- O envio unitario de template ja existe (`/api/wa/send-template`).
- A regra "1 dia = 1 protocolo" **ja esta implementada** (Fase 5A,
  colecao `attendances_daily`, granularidade dia no fuso BR — funcoes
  `get_or_create_daily_attendance`, `mark_protocol_informed`,
  `get_current_protocol_id`).
- **Nao existe** infra de disparo em lote: sem colecao de campanha, sem
  fila/worker, sem Cloud Tasks. O unico `bulk` hoje e
  `/api/admin/bulk-reassign` ([main.py:3302](../../main.py#L3302)), que
  reatribui contatos e nada tem a ver com envio de mensagens.
- **Nao existe** flag de opt-out de marketing no `wa_contacts` — e
  pre-requisito da Regra 3 abaixo.

---

## Parte 1 — Padronizacao de templates (Meta API)

Templates estritamente divididos entre as categorias da Meta (`Utility`
e `Marketing`) para operacao previsivel e sem banimento.

> **Aviso critico:** evitar variaveis-coringa que injetam textos longos
> (ex.: "Ola {{1}}, {{2}}" onde {{2}} carrega um paragrafo inteiro). A
> Meta bloqueia WABAs que tentam burlar a tarifacao por categoria.

### 1.1. Sistemicos (Utility) — fluxo interno e auditoria
- **Abertura com protocolo:** "Ola! Seu atendimento foi iniciado. Seu
  protocolo de hoje e {{1}}. Em breve um de nossos consultores falara
  com voce."
- **Takeover (assuncao):** "Ola, aqui e o Supervisor {{1}}. Estou
  assumindo seu atendimento a partir de agora para agilizar sua
  solicitacao."

### 1.2. Operacionais (Utility) — logistico e financeiro
Mais baratos, puramente informativos para garantir aprovacao.
- **Logistica (entrega/retirada):** "Ola {{1}}, passando para confirmar
  que a entrega do equipamento ({{2}}) esta agendada para o dia {{3}} no
  periodo da {{4}}. Agradecemos a preferencia!"
- **Financeiro (cobranca):** "Ola {{1}}, a fatura referente a locacao do
  equipamento {{2}} ja esta disponivel. O vencimento e no dia {{3}}.
  Segue o link/codigo para pagamento: {{4}}."
- **Suporte (deslocamento):** "Ola {{1}}, informamos que o tecnico {{2}}
  ja esta a caminho da sua obra para realizar a manutencao solicitada no
  equipamento {{3}}."

### 1.3. Retencao e vendas (Marketing) — conversao
Exige obrigatoriamente botao de "Parar promocoes" (opt-out) no rodape,
por regra da Meta **e** por exigencia da LGPD.
- **Recuperacao (follow-up):** "Ola {{1}}, tudo bem? Notamos que voce fez
  uma cotacao para {{2}} recentemente. Conseguimos uma condicao especial
  de frete para fecharmos hoje. Podemos seguir?"
- **Renovacao de locacao:** "Ola {{1}}, o periodo de locacao do
  equipamento {{2}} encerra no dia {{3}}. Deseja estender o prazo para
  nao interromper sua obra?"

---

## Parte 2 — Arquitetura de disparo em lote (bulk)

Disparo em lote (cobrancas, avisos) e comercialmente vital, mas um campo
minado tecnico. Liberar para o supervisor exige 4 regras absolutas para
nao corromper o banco nem banir o numero na Meta.

### Regra 1 — Arquitetura assincrona (a morte do front-end)
- **Problema:** loop de disparo no front (React) ou em funcao sincrona
  prende o cliente e quebra o envio se a internet do usuario oscilar.
- **Solucao:** o front envia payload minimo
  (`{template_id, array_de_leads}`). O back cria um documento de
  **Campanha** (`status: pendente`) e repassa o envio unitario a um
  **Worker** (fila em background). Net-new: definir colecao
  `campaigns` (escopada por `tenants/{tenant_id}/...` para isolamento) e
  o worker.

### Regra 2 — Rate limiting (prevencao de banimento Meta)
- **Problema:** disparar 1.000 mensagens no mesmo segundo bloqueia o
  numero por suspeita de spam.
- **Solucao:** fila com *rate limiting* (ex.: Google Cloud Tasks),
  diluindo para ~20 msg/s — envios constantes e seguros. Respeitar tambem
  o tier de mensagens da WABA.

### Regra 3 — Risco nuclear da LGPD (opt-out)
- **Problema:** disparo de marketing para quem pediu remocao gera bloqueio
  na Meta + passivo juridico.
- **Solucao:** antes de processar cada lead da fila, o back checa o
  Firestore. Se `opt_out_marketing: true`, **pula** o envio e contabiliza
  silenciosamente no relatorio de rejeicoes LGPD. Net-new: campo
  `opt_out_marketing` no `wa_contacts` (nao existe hoje) + captura do
  opt-out quando o cliente clica "Parar promocoes" (webhook do botao do
  template marketing).

### Regra 4 — Conformidade de protocolos (1 dia = 1 protocolo)
- **Problema:** disparos em lote precisam coexistir na timeline principal
  do atendimento (ja regida pela Fase 5A).
- **Solucao:** no disparo, o worker checa se o lead ja tem thread/atendimento
  do dia. Se nao houver, aplica *deferred execution*: cria um protocolo
  silencioso (reusar `get_or_create_daily_attendance`,
  [database_firestore.py:1402](../../database_firestore.py#L1402)) para
  atrelar a mensagem de lote. Se o lead responder ao template, a conversa
  volta a caixa de "Novos" associada ao **mesmo** protocolo valido (a
  logica de retorno-zumbi do Fase 5A ja cobre reabertura sem duplicar
  protocolo).

---

## Alternativas consideradas

1. **Envio em lote no front-end (loop sincrono).**
   - Pro: zero infra nova.
   - Con: quebra com oscilacao de rede, prende o navegador, sem rate
     limit — caminho direto pro banimento. **Rejeitada** (e a propria
     Regra 1).

2. **Worker sem rate limiting (fila simples).**
   - Pro: mais simples que Cloud Tasks.
   - Con: nao protege contra burst de envio; risco de ban. Aceitavel so
     com throttle manual confiavel.

3. **Campanha + worker + Cloud Tasks com rate limit + checagem de opt-out
   e protocolo (proposta).**
   - Pro: cobre os 4 riscos (rede, ban, LGPD, timeline). Escala e e
     auditavel.
   - Con: infra net-new (colecao `campaigns`, worker, Cloud Tasks, campo
     `opt_out_marketing`, relatorio de rejeicoes).

## Consequencias

### Positivas
- Disparo em lote viavel comercialmente sem arriscar a WABA.
- Templates padronizados por categoria reduzem reprovacao/bloqueio Meta.
- Opt-out estrutural = conformidade LGPD (consentimento revogavel,
  art. 8 §5) e protecao contra passivo juridico.
- Reuso do protocolo da Fase 5A mantem a timeline coerente.

### Negativas / pontos de atencao
- **LGPD/multi-tenant:** `campaigns` e o relatorio de rejeicoes devem
  ficar em `tenants/{tenant_id}/...` (isolamento estrutural, nunca filtro
  logico). Disparo so para leads do proprio tenant.
- **Minimizacao:** array de leads no payload deve conter so id/ref, nao
  PII redundante — o worker resolve os dados a partir do Firestore.
- **Auditoria:** disparo em lote e mutacao cross-user — exige
  `log_audit` (ex.: `BULK_CAMPAIGN_SENT`) com contagem de enviados,
  pulados-por-optout e falhas.
- **Categoria correta:** cobranca/logistica = Utility; promocao =
  Marketing com botao opt-out. Misturar categoria arrisca ban.
- **Falha de billing assincrona:** disparo em lote amplifica o problema
  da ADR [0004](0004-falha-billing-assincrona-webhook.md) — se a WABA do
  cliente estiver sem pagamento, a campanha inteira falha via webhook.
  Idealmente checar elegibilidade antes de enfileirar a campanha.

## Itens dependentes (fora do escopo deste ADR)

- Modelagem da colecao `campaigns` e do documento de progresso/relatorio.
- Escolha e configuracao da fila (Google Cloud Tasks vs alternativa).
- Captura do opt-out: webhook do botao "Parar promocoes" -> setar
  `opt_out_marketing` no `wa_contacts`.
- UI do supervisor para criar/acompanhar campanha (com preview de
  rejeicoes LGPD antes do disparo).
- Criar/submeter os templates desta ADR no Business Manager do cliente
  (cada WABA aprova os seus).
