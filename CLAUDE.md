# Castro Intelligence CRM — Diretrizes para colaboradores e IAs

Este arquivo é lido automaticamente pelo Claude Code (e ferramentas
similares) ao trabalhar neste repositório. Mantenha as instruções
atualizadas com decisões importantes de produto, arquitetura e
compliance.

---

## 1. Sobre o produto

Castro Intelligence CRM é um SaaS multi-tenant de atendimento via
WhatsApp Business Platform. Como **Tech Provider verificado pela Meta**
(Business ID `877897608035564`, App ID `1434723791183375`), atendemos
diferentes clientes B2B sob a mesma infraestrutura: imobiliárias,
clínicas médicas, locadoras de equipamentos e similares.

- **Empresa:** CASTRO INTELLIGENCE DATA ML LTDA (CNPJ 63.609.610/0001-07,
  Brasil).
- **Stack:** FastAPI + Firestore + Firebase Auth + React/TypeScript/Vite,
  hospedado no Cloud Run em `southamerica-east1`.
- **Modelo financeiro:** passthrough — Castro Intelligence cobra
  mensalidade SaaS do cliente; Meta cobra direto do cliente pelo uso
  (cliente é dono da WABA, configura método de pagamento no Business
  Manager dele); Castro Intelligence só paga GCP/Firebase.

Roadmap arquitetural completo em [docs/PLANO_COEXISTENCE_REFATORACAO.md](docs/PLANO_COEXISTENCE_REFATORACAO.md).

---

## 2. Compliance LGPD — diretriz obrigatória

Este produto opera sob jurisdição brasileira e processa dados pessoais
de operadores e clientes finais (potencialmente sensíveis em casos
como clínicas médicas). Toda contribuição (código, schema, UI, prompt)
deve respeitar a **Lei Geral de Proteção de Dados Pessoais (Lei nº
13.709/2018)**.

### Princípios aplicados

1. **Minimização e Necessidade.** Coletar apenas dados pertinentes,
   proporcionais e não excessivos à finalidade. Limitar processamento
   ao mínimo necessário.

2. **Finalidade e Transparência.** Toda coleta tem propósito legítimo,
   específico, explícito, informado ao titular.

3. **Consentimento Explícito.** Para novos dados pessoais, captura
   manifestação livre, informada e inequívoca do titular. Consentimento
   é revogável a qualquer momento.

4. **Dados Sensíveis com restrição máxima.** Saúde, biometria, origem
   racial — só com consentimento específico e destacado para finalidade
   específica. Em CRMs de clínica médica, campos sensíveis exigem:
   - Criptografia em repouso (além da encriptação default do Firestore).
   - Audit log de acesso (`audit_log` registra quem leu o quê).
   - Política de retenção definida (TTL ou expurgo periódico).
   - Acesso limitado a roles autorizadas.

5. **Direitos do Titular.** Sistema deve permitir, sob solicitação:
   acesso aos dados, correção, anonimização, bloqueio, eliminação.
   Sugerir endpoints/UI dedicados a isso quando ainda não existirem.

6. **Segurança da Informação.** Não expor dados de um titular para outro:
   - Em multi-tenant, isolamento estrutural via subcoleções
     `tenants/{tenant_id}/...` e Firestore rules baseadas em path —
     nunca apenas filtro lógico no backend.
   - Tokens, secrets e PII **jamais** em logs (use logger com
     redaction quando necessário).
   - Webhooks validam HMAC antes de processar payload Meta.

### Como aplicar em PRs e mudanças

Toda mudança que introduza nova coleta ou exposição de dado pessoal
deve, preferencialmente no próprio commit/PR ou em comentário no doc:

- Justificar a **finalidade específica**.
- Indicar onde o **consentimento** é capturado.
- Descrever **política de retenção** (quando o dado é deletado).
- Garantir **isolamento entre tenants** (validar Firestore rules + path).
- Adicionar **audit log** de quem acessou se for dado sensível.

### Conflito com a LGPD

Se uma solicitação conflita com a LGPD (ex.: pedir export massivo de
dados sem identificar quem é o titular), sinalize o conflito antes de
implementar e proponha um caminho alternativo conforme.

---

## 3. Convenções de código

### Backend (Python / FastAPI)

- Seguir estrutura de Tenant: toda função de dados recebe `tenant_id`
  como parâmetro explícito.
- Erros de Meta Graph API são extraídos via `_meta_error_detail` e
  retornados como HTTP 502 com `code`, `subcode` e `fbtrace_id`.
- Logs usam `logger.info`/`logger.warning` (nunca `print`). Não logar
  tokens, telefones, conteúdo de mensagens em produção.
- `httpx.AsyncClient` para chamadas externas com timeout explícito.
- Audit log via `log_audit(user_id, action, detail)` — mínimo
  obrigatório em qualquer mutação cross-user.

### Frontend (TypeScript / React)

- Tipos em `frontend/src/types.ts` são fonte da verdade. Atualizar
  primeiro lá, depois consumir.
- Endpoints centralizados em `frontend/src/api.ts`.
- Estado global em `CrmContext.tsx`.
- `tenant_id` nunca enviado pelo frontend — é injetado no token
  Firebase via custom claim e lido pelo backend.

### Git

- Branch padrão: `develop`.
- Commits em pt-BR (ASCII, sem acentos no commit message — só no body),
  com prefixos `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`.
- Co-author Claude quando aplicável:
  ```
  Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
  ```
- `git push` direto pra `develop` é permitido (sem PR formal hoje).

### Deploy

- Produção: Cloud Run service `castro-crm` (região `southamerica-east1`,
  projeto `project-26fb9c99-8ee9-4179-aef`).
- Staging: Cloud Run service `castro-crm-staging` (mesmo projeto, com
  `FIRESTORE_COLLECTION_PREFIX=castro_crm_staging`).
- Comando: `gcloud run deploy <service> --source . --region southamerica-east1 --quiet`.
- Dockerfile faz build do frontend (`npm run build`) automaticamente em
  multi-stage — não precisa pré-buildar.

---

## 4. Decisões arquiteturais ativas

- **Multi-tenant por subcoleções aninhadas em `tenants/{tenant_id}/...`**
  — não flat com `tenant_id`. Isolamento estrutural via path.
- **`phone_routing/{phone_number_id}` global** — índice O(1) pro webhook
  resolver tenant.
- **Firebase Auth custom claim `tenant_id`** — backend extrai do token,
  frontend não envia.
- **`wa_conversations`** entre `wa_contacts` e `wa_messages` — uma
  thread por (channel_id, wa_id). Conversation_id determinístico.
- **Auditoria distingue `channel_owner_user_id` (dono físico do número)
  de `sender_user_id` (quem digitou)** — fundamental no modelo coexistence
  com transferências.

---

## 5. Documentos relacionados

- [docs/PLANO_COEXISTENCE_REFATORACAO.md](docs/PLANO_COEXISTENCE_REFATORACAO.md) — plano
  arquitetural ativo (Fases 1–4).
- [docs/APP_REVIEW_SCREENCAST_SCRIPT.md](docs/APP_REVIEW_SCREENCAST_SCRIPT.md) — roteiro do screencast Meta App Review.
- [SISTEMA_COMPLETO.md](SISTEMA_COMPLETO.md) — overview funcional gerado por `scripts/build_sistema_completo.py`.
