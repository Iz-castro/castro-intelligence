---
name: hubloc-lead-drop-2026-08-18
description: "Diagnostico 2026-08-18 da queixa \"nao chega lead no bot\" da Hubloc — servico OK, queda e de trafego do botao do site; flags Meta abertas (name_status DECLINED canal 4, canal 1 Izael inacessivel)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9de4d0b6-e36d-4dee-9f9b-b3649c1a678d
  modified: 2026-08-18T12:31:45.631Z
---

**Queixa (Hubloc, 2026-08-18):** "nao esta chegando lead no bot". Rafael pediu pra descartar nosso servico antes de culpar o marketing.

**Conclusao:** servico OK. Evidencias (todas read-only em prod Oregon):
- Canais/phone_routing consistentes; hubloc = coex 1 (Izael), 2 (Aline), 3 (Danielle) + standard **4 = +55 31 3351-7604** (`phone_id 1118622994671651`, WABA 1548003596823528, e o numero do bot); varizemed = 7; varizemed-test = 6. `bot_enabled=True` na hubloc.
- Webhook: 100% POST /webhook = 200 desde 10/08 (1 unico 429 no dia 10); ~2.0–2.7k POST/dia util; `pending_webhook_events` = 0 em 14d.
- Bot builtin respondeu 187/189 leads novos do canal 4 em 21d (p50 4s); 2 excecoes = 1o inbound nao-texto / criado por msg de sistema.
- Volume de leads novos no canal 4 por semana ISO: 97, 64, 83, 90, 88, 79, 70, 58 → semana 34 comecou com 6 (seg 17/08). Mensagens com o texto pre-preenchido do botao do site ("Vim pelo site da Hub Loc") cairam de 9/dia (10–11/08) para 0 em 14, 15 e 16/08 e ~2/dia depois — enquanto inbound de contatos existentes e coex seguiram normais. Botao do site aponta certo (wa.me/553133517604). => queda e upstream (trafego/site/ads).

**Flags Meta abertas (nao causam a queixa):**
- Canal 4: `name_status=DECLINED` ("HUBCLOC COMERCIAL" recusado) → `can_send_message=LIMITED` (limite de conversas iniciadas pela empresa; templates/campanhas). Corrigir nome de exibicao no Business Manager.
- Canais 2/3: `name_status=NON_EXISTS`, tambem LIMITED.
- Canal 1 (coex do Izael, WABA 985540003931801): token nao acessa mais WABA/phone via Graph ("does not exist / missing permissions") — provavelmente desconectado na Meta, mas segue `is_active=True` no cadastro + phone_routing.

**Why:** registro do que ja foi verificado pra nao repetir a investigacao se a queixa voltar; scripts de diagnostico ficaram so no scratchpad da sessao (nao versionados).
**How to apply:** se a queixa voltar, comecar pelo trend semanal de `wa_contacts.first_seen_at` (created_source=webhook, channel_id=4) e pela contagem de "vim pelo site" por dia; conferir `subscribed_apps` e `health_status` via token do canal (nunca imprimir token). Ver [[campanha-template-varizemed]] pra contexto de envio de templates (LIMITED afeta).
