---
name: project-deploy-script-desatualizado
description: deploy.ps1/deploy.sh REMOVIDOS do repo (2026-08-06) — clobberavam env/secrets/scaling de prod; deploy = gcloud run deploy --source puro (Oregon)
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c0bbcb0-2d9d-4a43-a772-008691e003aa
  modified: 2026-08-06T17:57:30.921Z
---

`deploy.ps1` e `deploy.sh` foram **REMOVIDOS do repo em 2026-08-06**
(pedido do Rafael; recuperaveis no historico do git, commit anterior a
remocao). Motivo: estavam desatualizados e perigosos pra prod
(`castro-crm`) — usavam `--env-vars-file` (substitui TODAS as env vars)
+ `--set-secrets` (substitui todos os secrets) + flags fixas de scaling.
Rodar em prod causaria incidente (scaling regredia de 28/8/2Gi/2cpu pra
3/1/1Gi/1cpu, apagava `FEATURE_GOOGLE_CHAT`, `META_APP_ID`,
`EMBEDDED_SIGNUP_CONFIG_ID`, `CRON_OIDC_*`, secret `META_APP_SECRET`...).
Se alguem recuperar do historico, NAO usar em prod. O conteudo unico
deles (bootstrap de infra: service account, IAM bindings, bucket com
PAP, secrets) esta documentado em `docs/deploy/RUNBOOK_CUTOVER_PROD.md`
e `docs/deploy/MIGRACAO_GCP_OREGON_CHECKLIST.md`.

**How to apply:** deploy de prod (Oregon) = `gcloud run deploy castro-crm
--source C:\Rafael\castro-intelligence --region us-west1 --project
project-4a851bf9-f475-418c-800 --quiet` PURO — sem
`--env-vars-file`/`--set-env-vars`/`--set-secrets`/flags de scaling.
`--source` puro rebuilda a imagem e PRESERVA env, secrets e recursos da
revisao anterior. Pra mudar 1 env especifica: `--update-env-vars KEY=VAL`.
Depois PROMOVER POR NOME ([[project-deploy-staging-tag-traffic]]) e
lembrar do [[project-gcloud-python]] (CLOUDSDK_PYTHON).

**Gotcha do working directory (jun/2026):** o wd do PowerShell tool PERSISTE
entre comandos. Depois de um `cd ...\frontend; npm run build`, comandos
seguintes que usam `.` como source (`gcloud run deploy --source .` ou
`gcloud builds submit ... .`) apontam pra `frontend/`, que NAO tem Dockerfile.
Sintomas: `--source` cai em Buildpacks e falha com `EACCES: mkdir
'/frontend_dist'`; `builds submit --tag` falha com "Dockerfile required when
specifying --tag". NAO e flakiness do gcloud — e' o source dir errado.

**How to apply:** sempre passar o caminho ABSOLUTO da raiz como source, nunca
`.` (e nunca confiar no wd). Alternativa deterministica quando quiser separar
build de deploy: `gcloud builds submit <raiz> --tag <AR>/castro-crm:TAG`
(forca docker build) e depois `gcloud run deploy castro-crm --image
<esse-tag> --region us-west1` (sem flags de env/scaling -> preserva config).
