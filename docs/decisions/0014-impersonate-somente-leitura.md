# ADR 0014 - Ver como: impersonate somente leitura

**Data:** 2026-10-14. **Status:** identidade separada e HTTP/polling de 15 s aprovados, implementados e validados localmente. Feature desligada por default; publicacao e staging posteriores.
**Spec:** [HANDOFF_IMPERSONATE_READONLY.md](../HANDOFF_IMPERSONATE_READONLY.md).

O usuario aprovou substituir a autenticacao no UID real do alvo por identidade separada,
conforme a [revisao de arquitetura](../REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md).
**Historico do transporte direto, anterior ao contrato HTTP vigente:** Firestore Emulator
1.22.0/CLI 15.31.0 entregou evento em listener aberto 1,259 s apos expires_at; nova consulta
foi negada e fechar o registro invalidou o listener. Aquele transporte foi reprovado.
As 12 consultas reais Meus/pool de contatos/
conversas retornaram backups para operador normal e preview (24 observacoes indevidas nos prefixos
prod/staging do emulador), embora direct get negasse. Isso reproduz mismatch LGPD
preexistente herdado pelo modo novo localmente; nao afirma vazamento em producao nem
aprova fidelidade dessas queries. [Evidencias](../../tools/impersonate_emulators/DIAGNOSTICO.md).
Conforme a secao 7 do pedido, o runtime foi congelado antes de revisar D6. O usuario
depois aprovou [HTTP e polling15s](../REVISAO_IMPERSONATE_TTL_BACKEND.md): o temporario
nao le Firestore diretamente; backend filtra escopo/backup e revalida cada corpo na
saida. Todos os novos gates locais passaram: compile, sete sims existentes,
sim285/views92, emuladores779, npm ci e build final. Runtime/testes no commit local
16e4fd4; documentacao em commit separado, com historico no Git. Publicacao, ativacao
e aceite de staging continuam posteriores. Sessoes normais
preservam seus listeners; o mismatch normal de backup fica como pendencia preexistente.
A D1 original foi apenas um prototipo local, nunca publicado, e esta superada: autenticar
o UID real permitiria mutacoes na conta pelo Firebase Auth, fora do middleware/rules CRM.

## Contexto

O admin precisa reproduzir o CRM do operador para investigar relatos de conversas que somem.
A conta administrativa consulta uma janela global e tem escopo diferente do operador, cuja
caixa Meus usa o proprio UID e limite inicial de 50 threads. Visualizar pela conta do admin
nao reproduz essa evidencia. A visualizacao deve preservar nao-lidos, atribuicoes, identidade,
last_login e a sessao real tanto do alvo quanto do admin.

## Decisoes D1-D9

| # | Decisao | Motivo |
|---|---|---|
| D1 revisada | Emitir custom token para UID temporario `imp_ro_<sha256(prefixo)8>_<sid>`, diferente do admin/alvo. Claims `imp`, `imp_target_uid`, `imp_env`, `imp_by`, `imp_by_uid`, `imp_sid`, `imp_exp`, tenant, role e perfil vinculam-se ao registro autoritativo. | Firebase Auth autentica apenas a conta descartavel; backend autoriza o escopo do alvo, rules negam acesso temporario direto. |
| D2 | Negar metodos diferentes de GET/HEAD/OPTIONS no middleware, antes do endpoint; bloquear tambem GETs com escrita. Preservar somente os tres POSTs de leitura enumerados abaixo e o encerramento exato da propria sessao de suporte. | A seguranca independe da UI. Encerramento altera apenas metadados/auditoria de suporte; nao e uma permissao generica de escrita. |
| D3 | Manter permissoes efetivas do alvo nas leituras; retornar `user.impersonation`, sem marcar `read_only` ou `impersonating` no usuario. | Esses dois marcadores fazem `rbac.has_permission` negar tudo e eliminariam abas que o alvo realmente possui. |
| D4 revisada no transporte | Auth temporario em memoria e db=null, sem cliente Firestore temporario. Persistir em sessionStorage somente marcador de aba `1`, sem token, UID, nome ou dado CRM. | Evita trocar o admin em outras abas/persistir dados ou cair em Firestore; reload da aba marcada nunca restaura silenciosamente o Auth local do admin. |
| D5 | Transportar o custom token em `/#imp=<token>`, consumir no boot e apagar imediatamente com `history.replaceState`. | Fragmento nao chega ao servidor. O segredo nao vai a query string, logs ou armazenamento persistente. |
| D6 revisada | Validar registro, `imp_exp`, idade de `auth_time` e alvo no inicio E antes de entregar cada corpo HTTP bufferizado, sem memo final; polling fixo15000ms. Rules negam todo SDK/REST temporario antes/depois do prazo. TTL30min limitado5..60, folga60s so na idade do login. UI cancela requests, limpa estado e descarta respostas tardias. | Refresh/reuso nao renova autorizacao; query lenta nao entrega dados apos expirar/fechar. Sessoes normais mantem Firestore realtime. |
| D7 | Criar toggle `ver_como_usuario`, seed somente no `perfil_admin`. | Autoriza suporte explicitamente, preservando o fallback por role para docs sem a chave. Supervisor/operador nao recebem a permissao no seed. |
| D8 | Alvo ativo, mesmo tenant, com Firebase UID, diferente do solicitante e com role diferente de admin. Proibir aninhamento. | Evita cruzamento de tenant, escalada e confusao entre sessoes de suporte. |
| D9 | `FEATURE_IMPERSONATE=false` por default, centralizada em `config.py`; off retorna 404 no inicio e oculta o botao. | Rollout depende de configuracao explicita, conforme a convencao de feature flags do repo. |

O endpoint valida motivo com pelo menos 10 caracteres, claims estritos e correspondencia
entre alvo CRM, claims e operator_profile ativo. Role/perfil desatualizados recebem 409;
tenant divergente e rejeitado. Registra sessao, assina para UID temporario e exige auditoria
antes de responder. O link fica apenas na memoria do modal; logs tecnicos usam IDs/SID,
sem token, nome, email ou motivo. Nenhum atributo/credencial do alvo e copiado para Auth.

Autenticacao de `imp` ou UID reservado nunca cai no fluxo normal. Primeiro valida sujeito,
ambiente, tenant, registro e prazo; depois resolve `imp_target_uid` e retorna a whitelist
enriquecida de get_user_by_id. Sem sync, auto-provisionamento, last_login, audit de login,
atualizacao de claims ou cache da sessao real. `user.firebase_uid` continua sendo o do alvo;
`user.impersonation.auth_uid` identifica o login temporario. Nenhuma conta/token real e alterado.

## Revisao de transporte aprovada apos o diagnostico

As cinco leituras HTTP exclusivas do temporario sao snapshot, page, messages, thread e
internal-chat sob `/api/impersonation/view/`. Tenant, UID, role e perfil sao derivados
da sessao; nenhum seletor de identidade/colecao/query arbitrario e aceito. Parametros
desconhecidos sao rejeitados. A allowlist positiva possui39 templates GET, alem dos tres
POSTs de leitura e own-end. Os cinco transportes antigos e GET auditoria sao negados.

`impersonation_views.py` preserva top50 por mine/pool vazio/pool null e top300 global
para canSeeAll (role privilegiada E toggle). Limites crescentes e unread desc/recencia
desc mantem a origem; backup e removido antes de normalizar/entregar, sem reposicao
silenciosa. Campo is_backup ausente significa falso. `mine_load_more` preserva somente
o booleano do gate Meus da uniao bruta/deduplicada dos targets, incluindo ownership
numerico legado, sem expor IDs/arrays dos backups removidos. Thread e mensagens
validam ownership independente do dono do lead; protocolo usa o mesmo filtro.

O cliente temporario usa polling fixo15s e informa ultima atualizacao/desatualizado,
sem fallback para SDK mesmo offline/falha HTTP. Normal continua Firestore/realtime.
Backend bufferiza leituras e reautentica sem memo, rele registro e confere relogio apos
os awaits finais; query ou lookup que cruza prazo/fechamento nao entrega o corpo. UI
cancela fetches e descarta resposta tardia por geracao/deadline/selecionado.

Polling repete leituras. Envelope teorico de snapshot: operador ate150contatos+
150threads; supervisor canSeeAll ate200contatos e50+50+50+300+Nbackup threads, sem dedupe
de cobranca e sem medicao real. O target backup indexado original nao tem cap. Avaliar
custo/latencia antes de ativar; nao reduzir janelas silenciosamente. O mismatch de
backup das sessoes normais e as URLs conhecidas de midia anonima permanecem limites
preexistentes fora da revisao. Novo sim de janelas e emuladores deny-all sao gates
obrigatorios; resultados vigentes estao na entrega.

## Ajustes autorizados apos o inventario

O usuario autorizou explicitamente estes tres ajustes, depois de informadas as divergencias
entre a premissa do handoff e o codigo existente. Eles complementam a spec original.

1. **Allowlist exata de POSTs exclusivamente de leitura:**
   `/api/wa/contacts/picker/search`, `/api/wa/contacts/picker/by-tag` e
   `/api/admin/reopen-batch/preview`. A revisao posterior acrescentou apenas o encerramento
   proprio descrito abaixo; demais POSTs e PUT/PATCH/DELETE continuam bloqueados.
   Nao ha excecao por prefixo, substring ou body. Estes endpoints mantem
   autenticacao, RBAC, isolamento e limites atuais; liberar o metodo nao concede permissao.
2. **Guard de escrita nas rules de staging:** elas antes permitiam `read, write` por
   `emailAllowed()`, inclusive no wildcard de subcolecoes de tenants. Separar a leitura da
   escrita foi o primeiro ajuste. A revisao agora exclui UID reservado e token `imp` de
   todos os grants normais, inclusive flat, wildcard e plataforma. A revisao HTTP nega
   toda leitura/escrita temporaria direta. UID real com `imp` e UID temporario sem contrato sao negados.
   O comportamento normal atual e preservado. Middleware sozinho nao protege SDK/REST.
3. **Auditoria estrita opt-in:** `log_audit` era best-effort e absorvia falhas. Acrescentar
   parametro keyword-only `strict=False`, usando `strict=True` para `IMPERSONATE_START`
   e preservando o default dos outros callers. Falha
   na gravacao impede devolver o custom token; nao se inicia suporte sem registro auditado.

Busca e filtro por tag continuam POST porque nome/telefone e tag potencialmente sensivel
nao podem ir a URL/log do Cloud Run. Converte-los para GET com query string regrediria a
protecao LGPD do picker. A previa do lote e leitura; o disparo do lote permanece bloqueado.

## Registro, encerramento e limpeza da identidade temporaria

`impersonation.py` persiste `impersonation_sessions/{sid}` sob o tenant e prefixo do
ambiente; a colecao nao entra em `_GLOBAL_COLLECTIONS`. Registro e claims precisam
coincidir em UID autenticado, alvo, solicitante, tenant, ambiente, role/perfil e prazo.
Status fechado, vencimento, doc ausente ou falha de validacao impedem leitura. O cliente
nao le nem escreve o registro diretamente. O backend tambem confere perfil ativo;
mudanca de role/perfil invalida a sessao, enquanto toggles do mesmo perfil seguem ao vivo.

`POST /api/impersonation/end`, sem body ou SID/alvo arbitrario, fecha somente o registro
da propria credencial validada e audita `IMPERSONATE_END` com o admin original como ator.
Esta e uma excecao exata para o ciclo de suporte, separada dos tres POSTs de leitura.
O frontend bloqueia novas leituras imediatamente, tenta o endpoint antes de signOut e
cancela fetches e descarta estado/respostas tardias. Falha/timeout de rede encerra a aba localmente e avisa
que a revogacao no servidor nao foi confirmada antes do TTL original.

`POST /api/internal/cron/cleanup-impersonation` exige a autenticacao de cron existente;
nao e liberado para tokens de visualizacao. Funciona com a flag desligada. Consulta
por tenant, inclusive inativos: `status in [active, closed]`, `cleanup_after <= now`,
ordenacao `cleanup_after` e limite de lote. O indice composto esta em firestore.indexes.json.
Cleanup comeca duas horas apos emissao, depois da janela de troca do custom token.
Exclui somente o auth_uid gravado e reconstruido do ambiente/SID, diferente dos UIDs
reais; UserNotFound e idempotente. Falha permite retry; somente sucesso marca `cleaned`.
Tombstones nao entram nos proximos lotes; retencao posterior ainda depende de politica humana.
Nao ha scan de contas Auth nem exclusao/revogacao de UID do admin ou alvo.

Falhas parciais na emissao nao entregam token; o registro e fechado em compensacao
best-effort e continua elegivel para cleanup. Nao existe transacao entre Auth e Firestore.

## Inventario obrigatorio do handoff, secao 4.5

Inventario realizado **antes da trava**: 41 `@app.get` de `main.py`, helpers transitivos e
POSTs usados pelo frontend. O app A nao inclui routers adicionais; `superadmin_main.py`
e o app B separado, fora do escopo de impersonate. Referencias abaixo usam simbolos para
continuarem validas apos a insercao do endpoint.

### GET com escrita persistente propria

| Rota | Cadeia | Tratamento |
|---|---|---|
| `/api/admin/monitor/auditoria` | `main.monitor_auditoria` -> `database_firestore.log_audit`: grava `MONITOR_AUDITORIA_EXPORT` em `audit_log` depois de gerar o arquivo. | Negar em impersonate antes do endpoint, inclusive HEAD e barra final. A UI evita iniciar o download. |

### GETs com acesso externo de leitura

| Rota | Cadeia | Efeito e tratamento |
|---|---|---|
| `/api/wa/templates` | `main.wa_list_templates` -> `_load_approved_templates_for_channel` -> `channel_service.get_send_credentials` -> GET Meta `message_templates`. | Leitura externa e cache RAM; permitido. O helper de credenciais pode recarregar o cache de canais do Firestore, mas nao renova/grava tokens. |
| `/api/wa/channel/{channel_id}/billing-status` | `main.channel_billing_status` -> `_fetch_channel_billing_status` -> GET Meta WABA. | Leitura externa e cache RAM; permitido. Nao grava o health-check do cron. |
| `/api/gc/spaces` | `main.gc_list_spaces` -> `google_chat.list_spaces` -> `spaces.list().execute()`. | Consulta Google Chat, sem envio de mensagem; permitido. |
| `/media/{subdir}/{filename}` | `main.serve_media` -> `media.get_media_asset`. | Leitura de Firestore/GCS/local; permitido. Sem upload, escrita ou auditoria. |

Limite preexistente dessa ultima rota: nao exige get_current_user, e o fallback GCS/local
usa chave global. Uma URL conhecida pode ser consultada anonimamente apos TTL ou fim;
middleware de impersonation nao revoga esse acesso sem Authorization. Nao foi alterado
o fluxo normal de midia nesta tarefa e nao se deve prometer revogacao dessas URLs.

### Efeito transversal da autenticacao

Todos os GETs protegidos dependem de `main.get_current_user` ->
`auth.authenticate_firebase_token`. O caminho normal nao cacheado pode gravar identidade,
last_login, `LOGIN_SUCCESS_FIREBASE` e claims de tenant. O ramo `imp` elimina esses efeitos
conforme a secao 4.4; bloquear uma lista de GETs sem corrigir auth seria insuficiente.
O cache normal `(tenant, firebase_uid)` nao recebe o dict com `impersonation`.

### Demais 36 GETs: somente leitura propria

| Grupo | Rotas revisadas |
|---|---|
| Shell e verificacao | `/`, `/chat`, `/app`, `/webhook` |
| Sessao e catalogos | `/api/session`, `/api/client-config`, `/api/admin/roles`, `/api/admin/perfis-acesso`, `/api/settings/system`, `/api/settings/user`, `/api/wa/qualifications`, `/api/departments`, `/api/operators` |
| Contatos e threads | `/api/wa/contacts`, `/api/wa/contacts/all`, `/api/wa/contacts/picker`, `/api/wa/conversations`, `/api/wa/messages/{contact_id}`, `/api/wa/contact/{contact_id}`, `/api/wa/transfer-history/{contact_id}` |
| Administracao e lote | `/api/admin/reopen-batch/{batch_id}`, `/api/admin/channels`, `/api/admin/conflicts`, `/api/admin/protocol/{protocol_id}`, `/api/admin/pending-webhook-events`, `/api/admin/export`, `/api/admin/embedded-signup/config` |
| Chat interno | `/api/gc/conversations`, `/api/gc/messages/{conversation_id}` |
| Dashboard e monitor | `/api/admin/dashboard/summary`, `/api/admin/dashboard/ratings`, `/api/admin/monitor/fila`, `/api/admin/monitor/metricas` |
| Usage | `/api/wa/usage/current-month`, `/api/wa/usage/history`, `/api/wa/usage/{year_month}` |

`rbac.list_perfis` -> `_fill_missing_toggles` completa somente o dict da resposta, sem
backfill. `get_system_settings`, `get_user_settings` e getters de usage devolvem defaults
em memoria quando nao existe doc. `reopen_batch_status` sinaliza worker interrompido apenas
no dict devolvido, sem persistir a alteracao. Filas/metricas do monitor usam caches RAM.

### POSTs de leitura usados na navegacao

| Rota | Caller frontend | Helpers e efeitos | Decisao |
|---|---|---|---|
| `/api/wa/contacts/picker/search` | `CrmContext.pickerSearch` | `picker_contacts_query`, point-reads de contato/indice e `enrich_picker_rows`; throttle RAM e logs somente de contagens. | Allowlist exata aprovada. Termo continua no body. |
| `/api/wa/contacts/picker/by-tag` | `CrmContext.pickerByTag` | `get_system_settings`, `picker_contacts_query` e `enrich_picker_rows`; throttle RAM e logs somente de contagens. | Allowlist exata aprovada. Tag continua no body. |
| `/api/admin/reopen-batch/preview` | `ReopenBatchModal.loadPreview`, executado ao abrir o modal | `_reopen_classify_for_preview` -> `_plan_reopen_batch` -> scan Firestore e leitura de templates Meta; `_reopen_daily_cap` le contadores/lotes. Apenas cache/locks RAM. | Allowlist exata aprovada. Nao executa `_run_reopen_batch`. |

### POSTs automaticos de navegacao que escrevem

| Rotas | Efeito | Tratamento |
|---|---|---|
| `/api/wa/contact/{contact_id}/read`, `/api/wa/conversation/{conversation_id}/read` | Zera nao-lidos e recomputa derivado. Disparados pelo effect de abertura no `CrmContext`. | Pular na aba de visualizacao, sem update otimista; middleware nega se forcados. |
| `/api/wa/conversation/open` | Pode criar/atribuir thread e auditar. Chamado por `CrmContext.openConversationForContact`. | Pular escrita e consultar somente thread existente via `/api/impersonation/view/thread`; backend deriva ID canonico e confere ownership/backup. Nenhum getDoc temporario ou criacao de thread. Middleware nega o POST. |
| `/api/gc/mark-read/{conversation_id}` | Zera nao-lido interno ao selecionar conversa no `InternalChatPanel`. | Pular na aba de visualizacao; middleware nega se forcado. |

Envio, transcricao, assumir, transferir, fechar, qualificar, editar, salvar configuracoes,
signups e demais mutacoes continuam bloqueados pelo metodo e desabilitados na UI.

## Alternativas rejeitadas

- Token para o UID real do alvo (D1 original): entrega a conta de login ao cliente;
  mutacoes diretas no Firebase Auth contornam middleware e rules do CRM.
- Token para o UID do admin: reproduz a identidade e o escopo errados.
- Gravar `read_only`/`impersonating` no usuario: destrui fidelidade dos toggles.
- Somente desabilitar botoes: chamadas diretas e efeitos automaticos continuariam escrevendo.
- Auth/cache persistentes na aba do alvo: alteram outras abas e deixam dados em disco.
- Expirar apenas no frontend ou somente pelo ID token: refresh preserva os claims de suporte.
- Permitir qualquer POST de aparencia consultiva: amplia a superficie sem inventario.
- Transformar busca/tag em query GET: exporia PII e dado potencialmente sensivel na URL.
- Aceitar auditoria best-effort para inicio: uma falha deixaria acesso sem trilha persistida.

## Operacao e limites

Nao ha deploy, publicacao de rules, push, comandos gcloud nem acesso aos projetos/dados
reais do CRM nesta implementacao. Downloads publicos de ferramentas/dependencias e MOTD
inicial do CLI nao usaram credenciais ou APIs de dados CRM; testes de servicos usaram emuladores locais.
`FEATURE_IMPERSONATE` continua desligada por default. Publicar codigo e rules e uma etapa
humana posterior; o guard de staging so vale no ambiente depois da publicacao das rules.

Uso unico de `imp_sid` e opcional P1 e **nao foi implementado**. O mesmo custom token/link
pode ser trocado mais de uma vez dentro da validade do Firebase; registro fechado ou
vencido impede recuperar acesso CRM. Nenhum refresh/reuso estende o prazo original.
Nao compartilhar nem persistir o link. Reload da aba marcada mostra sessao encerrada,
sem restaurar a visualizacao ou carregar o Auth persistido do admin.

O token temporario nao precisa de email: sua prova e UID reservado, claims e registro
valido. Nunca incluir o email do alvo como contorno. Grants normais ainda exigem email.
Auth permanece sem nome, telefone, senha ou providers copiados do alvo. Antes de ativar,
conferir por procedimento humano que o namespace reservado nao pertence a conta real.

Rules negam todo acesso temporario direto antes/depois do prazo, inclusive SDK/REST e
listener. Backend revalida antes do corpo e UI revalida prazo em focus/visibility/online.
Isso nao apaga dados ja recebidos nem capturas/copias; URLs anonimas de midia conhecidas
continuam fora da revogacao. `Cache-Control: private, no-store` cobre
respostas da visualizacao, incluindo erros, alem dos endpoints que entregam/encerram acesso.

O codigo, rules e indice sao locais. Publicacao, agendamento do cron e teste humano
continuam pendentes; resultados locais detalhados acompanham o relatorio de entrega.

### IAM: passo humano, nao executado pelo agente

Com ADC no Cloud Run, `create_custom_token` usa IAM `signBlob`. A API
`iamcredentials.googleapis.com` precisa estar habilitada, e a service account de runtime
precisa de `roles/iam.serviceAccountTokenCreator` nela mesma. Comando do handoff, projeto
Oregon, **somente para um humano rodar**:

```powershell
$SA = gcloud run services describe castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --format="value(spec.template.spec.serviceAccountName)"
gcloud iam service-accounts add-iam-policy-binding $SA --member="serviceAccount:$SA" --role="roles/iam.serviceAccountTokenCreator" --project project-4a851bf9-f475-418c-800
```

## Roteiro manual em staging, pelo PO

1. Admin inicia Ver como num operador de teste: faixa vermelha permanente, mesmo Meus
   (janela inicial de 50), Novos/pool e menus do alvo. Motivo e obrigatorio e acesso auditado.
2. Abrir conversa preserva `unread_count` da thread e derivado do contato no Firestore.
3. Enviar, assumir, transferir e fechar estao desabilitados; forcados via API retornam 403.
4. A aba normal do admin permanece autenticada como admin no mesmo navegador.
5. No TTL ocorre signOut/terminate automatico e limpeza de estado. Reload nao restaura
   impersonate nem admin nessa aba. Query ou lookup final que cruza `imp_exp`/end nega
   payload; SDK/REST/listener direto temporario e negado desde o inicio.
6. Conferir `IMPERSONATE_START` com motivo e SID; last_login do alvo intacto, sem
   `LOGIN_SUCCESS_FIREBASE` emitido pela visualizacao. Falha simulada de audit impede acesso.
7. Supervisor com perfil custom mostra a aba Equipe conforme seus toggles efetivos.
8. Com as rules ja publicadas por humano, negar toda leitura/escrita direta temporaria
   via SDK/REST em tenant, outro ambiente, flat, wildcard staging e plataforma. HTTP
   respeita escopo de contato/thread e backup; sessao normal
   mantem sua politica; UID temporario sem `imp` e UID real com `imp` antigo sao negados.
9. Busca, filtro por tag e previa do lote funcionam com os POSTs exatos; POST arbitrario
   continua negado. Exportar auditoria do monitor retorna 403 antes de gerar audit/export.
10. UID autenticado e temporario e diferente do admin/alvo; nome/email da UI vem de
    /api/session. Nenhum atributo/credencial do alvo foi copiado para Auth; seus dados,
    conta e metadados de login continuam intactos. Storage da aba contem somente marcador
    nao secreto, sem token/UID/PII; Auth temporario em memoria e db=null sem Firestore temporario.
11. Encerrar fecha a propria sessao no servidor e grava IMPERSONATE_END pelo admin original.
    Se faltar rede, a aba encerra localmente e informa a ausencia de confirmacao remota.
    Retomar aba suspensa e concluir resposta atrasada nao repovoa dados depois do fim.
12. Confirmar o cron e indice publicados por humano; cleanup somente de registros vencidos
    depois de duas horas, incluindo tenants inativos, com retries e sem tocar contas reais.
13. Aba temporaria informa15s, ultima atualizacao e falha/desatualizado, sem requests
    sobrepostos nem fallback Firestore. Confirmar mais de50 por target/300global,
    paginacao, nao-lidas, timestamps empatados e gate Meus com ownership numerico legado.

Os gates locais e seus resultados devem ser registrados na entrega da implementacao;
esse roteiro depende de ambiente publicado e nao foi executado pelo agente.
Os criterios antigos de listener apos TTL e backup falharam no emulador; a revisao HTTP
foi aprovada depois desse diagnostico. Gates novos constam na entrega. Nenhum deles
substitui o aceite de staging ou verifica producao. Na validacao manual, testar tambem
URL de midia conhecida sem Authorization e registrar seu limite anonimo preexistente.
