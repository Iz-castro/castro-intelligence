# Deploy do Cloud Run A (`castro-crm`) — runbook manual passo a passo

> Guia humano pro deploy do CRM principal, pra seguir SEM o agente de IA.
> Projeto: `project-4a851bf9-f475-418c-800` (Oregon) · região `us-west1` · serviço `castro-crm`.
>
> **Regra de ouro:** o tráfego deste serviço é **PINADO por revisão** — todo deploy
> sobe a revisão nova a **0%** e a promoção é manual, **pelo NOME da revisão**.
> O texto que o `gcloud run deploy` imprime no final ("serving 100 percent" e até
> o nome da revisão) é **enganoso** — não confie nele em nenhum passo.

---

## 0. Pré-requisitos da máquina (uma vez)

- `gcloud` logado com conta que acessa o projeto Oregon (`gcloud auth login`).
- `CLOUDSDK_PYTHON` apontando pro Python 3.12 — já setado no escopo User desta
  máquina. Se o gcloud reclamar de versão de Python, rode antes:
  `$env:CLOUDSDK_PYTHON = "C:\Users\izael\AppData\Local\Programs\Python\Python312\python.exe"`
- ⚠️ O `gcloud config` da máquina aponta pro projeto **ANTIGO** de SP
  (`project-26fb9c99-8ee9-4179-aef`) → **`--project` explícito em TODO comando**
  (todos os comandos abaixo já têm).

Abra o PowerShell na raiz do repo e defina as variáveis usadas em tudo abaixo:

```powershell
$P = "project-4a851bf9-f475-418c-800"
$R = "us-west1"
```

---

## 1. Visão geral (o que o deploy faz)

`gcloud run deploy --source` manda a raiz do repo pro Cloud Build, que builda a
imagem com o `Dockerfile` da raiz:

| Estágio | O que faz |
|---|---|
| `node:22-slim` | `npm ci` + `npm run build` do frontend → `/frontend_dist` (typecheck estrito incluso) |
| `python:3.10-slim` | instala `requirements.txt`, **pré-baixa o modelo Whisper pra dentro da imagem** (`HF_HUB_OFFLINE=1` — ver incidente 2026-06-03) e copia o código |

- O upload do source é governado pelo `.gcloudignore` (exclui `.git`, `docs/`, `.venv`...).
- `--source` **PURO preserva** env vars, secrets e scaling da revisão anterior —
  por isso o comando de deploy não leva NENHUMA flag além das obrigatórias.
- **NUNCA** adicionar `--env-vars-file` / `--set-secrets` / flags de scaling (os
  antigos `deploy.ps1`/`deploy.sh` faziam isso, clobberavam a config de prod e
  foram removidos do repo em 2026-08-06).

---

## 2. Gates de validação (rodar ANTES do deploy)

```powershell
# Backend compila
.venv\Scripts\python.exe -m py_compile main.py webhook.py bot_service.py lgpd_bot.py database_firestore.py config.py tenant_service.py channel_service.py

# Simuladores do bot (mockados; exit 0 = ok)
.venv\Scripts\python.exe tools\sim_bot_flow.py
.venv\Scripts\python.exe tools\sim_cx_flow.py
.venv\Scripts\python.exe tools\sim_reception_flow.py

# Frontend (typecheck estrito + build — a imagem builda o dela; isto é só gate)
cd frontend
npm run build
cd ..
```

⚠️ `tools\cx_smoke.py` **não** entra no gate — ele bate no agente Dialogflow CX real.

---

## 3. Deploy (sobe a revisão nova a 0%)

```powershell
gcloud run deploy castro-crm --source C:\Rafael\castro-intelligence --region $R --project $P --quiet
```

- Caminho **ABSOLUTO** no `--source`, nunca `.` — se o shell estiver em
  `frontend\` (ex.: depois do gate acima), o `.` builda a pasta errada e falha.
- Demora vários minutos (npm + pip + modelo Whisper).
- Ao final o gcloud imprime um nome de revisão e "serving 100 percent" —
  **ignore os dois** (2026-07-29: imprimiu `00066-bsm`, mas criou `00067-frb`).

---

## 4. Descobrir o nome REAL da revisão nova

```powershell
gcloud run revisions list --service castro-crm --region $R --project $P --sort-by "~metadata.creationTimestamp" --limit 5
```

A revisão nova é a **primeira da lista** (mais recente por data de criação).
Anote também qual revisão está servindo 100% AGORA — é o seu alvo de rollback.

⚠️ NÃO se guie pelo NÚMERO: o fluxo staging+promote já bagunçou a numeração e a
revisão nova pode ter número MENOR que revisões antigas.

---

## 5. (Recomendado) Canário pela tag `staging`

A revisão nova está de pé, mas sem tráfego. Dá pra testar de verdade pela URL da
tag, sem afetar nenhum usuário:

```powershell
gcloud run services update-traffic castro-crm --region $R --project $P --update-tags staging=<REV_NOVA>
```

Teste em: `https://staging---castro-crm-jdznvidcxq-uw.a.run.app`
(login normal; ⚠️ é a MESMA base de dados de prod — cuidado com ações reais).

---

## 6. Promover pra 100% — POR NOME, nunca `--to-latest`

```powershell
gcloud run services update-traffic castro-crm --region $R --project $P --to-revisions <REV_NOVA>=100
```

E **confira** onde o tráfego ficou de fato:

```powershell
gcloud run services describe castro-crm --region $R --project $P --format "value(status.traffic)"
```

Tem que mostrar `percent: 100` na revisão que você promoveu. (`--to-latest` é
proibido aqui: com a numeração fora de ordem, "latest" pode cair na errada.)

---

## 7. Smoke pós-deploy

```powershell
(Invoke-WebRequest "https://castro-crm-jdznvidcxq-uw.a.run.app/" -UseBasicParsing).StatusCode
(Invoke-WebRequest "https://castro-crm-jdznvidcxq-uw.a.run.app/api/client-config" -UseBasicParsing).Content
```

- Os dois têm que dar **200**; o `client-config` tem que mostrar o `projectId`
  do Oregon (`project-4a851bf9-...`).
- Teste funcional: abrir o CRM no navegador (login + sidebar carregando) e, se
  possível, mensagem de teste no WhatsApp (inbound aparecendo na pool).
- Erros de runtime: Console GCP → Cloud Run → `castro-crm` → aba **Logs**.

---

## 8. Rollback (instantâneo)

```powershell
gcloud run services update-traffic castro-crm --region $R --project $P --to-revisions <REV_ANTERIOR>=100
```

Revisões antigas continuam prontas; a volta é imediata. `<REV_ANTERIOR>` é a que
você anotou no passo 4 (a que servia 100% antes da promoção).

---

## 9. Mudar UMA env var (sem deploy de código)

```powershell
gcloud run services update castro-crm --region $R --project $P --update-env-vars CHAVE=VALOR
```

- `--update-env-vars` mexe SÓ na(s) chave(s) citada(s). **Nunca** `--set-env-vars`
  (substitui TODAS).
- ⚠️ Isso também cria uma revisão NOVA a 0% (tráfego pinado) → repetir os passos
  4 e 6 pra promover.

---

## 10. Pegadinhas — resumo de bolso

| Pegadinha | Regra |
|---|---|
| `gcloud config` aponta pro projeto velho de SP | `--project` explícito em todo comando |
| `--source .` relativo | sempre caminho absoluto da raiz |
| gcloud reclama de Python | `CLOUDSDK_PYTHON` → Python312 (ver passo 0) |
| Saída do deploy mente | revisão real = `revisions list` por data; conferir `status.traffic` após promover |
| `--to-latest` | proibido — numeração fora de ordem cai na revisão errada |
| `WHISPER_MODEL_SIZE` | mudar exige REBUILD da imagem (é `ARG` do Dockerfile); `FEATURE_AUDIO_TRANSCRIPTION=true` só é seguro com o modelo embutido |
| Cloud Run B (`castro-superadmin`) | pipeline SEPARADO — nunca `--source` lá; ver [../DEPLOY_CLOUDRUN_B.md](../DEPLOY_CLOUDRUN_B.md) |
| Desligar Modo Recepção | NÃO precisa de deploy: `PUT pool_mode=legacy` em `system_settings/chat` (ADR 0010) |
| Scaling/env/secrets | não mexer no deploy; pra consultar valores vivos: `gcloud run services describe castro-crm --region $R --project $P` |

---

## 11. Estado de referência (2026-08-06)

- URL prod: `https://castro-crm-jdznvidcxq-uw.a.run.app`
- 100% do tráfego em `castro-crm-00074-zrt` (Modo Recepção, promovida 2026-08-05);
  tag `staging` apontando pra mesma revisão.
- [RUNBOOK_CUTOVER_PROD.md](RUNBOOK_CUTOVER_PROD.md) é STALE (cita SP /
  `southamerica-east1`) — serve só como referência de bootstrap de infra
  (IAM/bucket/secrets).
