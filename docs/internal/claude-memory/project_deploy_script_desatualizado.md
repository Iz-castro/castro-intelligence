---
name: project-deploy-script-desatualizado
description: NAO usar deploy.ps1/deploy.sh para deploy de prod — clobberaria env/secrets/scaling; usar gcloud run deploy --source puro
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c0bbcb0-2d9d-4a43-a772-008691e003aa
---

`deploy.ps1` e `deploy.sh` estao DESATUALIZADOS e perigosos pra deploy
de prod (`castro-crm`). Eles usam `--env-vars-file` (substitui TODAS as
env vars) + `--set-secrets` (substitui todos os secrets) + flags fixas
de scaling. Comparado ao prod real (jun/2026), rodar o script causaria
outro incidente:

- Scaling regrediria: `--max-instances 3` (prod=28), `--concurrency 1`
  (prod=8), `--memory 1Gi` (prod=2Gi), `--cpu 1` (prod=2), perde
  startup-cpu-boost.
- Apagaria env vars que so existem em prod: `FEATURE_MESSAGE_STATUS`,
  `FEATURE_GOOGLE_CHAT`, `META_APP_ID`, `EMBEDDED_SIGNUP_CONFIG_ID`,
  `ATTENDANCE_AUTOCLOSE_HOURS`, `SECRET_ROTATION_TS`,
  `CRON_OIDC_AUDIENCE`, `CRON_OIDC_SERVICE_ACCOUNT`.
- Removeria o secret `META_APP_SECRET` (nao esta no `--set-secrets` do
  script).

**How to apply:** pra deploy de prod, usar `gcloud run deploy castro-crm
--source . --region southamerica-east1 --project project-26fb9c99-8ee9-4179-aef
--quiet` PURO — sem `--env-vars-file`/`--set-env-vars`/`--set-secrets`/
flags de scaling. `--source` puro rebuilda a imagem e PRESERVA env,
secrets e recursos da revisao anterior. Pra mudar 1 env especifica:
`--update-env-vars KEY=VAL` (atualiza so ela). Lembrar do
[[project-gcloud-python]] (CLOUDSDK_PYTHON). Atualizar/consertar os
scripts e' tarefa pendente.

**Gotcha do working directory (jun/2026):** o wd do PowerShell tool PERSISTE
entre comandos. Depois de um `cd ...\frontend; npm run build`, comandos
seguintes que usam `.` como source (`gcloud run deploy --source .` ou
`gcloud builds submit ... .`) apontam pra `frontend/`, que NAO tem Dockerfile.
Sintomas: `--source` cai em Buildpacks e falha com `EACCES: mkdir
'/frontend_dist'`; `builds submit --tag` falha com "Dockerfile required when
specifying --tag". NAO e flakiness do gcloud — e' o source dir errado.

**How to apply:** sempre passar o caminho ABSOLUTO da raiz como source, nunca
`.` (e nunca confiar no wd): `gcloud run deploy castro-crm --source
c:\Rafael\castro-intelligence ...` ou `gcloud builds submit
c:\Rafael\castro-intelligence --tag <AR>:TAG`. Alternativa deterministica
quando quiser separar build de deploy: `gcloud builds submit <raiz> --tag
<AR>/castro-crm:TAG` (forca docker build) e depois `gcloud run deploy
castro-crm --image <esse-tag> --region southamerica-east1` (sem flags de
env/scaling -> preserva config).