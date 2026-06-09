---
name: project-whisper-cold-start-outage
description: FEATURE_AUDIO_TRANSCRIPTION=true derruba prod (cold-start baixa modelo Whisper do HF e estoura startup probe) — religar so com modelo embutido na imagem
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c0bbcb0-2d9d-4a43-a772-008691e003aa
---

Incidente em 2026-06-03 (~16:00 UTC): prod `castro-crm` voltou enxurrada
de 500/503/429, concentrados no `/webhook`. NAO era bug no handler.

**Causa raiz:** `FEATURE_AUDIO_TRANSCRIPTION=true` (ligado no deploy de
hoje, rev `castro-crm-00128`). [main.py:464](main.py#L464) chama
`init_speech_client()` DENTRO do startup event do FastAPI, que faz
`WhisperModel("base")` em [transcription_service.py:54](transcription_service.py#L54).
O modelo `Systran/faster-whisper-base` NAO esta embutido na imagem
(Dockerfile nao pre-baixa), entao toda instancia em cold-start baixa do
HuggingFace Hub sem `HF_TOKEN` (lento + rate-limited). O download bloqueia
o bind na porta 8080 -> startup TCP probe estoura (`DEADLINE_EXCEEDED`) ->
"instance was not started". Com `minScale=0` e pico no webhook, Cloud Run
nao sobe instancia saudavel -> "no available instance" (500/503) + 429.
A Meta re-tenta webhooks com erro -> realimenta o loop.

**Mitigacao (rev 00129, ~16:11 UTC):** desligou a flag pra estancar.

**Fix definitivo RESOLVIDO no mesmo dia (commit `1b71ef0`, rev `00131-4wb`):**
Dockerfile agora pre-baixa o modelo no docker build
(`ARG WHISPER_MODEL_SIZE=base`, `ENV HF_HOME=/opt/hf-cache`,
`RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"`)
e roda runtime com `ENV HF_HUB_OFFLINE=1` (nunca toca rede HF). Deploy
feito com `gcloud run deploy --source` PURO (sem flags) p/ preservar
env/secrets/scaling — NAO usar `deploy.ps1`/`deploy.sh` (ver
[[project-deploy-script-desatualizado]]). Flag religada
(`FEATURE_AUDIO_TRANSCRIPTION=true`); log confirma "Faster Whisper
carregado modelo=base" + probe na 1a tentativa + zero huggingface.co.

**Se religar com outro WHISPER_MODEL_SIZE:** exige rebuild (HF_HUB_OFFLINE=1
faz o load falhar gracioso se o size nao estiver embutido). Config Cloud
Run: maxScale=28, containerConcurrency=8, memory=2Gi, timeout=300.
