# Handoff — "Ver como" (impersonate SOMENTE LEITURA)

Branch: `feature/impersonate-readonly` (worktree `C:\Rafael\castro-intelligence-impersonate`, base `develop` @ ff226fb).
Autor do handoff: Claude (sessão de diagnóstico de 2026-10-14). Executor: Codex.
**Não fazer deploy nem push.** Commits locais nesta branch; o merge no `develop` será feito depois, junto com o PO.

**Atualizacao da sessao (2026-10-14): identidade separada e HTTP/polling de 15 s aprovados, implementados e validados localmente.**
O usuario revisou D1 e autorizou implementar a
[arquitetura separada](REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md).
O texto original abaixo fica preservado como historico. O contrato vigente esta nas
secoes 14/16 e no ADR 0014; ele substitui token no UID do alvo e transporte Firestore
direto. **Gate historico do transporte direto reprovado:**
Firestore Emulator 1.22.0/CLI 15.31.0 entregou evento em listener ja aberto 1,259 s apos
expires_at, embora nova consulta fosse negada e fechar registro invalidasse o listener.
Consultas reais Meus/pool de contatos/conversas devolveram backups a normal e preview
(24 observacoes indevidas em 12 formas, prefixos prod/staging apenas do emulador); direct get negou.
Aquele transporte nao cumpriu o contrato. Nao houve verificacao em producao. Conforme
a secao 7 do pedido, o runtime foi congelado antes da revisao. O usuario depois aprovou
o [transporte HTTP de 15 s](REVISAO_IMPERSONATE_TTL_BACKEND.md), vigente na secao 16.
A implementacao HTTP passou os novos gates locais, detalhados na entrega; isso nao
substitui aceite humano em staging. Nenhuma decisao alterada automaticamente. Feature desligada
por default; commits locais somente apos os gates. Sem push, deploy, comandos gcloud ou acesso aos projetos/dados
reais do CRM. Downloads publicos de dependencias/ferramentas e MOTD inicial do CLI nao
usaram credenciais nem APIs de dados CRM. Publicacao/ativacao nao
esta pronta; os resultados e limites estao na [entrega](ENTREGA_IMPERSONATE_READONLY.md).

---

## 0. Leia antes

1. `CLAUDE.md` (raiz) — invariantes que NÃO podem quebrar (isolamento LGPD em 3 camadas, multi-tenant, convenções:
   comentários pt-BR **sem acento**, `# -*- coding: utf-8 -*-`, logger `castro_crm.<modulo>`, nunca logar PII/token,
   feature flag env-driven em `config.py`).
2. `docs/PLANO_RBAC_E_SUPER_ADMIN.md` §5 (rascunho original do impersonate). **Esta spec diverge do §5 em pontos
   fechados abaixo** (seção 3) — onde divergir, vale esta spec.
3. `scripts/e2e_test_staging.py` (~linhas 200–260): já usa `create_custom_token` + `signInWithCustomToken` (REST) —
   referência de API e do requisito de IAM para assinar token.

## 1. Objetivo e motivação

Admin do tenant precisa **ver o CRM exatamente como um operador vê**, sem poder agir em nome dele, para comprovar
relatos ("a conversa some da minha tela"). Caso real que motivou (hubloc, 2026-10-14): a operadora Roberta dizia que
conversas sumiam; na conta admin "aparecia tudo" (janela global top-300 + escopo amplo), na dela não (janela
`assigned_to_uid == uid orderBy last_message_at desc limit 50`). Só deu para provar reproduzindo as queries dela
por script. Com o "Ver como", o admin teria visto na hora.

## 2. Escopo

**Dentro:** admin do tenant inicia uma sessão de visualização, em outra aba, logada COMO o operador-alvo, com faixa
vermelha permanente, **sem nenhuma escrita** (nem as automáticas: marcar como lida, auto-atribuir, last_login), com
expiração curta, auditoria e feature flag.

**Fora:** impersonate com escrita (decisão do PO em 2026-06-02: só leitura); impersonate cross-tenant pelo super-admin
(Cloud Run B); notificação ao usuário impersonado; sink BigQuery.

## 3. Decisões de desenho (fechadas)

| # | Decisão | Por quê |
|---|---|---|
| D1 | O custom token é emitido para o **uid do ALVO**, com os claims dele (`tenant_id`, `role`, `perfil_acesso_id`) + claims de impersonate. | As Firestore rules e os listeners filtram por `request.auth.uid` / `assigned_to_uid == uid` e pelo claim `role`. O rascunho do §5 emitia para o uid do admin — isso mostraria os dados do ADMIN, não do alvo. Fidelidade exige o uid do alvo. |
| D2 | Somente leitura é garantido **no backend** por método HTTP: requisição com token de impersonate e método ≠ GET/HEAD/OPTIONS → **403** antes do endpoint. | As rules já negam toda escrita client-side (`allow write: if false` em 100% das coleções — conferido). Toda escrita passa pelo backend. |
| D3 | Nas leituras (GET) o usuário-alvo tem as **permissões efetivas dele** (fidelidade de UI: abas, botões, Equipe etc.). | `rbac.has_permission` nega TUDO quando o dict do usuário tem `impersonating`/`read_only` (rbac.py:286–293). Se o dict da request carregar essas chaves, a UI perde as abas do alvo (ex.: supervisor sem "Equipe"). Não coloque essas chaves no `current_user`; a trava é a D2. |
| D4 | A aba de impersonate usa **Auth em memória** (`initializeAuth(app, {persistence: inMemoryPersistence})`) e **Firestore com cache em memória** (`memoryLocalCache()`). | O Auth do Firebase persiste por origem e é compartilhado entre abas: logar como o alvo na mesma origem derrubaria a sessão do admin nas outras abas. Cache em memória também evita deixar dados do alvo no IndexedDB (LGPD, máquina compartilhada). Fechar a aba encerra a sessão. |
| D5 | O token vai no **fragmento** da URL (`/#imp=<token>`), é lido no boot e apagado com `history.replaceState` imediatamente. | Fragmento não vai pro servidor/logs. Custom token vale 1h para troca; trate como segredo (mostrar uma vez, nunca logar). |
| D6 | Expiração dura: `imp_exp` (claim) **e** `auth_time` do ID token conferidos a cada request no backend; frontend faz `signOut` no vencimento. Default 30 min (`IMPERSONATE_TTL_MINUTES`). | Claims de custom token persistem nos refresh do ID token — sem checagem server-side a sessão viveria indefinidamente. |
| D7 | Permissão nova no catálogo RBAC: `ver_como_usuario` ("Ver como outro usuário — somente leitura"), seed **só no perfil_admin**. | Mesmo precedente do `ver_monitor_atendimento` (rbac.py:75–78). perfil_admin seed = todos os toggles; docs antigos sem a chave caem no fallback da role (admin → true; demais → false). Rode/considere `_fill_missing_toggles` (listagem admin). |
| D8 | Alvo elegível: mesmo tenant, ativo, com `firebase_uid`, **role ≠ admin**, ≠ o próprio solicitante. Sessão de impersonate não pode iniciar outra (sem aninhamento). | Evita escalada/confusão e loops. |
| D9 | Feature flag `FEATURE_IMPERSONATE` (default **false**) em `config.py`; desligada = endpoint 404 e botão oculto. | Convenção do repo: religar = env, não código. |

## 4. Backend

### 4.1 `config.py`
- `FEATURE_IMPERSONATE = os.environ.get("FEATURE_IMPERSONATE", "false").lower() == "true"`
- `IMPERSONATE_TTL_MINUTES = int(os.environ.get("IMPERSONATE_TTL_MINUTES", "30"))` (clamp 5..60)

### 4.2 `rbac.py`
- Adicionar `("Gestao", "ver_como_usuario", "Ver como outro usuario (somente leitura, suporte)")` ao `PERMISSION_CATALOG`.
  Seed: só perfil_admin (já recebe todas as chaves). NÃO incluir no supervisor/operador.
- Manter o ramo `read_only/impersonating` de `has_permission` (defesa), mas **não** marcar `current_user` com essas
  chaves (D3).

### 4.3 Endpoint `POST /api/admin/impersonate` (`main.py`)
Body `{ "user_id": int, "reason": str }`.
1. `FEATURE_IMPERSONATE` off → 404.
2. Request já é de impersonate (claim `imp`) → 403.
3. `ensure_permission(current_user, "ver_como_usuario")`.
4. `reason.strip()` com ≥ 10 caracteres → senão 400.
5. Alvo via `get_user_by_id(user_id)` no tenant do contexto (nunca cross-tenant): inexistente/inativo → 404;
   sem `firebase_uid` → 409; `role == "admin"` ou alvo == solicitante → 403.
6. Claims do alvo: `get_user_claims_strict(target_uid)` (firebase_admin_client.py) — copiar `tenant_id`, `role`,
   `perfil_acesso_id` (fallback: doc do usuário + `default_perfil_for_role`). Conferir `tenant_id` == tenant do admin.
7. `sid = uuid4().hex`; `exp = now + IMPERSONATE_TTL_MINUTES`.
8. Developer claims: `{"imp": True, "imp_by": <admin id>, "imp_by_uid": <admin uid>, "imp_sid": sid,
   "imp_exp": int(exp.timestamp()), "tenant_id": ..., "role": ..., "perfil_acesso_id": ...}`
   (nomes reservados de custom token: acr, amr, at_hash, aud, auth_time, azp, cnf, c_hash, exp, firebase, iat, iss,
   jti, nbf, nonce, sub — não usar).
9. `token = firebase_admin.auth.create_custom_token(target_uid, developer_claims, app=get_firebase_app())` → decode bytes.
   Envolver em try: falha de assinatura (IAM, seção 7) → 503 com mensagem clara, sem vazar detalhes.
10. Auditoria ANTES de responder: `log_audit(admin_id, "IMPERSONATE_START", f"target={user_id} sid={sid} exp={iso} motivo={reason[:200]}")`.
    Logger: só ids/sid — nunca o token, nunca PII.
11. Resposta: `{ "custom_token", "session_id", "expires_at", "target": {"id", "display_name", "role"} }`.

Opcional (P1, não bloqueante): **uso único** — gravar `impersonation_sessions/{sid}` (tenant-scoped) e, no 1º request da
sessão, carimbar o `auth_time`; requests com o mesmo `sid` e outro `auth_time` → 401 (impede reaproveitar o link dentro da 1h).

### 4.4 Autenticação (`auth.py::authenticate_firebase_token`)
Quando `decoded.get("imp")`:
- Validar `imp_exp > now` **e** `now - auth_time <= TTL (+60s de folga)`; senão 401 "Sessao de visualizacao expirada".
- Resolver o usuário-alvo **sem efeitos colaterais**: NÃO chamar `sync_user_identity`, `update_last_login`,
  `log_audit(LOGIN_SUCCESS_FIREBASE)` nem o caminho de `_resolve_tenant_id` que chama `set_tenant_claims`.
- **Cache de auth**: a chave hoje é `(tenant, firebase_uid)` — a MESMA da sessão real do alvo. Não grave o dict anotado
  nessa chave (use chave separada, ex. `(tenant, uid, "imp", sid)`, ou não cacheie). Senão a sessão real do operador
  passa a ver "impersonation" (ou o inverso).
- Retornar cópia do usuário com `impersonation = {"by": imp_by, "sid": sid, "expires_at": iso}` (sem `read_only`/
  `impersonating`, ver D3).

### 4.5 Trava de escrita (middleware)
No `tenant_context_middleware` (main.py:177 — já decodifica o token e guarda em `request.state.firebase_decoded`):
- `decoded.get("imp")` e `request.method not in ("GET", "HEAD", "OPTIONS")` → `JSONResponse(403, {"detail": "Modo visualizacao: somente leitura"})`
  sem chamar o endpoint; `logger.warning` com `sid`, método e path (sem PII).
- Expirado (D6) → 401 também aqui.
- **Inventário obrigatório:** liste no PR todos os `@app.get` com efeito colateral (escrita no Firestore, `log_audit`,
  envio externo) e bloqueie-os no modo impersonate. Liste também os POST de leitura que o frontend usa em navegação
  passiva (ex.: buscas) — decida caso a caso (allowlist explícita e mínima, documentada).

### 4.6 `/api/session`
Já devolve `user` e `perfil.toggles` (efetivos). Garantir que `user.impersonation` chegue ao frontend e que os toggles
sejam os do alvo (D3). Expor `FEATURE_IMPERSONATE` ao frontend (ex.: `/api/client-config` ou `/api/session`).

## 5. Frontend (`frontend/`)

1. **Boot (`src/firebase.ts`)**: antes de inicializar, ler `window.location.hash`; se tiver `imp=<token>`, guardar o
   token em memória, `history.replaceState` sem o hash, e inicializar com `initializeAuth(app, { persistence: inMemoryPersistence })`
   e `initializeFirestore(app, { localCache: memoryLocalCache() })` (D4). Depois `signInWithCustomToken(auth, token)`.
   Sem `imp`: comportamento atual intacto (`getAuth` + `browserLocalPersistence` + `persistentLocalCache`).
2. **Faixa**: componente fixo no topo (vermelho), em todas as telas: "Visualizando como {nome} — SOMENTE LEITURA —
   expira às HH:MM" + botão "Encerrar" (`signOut` e fechar a aba). `signOut` automático no vencimento.
3. **Sem efeitos automáticos** quando `impersonation` estiver ativo (o backend bloqueia, mas evite ruído/erros):
   - marcar como lida ao abrir conversa (`CrmContext.tsx` ~1800–1830; hoje pulado só com "Só espiar" de gestor) — pular SEMPRE;
   - `/api/wa/conversation/open` (auto-atribuição) e qualquer POST disparado só por navegar;
   - `mark-read` do chat interno (`InternalChatPanel.tsx:107`);
   - compositor, assumir, transferir, fechar, qualificar, editar contato, salvar configurações: desabilitados com tooltip
     "Somente leitura (modo Ver como)".
4. **Tela de Usuários** (`App.tsx`, lista/edição ~2090–2110): botão "Ver como" por usuário elegível (D8), só com
   `can("ver_como_usuario")` e flag ligada. Modal: motivo obrigatório (≥10), aviso LGPD curto ("acesso auditado"),
   "Gerar acesso" → mostra o link `${location.origin}/#imp=${token}` uma única vez, com "Copiar" e "Abrir em nova aba"
   (`window.open(url, "_blank", "noopener")`), e o horário de expiração.
   ⚠️ Não regredir a pegadinha conhecida dessa tela: trocar o Cargo zera o select de Perfil (`setEditPerfilId("")`).
5. `npm run build` (tsc estrito) tem que passar.

## 6. Segurança / LGPD — checklist

- [ ] Nenhum caminho grava em nome do alvo (inclui `last_login`, audit de login, claims, unread, auto-assign).
- [ ] Token nunca aparece em log, URL com query string, localStorage/sessionStorage ou IndexedDB.
- [ ] Sessão expira no servidor (D6) mesmo com refresh de token.
- [ ] Sem cross-tenant; alvo admin bloqueado; sem aninhamento.
- [ ] Auditoria `IMPERSONATE_START` com motivo; bloqueios logados com `sid`.
- [ ] Sessão real do alvo não é afetada (cache de auth separado; nada de `revoke_refresh_tokens` no alvo).
- [ ] A sessão do admin nas outras abas continua logada (D4).
- [ ] **Verificar em staging** que o ID token vindo do custom token traz `email` (as rules usam
      `signedIn()` = `request.auth.token.email != null`). Se não trouxer, incluir `email` do alvo nos developer claims.

## 7. Infra (passo HUMANO — não executar)

`create_custom_token` sem chave de service account (Cloud Run com ADC) assina via IAM `signBlob`. A service account de
runtime do `castro-crm` precisa de `roles/iam.serviceAccountTokenCreator` **nela mesma** e a API
`iamcredentials.googleapis.com` habilitada. Documentar no PR o comando para o humano (projeto Oregon):

```powershell
$SA = gcloud run services describe castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --format="value(spec.template.spec.serviceAccountName)"
gcloud iam service-accounts add-iam-policy-binding $SA --member="serviceAccount:$SA" --role="roles/iam.serviceAccountTokenCreator" --project project-4a851bf9-f475-418c-800
```

## 8. Testes e gates

Ambiente: o venv fica no repo principal. Na raiz da worktree:
`C:\Rafael\castro-intelligence\.venv\Scripts\python.exe <comando>`. Frontend: `cd frontend; npm ci; npm run build`.

1. **Novo** `tools/sim_impersonate.py` (padrão de `tools/sim_reception_flow.py`: Firestore em memória por monkeypatch;
   `firebase_admin.auth.create_custom_token`/`verify_id_token` stubados). Cobrir no mínimo:
   - início OK (claims corretos, audit gravado) e todas as negações da 4.3 (flag off, sem toggle, alvo admin/self/
     inativo/sem uid/outro tenant, motivo curto, aninhado);
   - `authenticate_firebase_token` com claim `imp`: zero escritas (sync/last_login/audit/claims) e cache não poluído
     (uma sessão normal do alvo logo depois NÃO tem `impersonation`);
   - expiração por `imp_exp` e por `auth_time`;
   - middleware: POST/PUT/PATCH/DELETE → 403 sem executar endpoint; GET passa; token normal não é afetado;
   - fidelidade: `effective_toggles` da sessão de impersonate == do alvo (não tudo false).
   Sair com 0/1 como os demais sims.
2. Gates existentes (todos têm que passar): `-m py_compile` da lista do CLAUDE.md + `tools\sim_bot_flow.py`,
   `sim_cx_flow.py`, `sim_reception_flow.py`, `sim_buffer_flow.py`, `sim_pool_wait_notice.py`, `sim_monitor_flow.py`,
   `sim_history_recency.py`.
3. NÃO rodar scripts que tocam Firestore/GCP reais (`scripts/*`, `tools/cx_smoke.py`, `tools/reopen_conciliation.py`).

## 9. Critérios de aceite (validação manual em staging, pelo PO)

1. Admin clica "Ver como" num operador de teste → abre aba com a faixa vermelha e o **mesmo "Meus"** do operador
   (mesmas 50), Novos/pool como o operador vê, sem menus administrativos.
2. Abrir uma conversa NÃO zera o não-lido do operador real (`unread_count` intacto no Firestore).
3. Enviar/assumir/transferir/fechar: desabilitado na UI; forçado via API → 403.
4. A aba normal do admin continua logada como admin (mesmo navegador).
5. Após o TTL a sessão cai sozinha; recarregar a aba não ressuscita.
6. Audit `IMPERSONATE_START` com motivo; `last_login` do operador inalterado; nenhum `LOGIN_SUCCESS_FIREBASE` do alvo.
7. Alvo com cargo supervisor + perfil custom (caso "Roberta": supervisor + `perfil_roberta`) mostra a aba Equipe (fidelidade de toggles).

## 10. Armadilhas já conhecidas (não caia nelas)

- Emitir o token para o uid do admin (§5 antigo) → mostra os dados do admin. Use o uid do alvo (D1).
- `has_permission` nega tudo com `impersonating`/`read_only` no dict → UI sem as abas do alvo (D3).
- Cache de auth com a mesma chave da sessão real do alvo (4.4).
- `authenticate_firebase_token` escreve em toda request não cacheada (4.4).
- Marcar como lida ao abrir e `/conversation/open` (auto-assign) destroem justamente a evidência investigada (5.3).
- Persistência do Auth compartilhada entre abas da mesma origem (D4).
- Claims do custom token sobrevivem ao refresh — expiração tem que ser checada no servidor (D6).
- Outras worktrees (`feature/followup`, `feature/reabertura-publicos`) podem criar ADR com o mesmo número: use **0014**
  e, se colidir no merge, renumere.

## 11. Entregáveis

- Código (backend + frontend) + `tools/sim_impersonate.py`.
- ADR `docs/decisions/0014-impersonate-somente-leitura.md` (decisões D1–D9 e o porquê).
- `CLAUDE.md`: nova linha em "Rodar e validar" (sim novo) e um bullet curto em "Invariantes" (impersonate = token do
  alvo, trava por método no backend, nada de escrita automática, TTL server-side).
- Commits nesta branch (estilo do repo, ex.: `feat(impersonate): ...`). **Sem push, sem deploy.**
- Mensagem final: resumo das mudanças, inventário da 4.5, resultado dos gates, comando de IAM (seção 7) e o roteiro de teste manual (seção 9).

## 12. Adendo autorizado na execucao (2026-10-14)

O inventario anterior a trava encontrou duas premissas incorretas no codigo e uma ambiguidade
entre D2 e a secao 4.5. As divergencias foram explicadas e o usuario autorizou explicitamente
os tres ajustes abaixo. O texto original e as decisoes D1-D9 acima foram preservados;
este adendo registra os complementos aprovados.

1. **Excecao minima a D2:** allowlist de POSTs exclusivamente de leitura, exatamente
   `/api/wa/contacts/picker/search`, `/api/wa/contacts/picker/by-tag` e
   `/api/admin/reopen-batch/preview`. Busca e tag continuam no body por LGPD, sem termo/tag
   em URL ou log. RBAC/escopo/limites seguem os do alvo. Qualquer outro POST continua 403.
2. **Rules de staging:** `firestore.rules` permitia escrita client-side por `emailAllowed()`,
   inclusive no wildcard dos tenants, ao contrario da premissa de D2. Negar escrita com
   claim `imp` em todas essas regras, preservando leitura e comportamento da sessao normal.
   A mudanca local precisa de publicacao humana posterior; nao houve deploy de rules.
3. **Auditoria obrigatoria:** o `log_audit` existente era best-effort e absorvia falhas.
   Adicionar modo estrito opt-in para `IMPERSONATE_START`: sem audit persistido, sem token
   devolvido ao solicitante. Demais callers preservam o comportamento atual.

O inventario completo das 41 rotas GET originais, cadeias de helpers, POSTs de consulta e
efeitos automaticos esta no [ADR 0014](decisions/0014-impersonate-somente-leitura.md),
junto com IAM para humano e roteiro manual ampliado. O unico GET com escrita persistente
propria e `/api/admin/monitor/auditoria` (audit do export), bloqueado no modo visualizacao.
Auth tambem tem efeitos de escrita transversais, eliminados no ramo `imp`.

Uso unico do link/SID (opcional P1 da secao 4.3) nao foi implementado. Continuam pendentes
de validacao humana em staging: claim `email` no ID token do custom token, fidelidade real
dos listeners, isolamento entre abas e guard de escrita nas rules ja publicadas. Nenhum
comando IAM/GCP real foi executado pelo agente. Resultados dos gates locais acompanham
a entrega da implementacao.

## 13. Revisao solicitada antes de nova implementacao

A revisao final identificou que o token do UID real tambem autentica no Firebase Auth,
cujas mutacoes de conta nao passam pelo backend CRM ou pelas rules Firestore. O usuario
escolheu rever D1 com uma identidade separada, preparando primeiro a arquitetura.

O documento [REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md](REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md)
propoe UID temporario por sessao, mapeamento server-side para o alvo, namespace reservado
que nunca entra no fluxo normal, TTL tambem nas rules, escopo estrito por ambiente/tenant,
encerramento da propria sessao e cleanup seguro da conta temporaria. Propoe nao copiar
email/credenciais do alvo para Auth e preserva queries/toggles do alvo no CRM.

Naquela etapa os detalhes eram proposta e os gates do prototipo original (156 asserts)
nao comprovavam o novo contrato. O usuario depois autorizou implementar a revisao;
o resultado atual e os gates correspondentes estao na secao seguinte e na entrega.

## 14. Contrato vigente: identidade separada (aprovado nesta sessao)

1. **D1 substituida:** custom token para `imp_ro_<sha256(prefixo)[:8]>_<sid32>`, nunca
   para o alvo ou admin. Claims incluem `imp_target_uid` e `imp_env`; nao copiam email,
   providers, nome ou credenciais do alvo para Auth. O CRM continua retornando o usuario
   alvo whitelisted, setor e toggles efetivos; as queries Meus/pool mantem o UID do alvo.
2. **Registro obrigatorio:** `tenants/{tenant}/impersonation_sessions/{sid}` no prefixo
   do ambiente, server-only inclusive para clientes normais de staging. Vincula UID
   temporario, alvo, admin, tenant, ambiente, role/perfil, emissao, prazo e estado. Nada
   entra em `_GLOBAL_COLLECTIONS`. Ausencia/divergencia/fechamento/vencimento nega acesso.
3. **Namespace reservado:** UID temporario sem `imp` valido e token `imp` com UID real
   sao rejeitados antes de cache, lookup por email, sync, provisionamento ou claims.
   Provisionamento/link e app B tambem rejeitam esse namespace. Mutacoes Auth afetam
   somente a conta temporaria, sem autorizar nova sessao normal do CRM.
4. **D2 complementada:** os tres POSTs de consulta da secao 12 sao as unicas excecoes
   de leitura. `POST /api/impersonation/end` e uma excecao especifica de ciclo de vida:
   fecha somente a propria sessao de suporte e audita com o admin original como ator.
   Nao aceita alvo/SID arbitrario. Nenhuma escrita CRM em nome do alvo e autorizada.
5. **D4 revista novamente na secao 16:** Auth temporario em memoria e sem cliente Firestore;
   `sessionStorage` guarda apenas marcador `1`
   da aba, sem token ou PII, para reload nao restaurar o admin naquela aba. Encerramento
   limpa estado/requests e descarta respostas atrasadas, faz signOut sem cliente Firestore temporario.
6. **D6 ampliada no desenho inicial, superada pela secao 16:** backend e rules Firestore
   devem conferir prazo absoluto e idade do login.
   Rules resolvem UID efetivo somente depois de validar registro/perfil ativo do alvo;
   sem requisito de email no ramo temporario. Role/perfil alterados invalidam a sessao.
   O ramo normal preserva suas regras. Staging nao concede seu wildcard ao temporario.
7. **Cleanup seguro:** `POST /api/internal/cron/cleanup-impersonation` usa a autenticacao
   de cron existente, inclui tenants inativos e consulta lote limitado por estado/prazo.
   Exclui somente UID reconstruido e registrado, apos duas horas da emissao. Nunca
   delete/revoke/update do alvo. Falhas sao repetiveis e `UserNotFound` e idempotente.
   O cron funciona mesmo com a feature desligada; agendamento sera feito por humano.
8. **Auditoria/rollout:** `IMPERSONATE_START` estrito antes de entregar token; falhas de
   assinatura/audit fecham o registro sem entregar acesso. `FEATURE_IMPERSONATE=false`
   por default. Publicar codigo, rules e indice de cleanup juntos antes de ativar.

Uso unico do custom token continua fora do escopo. Um link reusado nao vence o estado
ou o prazo do registro; excluir a conta cedo nao substitui essa autorizacao. Dados ja
recebidos/copias/capturas nao podem ser retirados remotamente pelas rules.

[Entrega e validacao atual](ENTREGA_IMPERSONATE_READONLY.md): resumo por arquivo,
inventario completo da secao 4.5, gates, comandos IAM exclusivamente humanos e roteiro
manual atualizado. O teste anterior de email Auth do alvo foi substituido por verificar
que a conta temporaria permanece sem email do alvo e que seu UID e diferente do real.

## 15. Historico dos bloqueios: listener depois do prazo e backup nas consultas

Backend py_compile, sete sims existentes, sim_impersonate (244 asserts), npm ci e build
final TypeScript/Vite passaram. O gate de Firestore Emulator 1.22.0 nao passou: listener
ja aberto recebeu evento 1,259 s apos expires_at. Consulta/contexto novo getDocFromServer negou;
fechar o documento de sessao invalidou o listener. A revalidacao por tempo no caminho
direto nao atende o TTL duro aprovado. Isso e uma divergencia do contrato, nao uma
decisao nova aceita. Conforme a secao 7 do pedido, o runtime foi congelado, sem commits,
antes de revisar esse ponto com o usuario. A aprovacao posterior esta na secao 16.
Feature permanece desligada.

Tambem houve 24 observacoes indevidas de backup: 12 consultas reais Meus/pool de contatos
e conversas, nos prefixos prod/staging do emulador, retornaram backup proprio/pool vazio/
pool nulo a operador normal e preview. Direct get de backup negou. E um mismatch LGPD
preexistente reproduzido localmente e herdado pelo modo novo; nao afirmar prod verificado
ou queries fieis aprovadas. Houve 149 verificacoes positivas antes da falha do assert TTL;
o assert de backup fica depois e nao e alcancado nessa execucao. As observacoes vieram
dos probes executados. [Evidencias](../tools/impersonate_emulators/DIAGNOSTICO.md).

Limite adicional preexistente: /media/{subdir}/{filename} nao exige autenticacao e pode
ler chave global GCS/local; URLs conhecidas continuam acessiveis anonimamente depois de
TTL/encerramento. Nao prometer revogacao dessas URLs na validacao manual. Os detalhes,
limites e roteiro futuro estao na entrega. A
[proposta alternativa de leitura por backend](REVISAO_IMPERSONATE_TTL_BACKEND.md)
foi aprovada depois destes achados; o novo contrato esta na secao seguinte.

## 16. Transporte revisado aprovado: HTTP e polling de 15 s

O usuario aprovou explicitamente a revisao de TTL por backend. Este adendo substitui
o transporte Firestore direto e a D6 da secao 14; identidade separada, registro, TTL,
auditoria, tres POSTs de leitura, encerramento e cleanup continuam obrigatorios.

1. Somente a aba temporaria usa cinco GETs `/api/impersonation/view/{snapshot,page,messages,thread,internal-chat}`.
   Nao abre getDoc/getDocs/onSnapshot nem usa fallback Firestore. Sessoes normais mantem
   transporte e queries atuais. Rules negam toda leitura/escrita do temporario, inclusive
   UID reservado sem claim, imp legado, flat, staging, plataforma e registro.
2. Primeira carga/abertura/Atualizar sao imediatas; polling fixo de 15000 ms, sem requests
   sobrepostos. A UI informa intervalo, ultima atualizacao e dados desatualizados.
   Atrasos podem chegar a 15 s; nao se promete realtime.
3. Tenant e UID vem somente da sessao validada. Janelas top50 por mine/pool vazio/pool
   null e top300 global do supervisor sao preservadas, inclusive limites crescentes e
   ordenacao de nao-lidas. Backup e filtrado no servidor antes de entregar, sem reposicao
   de itens mais antigos; campo ausente significa falso. Thread/mensagem tem ownership
   independente do dono do lead. Nenhuma ampliacao por setor, ID ou parametro arbitrario.
4. Allowlist positiva de GETs e parametros, mais os tres POSTs exatos e own-end. Os cinco
   transportes GET antigos e GET auditoria nao sao alternativas para o temporario.
   Validar registro/TTL/alvo na entrada E depois de bufferizar cada resposta de leitura,
   sem memo/cache da autorizacao final. Vencimento/fechamento durante query nega corpo.
5. Browser cancela requests e descarta respostas por geracao/deadline/selecionado; nao
   aplica resposta tardia nem restaura admin no reload. Leitura nao zera unread, nao
   cria/atribui thread, nao sincroniza conta nem escreve no alvo.
6. Novo `tools/sim_impersonate_views.py` cobre mais de50 por target/300 global, backup,
   legado, paginacao/nao-lidas, custom supervisor, IDOR, ordem e ausencia de fallback.
   Sim auth/HTTP cobre fechamento/TTL cruzado antes da entrega, inclusive lookup final,
   perfil estrito e retornos precoces no-store. Todos os gates locais passaram: sim285,
   views92, emuladores779, compile, sete sims existentes, npm ci e build final. A entrega
   registra resultados/limites; commits locais autorizados ficam registrados no Git.

O mismatch de backup das sessoes normais permanece preexistente e fora desta revisao;
nao foi verificado em producao. Polling nao revoga URLs anonimas de midia ja conhecidas,
copias ou capturas. A consulta indexada de backup do supervisor preserva o target
original sem cap; polling repete leituras a cada15s. A revisao aprovada explicita o
envelope teorico e exige avaliar custo/latencia antes da ativacao humana. Nenhum desses
limites autoriza reduzir janelas ou alterar sessoes normais silenciosamente.
