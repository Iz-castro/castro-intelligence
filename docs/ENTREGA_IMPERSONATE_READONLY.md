# Entrega - Ver como somente leitura com identidade separada

Data: 2026-10-14. Branch: `feature/impersonate-readonly`, base `develop`.
Runtime e testes: commit local `16e4fd4` (`feat(impersonate): adicionar visualizacao isolada somente leitura`).

**Revisao HTTP/polling de 15 s implementada e validada localmente; todos os gates passaram.**
Na etapa anterior, backend, simuladores e build frontend passaram, mas o Firestore Emulator 1.22.0
(CLI 15.31.0) entregou evento a listener ja aberto 1,259 segundo depois de `expires_at`.
Nova consulta/contexto `getDocFromServer` foi negada; fechar registro invalidou listener.
As 12 consultas reais Meus/pool de contatos/conversas, nos prefixos prod/staging,
devolveram backups de dono proprio/pool vazio/pool nulo para operador normal e preview:
**24 observacoes de entrega indevida**. Leitura direta de backup foi negada. Sao achados locais do emulador,
sem verificacao em producao; nao ha aprovacao de fidelidade/isolamento dessas queries.
Esse transporte direto nao cumpriu o contrato. [Evidencia e reproducao historicas](../tools/impersonate_emulators/DIAGNOSTICO.md).

Conforme a secao 7 do pedido, o runtime foi congelado e a divergencia foi apresentada.
O usuario depois aprovou [leituras por backend e polling de 15 s](REVISAO_IMPERSONATE_TTL_BACKEND.md).
O temporario deixa de ler Firestore diretamente; backend filtra backup e revalida a
autorizacao antes de entregar cada resposta. Sessoes normais permanecem no transporte
atual, com a pendencia preexistente de backup. Backend, simuladores, emuladores e build
frontend final passaram. Feature desligada por default; runtime/testes no commit acima,
documentacao em commit local separado. Sem push, deploy, comandos gcloud,
publicacao de rules/indices ou acesso aos projetos/dados
reais do CRM. Houve downloads publicos de dependencias, JRE/JAR e leitura inicial de MOTD
publico pelo CLI, sem credenciais ou APIs de dados do CRM. Artefatos de ferramentas locais
ficam ignorados; o harness atual restringe rede a loopback, exceto artefatos publicos.

Contrato aprovado: [revisao de identidade separada](REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md),
[handoff e adendos](HANDOFF_IMPERSONATE_READONLY.md) e [ADR 0014](decisions/0014-impersonate-somente-leitura.md).
A D1 original do handoff foi substituida: o custom token autentica uma identidade
temporaria, nunca a conta Firebase do operador-alvo.

## Mudancas por arquivo

| Arquivo | Mudanca |
|---|---|
| `.gitignore` | Exclui cache npm local usado na validacao; dependencias e artefatos temporarios nao entram nos commits. |
| `.gcloudignore` | Exclui o harness de emuladores do pacote de deploy do runtime. |
| `impersonation_identity.py` | Contrato puro do namespace `imp_ro_`, UID por hash do ambiente/SID, validacao dos claims e erro especifico para impedir provisionamento de identidades temporarias como usuarios reais. |
| `impersonation.py` | Registro tenant-scoped antes da assinatura; validacao sem cache/escrita, encerramento monotono e cleanup indexado com verificacoes antes de apagar somente a conta temporaria registrada. |
| `config.py` | Flag `FEATURE_IMPERSONATE=false`, TTL default 30 minutos limitado a 5..60 e polling temporario fixo de 15000 ms. |
| `rbac.py` | Toggle `ver_como_usuario`, seed somente admin; preview le perfil estrito sem cache normal, reutiliza snapshot no contexto da request e confere mudanca antes de entregar; normal preservado. |
| `auth.py` | Rejeita UID reservado sem contrato e token legado com UID real; valida registro/TTL, devolve whitelist enriquecida do alvo e metadata de suporte, sem sync, login audit, last_login ou cache do alvo. |
| `main.py` | Emissao para UID separado, registro e auditoria estrita; cinco GETs, allowlist positiva de rotas/parametros, perfil estrito no contexto e reautenticacao final sem memo; guards legados de canal/tenant/backup/protocolo/payload global; own-end, cron e no-store inclusive erros precoces. |
| `impersonation_views.py` | Queries com tenant/UID derivados da sessao; janelas originais por target/global, paginacao e nao-lidas; filtra backup/IDOR antes de entregar, Timestamp no formato SDK (UTC/milissegundos), strings legadas e ordem estavel preservadas, nenhum fallback amplo/escrita. |
| `database_firestore.py` | Auditoria estrita opt-in; bloqueia associacao de UID temporario a usuario/perfil CRM. |
| `pending_events.py` | Consulta por phone_id de canais visiveis, filtra cada change do batch pelo vinculo e remove detalhes globais/erros antes da resposta temporaria. Caminho normal preservado. |
| `firebase_admin_client.py` | Guards nos caminhos normais de claims, lookup/provisionamento e revogacao para o namespace reservado. Cleanup usa API especifica no servico de sessoes. |
| `tenant_bootstrap.py` | Propaga erro de identidade reservada em vez de cair no provisionamento local de fallback. |
| `superadmin_main.py` | Nega namespace temporario e tokens `imp` antes de ler permissoes da plataforma; sem impersonate cross-tenant. |
| `firestore.rules` | Nega toda leitura/escrita ao temporario, UID reservado sem claim e imp legado em todos os grants; sessoes normais preservadas. Emulador: 779 verificacoes aprovadas. |
| `firestore.indexes.json` | Indice `impersonation_sessions`: `status ASC`, `cleanup_after ASC`, escopo `COLLECTION`. |
| `frontend/src/firebase.ts` | Consome fragmento sem persistir token, Auth temporario em memoria e db=null sem cliente Firestore temporario; valida contrato e marcador nao secreto da aba para proteger reload. |
| `frontend/src/types.ts` | Tipos da configuracao e metadata de visualizacao com identidades de autenticacao e escopo separadas. |
| `frontend/src/api.ts` | Abort/deadline/geracao de HTTP; descarta respostas antigas/apos fim e mudanca de escopo. HTTP409 com sessao estabelecida fica desatualizado ate novo ciclo, sem logout indevido. |
| `frontend/src/hooks/useImpersonationPolling.ts` | Ciclos de polling sem sobreposicao, carga imediata, estado de ultima atualizacao/falha e cancelamento por geracao/encerramento. |
| `frontend/src/utils/impersonation.ts` | Valida envelope/deadline de visualizacao para impedir aplicar resposta atrasada ou de sessao divergente. |
| `frontend/src/context/CrmContext.tsx` | HTTP/polling sem Firestore temporario; janelas/ownership/TTL; fingerprint de toggles limpa selecao/caches/paginacao e invalida requests antigos. Refresh de sessao antigo e descartado, watcher deriva canal quando campo ausente; suprime unread/autoassign e mutacoes. |
| `frontend/src/App.tsx` | Botao por usuario elegivel, modal e faixa; controles de escrita indisponiveis e reset de perfil ao trocar cargo preservado; remonta apenas paineis temporarios ao mudar escopo, preservando Auth/settings. |
| `frontend/src/components/Impersonation.tsx` | Modal com motivo e aviso auditado, link exibido uma vez, faixa vermelha, prazo e encerramento com confirmacao do servidor quando disponivel. |
| `frontend/src/components/gchat/InternalChatPanel.tsx` | Polling HTTP temporario das janelas globais existentes; suprime mark-read/envio e descarta respostas tardias. |
| `frontend/src/components/monitor/MonitorModal.tsx` | Impede export de auditoria que produziria escrita. |
| `frontend/src/components/settings/QuickMessagesEditor.tsx` | Desabilita edicao/salvamento no modo visualizacao. |
| `frontend/src/styles.css` | Faixa fixa e apresentacao dos controles somente leitura. |
| `tools/sim_impersonate.py` | 285 asserts com Firestore em memoria e HTTP ASGI sem startup; cobre emissao, negacoes, cache, registry/end/cleanup, allowlist, revalidacao final por TTL/fechamento/perfil, no-store precoce, canais visiveis e payloads globais podados. |
| `tools/sim_impersonate_views.py` | 92 asserts com mais de50 por target e300 global, backup/legado, gate Meus bruto, paginacao/nao-lidas, custom supervisor, thread/mensagem/protocolo IDOR, Timestamp/ordem estavel e erro de indice sem scan. |
| `tools/impersonate_emulators/` | Harness local e diagnostico historico de TTL/backup; gate atual de 779 verificacoes/zero falhas comprova deny-all temporario, conta original intacta e pendencia normal preservada. |
| `docs/HANDOFF_IMPERSONATE_READONLY.md` | Spec original e adendos autorizados; documenta a substituicao de D1. |
| `docs/REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md` | Contrato aprovado da identidade temporaria, limites e operacao; transporte direto superado pela revisao HTTP. |
| `docs/REVISAO_IMPERSONATE_TTL_BACKEND.md` | Revisao aprovada HTTP/polling, janelas, validacao final, limites/custo e gates. |
| `docs/decisions/0014-impersonate-somente-leitura.md` | Decisoes e inventario obrigatorio. |
| `CLAUDE.md` | Gate do simulador novo e invariante de identidade separada/TTL/ausencia de escrita do alvo. |
| `docs/README.md`, `docs/decisions/README.md` | Indices da documentacao. |
| `docs/ENTREGA_IMPERSONATE_READONLY.md` | Esta consolidacao: arquivos, inventario, gates, IAM e validacao manual. |

## Inventario obrigatorio da secao 4.5

Realizado antes da implementacao da trava: **41 rotas GET** de `main.py`, incluindo
os helpers chamados por elas. O app B e separado. O inventario detalhado permanece
no ADR 0014; esta tabela reproduz sua classificacao completa.

O inventario abaixo preserva as 41 rotas originais. No contrato revisado, a allowlist
positiva tem **39 templates GET**: retira os cinco transportes antigos (contacts,
conversations, messages por contato e dois GC), `/webhook` e auditoria; inclui os cinco
novos GETs. Paths desconhecidos e parametros desconhecidos sao negados. Contatos/all,
detalhe, picker, protocolo e export mantem guard de backup/escopo do alvo; protocolo
filtra mensagens por ownership de thread independente do dono do lead. Os tres POSTs
de consulta tambem passam pela revalidacao final.

Leituras globais existentes receberam protecao especifica somente no ramo temporario:
templates/billing conferem tenant E conjunto de canais visiveis antes de cache/Meta;
pending-webhook consulta somente phone_ids desses canais e poda cada change de batch
misto, removendo entry global/detalhes de erros e excluindo evento sem vinculo provado;
GC spaces deriva salas conhecidas das conversas do tenant, sem listar a conta global
do app Google Chat. Conflitos/ratings permissionados removem backups para perfil sem
canSeeAll. Permissoes globais de painel do alvo e comportamento normal sao preservados.

| Classe | Rotas | Tratamento |
|---|---|---|
| GET com escrita persistente propria (1) | `/api/admin/monitor/auditoria` | Grava `MONITOR_AUDITORIA_EXPORT` via `log_audit`; GET e HEAD bloqueados antes do endpoint, inclusive barra final. |
| Leitura externa (4) | `/api/wa/templates`; `/api/wa/channel/{channel_id}/billing-status`; `/api/gc/spaces`; `/media/{subdir}/{filename}` | Consultam Meta, Google Chat ou midia Firestore/GCS/local; somente leitura e caches RAM, sem envio/upload/renovacao persistida. Permitidos no escopo do alvo. |
| Shell e verificacao (4) | `/`; `/chat`; `/app`; `/webhook` | Sem escrita propria. |
| Sessao e catalogos (9) | `/api/session`; `/api/client-config`; `/api/admin/roles`; `/api/admin/perfis-acesso`; `/api/settings/system`; `/api/settings/user`; `/api/wa/qualifications`; `/api/departments`; `/api/operators` | Sem escrita propria; defaults e preenchimento de toggles apenas na resposta. |
| Contatos e threads (7) | `/api/wa/contacts`; `/api/wa/contacts/all`; `/api/wa/contacts/picker`; `/api/wa/conversations`; `/api/wa/messages/{contact_id}`; `/api/wa/contact/{contact_id}`; `/api/wa/transfer-history/{contact_id}` | Leituras com as permissoes e escopo do alvo. |
| Administracao e lote (7) | `/api/admin/reopen-batch/{batch_id}`; `/api/admin/channels`; `/api/admin/conflicts`; `/api/admin/protocol/{protocol_id}`; `/api/admin/pending-webhook-events`; `/api/admin/export`; `/api/admin/embedded-signup/config` | Sem escrita propria; status de worker interrompido e ajustado apenas no dict devolvido. |
| Chat interno (2) | `/api/gc/conversations`; `/api/gc/messages/{conversation_id}` | Sem escrita propria. |
| Dashboard e monitor (4) | `/api/admin/dashboard/summary`; `/api/admin/dashboard/ratings`; `/api/admin/monitor/fila`; `/api/admin/monitor/metricas` | Leituras e caches RAM. |
| Usage (3) | `/api/wa/usage/current-month`; `/api/wa/usage/history`; `/api/wa/usage/{year_month}` | Leituras/defaults sem backfill. |

Efeito transversal eliminado: o caminho normal de auth pode gravar identidade,
last_login, `LOGIN_SUCCESS_FIREBASE` e claims. A identidade temporaria nunca entra
nesse caminho e nao usa nem polui o cache da sessao real do alvo.

Limite preexistente de midia: `main.serve_media` nao exige autenticacao de sessao, e
`media.get_media_asset` pode ler chave GCS/local global. Uma URL conhecida pode continuar
acessivel sem Authorization depois do TTL/encerramento. O middleware controla a request
que apresenta token imp; ele nao revoga URLs anonimas ja obtidas. Isso nao e uma escrita
ou alteracao da conta alvo, mas impede prometer revogacao de acesso a essas URLs.

Allowlist exata de **tres POSTs de leitura**, preservando RBAC, limites e isolamento:

| POST | Caller e efeito |
|---|---|
| `/api/wa/contacts/picker/search` | `CrmContext.pickerSearch`: consultas/point-reads e enriquecimento; throttle RAM. Termo permanece no body por LGPD. |
| `/api/wa/contacts/picker/by-tag` | `CrmContext.pickerByTag`: configuracao/consultas/enriquecimento, sem backfill. Tag permanece no body. |
| `/api/admin/reopen-batch/preview` | `ReopenBatchModal.loadPreview`: classifica contatos, le templates/limites e usa caches/locks RAM; nao executa o lote. |

Excecao adicional de suporte: `POST /api/impersonation/end` fecha somente o registro
da propria sessao autenticada e audita como o admin original. Nao recebe SID/alvo
arbitrario nem permite mutar dados CRM. Nao e uma quarta consulta da allowlist.

POSTs automaticos que escrevem continuam bloqueados e sao suprimidos no frontend:

| Rotas | Efeito evitado |
|---|---|
| `/api/wa/contact/{contact_id}/read`, `/api/wa/conversation/{conversation_id}/read` | Zeramento de nao-lidos e recomputacao do derivado. |
| `/api/wa/conversation/open` | Criacao/autoatribuicao de thread e auditoria. A visualizacao abre somente thread existente por leitura. |
| `/api/gc/mark-read/{conversation_id}` | Zeramento de nao-lido do chat interno. |

Demais POSTs e todos PUT/PATCH/DELETE do CRM sao negados antes do endpoint;
envio, assumir, transferir, fechar, qualificar, editar e salvar tambem ficam
indisponiveis na UI. O novo cron interno exige autenticacao propria e nao e liberado
para tokens de visualizacao.

## Gates locais

Python usado: `C:\Rafael\castro-intelligence\.venv\Scripts\python.exe`.
Todos os simuladores desta tabela usam mocks; scripts de producao e os tools reais
`cx_smoke.py`/`reopen_conciliation.py` nao foram executados.
A rodada final de backend/sims foi repetida depois da revisao HTTP e passou. O build
frontend final tambem passou apos os ajustes de revogacao/geracao. Gates locais nao
equivalem a aceite de staging.

| Gate | Resultado confirmado |
|---|---|
| `-m py_compile` da lista do CLAUDE.md e todos os modulos novos/alterados | Rodada final completa aprovada, exit 0. |
| `tools/sim_bot_flow.py` | Aprovado: 71 asserts, exit 0. |
| `tools/sim_cx_flow.py` | Aprovado: 222 asserts, exit 0. |
| `tools/sim_reception_flow.py` | Aprovado: 285 asserts, exit 0. |
| `tools/sim_buffer_flow.py` | Aprovado: 59 asserts, exit 0. |
| `tools/sim_pool_wait_notice.py` | Aprovado: 48 asserts, exit 0. |
| `tools/sim_monitor_flow.py` | Aprovado: 69 asserts, exit 0. |
| `tools/sim_history_recency.py` | Aprovado: 45 asserts, exit 0. |
| `tools/sim_impersonate.py` | Revisao HTTP: **285 asserts, 0 falhas, exit 0**. Firebase stubado e Firestore em memoria; HTTP ASGI sem lifespan/startup inclui TTL/registro fechado no lookup final, perfil estrito/cache isolado, no-store precoce e seis rotas legadas. |
| `tools/sim_impersonate_views.py` | Revisao HTTP: **92 asserts, 0 falhas, exit 0**. Janelas/ordem/backup/legado/gate Meus/IDOR/paginacao/Timestamp em memoria; sem clientes externos. |
| `npm.cmd ci` em `frontend/` | Aprovado; 156 pacotes instalados. |
| `npm run build` em `frontend/` | **Build final aprovado, exit 0:** tsc e Vite (73 modulos), apos revisao de escopo/geracao/refresh antigo. Aviso de chunk Firebase acima de 500 kB. |
| `git diff --check` | Aprovado. |
| Harness local Auth/Firestore Emulator | **Contrato atual aprovado: 779 verificacoes, zero falhas, exit 0.** Auth preserva conta original; SDK/REST/listener temporarios negados desde o inicio, com/sem claims/refresh, tenant/flat/staging/plataforma/registro. Etapa historica direta continua reprovada (149 positivas, evento +1,259 s e 24 observacoes backup); [diagnostico completo](../tools/impersonate_emulators/DIAGNOSTICO.md). O achado normal nao e corrigido por esta revisao. |

Validacao manual em staging nao foi executada e nao e substituida pelos mocks.
O usuario aprovou a revisao HTTP apos a falha historica; todos os novos gates locais
passaram. Runtime/testes foram commitados localmente; a documentacao segue em commit
separado, com historico no Git. O mismatch LGPD de backup normal
permanece pendencia preexistente e nao e verificacao de vazamento em producao. No novo
transporte temporario, a filtragem e feita no servidor e deve ser provada pelos gates.

Tradeoff de custo: cada ciclo de snapshot pode consultar ate150 contatos+150 threads
do operador; supervisor com canSeeAll ate200 contatos e50+50+50+300+Nbackup threads.
Sao envelopes teoricos, sem dedupe de cobranca nem custo real medido, repetidos a cada15s;
ha leituras adicionais de perfil/registro/catalogos/historico. O target indexado de
backup do supervisor preserva a consulta original sem cap. Avaliar custo/latencia antes
de ativar, sem reduzir janela ou ampliar cache da autorizacao silenciosamente.

## IAM, indice e cron: operacao humana posterior

Nenhum comando desta secao foi executado pelo agente.

Com ADC no Cloud Run, assinatura do custom token usa IAM `signBlob`. A API
`iamcredentials.googleapis.com` precisa estar habilitada. Comando literal da secao 7
do handoff, para um humano executar no projeto Oregon:

```powershell
$SA = gcloud run services describe castro-crm --region us-west1 --project project-4a851bf9-f475-418c-800 --format="value(spec.template.spec.serviceAccountName)"
gcloud iam service-accounts add-iam-policy-binding $SA --member="serviceAccount:$SA" --role="roles/iam.serviceAccountTokenCreator" --project project-4a851bf9-f475-418c-800
```

Antes de ativar, o humano deve publicar conjuntamente codigo/rules e o indice
versionado `impersonation_sessions(status ASC, cleanup_after ASC)`, escopo COLLECTION.
Conferir tambem que o runtime tem permissao para a exclusao Auth usada pelo cleanup,
sem ampliar a role de assinatura para cobrir operacoes diferentes.

O endpoint operacional e `POST /api/internal/cron/cleanup-impersonation`, reutilizando
o gate existente de cron: OIDC com `CRON_OIDC_AUDIENCE` e
`CRON_OIDC_SERVICE_ACCOUNT`; `X-Cron-Secret`/`INTERNAL_CRON_SECRET` e o fallback
existente de desenvolvimento/staging. Agendamento autenticado e publicacao de indice
sao passos humanos; nenhum job foi criado. A frequencia operacional deve ser definida
pelo responsavel antes da ativacao.

O cleanup funciona com a feature desligada. Inclui tenants inativos; consulta somente
registros active/closed com `cleanup_after <= now`, ordenados e limitados por tenant.
O default e 100 registros por tenant/chamada, limitado a 500. Nao varre usuarios Auth.
Apaga apenas o UID reconstruido a partir de ambiente/SID e registrado, diferente dos
UIDs reais do admin/alvo. `UserNotFound` e sucesso; falha mantem retry. Registro invalido
nao produz exclusao e e adiado para nao bloquear o lote. `cleaned` fica fora da selecao.

`cleanup_after` nasce duas horas apos emissao, separado do TTL de leitura. Os tombstones
permanecem: retencao posterior deve ser definida antes de implantar TTL Firestore;
nao apagar o registro antes de remover a conta temporaria correspondente.

## Roteiro manual em staging, pelo PO

Validacao local concluida. O roteiro abaixo fica para o PO, depois da publicacao
humana de codigo/rules/indice e configuracao operacional, com operador de teste.
Nenhum desses passos em staging foi executado nesta entrega.

1. Admin abre Ver como: motivo minimo de 10 caracteres, aviso de acesso auditado e link
   exibido uma vez. A nova aba mantem faixa vermelha, mesmo Meus inicial de 50,
   Novos/pool e menus do alvo. Supervisor com perfil custom mostra Equipe conforme toggles.
2. Conferir que Firebase Auth autenticou UID temporario diferente do admin/alvo, sem
   email/nome/providers copiados. O usuario CRM e o UID usado nos filtros continuam sendo
   os do alvo. A conta Firebase original e seu last sign-in permanecem inalterados.
3. Abrir conversa nao zera `unread_count` da thread nem o derivado do contato; nao cria
   thread nem autoatribui. Abrir chat interno tambem preserva nao-lidos.
4. Enviar, assumir, transferir, fechar, qualificar, editar e salvar estao indisponiveis;
   forcados via API retornam 403. Escrita direta Firestore via SDK/REST tambem e negada.
5. A aba normal do admin continua logada como admin no mesmo navegador. Auth temporario
   usa memoria e db=null sem cliente Firestore nessa aba; token desaparece do fragmento e nao vai a
   localStorage, sessionStorage ou IndexedDB. O marcador da aba nao contem dados/token.
6. No TTL a aba cancela requests e limpa estado; refresh do ID token nao renova prazo.
   Testar aba suspensa e retorno por foco/online; reload nao entra na sessao persistida
   do admin naquela aba. GET lento que cruza TTL/fechamento devolve401 sem dados.
   Firestore direto temporario e negado antes e depois do prazo, inclusive reconexao.
7. Conferir `IMPERSONATE_START` com motivo/SID, sem `LOGIN_SUCCESS_FIREBASE` do alvo,
   last_login CRM intacto e logs tecnicos sem token/PII. Falha controlada de audit impede
   a entrega de acesso. Respostas imp e emissao possuem `Cache-Control: private, no-store`.
8. Busca, filtro por tag e previa de lote funcionam pelos tres POSTs exatos; disparo e
   POST arbitrario seguem negados. GET/HEAD de auditoria do monitor retornam 403 sem audit.
9. Encerrar online fecha somente a propria sessao e grava `IMPERSONATE_END` como admin
   original; request posterior e negado. Enviar SID de outra sessao no body nao a fecha.
   Se sem rede, verificar mensagem honesta: encerramento local nao confirma revogacao no
   servidor antes do TTL. O link nao e anunciado como de uso unico.
10. Tentar token legado com UID real + imp e UID reservado sem contrato, inclusive apos
    vincular uma credencial a conta temporaria: nao entram no CRM ou app B. Mutacoes Auth
    controladas na conta temporaria nao alteram a conta original do operador.
11. Testar Firestore fora do tenant/ambiente, staging wildcard, colecoes flat/plataforma,
    backup, IDOR, mudanca de dono e paginacao. Mudar role/perfil ou desativar o alvo
    deve invalidar a visualizacao; alterar toggles do mesmo perfil deve refletir o perfil
    efetivo. Backup proprio/pool/legado deve ser filtrado no HTTP antes da entrega, com
    top50 sem reposicao; role comum nao amplia por setor. A falha historica de backup
    normal permanece documentada e nao foi verificada em producao.
12. Conferir que a aba temporaria nao chama getDoc/getDocs/onSnapshot, mesmo com preferencia
    snapshot, falha HTTP/offline ou reconexao. Primeira carga e abertura sao imediatas;
    polling informa15s/ultima atualizacao/desatualizado e nao sobrepoe ciclos. Testar mais
    de50 por target e300 global, paginacao, nao-lidas e ordem. Tentativa SDK/REST ou listener
    direto temporario e negada desde o inicio. Dados ja recebidos e capturas/copias
    nao sao apagados retroativamente pelo servidor. Testar separadamente URL de midia
    conhecida sem Authorization: esse caminho anonimo preexistente nao e revogado por
    TTL/encerramento, e nao deve ser confundido com uma nova leitura CRM autorizada.
13. Depois de `cleanup_after`, executar o cron com credencial operacional: somente conta
    temporaria registrada e removida e registro vira cleaned. Confirmar retry de falha e
    UserNotFound idempotente, sem delete/revoke/update nas contas reais de admin/alvo.

Os gates locais passaram: HTTP revalida prazo/registro antes de entregar e o
temporario nao recebe acesso direto pelo Firestore. O aceite real continua humano.
Permanecem passos operacionais humanos a publicacao, IAM, indice, agendamento,
verificacao previa de que o namespace reservado nao pertence a usuario real e validacao
manual. A feature continua desligada por default; nenhum desses passos foi executado.
