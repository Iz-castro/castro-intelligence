# Deploy GCP — Comandos rapidos

Servico: `castro-crm`
Projeto: `project-26fb9c99-8ee9-4179-aef`
Regiao: `southamerica-east1`

---

## Adicionar uma env nova (sem alterar as existentes)

```bash
gcloud run services update castro-crm \
  --region southamerica-east1 \
  --update-env-vars "NOVA_VARIAVEL=valor"
```

Varias de uma vez:

```bash
gcloud run services update castro-crm \
  --region southamerica-east1 \
  --update-env-vars "VAR1=valor1,VAR2=valor2"
```

---

## Atualizar uma env existente

Mesmo comando — `--update-env-vars` sobrescreve se ja existir:

```bash
gcloud run services update castro-crm \
  --region southamerica-east1 \
 
```

---

## Remover uma env

```bash
gcloud run services update castro-crm \
  --region southamerica-east1 \
  --remove-env-vars "VARIAVEL_PARA_REMOVER"
```

---

## Ver envs atuais

```bash
gcloud run services describe castro-crm \
  --region southamerica-east1 \
  --format="yaml(spec.template.spec.containers[0].env)"
```

---

## Deploy (build + deploy do codigo)

### Via script completo (recomendado para primeiro deploy ou mudancas de infra)

```powershell
.\deploy.ps1
```

### Deploy rapido (apenas codigo, sem alterar infra/secrets)

```bash
gcloud run deploy castro-crm \
  --source . \
  --region southamerica-east1 \
  --project project-26fb9c99-8ee9-4179-aef
```

```ps
gcloud run deploy castro-crm `
  --source . `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef
```

Isso faz build do Dockerfile no Cloud Build e deploy automatico.

### Deploy de uma imagem ja construida

```bash
# Build
gcloud builds submit --tag gcr.io/project-26fb9c99-8ee9-4179-aef/castro-crm

# Deploy
gcloud run deploy castro-crm \
  --image gcr.io/project-26fb9c99-8ee9-4179-aef/castro-crm \
  --region southamerica-east1
```

### Build local com Docker e deploy por imagem

Use este fluxo quando quiser buildar no seu computador e mandar a imagem pronta para o Cloud Run. Em geral, isso deixa o deploy mais rapido e mais previsivel do que `--source .`, porque o Cloud Run recebe uma imagem ja publicada.

#### 1. Autenticar o Docker no Artifact Registry

```powershell
gcloud auth configure-docker southamerica-east1-docker.pkg.dev
```

#### 2. Buildar a imagem localmente

```powershell
docker build -t southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm .
```

Opcionalmente, use uma tag de versao ou data:

```powershell
docker build -t southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm:2026-03-27-1 .
```

#### 3. Enviar a imagem para o registry

```powershell
docker push southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm
```

Ou, com tag versionada:

```powershell
docker push southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm:2026-03-27-1
```

#### 4. Fazer o deploy da imagem pronta

```powershell
gcloud run deploy castro-crm `
  --image southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef
```

Ou, com tag versionada:

```powershell
gcloud run deploy castro-crm `
  --image southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm:2026-03-27-1 `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef
```

### Diferenca entre os dois fluxos

- `gcloud run deploy --source .`
  - mais simples
  - o Google faz o build do Dockerfile no Cloud Build
  - bom para deploy rapido sem pensar em tags

- `docker build` + `docker push` + `gcloud run deploy --image`
  - voce controla a imagem que esta indo para producao
  - permite versionar por tag
  - costuma deixar o deploy mais rapido quando a imagem ja foi buildada e enviada
  - melhor para repetibilidade e rollback por tag

### Observacao importante

O comando abaixo ainda faz o build **na nuvem**, nao no seu computador:

```powershell
gcloud builds submit --tag southamerica-east1-docker.pkg.dev/project-26fb9c99-8ee9-4179-aef/cloud-run-source-deploy/castro-crm .
```

Ele e util quando voce quer publicar uma imagem primeiro e depois fazer `deploy --image`, mas o processamento continua no Cloud Build.

---

## Verificar status do servico

```bash
# URL do servico
gcloud run services describe castro-crm \
  --region southamerica-east1 \
  --format="value(status.url)"

# Logs em tempo real
gcloud run services logs tail castro-crm --region southamerica-east1

# Ultimas revisoes
gcloud run revisions list --service castro-crm --region southamerica-east1
```

---

## Rollback (voltar para revisao anterior)

```bash
# Listar revisoes
gcloud run revisions list --service castro-crm --region southamerica-east1

# Redirecionar trafego para revisao anterior
gcloud run services update-traffic castro-crm \
  --region southamerica-east1 \
  --to-revisions NOME_DA_REVISAO=100
```
