---
name: project-gcloud-python
description: Deploys gcloud falham com Python 3.8; precisam de CLOUDSDK_PYTHON apontando para Python312
metadata: 
  node_type: memory
  type: project
  originSessionId: dab2543b-9e4a-40cf-88c3-3d467d17781b
---

`gcloud run deploy` (deploy do castro-crm no Cloud Run) falha com
"gcloud failed to load. You are running gcloud with Python 3.8, which is
no longer supported" quando `CLOUDSDK_PYTHON` nao esta setado — o gcloud
acaba pegando o `Python38` do PATH em vez do `Python312`.

**Fix aplicado (2026-06-03):** `CLOUDSDK_PYTHON` gravado permanentemente
no escopo User apontando para
`C:\Users\izael\AppData\Local\Programs\Python\Python312\python.exe`.

**How to apply:** se um deploy voltar a falhar com esse erro (ex.: shell
que nao herdou a env var, ou o Bash tool em vez do PowerShell), prefixar
o comando com `$env:CLOUDSDK_PYTHON = "C:\Users\izael\AppData\Local\Programs\Python\Python312\python.exe";`
antes do `gcloud run deploy`. Pythons instalados: 3.12 (default) e 3.8.
