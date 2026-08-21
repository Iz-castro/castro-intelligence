---
name: project-campanha-template-varizemed
description: "Campanha de aviso de troca de numero da Varizemed — scripts prontos, teste enviado 2026-08-08, lista grande de 4.592 pendente de criterios do Rafael"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8bbbed4e-abd8-4f9a-8861-cdeb72f547c3
  modified: 2026-08-08T20:33:26.521Z
---

Campanha para avisar os pacientes da Varizemed que o numero de atendimento mudou,
disparando o template **`aviso_novo_numero_val`** (UTILITY, pt_BR, APPROVED, **zero
variaveis** — so BODY+FOOTER, entao o payload vai SEM `components`; mandar components
da erro 132000).

**Infra (verificada em prod 2026-08-07):** canal standard **7** do tenant `varizemed`,
`phone_number_id=1257632794095120`, WABA `28119031584452691`, display +55 31 9979-4546,
quality GREEN, throughput STANDARD, `health_status.can_send_message=AVAILABLE`.

**Scripts (versionados em `51ff640`, 2026-08-21):**
- `scripts/wa_phone_norm.py` — normalizacao de numero BR + leitura tolerante de CSV.
  Autotestes embutidos (`python scripts/wa_phone_norm.py`).
- `scripts/send_template_bulk.py` — o disparo. Default e DRY-RUN; so envia com `--yes`.
  **Zero writes no Firestore** de proposito (so LE o doc do canal): pre-criar contato
  ou conversation quebraria o bot (`bot_completed`) ou entupiria a caixa da recepcao.
  Quem responde entra pelo webhook normal.

**Decisoes que custaram caro e nao devem ser reabertas:**
- **9o digito:** o script ADICIONA o 9 (wa_id de 13 digitos), alinhado com
  `database_firestore.normalize_br_phone`. A Meta responde com o canonico DELA, que no
  Brasil vem **sem** o 9 — isso e esperado e converge, porque `webhook.py:540` aplica
  `normalize_br_phone` no inbound. Confirmado no envio real de 2026-08-08.
- **Sinal do "+":** quando o valor cru comeca com "+", os digitos ja sao E.164 completos.
  E PROIBIDO aplicar o palpite "10/11 digitos = BR sem DDI" — um "+1 415 555 0123"
  viraria "DDD 14" e o template sairia para um celular brasileiro aleatorio.
- **Nome do relatorio NAO leva data.** Bug critico achado em revisao adversarial: com
  data no nome, a virada do dia gerava arquivo novo, a retomada devolvia vazio em
  silencio e o fatiamento diario reenviava os MESMOS primeiros N todo dia. Corrigido:
  sufixo estavel `{tenant}_ch{canal}` + glob dos irmaos `<template>_*.csv` com regra
  **terminal vence** (um `sent` nunca e rebaixado por `failed_retryable`).
- **Limite da Meta e por BUSINESS PORTFOLIO** (mudou 07/10/2025), contando
  destinatarios UNICOS numa janela movel de 24h: 250 -> 2.000 -> 10.000 -> 100.000.
  **Nao existe codigo de erro para tier estourado** — o script tem que contar sozinho,
  por isso `--max-sends` default 250. Tier vigente da Varizemed ainda NAO foi confirmado.
- **Template pacing vale para UTILITY.** Se `messages[0].message_status` vier
  `held_for_quality_assessment`, PARE — o script aborta sozinho.

**Estado em 2026-08-08:**
- Teste real enviado e recebido OK nos 2 numeros do Rafael (relatorio em
  `scripts/_exports/campanhas/aviso_novo_numero_val_teste.csv`).
- Lista canario de **21 destinatarios** montada em
  `scripts/_exports/campanhas/canario_20260807.csv` (uniao dedupada dos 3 CSVs de
  recorte). NAO enviada — Rafael adiou para segunda.
- Lista grande: 4.670 linhas -> **4.604 unicos** (34 pessoas apareciam em 12 e 13
  digitos; sem dedupe receberiam 2x). Rafael vai revisar/classificar e mandar um CSV novo.
- **Revisao adversarial INCOMPLETA** (estourou limite de sessao): a lente de correcao
  fechou e achou o bug critico acima; as lentes de **seguranca/LGPD** e **conformidade
  Meta** rodaram mas os verificadores morreram; a de **usabilidade operacional** nao
  rodou. Terminar antes do disparo dos 4.592.

**LGPD:** os CSVs tem telefone de paciente. `docs/*.csv` e `*.xlsx` foram adicionados ao
`.gitignore` (o arquivo tinha sido largado em `docs/`, que e versionado). Relatorios e
listas vivem em `scripts/_exports/campanhas/`.

Bug separado aberto no mesmo dia: [[bug-val-resposta-duplicada]].
