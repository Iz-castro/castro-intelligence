---
name: project_oregon_prod_cutover
description: Prod migrou para Oregon — projeto/regiao novos para deploy; gcloud config aponta pro projeto VELHO
metadata: 
  node_type: memory
  type: project
  originSessionId: 35e65cd4-7e08-4763-8199-87d102609080
---

Em 2026-06-16 o usuario confirmou que a prod opera no projeto NOVO (Oregon),
nao mais no antigo de southamerica-east1.

**Alvo de prod atual (usar em todo deploy):**
- Projeto: `project-4a851bf9-f475-418c-800`
- Regiao: `us-west1`
- Serviço Cloud Run: `castro-crm`
- URL: `https://castro-crm-jdznvidcxq-uw.a.run.app` (tambem `https://castro-crm-28179318848.us-west1.run.app`)

**Pegadinha:** `gcloud config get-value project` retorna o projeto ANTIGO
`project-26fb9c99-8ee9-4179-aef` (southamerica-east1, legado). NUNCA confiar
no projeto default do config — passar `--project project-4a851bf9-f475-418c-800
--region us-west1` EXPLICITO em todo comando gcloud (deploy, describe, logs).

Deploy continua via `gcloud run deploy castro-crm --source . --project
project-4a851bf9-f475-418c-800 --region us-west1 --quiet` (ver
[[project_deploy_script_desatualizado]] e [[project_gcloud_python]] para
CLOUDSDK_PYTHON=Python312).

**PEGADINHA CRITICA (confirmada 2026-06-26): deploy puro NAO promove
tráfego.** O serviço esta com o tráfego PINADO explicitamente numa
revisao especifica (com `tag: staging`), nao em `latestRevision:true`
— resultado do workflow de staging tagged (ver
[[project_picker_pin_extraconversations]]). Entao `gcloud run deploy
--source` CRIA a revisao nova mas o tráfego CONTINUA na revisao antiga
(0% pra nova). O output do deploy engana: imprime a revisao ANTIGA como
"serving 100 percent". Os numeros de revisao tambem ficam fora de ordem
(00028 criada DEPOIS de 00029) por causa do workflow.

**INCIDENTE 2026-07-17 (quase-promocao errada):** o output do deploy
imprimiu "revision [castro-crm-00069-cef] has been deployed" mas a
revisao criada pelo deploy era a **castro-crm-00050-tpf** — o nome no
output era a revisao ANTIGA pinada (numero 00050 criado DEPOIS do
00069!). Alem disso `latestReadyRevisionName` logo apos o deploy ainda
apontava pra antiga (a nova nao tinha ficado Ready). REGRAS: (a) NUNCA
confiar no nome de revisao impresso pelo deploy; (b) identificar a
revisao nova por `status.latestCreatedRevisionName` + creationTimestamp
(`gcloud run revisions list --limit 5`), nao por numero nem por
latestReady; (c) em caso de duvida, baixar o zip de
`run.googleapis.com/build-source-location` e conferir o codigo.

**Ordem verdadeira das revisoes = label configurationGeneration (nao o
nome!).** Confirmado 2026-07-17: gen 21..50 monotonico com timestamp;
os NOMES drifteram (gen49=00069-cef, gen50=00050-tpf; ha ate dois
"00037-*"). Causa: dois contadores — config generation (so template,
=50) vs service generation (qualquer mudanca, inclui update-traffic/
tags, =73); o workflow de staging/pinning infla o segundo e os nomes
ora vem de um, ora de outro. Promote NUNCA renomeia revisao. Comando
pra ver a ordem real: revisions list --format json e ler
metadata.labels.'serving.knative.dev/configurationGeneration'.
Proposta (pendente de OK do Rafael): passar `--revision-suffix
d<yyyyMMdd-HHmm>` nos proximos deploys pra nome cronologico legivel.

**Sempre apos o deploy:** (1) `gcloud run services describe castro-crm
... --format "yaml(status.traffic, status.latestReadyRevisionName)"` pra
achar a revisao nova (latestReadyRevisionName) e ver onde esta o tráfego;
(2) promover: `gcloud run services update-traffic castro-crm
--to-revisions <REVISAO_NOVA>=100 --project project-4a851bf9-f475-418c-800
--region us-west1 --quiet` (usar `--to-revisions`, NAO `--to-latest`, pra
preservar o modelo de pinning); (3) re-describe pra confirmar 100% na
nova. O `tag: staging` fica na revisao antiga — mover so se quiser alinhar
a URL de staging.

Rollback de uma revisao ruim: `gcloud run services update-traffic castro-crm
--project project-4a851bf9-f475-418c-800 --region us-west1 --to-revisions
<REVISAO_BOA>=100`.

O CLAUDE.md ainda lista o projeto antigo como prod ("atualizar quando o cutover
completar") — esta desatualizado quanto ao alvo de deploy.

**PEGADINHA ADC (confirmada 2026-06-29): o ADC local aponta pro projeto VELHO.**
`%APPDATA%\gcloud\application_default_credentials.json` tem quota_project =
`project-26fb9c99-...` (antigo). Logo `firestore.Client()` SEM projeto explicito
vai no Firestore ERRADO. `firestore_common.get_firestore_client()` usa
`FIRESTORE_PROJECT_ID` se setado, senao cai no default (=velho). NUNCA rodar
script Firestore local sem `FIRESTORE_PROJECT_ID=project-4a851bf9-f475-418c-800`.

**Como ler/escrever no Firestore Oregon DE FORA do Cloud Run (REST + token gcloud,
que tem acesso Oregon — evita o problema do ADC):**
- Base: `https://firestore.googleapis.com/v1/projects/project-4a851bf9-f475-418c-800/databases/(default)/documents/castro_crm_tenants/hubloc`
- Auth header: `Bearer $(gcloud auth print-access-token)`.
- Prefix Oregon = `castro_crm`; tenant = `hubloc`. Conversas: subcolecao `wa_conversations`
  (doc id = `{channel}__{wa_id}`, ex. `4__55319XXXXXXXX`). Contatos: `wa_contacts`
  (doc id = contact_id). Mensagens: `wa_messages` (filtrar por conversation_id + direction).
- Ler: POST `:runQuery` (structuredQuery com fieldFilter) e `:runAggregationQuery`
  (count). Escrever so um campo: PATCH `...{doc}?updateMask.fieldPaths=campo` (preserva o resto).
- CASO REAL: operador abrir lead de POOL pelo picker -> `/conversation/open`
  AUTO-ATRIBUI o atendimento ao opener (comportamento coex existente, upsert
  auto_assign se a conversa nao tinha dono) -> some de "Novos" e vai pra "Meus".
  Fix cirurgico: PATCH `assigned_to=null`, `assigned_to_uid=""` (+ repor `unread_count`
  = nº de inbound, pq o open marca como lido). Clicar no SIDEBAR de "Novos" (nao
  picker) NAO atribui, so zera o unread (mark-read). dept (setor) e preservado no open.
