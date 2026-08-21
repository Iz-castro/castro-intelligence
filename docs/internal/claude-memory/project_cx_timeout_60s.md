---
name: project-cx-timeout-60s
description: "Timeout do DetectIntent (CX) 15s->60s em 2026-08-18; em 2026-08-20 o PO REVERTEU a política de reenvio: read-timeout da chamada PRINCIPAL agora reenvia 1x com teto inteiro (CX_READ_TIMEOUT_RETRY, commit 3c05457, EM PROD rev 00085-vcr); knobs CX_DETECT_TIMEOUT_SECONDS + CX_READ_TIMEOUT_RETRY"
metadata: 
  node_type: memory
  type: project
  originSessionId: d5b92a72-2397-44da-a9f4-eb3e65f92f70
  modified: 2026-08-20T19:36:40.428Z
---

**Pedido do Rafael (2026-08-18):** "aumentar o tempo de espera pra 1 minuto". Gatilho: lead da
varizemed (contato 264) aceitou a LGPD e recebeu "instabilidade momentanea" porque o DetectIntent
estourou 15s duas vezes. Dados 11-18/08: ~7% dos turnos >15s, zero 5xx — lentidao genuina do
agente generativo.

**EM PROD desde 2026-08-18 (rev `00083-rz8`, commit `b503870`):** teto 60s por TURNO
(`CX_DETECT_TIMEOUT_SECONDS`, parse defensivo), connect=10s, 5xx/rede retry 1x, orcamento por
turno pros reenvios de frase de erro.

**MUDANCA 2026-08-20 (PO reverteu o "sem reenvio" — EM PROD rev `00085-vcr`, promovida por
nome ~19:40Z, commit `3c05457` pushado; gcloud imprimiu de novo a rev ANTERIOR 00084-h4w
como "serving 100%" — mentira de sempre):**
incidente contato 308 varizemed: aceite LGPD 14:02 BRT, turno do agente >109s
(DEADLINE_EXCEEDED no proprio Dialogflow: "Resend the request with a higher deadline"; 78s so
ate o 1o tool-call do `val-memory`), lead ficou no vacuo. Rafael pediu retry ANTES do fallback.
Implementado: read-timeout da chamada PRINCIPAL (`timeout_s=None`) reenvia a MESMA mensagem 1x
com o teto INTEIRO de novo — pior caso ~2x60s segurando o webhook (Cloud Run timeout=300s ok,
`was_dup` absorve reentregas da Meta, dedupe funciona mid-flight, provado 20/08). Reenvio por
frase de erro (timeout_s explicito, sobra de orcamento) segue SEM read-retry. Kill-switch sem
deploy: `CX_READ_TIMEOUT_RETRY=false` (default true). Risco assumido: se a 1a chamada completar
no agente apos nosso timeout, o reenvio duplica o turno na sessao. Testes: secao u do
`tools/sim_cx_flow.py` (172 checks: a/a2/a3 + g2 kill-switch). CLAUDE.md/.env.example/config.py
atualizados. Evidencia do incidente: `docs/CX_TIMEOUT_LGPD_2026-08-20_DEV_IA.md` (doc pro dev
de IA; env prod da Val = `05267e69`).

**How to apply:** teto ajustavel por env (`gcloud run services update --update-env-vars`,
promover por NOME). Qualquer coisa que segure o webhook mais tempo tem que respeitar o guard
`was_dup` (texto E audio) — Meta reentrega ~23s sem ACK. Gap conhecido: `user_first_input` so
vai ao CX no turno do aceite; se esse turno falha, o proximo turno NAO reenvia a pergunta
original (follow-up oferecido, nao pedido). Follow-up antigo aberto: `transcribe_audio_bytes`
sincrona bloqueia o event loop.
