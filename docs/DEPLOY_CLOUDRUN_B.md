# Deploy do Cloud Run B (`castro-superadmin`) — como a imagem é criada e subida

> Referência reproduzível do pipeline de build/deploy do serviço super-admin.
> Serviço SEPARADO do CRM (Cloud Run A), no mesmo projeto GCP e mesmo git.
> Projeto: `project-4a851bf9-f475-418c-800` · região `us-west1`.

> **Status em 2026-08-21:** pipeline **inalterado** desde 2026-07-31 (rev `00004-c8d`,
> commit `c2d4f0e`) — o que está abaixo continua sendo o jeito de buildar e subir o B.
> A proteção de borda do serviço (IAP+LB vs Cloudflare Access) segue **em aberto**:
> `docs/HANDOFF_IAP_E_TENANT2.md`.

---

## Visão geral (por que assim)

O B reusa o **mesmo repositório** (fonte única do `bootstrap_tenant` — sem drift),
mas roda como **serviço/imagem/SA separados**. A separação de segurança é de *runtime*
(serviço + service account + auth próprios), não de repo.

Três artefatos versionados fazem o build:

| Arquivo | Papel |
|---|---|
| `Dockerfile.superadmin` | imagem MÍNIMA: copia só os módulos que o B usa + a página; NÃO leva `main.py`/`webhook`/`media`/frontend/whisper |
| `requirements-superadmin.txt` | deps enxutas (sem `faster-whisper`/`pyngrok`) |
| `cloudbuild-superadmin.yaml` | build com o Dockerfile próprio (o `gcloud run deploy --source` usaria o Dockerfile do A) |

---

## 1. Como o conjunto mínimo de arquivos foi definido (fecho de imports)

Pra não copiar código a mais (nem a menos) na imagem, o conjunto de módulos foi
**computado**, não adivinhado: importa-se o `superadmin_main` (+ o import lazy do
`tenant_bootstrap`) e inspeciona-se quais `.py` LOCAIS o Python carregou.

```python
import os, sys
before = set(sys.modules)
import superadmin_main
import tenant_bootstrap            # o import lazy do endpoint de criar-tenant
here = os.path.dirname(os.path.abspath("superadmin_main.py"))
local = sorted({
    os.path.basename(m.__file__)
    for name, m in sys.modules.items()
    if getattr(m, "__file__", None)
    and m.__file__.startswith(here) and "site-packages" not in m.__file__ and ".venv" not in m.__file__
})
print(local)
```

Resultado (11 módulos) — é exatamente o que o `Dockerfile.superadmin` copia:
`config.py, firebase_admin_client.py, firestore_common.py, super_admin.py,
tenant_service.py, tenant_bootstrap.py, database_firestore.py, rbac.py,
bootstrap_data.py, pii_redaction.py, superadmin_main.py` + `superadmin_web/`.

Refazer esse passo se o `superadmin_main` passar a importar algo novo.

---

## 2. `Dockerfile.superadmin` (o que entra na imagem)

- Base `python:3.10-slim` (sem Node, sem ffmpeg, sem modelo Whisper).
- `apt-get` só `gcc libffi-dev` (build de wheels).
- `pip install -r requirements-superadmin.txt`.
- `COPY` **explícito** dos 11 módulos + `superadmin_web/` (nada além).
- `CMD ["uvicorn", "superadmin_main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]`.

> Detalhe de segurança: o que **roda** no container é só o que o `COPY` traz. O build
> context (`--source .`/`gcloud builds submit .`) sobe o repo temporariamente (governado
> pelo `.gcloudignore`, que exclui `.git`/`docs`/`.venv`), mas isso não fica na imagem.

---

## 3. Build da imagem (Cloud Build)

O `gcloud run deploy --source` usaria o `Dockerfile` da RAIZ (que é o do A). Para usar o
`Dockerfile.superadmin`, o build vai por um `cloudbuild.yaml` (`docker build -f ... && push`):

```bash
P=project-4a851bf9-f475-418c-800
IMG=us-west1-docker.pkg.dev/$P/cloud-run-source-deploy/castro-superadmin:latest

gcloud builds submit \
  --config cloudbuild-superadmin.yaml \
  --substitutions _IMAGE=$IMG \
  --project $P .
```

(Empurra a imagem pro Artifact Registry `cloud-run-source-deploy`, que já existe dos
deploys do A. ~1 min.)

---

## 4. Service account dedicada (uma vez)

```bash
P=project-4a851bf9-f475-418c-800
SA=castro-superadmin-sa

gcloud iam service-accounts create $SA --project $P \
  --display-name "Castro Superadmin (Cloud Run B)"

# só o necessário pro bootstrap_tenant:
gcloud projects add-iam-policy-binding $P \
  --member "serviceAccount:$SA@$P.iam.gserviceaccount.com" \
  --role roles/datastore.user --condition=None       # ler/escrever Firestore
gcloud projects add-iam-policy-binding $P \
  --member "serviceAccount:$SA@$P.iam.gserviceaccount.com" \
  --role roles/firebaseauth.admin --condition=None    # criar usuário + setar claims
```

---

## 5. Deploy no Cloud Run

```bash
P=project-4a851bf9-f475-418c-800
IMG=us-west1-docker.pkg.dev/$P/cloud-run-source-deploy/castro-superadmin:latest
SA=castro-superadmin-sa@$P.iam.gserviceaccount.com

gcloud run deploy castro-superadmin \
  --image "$IMG" --region us-west1 --project $P \
  --service-account "$SA" \
  --allow-unauthenticated \
  --set-env-vars "FIRESTORE_PROJECT_ID=$P,FIRESTORE_COLLECTION_PREFIX=castro_crm,FIREBASE_WEB_API_KEY=<web_api_key>,FIREBASE_WEB_AUTH_DOMAIN=$P.firebaseapp.com,FIREBASE_WEB_APP_ID=<web_app_id>,FIREBASE_WEB_MESSAGING_SENDER_ID=<sender_id>" \
  --min-instances 0 --max-instances 3 --memory 512Mi --quiet
```

Notas:
- **Sem** `SUPERADMIN_REQUIRE_MFA` no deploy → o código força `_REQUIRE_MFA=true` em
  Cloud Run (guarda-dura). O env só desliga MFA em run LOCAL.
- `--allow-unauthenticated`: a auth é feita no APP (`require_super_admin`), não na infra.
  (Endurecer com IAP/ingress é o próximo passo — ver `docs/HANDOFF_IAP_E_TENANT2.md`.)
- Os valores `FIREBASE_WEB_*` são os mesmos do serviço A (copiar do
  `gcloud run services describe castro-crm ...`). A `apiKey` web NÃO é segredo.

---

## 6. Domínio autorizado no Firebase Auth (senão login dá `auth/unauthorized-domain`)

A URL do B precisa estar nos "authorized domains" do Firebase Auth. Feito via API do
Identity Platform (append, não replace):

```bash
P=project-4a851bf9-f475-418c-800; TOK=$(gcloud auth print-access-token)
BASE=https://identitytoolkit.googleapis.com/admin/v2/projects/$P/config
# GET authorizedDomains, adiciona a URL do B, PATCH com updateMask=authorizedDomains
# (header obrigatório: x-goog-user-project: $P)
```

(No console: Authentication → Settings → Authorized domains.)

---

## 7. Smoke pós-deploy

```bash
URL=https://castro-superadmin-28179318848.us-west1.run.app
curl -s -o /dev/null -w "%{http_code}\n" $URL/                       # 200 (página)
curl -s -o /dev/null -w "%{http_code}\n" $URL/api/superadmin/config  # 200
curl -s -o /dev/null -w "%{http_code}\n" $URL/api/superadmin/whoami  # 401 (sem token)
curl -s -D - -o /dev/null $URL/ | grep -i "content-security-policy"  # headers de segurança
```

---

## 8. Rebuild + redeploy (o ciclo normal ao mudar código)

```bash
P=project-4a851bf9-f475-418c-800
IMG=us-west1-docker.pkg.dev/$P/cloud-run-source-deploy/castro-superadmin:latest
SA=castro-superadmin-sa@$P.iam.gserviceaccount.com

# 1) valida local
.venv/Scripts/python.exe -m py_compile superadmin_main.py
.venv/Scripts/python.exe <test_superadmin.py>        # matriz de teste (scratchpad)

# 2) build
gcloud builds submit --config cloudbuild-superadmin.yaml --substitutions _IMAGE=$IMG --project $P .

# 3) deploy (mesma env/SA; --image aponta pra :latest recém-buildada)
gcloud run deploy castro-superadmin --image "$IMG" --region us-west1 --project $P --service-account "$SA" --quiet
```

Rollback: `gcloud run services update-traffic castro-superadmin --region us-west1 --to-revisions <rev-anterior>=100`.

---

## 9. Histórico
- Build inicial + deploy (rev `00001-4f4`) 2026-07-11.
- Rebuild + redeploy pós-revisão adversarial (rev `00002-7pm`) 2026-07-12.
- Editor de tenant (PATCH `/api/superadmin/tenants/{tid}` + UI) e `enterprise_ai`
  fora do select de criação (rev `00004-c8d`) 2026-07-31, commit `c2d4f0e`.
  Smoke ok (200/200/401 + PATCH sem token 401 + CSP). Obs.: o B serve `latest`
  (tráfego NÃO pinado — diferente do A).
