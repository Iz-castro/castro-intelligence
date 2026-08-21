---
name: varizemed-migration
description: Tenant
metadata: 
  node_type: memory
  type: project
  originSessionId: 535f93e8-1725-4ae6-827a-2268b798f3c3
  modified: 2026-08-10T18:19:34.465Z
---

Tenant #2 real será a **Varizemed** (clínica médica) — migração do stack próprio
(Flask + Twilio + Dialogflow CX, projeto GCP `val-02-469714`, `southamerica-east1`)
para o Castro CRM (Meta Cloud API direta). Decidido em 2026-07-12.

**Fontes:** repos locais em `c:\Rafael\Varizemed` (`varizemed-webhook@5a0a1fc`,
`varizemed-crm@1693719`); relatório `docs/RESPOSTAS-MIGRACAO-CX.md` (git-ignored —
contém IDs reais; entrada no .gitignore adicionada 2026-07-12). Verificação
adversarial multi-agente 2026-07-12: 33 afirmações, 0 refutadas, 6 parciais +
31 omissões — correções e gaps registrados como adendo no próprio relatório.

**Fatos que definem o conector CX:** sem fulfillment webhooks (nada a portar);
resposta do CX é só-texto (+ parâmetros de sessão persistidos por turno em
`session_parameters`); handoff = parâmetro `handoff_request` truthy (só avaliado em
status `bot`) OU match exato de `DF_HANDOFF_TEXT_HINTS`; sessão = telefone
só-dígitos, `user_id` E.164 e `user_name` re-injetados a cada turno; sem gate LGPD
no pipeline deles (nosso `lgpd_bot.py` antes do motor é adição nova). Ponto de
inserção no Castro: dispatcher por tenant em `process_bot_message`
(`bot_service.py`), engine em `settings.ai` do doc do tenant.

**Riscos de cronograma:** mídia do histórico vive em URLs da API Twilio com Basic
Auth — job de download + re-hospedagem OBRIGATÓRIO antes de desligar a conta
Twilio; hashes scrypt (Werkzeug) não importam pro Firebase Auth → atendentes
re-cadastram; schema deles é 1-doc-por-telefone sem canal/episódio → import pro
modelo (channel_id, wa_id) exige normalização pesada.

**Plano acordado (ordem):** (1) camada de entitlements por tenant — `plan` hoje é
só rótulo, criar `features`; (2) motor de disparo em lote (ADR 0005: campaigns,
Cloud Tasks, opt_out_marketing) — serve reabertura em massa (botão que a Varizemed
tem hoje, manual com preview+cooldown 24h) e marketing; (3) conector Dialogflow CX;
(4) migração do número Twilio→WABA + import de histórico (molde:
import_backup_hubloc).

**✅ E2E EM PROD (2026-07-14/15):** motor CX por tenant VIVO — Varizemed(teste)
com número real +55 31 7195-7758, Val respondendo, LGPD+handoff OK, Hubloc
intacto. MFA no login do CRM entregue (bônus). Admin do tenant =
contato@castrointelligence.com.br (rafaluisc/izael/castrointelligence@gmail já são
Hubloc → guard "1 email=1 tenant"). **Pendências consolidadas em
`docs/PENDENCIAS_E_ROADMAP.md`.** Gate pra Varizemed REAL (decisão PO): disparo em
massa + áudio no bot + hardening LGPD + import de histórico. UI batch (API×coex,
repositório de encerrados, mobile) junto do front modular.

**Export do agente recebido (2026-07-12, `docs/exported_agent_val-05/` JSON
package) — VIROU O PLANO DE CABEÇA:** o `val-05` NÃO é DetectIntent
determinístico, é agente **GENERATIVO** (Gemini 2.5 Flash, playbooks + tools +
RAG). Entrada: flow determinístico `lgpd_intro_flow` → webhook
`check_lgpd_consent` (Cloud Function) → SIM existe gate LGPD, no agente. Start
playbook `val_greeting` → playbook `val_router` (cérebro, 8 steps). Toda a lógica
de negócio vive em 2 Cloud Functions (us-west1, sufixo `-test`): **VarizemdRouter**
(classify_intent/validate_insurance/get_doctors/treatment/scheduling — "Python
decide, LLM fala", emite agent_guidance interno) e **ValMemory** (memória de sessão
no Firestore por telefone E.164). Conhecimento clínico embutido e específico
(5 especialidades, 8 tipos de convênio, preços fixos, médicos nominais, guard-rails
anti-alucinação, blind calendar). Filtros RAI em BLOCK_NONE (revisar).

**Isso reescreve o item (3) "conector":** não é conector fino pro DetectIntent. Duas
rotas — (A) manter agente CX e só apontar webhook do Castro pra ele (cross-project,
premium vira revenda); (B) trazer agente+2 Functions+Firestore pra Oregon (realiza
premium="nossa IA do CX"; agente vira TEMPLATE do vertical clínica). Falta ainda:
valores de PROD (export é val-05 de teste, um exemplo mostra erro 404 db val-4 não
provisionado), código-fonte das 2 Cloud Functions (só temos schema OpenAPI), e as
fontes RAG do Knowledge Connector.

**Pendências ainda só o time Varizemed responde:** valores de prod (agente+Functions),
volume mensal, corpo dos templates Twilio Content API, código Python das 2 Functions.

**ESTADO 2026-07-14 — VER `docs/RETOMAR_VARIZEMED_CX.md` (doc de retomada
autossuficiente).** Trilha CRM commitada+pushada no develop (último: `3c31084`).
Fix get_send_credentials, planos professional/ai_custom/enterprise_ai +
_LEGACY_PLAN_MAP + PLAN_MODULES + /api/session, conector `bot_engine_dialogflow.py`
(DetectIntent REST v3 async), dispatcher `process_bot_message_async` +
`_process_cx_message` (gate LGPD local; tenant COM settings.ai NUNCA cai no builtin
Hubloc), guard redelivery no webhook, scripts migrate_plans/set_tenant_ai/register_phone.
Revisão adversarial (27 agentes): 13 achados, TODOS corrigidos (2 alta LGPD).

**SMOKE do agente OK** (3/3) e **VALIDAÇÃO STAGING OK** (revisão tag `staging`,
--no-traffic, prefixo `castro_crm_staging`, prod intacta): provou dispatcher CX +
aviso LGPD Varizemed + consent versão `varizemed-2026-07` (não hubloc) + DetectIntent
real. **BUG achado no staging e corrigido** (`3c31084`): agente FALA a transferência
mas NÃO seta `handoff_request` (logs handoff=False) → contato não entrava na fila;
fix = detectar handoff por parâmetro OU texto (`_cx_is_handoff`, override via
settings.ai.handoff_text_hints). **PENDENTE:** re-testar handoff no staging (build
do fix `f6dff730` rodava ao pausar) → depois promover prod (⚠ setar
FIRESTORE_COLLECTION_PREFIX=castro_crm explícito senão herda staging) + deploy Cloud
Run B + criar tenant real + Rafael faz embed do número. Detalhes/comandos/limpeza:
`docs/RETOMAR_VARIZEMED_CX.md`.

**Gotchas confirmados:** bot_key "atendimento" é INVÁLIDO (válidos: comercial/
financeiro/administrativo/sac) → handoff usa `sac`; ADC local está impersonando
`castro-crm-run` (tem dialogflow.client no castro-ia + Firestore write); app secret =
`castro-crm-whatsapp-app-secret` (Secret Manager). Config real do agente: projeto
`castro-ia`, location `us-central1`, agent `5fa69ea1-bc68-445b-9d20-d72265aaaf36`.

**Config real do agente IA (Dev IA, 2026-07-13):** AI_PROJECT=`castro-ia`,
location=**`us-central1`** (regional, NÃO global), AGENT_ID=
`5fa69ea1-bc68-445b-9d20-d72265aaaf36`, language pt-br. Pendente do Dev IA
(SYNC-1): URLs das 2 Cloud Functions + IAM roles/dialogflow.client pra SA do CRM.
Próximo do CRM após SYNC-1: rodar set_tenant_ai.py (--lgpd-notice/--lgpd-policy-version
OBRIGATÓRIOS quando ativo) no tenant varizemed-test.

**✅ TENANT REAL CRIADO EM PROD (2026-07-28/29):** doc `castro_crm_tenants/varizemed`,
`plan=ai_custom`, `is_active=True`, criado 28/07 22:34Z **pelo painel B** (audit
`create_tenant_attempt`/`create_tenant_ok`, admin `contato@clinicavarizemed.com.br`,
`admin_provisionado=True`), `allowed_email_domains=['clinicavarizemed.com.br']`.
`settings.ai` completo (mesmo agent `5fa69ea1-…` do teste, `handoff_bot_key=sac` →
setor 3 Recepção, `lgpd_policy_version=varizemed-2026-07`). Canal 7
(+55 31 9979-4546) roteado 29/07 16:31Z, `bot_enabled` ligado 16:41Z. **Fluxo CX
rodou ponta a ponta 2× em prod no dia 29/07** (45 mensagens, LGPD, handoff,
temperatura no contato e na thread, resumo no thread). ⚠ `bot_states` vazio é
ESPERADO após handoff (`_clear_bot_state`) — não significa "nunca rodou".

⚠ **`varizemed-test` continua VIVO em prod** (criado 14/07): `is_active=True`,
`bot_enabled=True`, canal 6 ativo e roteado (+55 31 7195-7758), MESMO `agent_id`.
Responde de verdade se alguém mandar mensagem. Decidir desativar. Além disso ele
tem DOIS setores ativos com `bot_key='sac'` (ids 3 e 5) → `_dept_id_by_bot_key`
resolve por ordem, não por intenção (mesma classe do incidente "Vendas" duplicado).

⚠ Com **3 tenants ativos**, `single_active_tenant()` retorna None → login sem claim
e sem domínio casado agora é **403** (rede de transição desarmada, by design).
CLAUDE.md ("hoje só hubloc é operacional") ficou desatualizado.

**2026-08-10 — 2 vazamentos da era single-tenant achados pelo PO em prod (rev
`castro-crm-00079-hlp`, commit `7efd537`):** (1) a despedida da RECUSA LGPD era
constante com "A Hub Loc agradece o seu contato!" — 2 leads da clinica (contatos
84 e 85) receberam a marca da locadora; fix data-driven no padrao do topbar:
`lgpd_bot._recusa_resposta()` resolve `tenant.name` em runtime (sem nome ->
neutra; SEM artigo antes do nome — genero). O aviso default do builtin segue
hubloc-branded (ok enquanto hubloc for o unico builtin; comentario de alerta no
codigo). (2) AUDIO deixava a Val muda: dispatch de bot so rodava pra msg_type
"text" e a transcricao (faster-whisper) e salva DEPOIS — fix: webhook roda o
mesmo dispatch guardado com o transcript apos salva-lo (contato re-lido no
ponto; STT_FALLBACK_TEXT nunca vai pro bot). Efeito assumido: consentimento
LGPD por audio passa a valer. Caminho webhook->stt->bot NAO tem simulador —
validacao manual pendente (audio no numero de teste apos aceite).

Ver [[cx-params-struct-bug]].

**LGPD:** clínica = dado sensível → frente própria antes do go-live (criptografia
em repouso de campos sensíveis, audit log de leitura, retenção/TTL — exigências do
CLAUDE.md §2.4 que o Hubloc nunca precisou). Ver [[multitenant-fase2-roadmap]].

**2026-08-03 — operadores + setor único:** Rafael deletou (soft) os setores
built-in do varizemed; ativo só o **id=1, renomeado Geral→"Recepção" com
bot_key=sac pela UI** (a inativa id=3 "Recepção" foi renomeada "Recepção (antiga)"
via write direto pra liberar o nome — a checagem de duplicata NÃO ignora inativos).
`handoff_bot_key=sac` agora resolve direto (antes caía no fallback com ERROR por
handoff). Backfill aplicado: 4 convs + 4 contatos dept 3→1. Operadores comuns
provisionados via **`scripts/provision_operator.py`** (criado nesta data,
NÃO commitado ainda; expõe provision_operator na CLI — a página Equipe não tem
botão de cadastro): atendimento@clinicavarizemed.com.br (users/2) e
flopescristina@gmail.com (users/3, gmail = precisa do script mesmo, domínio nunca
roteia), ambos setor 1. **Gotcha do frontend:** pool "Novos" filtra por setor pro
operador comum (thread do próprio setor OU sem setor — CrmContext
novosConversations); operador sem department_id não vê pool carimbada → sempre
provisionar operador comum COM setor.

**2026-08-03 — billing da WABA resolvido + template de reabertura próprio:**
template `varizemed_retomada_generica_utility_v1` (utility, {{1}}=nome
{{2}}=data) aprovado na WABA da Varizemed. Primeiros envios falharam com erro
Meta **131042** (currency not configured — a WABA não tinha moeda/método de
pagamento); a equipe configurou pelo billing hub e o template passou a sair.
Gotcha de diagnóstico: 131042 chega ASSÍNCRONO via status webhook (UI mostra
sent→failed sem motivo; o code/title só aparece no log `[WA STATUS]` do
webhook) — o tradutor 402 do /send-template só pega billing síncrono (131009).
⚠ Template da Varizemed com botão "[Continuar]" NÃO é reconhecido como
reabertura: frontend (isReopenTemplate) e webhook (_handle_reopen_button)
casam por "retomar"/"encerrar" — botão deve ser "Retomar …" ou exige ajuste
nos matchers.
