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
# Rode este comando dentro da pasta do projeto:
# C:\Projetos\Hubloc\castro-intelligence
gcloud run deploy castro-crm \
  --source . \
  --region southamerica-east1 \
  --project project-26fb9c99-8ee9-4179-aef
```

Isso faz build do Dockerfile no Cloud Build e deploy automatico.

Se voce estiver um nivel acima (`C:\Projetos\Hubloc`), use:

```powershell
gcloud run deploy castro-crm `
  --source .\castro-intelligence `
  --region southamerica-east1 `
  --project project-26fb9c99-8ee9-4179-aef
```

### Deploy de uma imagem ja construida

```bash
# Build
gcloud builds submit --tag gcr.io/project-26fb9c99-8ee9-4179-aef/castro-crm

# Deploy
gcloud run deploy castro-crm \
  --image gcr.io/project-26fb9c99-8ee9-4179-aef/castro-crm \
  --region southamerica-east1
```

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
