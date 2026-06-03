# ADR 0004 — Tratar falha de billing assincrona (webhook failed) e avisar o admin

- **Status:** Proposed (ideia registrada, aguardando priorizacao)
- **Data:** 2026-06-03
- **Autores:** Rafa + Claude (analise inicial)
- **Relacionado:** `_process_statuses` em [webhook.py:689](../../webhook.py#L689),
  guard de billing sincrono em [main.py:1743](../../main.py#L1743),
  `update_wa_message_status` em [database_firestore.py:1916](../../database_firestore.py#L1916).

## Contexto

Em 2026-06-03 um template foi enviado pelo numero coexistence e a Meta
**aceitou o POST** (retornou `wamid`), mas falhou a entrega depois, via
webhook de status, com:

```
code=131042  Business eligibility payment issue
"Message failed to send because no payment method is set up for your
 WhatsApp Business account. Visit https://business.facebook.com/billing_hub/...
 to resolve this issue."
```

Ou seja: o cliente (dono da WABA, modelo passthrough) estava sem forma
de pagamento configurada. A Meta convenientemente entrega o **link
direto do billing hub** dentro de `error_data.details`.

Dois gaps ficaram evidentes:

1. **O guard de billing so cobre o caminho sincrono.** Em
   [main.py:1743-1748](../../main.py#L1743-L1748), `/api/wa/send-template`
   detecta billing e converte para HTTP 402 — mas so quando o POST de
   envio falha na hora (`131009`, subcodes `2494051/2494052`, ou as
   strings "not subscribed"/"payment"). Quando a Meta **aceita** o POST
   e falha **assincronamente** via webhook (como o `131042` deste
   incidente), o erro nao passa por esse guard.

2. **A falha assincrona e silenciosa para o admin.** O webhook
   (`_process_statuses`) agora **loga** o motivo (melhoria de
   2026-06-03), mas nada e exposto no CRM: a mensagem so vira
   `status="failed"`, sem motivo persistido nem notificacao. O admin so
   descobre o problema de pagamento se for ler os logs do Cloud Run —
   improvavel no dia a dia.

Resultado pratico: a WABA do cliente para de enviar e ninguem no CRM e
avisado de que basta adicionar um cartao no link que a propria Meta ja
forneceu.

## Decisao proposta

Tratar falhas de billing/elegibilidade **no handler de status do
webhook** (alem do caminho sincrono), e **avisar o admin** com o link
que a Meta entrega.

1. **Mapear codigos de billing/elegibilidade no webhook.** Em
   `_process_statuses`, ao receber `failed`, reconhecer um conjunto de
   codigos conhecidos como "billing" — pelo menos `131042` (Business
   eligibility payment issue) e `131009`, mais a heuristica de
   `"payment"`/`"not subscribed"` em title/details como rede de
   seguranca para variantes futuras.

2. **Persistir o motivo no `wa_messages`.** Estender
   `update_wa_message_status` para gravar `error_code` e `error_title`
   (e talvez `error_details`) quando `state == "failed"`, para a UI
   poder mostrar "Falhou: sem forma de pagamento" na propria conversa,
   sem ir a Graph API.

3. **Notificar o admin do tenant.** Em falha de billing, criar uma
   notificacao/banner no CRM (idealmente uma so por tenant ate ser
   resolvida, para nao spammar a cada mensagem) com CTA apontando para
   o link de billing extraido de `error_data.details`. Possivel reuso
   do painel de chat interno / Google Chat (ver memoria de integracao)
   para alertar supervisor.

4. **Reaproveitar a deteccao no sincrono.** Centralizar a lista de
   codigos/heuristica de billing num helper unico, usado tanto pelo
   guard sincrono ([main.py:1743](../../main.py#L1743)) quanto pelo
   webhook, evitando divergencia (hoje o sincrono nao conhece `131042`).

## Alternativas consideradas

1. **Manter so o log (estado atual pos-2026-06-03).**
   - Pro: zero codigo novo; o motivo ja aparece no Cloud Run.
   - Con: admin nao ve no produto; depende de alguem inspecionar log.
     Tempo de reacao alto — a WABA fica parada sem aviso.

2. **So persistir `error_code` no `wa_messages` (sem notificacao).**
   - Pro: simples; UI consegue mostrar o motivo na conversa.
   - Con: admin so ve se abrir aquela conversa especifica; nao ha
     alerta proativo de "sua conta esta sem pagamento".

3. **Persistir + notificar o admin com o link de billing (proposta).**
   - Pro: cobre os dois gaps; reação rapida; reusa o link que a Meta
     ja fornece. Centraliza a logica de billing num helper.
   - Con: codigo adicional (campo novo, notificacao, dedupe por tenant,
     UI). Precisa decidir o canal do alerta (banner no CRM? chat
     interno? e-mail?).

## Consequencias

### Positivas
- Falha de pagamento vira **acionavel** no produto, nao um `failed`
  mudo.
- Logica de billing deixa de estar duplicada/divergente entre sincrono
  e assincrono.
- UI pode mostrar o motivo real da falha por mensagem.

### Negativas / pontos de atencao
- **LGPD:** `error_data.details` da Meta pode conter URL com
  `business_id`/`asset_id` do cliente — sao identificadores de conta
  business, nao PII de titular, mas a notificacao deve ser visivel
  apenas a roles admin do tenant dono da WABA (isolamento por
  `tenant_id`), nunca cross-tenant.
- Definir politica de **dedupe** do alerta (1 por tenant ate resolver)
  para nao gerar uma notificacao por mensagem falhada durante o periodo
  sem pagamento.
- Modelo passthrough: a acao (adicionar cartao) e **do cliente**, dono
  da WABA — a copy do alerta deve deixar isso claro e so direcionar ao
  link, sem a Castro Intelligence assumir a cobranca.

## Itens dependentes (fora do escopo desta ADR)

- Definir o canal e a UX do alerta (banner persistente no CRM x chat
  interno x e-mail ao admin).
- Levantar a lista completa de codigos de billing/elegibilidade da Meta
  que chegam por webhook assincrono (alem de `131042`/`131009`).
