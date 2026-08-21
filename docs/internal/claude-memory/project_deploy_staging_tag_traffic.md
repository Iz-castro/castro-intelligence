---
name: project_deploy_staging_tag_traffic
description: "Deploy direto na prod sobe revisão a 0% (tráfego fixado por tag staging); promover por NOME, nunca --to-latest"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4552cda5-bcd0-4b27-ad99-ea050ef24ef9
  modified: 2026-07-29T17:37:55.943Z
---

O serviço prod `castro-crm` (Oregon) usa **tag `staging`** (ex.: `00095-juy` tagueada "staging") e **tráfego FIXADO por revisão** (traffic assignado por `revisionName` explícito, não "serve latest").

Consequências ao deploiar direto pra prod com `gcloud run deploy --source`:
- A revisão nova sobe **a 0%** — serviço com tráfego fixado NÃO migra automático. A linha "revision [X] has been deployed and is serving 100 percent" do gcloud se refere à revisão VELHA ainda fixada, não à nova → **enganosa**.
- O fluxo tag-staging + promote **bagunça a numeração**: a revisão nova pode receber número MENOR que revisões mais antigas (caso real 2026-07-24: `00064-2f9` criada DEPOIS da `00096-ray`). Logo `latestReadyRevisionName` e **`--to-latest` apontam pra revisão ERRADA** (a de número maior, mais velha).

**Sempre, depois de deploiar na prod, promover por NOME e conferir:**
```
gcloud run services update-traffic castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --to-revisions <REV_NOVA>=100
gcloud run services describe castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --format="json(status.traffic)"
```
Não confiar na mensagem "serving 100 percent" do deploy; não usar `--to-latest`. A tag `staging` sobrevive ao `--to-revisions` (é gerida à parte). Rafael já tinha visto isso antes — é comportamento conhecido do serviço, não bug do deploy desta vez. Relacionado: [[project_oregon_prod_cutover]], [[project_deploy_script_desatualizado]].

**PIOR (caso real 2026-07-29): o NOME de revisão impresso pelo deploy também pode estar ERRADO.** O `gcloud run deploy` imprimiu "revision [castro-crm-00066-bsm] has been deployed" mas a revisão realmente criada foi `castro-crm-00067-frb` (a 00066-bsm era de um deploy anterior do mesmo dia, 15:45Z, ~2h antes). Promovi a errada por ~2 min até o Izael notar no console. **Descobrir o nome da revisão nova SEMPRE via:**
```
gcloud run revisions list --service castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --sort-by "~metadata.creationTimestamp" --limit 3
```
(a mais recente por creationTimestamp = a do deploy). Smoke que prova o frontend novo no ar: o HTML de `GET /` referencia o hash do bundle do build local (ex.: `index-PtZygPff.js`).
