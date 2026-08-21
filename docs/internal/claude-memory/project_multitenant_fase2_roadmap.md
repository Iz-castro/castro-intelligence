---
name: project_multitenant_fase2_roadmap
description: Multi-tenant Fase 2 — backbone JA em prod; gargalo unico e ADR 0007 (canais flat); caminho critico M-A1..M-A5 mapeado; relatorio completo no plano
metadata:
  node_type: memory
  type: project
  originSessionId: 4a88a0f8-336a-41bc-8e73-70a3a3ec2622
---

2026-06-30: compilado de pendencias + roadmap multi-tenant Fase 2 (usuario vai
discutir na empresa antes de executar; NADA implementado ainda). Relatorio completo:
`C:\Users\izael\.claude\plans\rosy-questing-walrus.md`.

**RELEITURA-CHAVE (verificado no codigo, nao so nos docs):** a maior parte do "Fase 2"
JA ESTA EM PROD. Pronto: context machinery (`firestore_common.py` roteia `tenants/{tid}/`),
resolucao de tenant por JWT claim (`auth.py`+middleware `main.py:160-188`), `tenant_service.py`
CRUD + `phone_routing`, webhook resolve tenant O(1) (`webhook.py:47-67`), `wa_conversations`
+ auditoria coex (sender_user_id vs channel_owner_user_id), usage/402/health-cron per-tenant,
e **rules PROD estritas por path** (`firestore.rules:177-287`). Os docs (PLANO/RETOMAR)
descrevem o plano e alguns status estao DESATUALIZADOS (diziam pendente o que ja foi feito;
diziam rules "permissivas em prod" mas o codigo tem rules estritas — confirmar se estao
PUBLICADAS no console).

**GARGALO UNICO p/ o 2o tenant = ADR 0007 (canais flat).** `castro_crm_channels` e
`pending_webhook_events` sao flat (via `_flat_collection`). Riscos: (1) READ cross-tenant
em `GET /api/admin/channels` (cache global inteiro); (2) WRITE cross-tenant gravissimo —
`_default_channel_id` e int global, envio sem channel_id sai pela WABA do outro tenant;
(3) colisao de event_id em pending_webhook_events. BLOQUEANTE, nao teorico.

**CAMINHO CRITICO MINIMO (Parte A):** M-A1 ADR0007 Fase 1 (filtro logico por
get_tenant_context em get_all_active_channels/get_channels_for_user; `_default_channel_id`
vira dict[tid]; auto-id UUID em enqueue_pending_event) [S/baixo] -> M-A2 `bootstrap_tenant(tid)`
(semear setores/admin + set_tenant_claims+revoke NA CRIACAO; refatorar `main.py:476-481`
pra usar, hubloc idempotente) [M] -> M-A3 `scripts/create_tenant.py`+runbook [S] -> M-A4
endurecer rules de STAGING + VERIFICAR no console que as rules PROD estao publicadas [S]
-> M-A5 GATE ensaio de onboarding + auditoria de vazamento. Legal em paralelo (ADR 0002
se coex; Oregon DPA/SCC/RoPA).

**Parte B (depois do #2):** M-B1 migracao estrutural canais->tenants/{tid}/channels (ADR0007
Fase 2, L/alto); M-B2 RBAC dinamico (perfis_acesso por tenant); M-B3 super-admin Cloud Run B
(impersonate, lifecycle); M-B4 billing enforcement; M-B5 self-service+white-label.

**DECISOES:** D1 = DECIDIDO 2026-06-30 — cliente novo (#2) vai de STANDARD, MAS coex
tem que continuar DISPONIVEL (nao regredir; arquitetura ja suporta os dois — hubloc usa
1 standard + 2 coex). Coex p/ novos tenants so libera apos ADR 0002 (legal).
D2 = DECIDIDO 2026-07-01 — fazer Fase 1 (filtro logico) E Fase 2 (migracao estrutural
canais->tenants/{tid}/channels), SEQUENCIADAS (Fase 1 destrava; Fase 2 logo em seguida,
sem ninguem esperando).
D3 = DECIDIDO 2026-07-01 — criar tenant via UI SUPER-ADMIN (Cloud Run B), construido
INCREMENTAL (Sprint 0 §6 do PLANO_RBAC -> B minimo so-criar-tenant -> crescer com
impersonate/analytics/etc). NAO usar script descartavel. Motivo: criar tenant e operacao
privilegiada de root; o "grande" do B e a superficie de seguranca (servico separado +
Admin SDK + MFA-na-sessao + sessao 15min + audit imutavel BigQuery + kill switch), nao o
formulario. Nao pode ser botao no A (principio §4.1: comprometer A != comprometer todos).
D4 = DECIDIDO 2026-07-01 — RBAC dinamico ANTES do #2 (decisao do usuario, contra minha
recomendacao inicial). Racional valido: fazer a migracao RBAC no hubloc (tenant que
controlamos) enquanto so tem 1 tenant, pra o #2 NASCER ja no modelo dinamico (evita migrar
cliente pagante ao vivo). Custo aceito: mais escopo antes do #2 (regressao em todo check de
permissao) -> #2 sai mais tarde. RBAC = M-B2 promovido pra pre-#2.
D5 = DECIDIDO — testar com AGENTES; usuario autorizou gasto ALTO de tokens ("quantos quiser").
Aplicar no BUILD de cada milestone: workflow de testes (gerar casos + rodar em staging +
verificar isolamento adversarialmente). Nada a testar ainda (nada implementado).
D6 = DECIDIDO (recomendado) — claim ATOMICO: setar custom claim + revokeRefreshTokens NA
CRIACAO do tenant/admin, pra o 1o login ja vir com tenant_id/perfil_acesso_id. Evita o footgun
"admin novo nao enxerga o tenant" do estado atual (claim setado async sem forcar refresh).

**VERIFY-FIRST FEITO 2026-07-01 (usuario colou as rules do console):** rules estritas de PROD
CONFIRMADAS publicadas (bloco castro_crm_tenants/{tid} com request.auth.token.tenant_id ativo).
ACHADO CRITICO PRE-#2: `ownsTenant(tid) = emailAllowed() && tokenTenantId()==tid` — e
`emailAllowed()` e whitelist hardcoded do hubloc (2-3 founders + *@hubloc.com.br). Como TUDO no
bloco estrito passa por ownsTenant/tenantOperatorActive/canSeeContactScoped, operador de tenant #2
(email nao-hubloc) seria BARRADO nas proprias rules -> nao le nem o proprio tenant. FIX obrigatorio
(M-A4): remover emailAllowed() das rules tenant-scoped, isolar por claim tenant_id + operator_profile
ativo (nao enfraquece hubloc). O comentario firestore.rules:6-7 ja avisa isso. DRIFT: repo tem
castrointelligence@gmail.com no emailAllowed() que o publicado NAO tem -> republicar. Canais: NAO
tem regra de channels no PROD -> deny-by-default p/ cliente -> backend-only -> confirma M-A1 (filtro
backend) como ponto de aplicacao certo. Staging segue permissivo (emailAllowed em tudo) -> M-A4.

**PROGRESSO DE EXECUCAO:**
- M-A1 (ADR 0007 Fase 1, isolamento logico de canais) = DEPLOYADO EM PROD 2026-07-01
  (commit c6ba72f, rev castro-crm-00037-ruh). channel_service.py: get_all_active_channels/
  get_channels_for_user filtram por get_tenant_context() (fallback "hubloc"); _default_channel_id
  virou dict[tenant]->channel_id (refresh calcula 1o standard ativo por tenant); get_default_channel
  le o default do tenant atual. pending_events.enqueue_pending_event usa auto-id do Firestore (era
  next_sequence -> colidia entre tenants); event_id agora STRING -> 3 endpoints /api/admin/
  pending-webhook-events/{id}/(retry|dismiss|delete) tipam str; scripts _drain_*_tmp.py ajustados
  (hash crc32 estavel no shard). Revisao adversarial (9 agentes) = SHIP; unit test isolamento 9/9
  (scratchpad, em memoria); staging+prod HTTP 200. Comportamento IDENTICO pro hubloc (single-tenant);
  filtro so "morde" com 2o tenant. get_channel/get_channel_by_phone_id NAO filtrados (webhook precisa
  resolver tenant; aceitavel no Fase 1). PROXIMO: M-A4 (rules: tirar emailAllowed do ownsTenant) ou
  M-A2 (bootstrap_tenant) ou M-B2 (RBAC dinamico, decidido ANTES do #2).

- M-A2 (bootstrap_tenant + claim atomico D6) = DEPLOYADO EM PROD 2026-07-03 (commit 93ae7e1,
  rev castro-crm-00039-cob). NOVO tenant_bootstrap.py: bootstrap_tenant(tid,name,admin_email,...)
  = porta unica de provisionamento (tenant + setores + admin), idempotente; serve o hubloc no
  startup E o onboarding de tenants novos (Cloud Run B futuro). ensure_tenant_admin resolve a
  conta Firebase ANTES do upsert (users doc + operator_profile + claims linkados); set+revoke SO
  quando claims divergem (leitura ESTRITA get_user_claims_strict: erro != vazio -> nao desloga o
  admin em cold-start); guard "um email = um tenant" (aborta se conta ja e de outro tenant, LGPD).
  firebase_admin_client.py: +get_or_create_firebase_user/get_user_claims_strict/revoke_refresh_tokens;
  set_tenant_claims aceita base_claims e nao apaga claims extras em falha de leitura. main.py:
  startup usa bootstrap_tenant("hubloc",...) (comportamento IDENTICO, no-op idempotente); 3 funcs
  bootstrap antigas removidas + imports mortos limpos. Corrigiu de graca o quirk antigo (boot
  zerava firebase_uid do doc com upsert(firebase_uid="")). Revisao adversarial 2 rounds (round 1
  achou 4, incluindo o MEDIUM que deslogaria o admin — TODOS corrigidos; round 2 = SHIP_WITH_NITS,
  LOWs corrigidos). Unit test em memoria 28/28 (10 cenarios). Staging boot validado por LOG:
  "Setores ja existentes (8) pulado" + "Bootstrap admin sincronizado tenant_id=hubloc" + AUSENCIA
  de "Claims do admin provisionados" (= rafa NAO deslogado). LIMITACOES documentadas pro Cloud Run
  B one-shot (guard nao cobre conta sem claim; falha de leitura nao converge sozinha). Test em
  scratchpad/test_ma2_bootstrap.py.
  PROXIMO: M-A4 (rules: tirar emailAllowed do ownsTenant — bloqueador achado no verify-first) OU
  M-B2 (RBAC dinamico, decidido ANTES do #2) OU Cloud Run B minimo. Ver ORDEM no doc.

- M-A4 (rules multi-tenant: isolar por claim tenant_id) = PUBLICADO EM PROD 2026-07-03
  (commit 8893bc5 no develop; publish via REST, NAO e deploy de Cloud Run — rules sao
  recurso Firebase separado). firestore.rules ownsTenant(tid) passou de
  `emailAllowed() && tokenTenantId()==tid` para `tokenTenantId()==tid`. Ruleset ativo em prod
  `faa492f1-c3c7-45d9-b5b3-8f141af2a1c9` (verificado byte-a-byte na fonte). Publish/rollback via
  scratchpad/publish_ma4_rules.py (--rollback re-publica firestore.rules.bak-publicado-20260703,
  o ruleset anterior, salvo no repo). GOTCHA da API firebaserules: precisa header
  `x-goog-user-project: project-4a851bf9-f475-418c-800` senao 403 (SERVICE_DISABLED no projeto
  default do gcloud); PowerShell Invoke-RestMethod TRAVA em POST grande -> usar httpx do .venv.
  Pre-flight 13/13 operadores ativos do hubloc com claim+profile (lockout=0). Matriz 16/16 no
  motor REAL de rules (endpoint :test, sem publicar; scratchpad/test_ma4_rules.py). Canario pos-
  publish OK (usuario logou operador comum E admin, enviou+recebeu). Revisao adversarial 18 agentes
  (3 finders + verify + synth) = veredito SHIP, 0 bloqueadores: para a populacao viva do hubloc e
  NO-OP byte-a-byte (remover termo de AND so relaxa; o termo removido era redundante com deter o
  claim, que so e emitido apos passar o MESMO gate de email do backend _firebase_email_allowed).
  emailAllowed() ainda gateia so colecoes FLAT legadas + bloco STAGING (ambos VAZIOS em Oregon).
  4 FOLLOW-UPS pre-existentes (is_regression=false, NAO bloquearam; grupo "M-A4b", PRE-REQUISITO
  do tenant #2, NAO deste deploy): (i) OFFBOARDING ** — deactivate_user (database_firestore.py:393)
  so grava is_active=0; falta revoke_refresh_tokens + limpar claim tenant_id/role; as ~11 subcolecoes
  gateadas SO por ownsTenant (nao tenantOperatorActive) deixam desativado com claim residual ler PII
  do proprio tenant por ~1h (TTL do ID token). Fix: revogar na desativacao OU trocar essas subcolecoes
  p/ tenantOperatorActive. (ii) ROLE STALE — troca de cargo (main.py:666) nao reescreve claim role;
  admin rebaixado mantem leitura privilegiada ~1h. (iii) MIS-PROVISIONAMENTO — _resolve_tenant_id
  faz fallback cego p/ hubloc (auth.py:172) + admin_create_user (main.py:640) cria operador sem claim;
  fechar antes de ampliar ALLOWED_FIREBASE_EMAIL_DOMAIN p/ o #2. (iv) storage.rules ainda whitelist
  hubloc (inocuo hoje: midia via backend Admin SDK, sem Storage client-side). Detalhe no bloco 0c do
  doc ROADMAP. Nota: alem do M-A4b, PENDENTE do proprio M-A4 = endurecer rules de STAGING (espelhar
  PROD) — baixo risco, staging vazio em Oregon.
  PROXIMO: M-B2 (RBAC dinamico no hubloc, decidido ANTES do #2) OU Sprint 0 RBAC/super-admin OU
  Cloud Run B minimo. Ver ORDEM (bloco pos-0c) no doc.

- M-A4b (lifecycle de claims no ciclo de vida do usuario) = EM PROD 2026-07-04 (commit
  1dbb752, rev castro-crm-00041-rij). Fecha as lacunas que o M-A4 abriu ao autorizar rules
  por claim. OFFBOARDING (DELETE /api/admin/users/{id}): clear_tenant_claims (limpa
  tenant_id/role, preserva extras tipo super_admin, UserNotFound=True) + revoke +
  invalidate_auth_cache; GUARD anti-ressurreicao em auth.authenticate_firebase_token: login
  de conta DESATIVADA -> 403 ANTES do auto-provision (fecha o buraco em que, com
  AUTO_PROVISION=true em prod, o desativado era recriado como doc novo ativo e o claim
  re-emitido -> offboarding TERMINAL sem depender de flipar o flag; tb evita duplicata _2).
  DELETE idempotente via get_user_raw_by_id (retry do clear em vez de 404); retorna
  claims_cleared. ROLE (PUT): reemite claim role decidindo pela divergencia do CLAIM (nao do
  doc -> re-salvar mesmo cargo = retry) + revoke + invalida cache; guard cross-tenant.
  CRIACAO (POST): provision_operator em tenant_bootstrap = LOOKUP-only da conta Firebase (NAO
  pre-cria — 8/13 operadores usam provider senha, conta pre-criada quebraria onboarding),
  claim atomico se conta existe, guard "um email=um tenant" (TenantConflictError->409); recusa
  recriar sobre doc DESATIVADO (DeactivatedUserError->409) p/ nao gerar gemeo ativo+inativo que
  o _get_first_by_field (limit(1) sem order_by) poderia surfacar e o guard 403ar alguem valido.
  Helpers novos: firebase_admin_client.clear_tenant_claims/get_firebase_uid_by_email;
  database_firestore.get_user_raw_by_firebase_uid_or_email/get_user_raw_by_id. Revisoes: core
  SHIP (22 ag) + delta SHIP (gate pre-deploy de duplicatas PASSOU: 13 docs, 0 gemeos). Testes:
  44 (claims/provision) + 11 (guard) em memoria + INTEGRACAO ponta-a-ponta na conta
  teste@ (id=13) contra Firebase real (cargo->claim reemitido, desativa->claim limpo+guard
  bloquearia, dedup 409), restaurada ao snapshot exato. Staging tagged 00041-rij boot limpo,
  login canario operador+admin ok, promovido via update-traffic. Rollback = update-traffic p/
  rev 00040-*. PENDENTE do grupo M-A4b (pre-#2, NAO shipado): matar fallback cego
  _DEFAULT_TENANT=hubloc (auth.py:172) + AUTO_PROVISION tenant-aware; gate de login por dominio
  (allowed_email_domains soft, evoluir _firebase_email_allowed); storage.rules; FOLLOWUP
  disabled=True na conta Firebase ao desativar (belt-and-suspenders, fecha 100% resid client-SDK
  se clear falhar, muda reativacao p/ exigir re-habilitar); guards de escalacao (supervisor nao
  cria/promove admin; ninguem muda proprio cargo) -> M-B2. PROXIMO: M-B2 (RBAC dinamico) OU
  Cloud Run B minimo OU as pendencias pre-#2 acima.

- M-B2 (RBAC dinamico por tenant) = IMPLEMENTADO + REVISADO 2026-07-04, **NAO DEPLOYADO**
  (pendente staging tagged -> testes por agentes D5 -> prod). Commits no develop local:
  9fda420 (backend+rules), 0af0a1c (frontend), 7d3838e (docs), 5a761b3 (fixes da revisao).
  Fases 1-4 do PLANO_RBAC §3.8 numa tacada, dual-check ativo (toggle do perfil decide;
  perfil/chave ausente -> fallback = seed da ROLE = comportamento pre-RBAC; dia 0 identico).
  NUCLEO: rbac.py — catalogo FIXO de 28 toggles (SO chaves com enforcement real; ver_proprios/
  sem_dono/setor/audit_log/transfer_log/re_onboarding do rascunho NAO entraram — sem ponto de
  codigo controlavel; PLANO_RBAC §3.4.1 documenta), 3 seeds validados 1:1 por inventario
  (divergencias do rascunho: supervisor TEM exportar/coex/canais; operador TEM transferir;
  destrutivos viraram desativar_usuarios/canais/departamentos + gerenciar_config_sistema
  so-admin), cache TTL 60s (RBAC_PERFIL_CACHE_TTL_SECONDS) + cache curto de FALHA (5s,
  anti retry-storm), has_permission/ensure_permission/effective_toggles/can_see_all_tenant/
  toggles_beyond_user, CRUD com tenant_id explicito + lock perfil_admin. perfis em
  tenants/{tid}/perfis_acesso/{id}; users.perfil_acesso_id (+espelho operator_profiles +
  claim perfil_acesso_id derivado da role qdo nao explicito); seed+backfill idempotentes no
  bootstrap_tenant. main.py: 46 checks migrados + enforcements novos (transfer/template/
  qualify/declared/arquivar/manual/propria-thread/fechar/reabrir/assumir_coex — todos true
  nos seeds relevantes) + CRUD /api/admin/perfis-acesso (audit permission_change) + GUARDS:
  supervisor nao cria/promove/rebaixa admin; ninguem muda proprio cargo/perfil; ANTI-
  AMPLIFICACAO POR NIVEL (ninguem concede toggle que nao tem — cobre perfil-clone de admin e
  auto-edicao do proprio perfil). Frontend: perfil efetivo via /api/session + snapshot ao vivo
  de perfis_acesso; can() deny-by-default + canSeeAll (toggle E role privilegiada = TETO das
  rules, aplicado TAMBEM no REST via can_see_all_tenant — 3 camadas em sincronia); UI master-
  detail "Perfis de acesso" (menu engrenagem, admin) + select de perfil no editor de usuario.
  Rules: perfis_acesso read p/ membros do tenant, write false; rules seguem autorizando por
  claim ROLE (§3.6) — perfil ampliado alem da role NAO vale em snapshot nem REST (exige mudar
  role). REVISAO ADVERSARIAL 8 finders + verify: 10 findings TODOS corrigidos em 5a761b3
  (destaques: update_user so re-deriva perfil qdo role MUDA — payload ecoando role nao reseta
  perfil custom; _resolve_tenant SEM fallback hubloc — sem tenant vira fallback de role, nunca
  doc de outro tenant; claim churn zerado p/ usuarios pre-M-B2; precedencia qualquer_thread
  engloba propria; fechar/reabrir de terceiros = qualquer_thread OU assumir_supervisor;
  create_perfil rejeita base desconhecida). GOTCHAS: fase 5 (matar fallback de role) fica
  pos-bake-in; rolling deploy com replica antiga -> /api/session sem perfil -> UI fail-closed
  (can()=false) ate refresh (transiente, documentado); ROLE segue sendo o teto duro de
  seguranca (rules + guards de escalacao).
  STAGING + RULES FEITOS 2026-07-05: revisao castro-crm-00043-sag deployada no-traffic e
  tag `staging` movida pra ela (URL staging---castro-crm-jdznvidcxq-uw.a.run.app; prod segue
  100% na 00041-rij; tag mb2 temporaria removida). Boot validado por log: "Perfis RBAC
  semeados created=3" + "Backfill perfil_acesso_id users=13" + SEM "Claims do admin
  provisionados" (ninguem deslogado) + 0 erros. Firestore conferido: 3 seeds (admin=28/
  sup=22/op=10 toggles true), 13/13 users com perfil_acesso_id (4 admin, 9 operador; hubloc
  nao tem supervisor hoje). RULES PUBLICADAS: ruleset 21cf3d0c-db57-4c44-aa8a-baa354880687
  (diff = SO o bloco perfis_acesso; backup do faa492f1 commitado em
  firestore.rules.bak-publicado-20260705, commit 6a38330; rollback = re-publicar o .bak).
  Matriz 23/23 no motor real (:test): 16 casos M-A4 (regressao) + 7 perfis_acesso (op le
  proprio/outro perfil do tenant; write nega ate p/ admin; cross-tenant/sem-claim/anon
  negam). Scripts da sessao: publish_mb2_rules.py + test_mb2_rules.py (scratchpad 22aebcf9).
  CANARIO 2026-07-05 ACHOU 1 BUG DE DESIGN (fix f671f88, redeploy 00045-xim): o modal de
  perfis abre com perfil_admin selecionado; admin desligou 2 toggles NELE sem perceber
  (audit permission_change reconstruiu: save no perfil_admin 24s antes do perfil_operador)
  e o guard anti-amplificacao virou RATCHET — admin "sem" o toggle nao podia religa-lo em
  perfil nenhum, reparo so via Admin SDK (feito, com audit op=repair). FIX: perfil de
  sistema (is_system_locked) agora trava TODOS os toggles em ligado (teto do tenant;
  admin limitado = perfil custom base admin) + toggles_beyond_user faz bypass p/ role
  admin (guard segue p/ supervisor delegado). LOCKED_ADMIN_TOGGLES removido.
  ✅ PROMOVIDO PRA PROD 2026-07-06: rev castro-crm-00045-xim a 100% (update-traffic);
  rollback = update-traffic p/ 00041-rij. 1 unico 503 no cutover = quota cpu_allocation
  do Cloud Run (follow-up: quota apertada qdo staging tagged + prod escalam juntos; o 503
  avulso que o usuario viu no canario era o mesmo fenomeno). Commits develop LOCAIS (nao
  pushed): 9fda420/0af0a1c/7d3838e/5a761b3/6a38330/f671f88 + docs.
  PROXIMO: resto pre-#2 (matar _DEFAULT_TENANT=hubloc + AUTO_PROVISION tenant-aware,
  gate dominio allowed_email_domains, storage.rules) -> Cloud Run B minimo -> M-A5 GATE.
  Fase 5 do RBAC (matar fallback de role) = pos-bake-in.

- LOGIN TENANT-AWARE (mata _DEFAULT_TENANT cego + gate 0b) ✅ EM PROD 2026-07-06, rev
  castro-crm-00047-sin (rollback = update-traffic p/ 00045-xim). Fecha bloqueadores 0b
  (gate hubloc-only) e 0c(iii) (mis-provisionamento cego) do pre-#2. Commits develop:
  474515e (core) + 3732ccc (hardening da revisao). RESOLUCAO DE TENANT NO LOGIN (auth.py,
  SEM default cego): claim tenant_id -> dominio do email (tenant.allowed_email_domains) ->
  rede de transicao (tenant_service.single_active_tenant: so enquanto EXATAMENTE 1 tenant
  ativo; ao criar o #2, retorna None e desarma sozinho). Login que nao resolve tenant =
  403 (nunca cai em tenant arbitrario). Gate _login_gate: founder (env ALLOWED_FIREBASE_
  EMAILS) OU claim presente OU dominio casa tenant. AUTO_PROVISION so quando dominio
  resolve tenant E email_verified. tenant_service: allowed_email_domains no schema
  (create/update_tenant, normalizado), resolve_tenant_by_email_domain (None se >1 casa =
  ambiguo), single_active_tenant. hubloc.allowed_email_domains=["hubloc.com.br"]
  backfillado via Admin SDK + RECONCILIADO no boot (bootstrap_tenant seta se vazio;
  startup passa explicito -> duravel em DR). REVISAO ADVERSARIAL (workflow 5 dimensoes ->
  verify, 26 agentes) = 20 sobreviventes / 14 CONFIRMED; criticos corrigidos: (1)
  PROVEDOR PUBLICO (gmail/outlook/...) NUNCA vira allowed_email_domains
  (normalize_email_domains dropa + is_public_email_provider) — senao bootstrap fresh/DR
  derivava do email founder (outlook.com) e QUALQUER conta do provedor auto-provisionava
  como operador (PII cross-tenant); (2) email_verified OBRIGATORIO no auto-provision (o
  Email/Password e publico, signUp alcancavel); (3) env belt-and-suspenders
  (_global_env_domain_match) era ILUSORIO — autorizava entrada sem resolver tenant (gate/
  resolver desacoplados) -> aposentado, robustez vem do reconcile no boot; (4)
  refresh_tenants resiliente a falha (roda no login path de toda request; login por claim
  short-circuita antes); (5) colisao de dominio entre tenants rejeitada. Matriz em memoria
  13/13 (scratchpad/test_login_tenant.py). CANARIO staging (dados reais de prod): admin
  200 sem churn, operador 200 escopo proprio, ESTRANHO rlcastrobh@gmail.com 403 + ZERO doc
  criado (hubloc segue 13 users). Scripts: test_login_tenant.py + workflow review-login-
  tenant-resolution (scratchpad 22aebcf9). FOLLOW-UPS (nao bloqueiam): founder cross-tenant
  SEM claim + 2 tenants -> 403 (intencional: Cloud Run A exige tenant concreto; cross-
  tenant e Cloud Run B; os 3 founders atuais tem claim); cache cross-instance 60s ao criar
  #2 (transiente); guarda-corpo de dominio na UI (backend ja devolve domain_warning no
  admin_create_user; falta dialog de confirmacao no frontend).

- STORAGE / 0c(iv) ✅ RESOLVIDO 2026-07-06 (commit 3b579f6). A pergunta do usuario "esta
  usando storage antigo?" destravou o real quadro: a prod Oregon usa bucket GCS PURO
  `...-castro-crm-media` servido 100% pelo backend (serve_media -> Admin SDK download_as_
  bytes); frontend NAO usa Firebase Storage SDK; NAO ha release firebase.storage/... no
  projeto novo. O storage.rules do repo (whitelist hubloc) so estava publicado no projeto
  ANTIGO (SP). Logo o "bloqueador" nem existia na prod nova. Feito: (1) storage.rules
  reescrito deny-all backend-only (backstop documentado — default do Firebase Storage e
  permissivo); (2) PAP `enforced` no bucket novo (LGPD; midia segue 200); (3) bucket
  Firebase ANTIGO (project-26fb9c99.../.firebasestorage.app, 1487 objs duplicados) LIMPO
  apos PROVA DE COMPLETUDE — 2487/2532 midias do Firestore estao no bucket novo; 45 refs
  ORFAS (10/jun tarde = teste do cutover) sumidas de AMBOS os buckets (nada que a prod usa
  vivia so no antigo); soft-delete 7 dias como rede. Follow-up cosmetico: 45 msgs com
  media_path 404 (nao vale limpar). Decommission do projeto antigo = item a parte.
  >>> PRE-#2 COMPLETO (M-A1, M-A2, M-A4, M-A4b, M-B2, login tenant-aware, storage — tudo
  em prod). PROXIMO = Cloud Run B minimo (D3), escopo ENXUTO SEGURO aprovado 2026-07-06:
  Fase A Sprint 0 (super_admins/{uid} + grant_super_admin.py + log_system_audit +
  audit_logs_system + isSuperAdmin nas rules — HOJE tudo POR CONSTRUIR, so ha comentarios
  preservando o claim super_admin no firebase_admin_client) + Fase B servico separado
  castro-superadmin (require_super_admin: claim+doc+MFA-amr; POST criar-tenant ->
  bootstrap_tenant+audit; UI minima). DEFERIDO no v1: sessao-cookie 15min, dominio proprio,
  sink BigQuery, impersonate. Pre-req manual: founders com MFA/TOTP enrolled. Depois: M-A5
  GATE (ensaio onboarding + auditoria vazamento) -> ligar tenant #2.

- CLOUD RUN B FASE A / SPRINT 0 ✅ FEITO 2026-07-07 (commit 537fcf2). Fundacao super-admin,
  nao toca o Cloud Run A. super_admin.py (super_admins/{uid} root source-of-truth +
  log_system_audit em audit_logs_system/{id} root imutavel que PROPAGA falha);
  firebase_admin_client.set_super_admin_claim (preserva claims, leitura estrita);
  scripts/grant_super_admin.py (--seed/--list/--grant/--revoke; grant exige mfa_enrolled,
  --allow-no-mfa p/ bootstrap). SEED JA EM PROD: 2 founders rafa(uid mbg9JRY86MUADtfja6pi3zxs7Az2)
  + izael(uid dFn2kayBsEOnS7A9BFmbBivNUGt1), is_active=true, mfa_enrolled=false, claim NAO
  concedido (inertes ate o grant pos-MFA). firestore.rules: isSuperAdmin() (claim fast-path,
  CEGO a tenant-scoped) + super_admins/audit_logs_system (read so super-admin, write false),
  PUBLICADO ruleset cb1bd995 (aditivo puro vs 21cf3d0c; backup .bak-publicado-20260705).
  RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md. **BLOQUEIO RESOLVIDO 2026-07-07:** upgrade p/ Identity
  Platform FEITO pelo usuario (Firebase Console -> Authentication -> "Fazer upgrade para
  ativar"); TOTP LIGADO via API (mfa.state=ENABLED, totpProviderConfig adjacentIntervals=5).
  Operadores intactos (prod 200, zero 4xx em /api/session, sem logout). Enrollment do TOTP
  vem no login do Cloud Run B (sem auto-enroll no Console). FASE B DESBLOQUEADA. PROXIMO: Fase B (servico
  castro-superadmin: login + enroll MFA + require_super_admin[claim+doc+MFA-amr] + POST
  criar-tenant->bootstrap_tenant+log_system_audit + UI minima).

- FASE B (Cloud Run B) CONSTRUIDA E DEPLOYADA 2026-07-11 — servico castro-superadmin NO AR
  em https://castro-superadmin-28179318848.us-west1.run.app (rev 00001-4f4). Commits:
  a59736e (backend), a17d0cc (pagina+MFA), + Dockerfile/reqs/cloudbuild. superadmin_main.py
  (FastAPI separado): _authorize(require_mfa) -> require_super_admin (claim+doc+MFA-na-sessao
  via firebase.sign_in_second_factor; SUPERADMIN_REQUIRE_MFA=false so bootstrap) e
  require_super_admin_bootstrap (claim+doc SEM MFA, so pro POST /mfa/enrolled logo apos o
  enroll). Endpoints: POST /api/superadmin/tenants (audit-ANTES-aborta + tenant_exists->409 +
  bootstrap_tenant + warning se admin nao provisionado), GET tenants, whoami, POST
  mfa/enrolled, GET config, /. superadmin_web/index.html = pagina estatica unica (Firebase JS
  SDK CDN 10.12.2; login Google/email; enroll TOTP mostra secretKey base32; resolve 2o fator
  no login; whoami do backend decide painel/enroll/erro). Teste por script 16/16
  (scratchpad/test_superadmin.py). Deploy: SA DEDICADA castro-superadmin-sa (roles datastore.user
  + firebaseauth.admin, so isso); Dockerfile.superadmin MINIMO (11 modulos do fecho de imports +
  pagina, sem main.py/webhook/media/whisper/frontend); build via cloudbuild-superadmin.yaml ->
  AR cloud-run-source-deploy/castro-superadmin; --allow-unauthenticated (auth e o
  require_super_admin no app; IAP=fast-follow). Claim super_admin CONCEDIDO aos 2 founders
  (--allow-no-mfa, bootstrap; refresh revogado). GOTCHA: /healthz retorna 404 preso (cache de
  edge do 1o hit em cold-start; cosmetico, os endpoints reais funcionam). M-A5 ENSAIO VALIDADO
  2026-07-11/12: Rafael logou no B (Google+TOTP enrollado+relogin c/ codigo), criou o tenant
  de teste `ensaio1` (name=Timmy, admin contato@castrointelligence.com.br, dominio
  castrointelligence.com.br). Auditoria server-side OK: doc + audit_logs_system
  (create_tenant_attempt+ok, actor=rafa) + 4 setores default + 3 perfis RBAC + admin com claim
  atomico {tenant_id:ensaio1, role:admin, perfil:perfil_admin} + ensaio1 vazio/isolado (0
  contatos/msgs). ISOLAMENTO CONFIRMADO PELO RAFAEL POR DENTRO: setei senha temp
  (Ensaio-Teste-2026) na conta contato@ (uid PQJB2kRCvqhLx3KR08E9TkRLa2K3, nasceu sem senha),
  ele logou no CRM (Cloud Run A) como admin do ensaio1 -> tenant vazio, sem dados do hubloc
  ("tudo como previsto"). O onboarding ponta a ponta esta PROVADO.
  PENDENTE p/ fechar e ligar o #2 REAL: (1) LIMPAR o ensaio1 (delete tenant+subcolecoes +
  desativar/limpar claim da conta contato@ + revogar token + tirar o dominio de teste); (2)
  REVISAO ADVERSARIAL do servico B (superadmin_main + fluxo MFA) — NAO rodada ainda; mesmo
  padrao que pegou 2 criticos no login e o ratchet no M-B2. So depois: criar tenant #2 real.
  Gotcha aberto: /healthz do B da 404 preso (cache edge cold-start, cosmetico).

- REVISAO ADVERSARIAL DO B (workflow 5-dim, 30 ag) 2026-07-12 = 25 achados (16 CONF). CRITICOS/
  ALTOS CORRIGIDOS (commit a7cc82e, redeploy rev castro-superadmin-00002-7pm): (1) MFA GUARDA
  DURA — no servico deployado (IS_CLOUD_RUN) MFA e SEMPRE exigido, env SUPERADMIN_REQUIRE_MFA=false
  so vale em run LOCAL (fecha 'env mal setado + grant --allow-no-mfa = tenant so com senha'); (2)
  XSS — esc() escapa todo campo do backend antes de innerHTML (lista tenants + gmsg); (3)
  mfa_enrolled VERIFICADO via Admin SDK (enrolled_factors) antes de marcar o flag; (4) kill switch
  imediato — verify_firebase_id_token(check_revoked=True) no B (param novo, A inalterado); (5)
  security headers/CSP (frame-ancestors none/object-src none/base-uri) + audit-after best-effort
  (_audit_after nao mascara resultado) + /healthz nao vaza require_mfa + secret TOTP limpo pos-enroll.
  Teste 18/18. ACEITOS/DOC (residual, baixo, atores confiaveis): SA firebaseauth.admin necessario
  (sem role mais fino); TOCTOU no create (create_tenant re-checa; raro); email-by-tenant precheck
  (limitacao documentada, warning aparece); rules isSuperAdmin claim-only no path client-SDK
  (ninguem usa client-SDK pra ler super_admins/audit; backend agora check_revoked). PENDENTE =
  DECISAO DE INFRA do usuario: --allow-unauthenticated + ingress all sem IAP/rate-limit (a
  auth do app e fail-closed e o unico portao de rede). Opcoes: A) aceitar v1 + IAP fast-follow
  (rec; IAP tem friccao: usa identidade Google, rafa loga com outlook); B) IAP agora (LB +
  Google identity); C) rate-limit in-app. Depois disso: criar tenant #2 REAL.

**DECISAO DE DESIGN — identidade/dominio do tenant (SOFT, fechada 2026-07-03):** o dominio
NAO autoriza acesso (o claim tenant_id autoriza; M-A4 tira a whitelist de email). Guardar
`allowed_email_domains` (LISTA) no doc do tenant, default = dominio do email do admin, EDITAVEL
(admin do tenant e/ou super-admin), so como (1) guarda-corpo ao criar operador de fora do dominio
(avisa, nao bloqueia) e (2) roteamento de login novo sem claim (evita fallback "hubloc" errado do
auth._resolve_tenant_id). SOFT/Forma A: excecao NAO e campo/allowlist — e so o admin criar o
operador mesmo assim (com aviso); os "de fora" sao deriveis. Rejeitada Forma B (extra_allowed_emails
explicito). Pre-req: criar operador pela UI deve SETAR O CLAIM (senao o dominio vira necessario pra
rotear). Detalhe no doc ROADMAP secao "Identidade/dominio do tenant". Entra no escopo do Cloud Run B.

Relacionado: [[project_standard_channel_migration]] (ADR 0007 ja citado la),
[[project_operator_isolation_lgpd]] (wa_messages rules pendente), [[project_oregon_prod_cutover]].
