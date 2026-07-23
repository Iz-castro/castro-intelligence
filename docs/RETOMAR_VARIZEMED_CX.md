# Retomar — Integração CX Varizemed (estado em 2026-07-14)

> Doc de retomada. Autossuficiente com `docs/PLANO_TENANT_TESTE_VARIZEMED_CX.md`
> (contrato completo das 2 trilhas). Sem valores de secret aqui.

## Onde paramos (uma frase)

Motor de bot Dialogflow CX por tenant **codado, revisado, commitado e VALIDADO em
staging**; achamos e corrigimos 1 bug no staging (handoff por texto); falta
**re-testar o handoff no staging** (build do fix rodando), depois **promover pra
prod + criar o tenant real + embed do número**.

## Estado dos ambientes

- **develop:** todo o código no repo. Último commit relevante: `3c31084`
  (fix handoff por texto). Antes: `47bc313`, `e80a039`, `e6e2ba0`, `adae9a4`.
- **Prod (`castro-crm`, us-west1, projeto `project-4a851bf9-f475-418c-800`):**
  INTACTA, servindo revisão `castro-crm-00047-sin` (Hubloc), código ANTIGO.
- **Staging:** revisão com tag `staging` + `--no-traffic` + prefixo
  `castro_crm_staging`. URL `https://staging---castro-crm-jdznvidcxq-uw.a.run.app`.
  **Build do fix rodando** ao pausar: Cloud Build id `f6dff730-11b1-42f3-b6fe-6ad324793091`
  (região us-west1). Roda server-side, completa sozinho.
- **Agente CX (Dev IA):** projeto `castro-ia`, location **us-central1** (NÃO global),
  agent `5fa69ea1-bc68-445b-9d20-d72265aaaf36`, pt-br. 2 Cloud Functions
  (`varizemed-router`, `val-memory`) no ar em us-west1, autenticadas. Banco seed OK.
  IAM: `castro-crm-run@project-4a851bf9-...` tem `roles/dialogflow.client` no castro-ia.

## O que a validação em staging PROVOU (2026-07-14)

Via webhook sintético assinado no tenant fake `varizemed-cxtest` (prefixo staging):
- Dispatcher roteia pro caminho CX (não builtin).
- Gate LGPD usa o **aviso da Varizemed** (não Hubloc).
- Consentimento grava **`lgpd_policy_version=varizemed-2026-07`** (não hubloc) — fix ALTA OK.
- **DetectIntent roda de verdade** do serviço deployado (Val respondeu com conteúdo real).
- **BUG encontrado + corrigido:** o agente FALOU a transferência mas `handoff_request`
  veio `False` (logs: `handoff=False`) → contato não entrava na fila. Fix `3c31084`:
  detecta handoff por parâmetro **OU** texto (`_cx_is_handoff` + `_DEFAULT_HANDOFF_TEXT_HINTS`
  em bot_service.py; sobrescrevível por `settings.ai.handoff_text_hints`). Sim 47/47.

## PRÓXIMO PASSO IMEDIATO — re-testar handoff no staging

1. Confirmar o build: `gcloud builds describe f6dff730-11b1-42f3-b6fe-6ad324793091
   --project project-4a851bf9-f475-418c-800 --region us-west1 --format="value(status)"`
   (esperar `SUCCESS`) e a revisão nova com tag `staging` servindo.
2. Re-mandar o handoff com **msg_id NOVO** (o guard was_dup bloqueia repetido):
   ```
   cd c:/Rafael/castro-intelligence
   export WA_APP_SECRET=$(gcloud secrets versions access latest --secret=castro-crm-whatsapp-app-secret --project=project-4a851bf9-f475-418c-800)
   .venv/Scripts/python.exe "<SCRATCHPAD>/webhook_stg.py" "quero falar com um atendente" 004
   ```
3. Observar (esperado agora: `bot_completed=True`, `department_id=1`, system message):
   ```
   FIRESTORE_PROJECT_ID=project-4a851bf9-f475-418c-800 FIRESTORE_COLLECTION_PREFIX=castro_crm_staging .venv/Scripts/python.exe "<SCRATCHPAD>/observe_stg.py"
   ```
   `<SCRATCHPAD>` = `C:/Users/izael/AppData/Local/Temp/claude/c--Rafael-castro-intelligence/535f93e8-1725-4ae6-827a-2268b798f3c3/scratchpad`
   (scripts: `provision_stg.py`, `webhook_stg.py`, `observe_stg.py`; recriáveis se sumirem).

## Depois do staging OK — sequência pra prod + embed

1. **Promover pra prod** (⚠ setar o prefixo de volta explicitamente, senão herda staging):
   ```
   gcloud run deploy castro-crm --source . --region us-west1 --project project-4a851bf9-f475-418c-800 --update-env-vars FIRESTORE_COLLECTION_PREFIX=castro_crm
   ```
   Conferir prod HTTP 200 + prefixo `castro_crm` depois.
2. **Deploy Cloud Run B** (`castro-superadmin`) com o código novo, pro painel aceitar
   `ai_custom` (imagem via `cloudbuild-superadmin.yaml`/`Dockerfile.superadmin`; ver
   `docs/HANDOFF_IAP_E_TENANT2.md`).
3. **Criar tenant `varizemed-test`** (plano `ai_custom`, admin `rafaluisc@outlook.com`)
   pelo painel super-admin (com MFA).
4. **`scripts/set_tenant_ai.py`** no `varizemed-test` com: `--gcp-project castro-ia
   --location us-central1 --agent-id 5fa69ea1-bc68-445b-9d20-d72265aaaf36
   --handoff-bot-key sac --lgpd-notice "<aviso>" --lgpd-policy-version varizemed-2026-07`
   (⚠ `--lgpd-notice` e `--lgpd-policy-version` são OBRIGATÓRIOS com motor ativo).
   Aviso LGPD da Varizemed (fornecido pelo PO): "Bem-vindo(a) à Varizemed! Para
   iniciarmos o seu atendimento com total segurança, preciso que você aceite a nossa
   Política de Privacidade. Você pode ler todos os detalhes aqui:
   https://varizemed.com.br/politica-de-privacidade/"
5. **Setor "Recepção"** com `bot_key=sac` (⚠ "atendimento" é INVÁLIDO — válidos:
   comercial/financeiro/administrativo/sac) + ligar `bot_enabled` do tenant.
6. **Rafael faz o Embedded Signup** com o número real (standard). Se travar, fallback:
   `scripts/register_phone.py` + `POST /api/admin/channels`. Depois testa mensagens no WhatsApp.

## Limpeza pendente (quando o teste staging terminar)

- Apagar tenant/canal de teste do prefixo staging (`varizemed-cxtest`,
  `castro_crm_staging_*`): usar `scripts/delete_channel.py` com
  `FIRESTORE_COLLECTION_PREFIX=castro_crm_staging` + remover o doc do tenant.
- Apagar o doc de smoke `conversations/+5571900000001` no banco `castro-ai-test` (castro-ia).
- `gcloud config set builds/timeout 3600` foi setado nesta máquina (ok manter).

## Follow-up pro Dev IA (não bloqueia)

O agente não seta `handoff_request` de forma confiável — o CRM já cobre por texto,
mas seria bom o Dev IA reforçar o Step 8 (Atomic Closure) do playbook pra setar o
parâmetro sempre que sair do Step 6.
