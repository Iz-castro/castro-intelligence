# Revisao de arquitetura - Ver como com identidade separada

**Data:** 2026-10-14. **Status:** identidade separada e transporte HTTP/polling aprovados, implementados e validados localmente. Feature desligada por default; aceite de staging posterior.

O usuario aprovou rever a D1 do [handoff](HANDOFF_IMPERSONATE_READONLY.md)
para proteger tambem a conta de login do operador. O codigo local agora autentica
uma identidade temporaria e autoriza o alvo por registro server-side. Este documento
registra o contrato aprovado e a implementacao parcial; nao afirma cumprimento integral.
O Firestore Emulator 1.22.0/CLI 15.31.0 entregou evento a listener aberto 1,259 s apos expires_at.
Nova consulta foi negada e fechar o registro invalidou o listener, mas o prazo duro
aprovado ainda nao foi comprovado para a assinatura aberta. As 12 consultas reais Meus/pool
de contatos/conversas retornaram backups a normal e preview (24 observacoes indevidas, prefixos prod/staging
do emulador), embora direct get negasse. Isolamento/fidelidade dessas queries nao esta
aprovado e nao foi testado em producao. [Diagnostico](../tools/impersonate_emulators/DIAGNOSTICO.md).
Conforme a secao 7 do pedido, o runtime foi congelado antes da revisao. O usuario depois
aprovou [HTTP e polling de 15 s](REVISAO_IMPERSONATE_TTL_BACKEND.md), substituindo neste
documento as exigencias de leitura direta/UID efetivo/TTL nas rules: agora todo acesso
Firestore temporario e negado, e o backend revalida antes de entregar cada resposta.
O restante do contrato de identidade/registry/end/cleanup permanece. Implementacao local
e novos gates concluidos: compile, sete sims existentes, sim285/views92, emuladores779,
npm ci e build final aprovados. Commits locais autorizados ficam registrados no Git. Publicacao/ativacao,
agendamento e aceite humano em staging continuam posteriores.

**Historico:** houve primeiro um prototipo local com token do UID real do alvo; a revisao
identificou mutacoes de conta via Firebase Auth e o usuario pediu este desenho antes de
implementar. A proposta foi depois aprovada. O prototipo original e seus gates nao sao
evidencia do contrato atual; a D1 antiga esta superada e nunca foi publicada.

## 1. Desenho adotado em linguagem simples

Uma identidade de login descartavel e utilizada para cada visualizacao. Ela recebe autorizacao
curta para consultar os mesmos dados que o operador, sem entrar na conta Firebase dele.

| Parte | Identidade utilizada |
|---|---|
| Login da aba de visualizacao | Conta temporaria, diferente do admin e do alvo |
| Usuario exibido, perfil, menus e filtros Meus/pool | Operador-alvo autorizado pelo servidor |
| Conta Firebase original do operador | Nenhum login, atualizacao ou revogacao |
| Sessao normal do admin | Continua separada nas outras abas |

As mudancas possiveis na propria conta temporaria nao devem conceder acesso normal ao
CRM nem alterar a conta original. A separacao exige regras de autorizacao,
e nao apenas trocar o UID na chamada de assinatura.

## 2. Por que a D1 original precisa mudar

Um custom token autentica a conta indicada pelo UID; se esse UID nao existir, o primeiro
login cria uma conta Auth. O Firebase Auth oferece atualizacao de perfil, senha,
vinculacao de credenciais e exclusao de conta. Esses caminhos nao passam pelo middleware
do CRM nem pelas rules do Firestore. [Custom tokens](https://firebase.google.com/docs/auth/admin/create-custom-tokens),
[gerenciamento de usuarios Web](https://firebase.google.com/docs/auth/web/manage-users),
[vinculacao de contas](https://firebase.google.com/docs/auth/web/account-linking).

**Conclusao de desenho:** emitir para o UID real do alvo entrega a identidade dele ao
cliente. A marca imp restringe nossos servicos, mas nao transforma o Firebase Auth em
um servico somente leitura. Emitir para um UID separado limita essas operacoes a conta
descartavel. Nao foram executadas operacoes nas contas/projetos reais para demonstrar esse risco.

O novo significado de "somente leitura" deve ser preciso: **nenhuma escrita nos dados
ou na conta do operador-alvo**. A infraestrutura da visualizacao precisa criar um
registro de sessao, gravar auditoria e criar/excluir sua propria conta temporaria.

## 3. Decisoes aprovadas (transporte revisado pelo documento HTTP)

| Decisao | Contrato atual e impacto sobre o handoff |
|---|---|
| D1 revisada | Custom token para UID temporario unico por SID; alvo apenas em referencia assinada e registro server-side. Substitui a D1 original. |
| D2 complementada | Preservar trava HTTP, tres POSTs de leitura aprovados e bloqueio do GET auditado. Acrescentar somente o encerramento da propria sessao, descrito abaixo, que grava metadados de suporte, nunca dados do alvo. |
| D3 mantida | /api/session devolve usuario-alvo filtrado/enriquecido e seus toggles efetivos; nunca read_only/impersonating no dict de RBAC. |
| D4 revista no transporte | Auth temporario em memoria e db=null sem cliente Firestore temporario. Um marcador de aba em sessionStorage, sem token, UID, nome ou dados CRM, evita que reload entre silenciosamente na sessao persistida do admin. |
| D5 mantida | Link com custom token temporario no fragmento, removido no boot; token apenas em memoria. Reuso dentro da validade continua uma limitacao explicita. |
| D6 revisada novamente | Prazo absoluto na entrada e antes do corpo HTTP, com registry/perfil estritos; polling15s. Todo Firestore direto temporario negado. Frontend descarta resposta tardia e limpa memoria. |
| D7/D8/D9 mantidas | Toggle seed so admin, alvo elegivel no mesmo tenant, sem aninhamento e feature desligada por default. |

Nao copiar email, nome, telefone, senha, providers ou credenciais do alvo para a conta
temporaria. Nome/email usados pela UI e filtros internos continuam vindo do usuario
CRM retornado por /api/session. Autorizacao temporaria nao dependera de email Auth.

## 4. Duas identidades, um escopo autorizado

Exemplo do contrato adotado, sem token real:

~~~text
auth_uid:       imp_ro_<hash8_do_prefixo>_<sid_aleatorio>
effective_uid:  UID do operador-alvo
tenant_id:      tenant validado do solicitante e do alvo
imp_env:        FIRESTORE_COLLECTION_PREFIX exato do ambiente
~~~

auth_uid identifica quem autenticou no Firebase. effective_uid identifica de quem se
pode consultar o escopo no CRM. O browser nao escolhe livremente esse mapeamento.

Claims emitidos: imp=true, imp_sid, imp_target_uid, imp_by, imp_by_uid, imp_env, imp_exp,
tenant_id, role e perfil_acesso_id do alvo. Nao copiar claims extras como super_admin.
Campos temporais usam UTC com precisao de segundos; auth_time e emitido pelo Firebase,
nao pelo nosso custom token. TTL autorizado tambem fica no registro server-side.

O namespace imp_ro_ e reservado pelo helper compartilhado impersonation_identity.py. Antes da
ativacao, conferir por procedimento humano que ele nao pertence a nenhum usuario real;
a limpeza nunca selecionara contas apenas pelo namespace.

Reconhecer o UID reservado antes de cache, lookup por email, resolucao de dominio,
sincronizacao ou auto-provisionamento. UID temporario sem claims validos recebe acesso
negado. UID real com imp tambem e negado: tokens do desenho antigo nao serao aceitos.
Um login por provider/senha vinculado a conta temporaria preserva o UID reservado e
nunca vira sessao normal do CRM. Provisionamento/edicao nao pode associar UID reservado
a usuario real; o alvo tambem nao pode ter UID reservado.

## 5. Registro obrigatorio de sessao

O registro tenants/{tenant_id}/impersonation_sessions/{sid} e criado dentro da raiz
do prefixo do ambiente. A colecao continua tenant-scoped; nao entra em _GLOBAL_COLLECTIONS.

Campos minimos: auth_uid, target_uid, target_user_id, admin_uid, admin_user_id, tenant_id,
environment, role_at_start, perfil_acesso_id_at_start, ttl_seconds, created_at, expires_at,
cleanup_after e status (active, closed, cleaned). O motivo fica na auditoria existente,
sem repetir PII. Nao armazenar custom/ID/refresh tokens.

Antes de entregar acesso, o endpoint preserva a validacao do admin, alvo e motivo;
gera SID/UID temporario; grava o registro; assina; exige IMPERSONATE_START estrito.
Qualquer falha impede devolver o token. Registro incompleto fica inelegivel ou e
fechado para limpeza. Nao ha transacao atomica entre Firestore e Firebase Auth;
falhas parciais precisam de compensacao idempotente.

O registro e a fonte autoritativa para ligar UID temporario, alvo, ambiente, prazo
e estado. O backend confere correspondencia exata com os claims; registro
ausente, fechado, vencido ou divergente nega acesso. O cliente nao escreve nele.
A leitura direta do documento tambem e negada ao cliente. A revisao HTTP removeu as
leituras auxiliares do registro nas rules: nenhum acesso temporario direto e permitido.

## 6. Backend: resolver o alvo sem autenticar a conta dele

O ramo temporario de auth.py valida UID reservado, formato, SID, ambiente, tenant,
registro, imp_exp e idade de auth_time. So depois resolve target_uid por lookup
exato e usa a whitelist de get_user_by_id, incluindo department_name.
Sem fallback por email, sync, last_login, audit de login, claims ou cache do alvo.

current_user.id, firebase_uid, role e perfil continuam sendo os do alvo.
user.impersonation acrescenta SID, solicitante, prazo e UID temporario autenticado.
O UID temporario nao e gravado em assigned_to_uid, users ou operator_profiles.
Autorizacao de leitura segue o RBAC do alvo, sem apagar seus toggles.

O middleware reconhece tanto imp quanto o namespace reservado. Retirar imp ou
apresentar contrato incompleto nao permite cair no fluxo normal. Preservar os tres
POSTs de leitura exatos e negar GET/HEAD /api/admin/monitor/auditoria.

POST /api/impersonation/end foi implementado, autorizado somente para a propria sessao:
valida identidade temporaria, fecha registro e audita com solicitante original
como ator. Nao aceita SID/alvo arbitrario nem permite iniciar outra sessao. A excecao
HTTP e restrita ao ciclo de vida do suporte, separada da allowlist de consultas.
Se nao houver rede, a UI encerra localmente; revogacao no servidor nao e garantida
antes do TTL. SignOut local nao deve ser apresentado como revogacao da credencial.

O app B continua fora do escopo: nao copiar super_admin e negar o namespace
temporario em sua autorizacao como defesa adicional, sem adicionar impersonate ao B.

## 7. Historico: delegacao Firestore estreita, superada pela revisao HTTP

**Secao preservada como historico do desenho que falhou no emulador.** O contrato
vigente nega toda leitura/escrita temporaria direta; nao implementa effectiveUid,
validacao de registry nem TTL de listener nas rules. Ver a
[revisao HTTP aprovada](REVISAO_IMPERSONATE_TTL_BACKEND.md) e o diagnostico. Sessoes
normais preservam seus grants, sempre excluindo UID reservado e imp legado.

As rules podem ler claims assinados e documentos auxiliares. Essa leitura embutida
tem custo e limites; o guard implementado usa registro da sessao e perfil ativo do alvo,
sem scans ou dados de contato no controle de acesso.
[Claims nas rules](https://firebase.google.com/docs/rules/rules-and-auth),
[condicoes e leituras auxiliares](https://firebase.google.com/docs/firestore/security/rules-conditions).

Separar os principals explicitamente:

| Principal | Comportamento |
|---|---|
| UID normal, sem imp | Manter regras normais atuais |
| UID reservado + contrato e sessao validos | Somente leitura, no tenant/prefixo e escopo do alvo |
| UID reservado sem contrato valido, ou UID real com imp | Nenhum acesso |

effectiveUid() so retorna o alvo depois de validar a sessao. Usar esse UID em
comparacoes de dono e no lookup do perfil ativo, preservando pool, backup e role.
Nao substituir request.auth.uid cegamente em todo arquivo: esse valor continua
obrigatorio na prova da identidade temporaria. Leitura self de super_admins e
isSuperAdmin nunca usam UID efetivo para conceder acesso de plataforma.

Helpers devem ter dependencia sem recursao: validar estrutura dos claims e UID
reservado; ler registro/perfil por campos assinados e paths validados; conferir o
vinculo/autorizacao; so entao disponibilizar effectiveUid(). Esse guard nao chama
helpers como signedIn/ownsTenant/tenantOperatorProfile que dependam dele. Em especial,
evitar o ciclo effectiveUid -> validSession -> tenantOperatorProfile -> effectiveUid.

O ramo temporario verifica request.time < expires_at, prazo dos claims, idade de
auth_time, estado da sessao, ambiente, tenant e alvo ativo. O relogio e do servidor,
nao do browser. TTL do registro e limitado a 300..3600 segundos e a idade do login
tem a folga de 60 segundos do handoff, sem estender expires_at.
signedIn() nao pode exigir email para esse ramo: a prova e UID + sessao valida.
O caminho normal preserva a exigencia atual de email. Desativacao do alvo ou mudanca
de sua role/perfil de acesso invalida a visualizacao e exige nova sessao; mudancas
nos toggles do mesmo perfil continuam refletindo sua permissao efetiva ao vivo.
[Request das rules](https://firebase.google.com/docs/reference/rules/rules.firestore.Request).

**Staging exige cuidado especial:** seus matches permissivos sao combinados por OR.
Um allow false especifico nao anula outro allow true. Todos os ramos normais
(emailAllowed, flat, wildcard de tenants e helpers super-admin/self) devem excluir
UIDs reservados e tokens imp. Acrescentar leitura temporaria apenas em subcolecoes
explicitamente permitidas, com politica equivalente a producao, nunca por um OR
permissivo no wildcard. Helpers de perfil devem receber a raiz do ambiente; hoje
tenantOperatorProfile esta fixo em castro_crm_tenants. Negar acesso a outro
ambiente/tenant, colecoes flat e documentos de plataforma.
[Combinacao de matches](https://firebase.google.com/docs/firestore/security/rules-structure#overlapping_match_statements).

storage.rules ja nega todo acesso client-side; manter essa regra. Midia continua
servida pelo backend, sem conceder acesso Firebase Storage a identidade temporaria.

## 8. Frontend: preservar fidelidade e encerrar a sessao

O inventario de CrmContext.tsx mostra que Meus, paginacao e posse usam
sessionUser.firebase_uid, que continuara sendo o do alvo. Manter filtros,
ordenacao e limite inicial de 50. firebaseUser.uid/auth.currentUser.uid continuam
sendo os da conta temporaria e servem ao controle de autenticacao/concorrencia.
Nao igualar os dois UIDs nem mudar queries para o UID temporario.

O polling so inicia apos /api/session validar contrato. A faixa usa a identidade CRM.
O transporte HTTP preserva os targets do UID do alvo; a aba temporaria tem Auth em
memoria e db=null, sem cliente Firestore. Preservar controles desabilitados e skip de
unread/autoassign/chat interno; sessoes normais mantem SDK/listeners atuais.

No vencimento ou encerramento: bloquear novas acoes; cancelar fetches; limpar
estado e referencias; descartar respostas assincronas atrasadas; fazer signOut e
invalidar geracao dos requests. Revalidar prazo em focus, visibilitychange
e online para lidar com abas suspensas. O marcador nao secreto da aba impede que
reload carregue o Auth persistido do admin naquela aba.

Rules negam todo SDK/REST/listener temporario desde o inicio. Backend valida prazo
antes do corpo HTTP, mas nao apaga dados ja recebidos, capturas/copias ou URLs anonimas
de midia ja conhecidas. Testar consultas/lookup final lentos, reconexao e resposta tardia.

## 9. Ciclo de vida e limpeza

O primeiro login cria a conta Auth temporaria, sem email, senha ou perfil copiado.
O registro existe antes da entrega do token; o desenho nao depende
de trigger de criacao nem de claims de sessao como marcador permanente no UserRecord.
[Criacao por custom token](https://firebase.google.com/docs/auth/admin/create-custom-tokens).

Limpar por consulta indexada: status in [active, closed] e cleanup_after <= now,
ordenada por cleanup_after e com lote limitado por tenant/prefixo. Excluir status
cleaned da selecao para tombstones antigos nao bloquearem a drenagem dos proximos
lotes. Percorrer tambem tenants inativos com registros pendentes; documentar o indice
composto necessario. Excluir somente o auth_uid registrado, sem varrer todos os
usuarios Auth ou selecionar contas apenas pelo prefixo.

Antes de delete_user: validar formato, UID reconstruido a partir de ambiente/SID,
correspondencia com registro, prazo e diferenca em relacao aos UIDs reais do admin
e alvo. UserNotFound e sucesso idempotente. So marcar status=cleaned apos sucesso de
delete/UserNotFound. Falha da API mantem registro para retry. Nunca chamar
delete/revoke/update sobre target_uid.

**Prazo adotado de cleanup: duas horas apos emissao**, em cron interno autenticado.
Isso e separado do TTL de leitura, que continua 30 minutos por default.
Inferencia: apagar aos 30 minutos permite que o custom token, trocavel por ate uma
hora, recrie a conta. A limpeza posterior evita essa janela, enquanto backend/rules
ja negam acesso vencido. Deletar Auth nao substitui expiracao no backend/rules.
[Custom tokens](https://firebase.google.com/docs/auth/admin/create-custom-tokens),
[sessoes Firebase](https://firebase.google.com/docs/auth/admin/manage-sessions).

Manter tombstone do registro apos limpeza e aplicar retencao posterior definida,
sem TTL Firestore que possa apagar a unica referencia antes do cleanup Auth.
O endpoint POST /api/internal/cron/cleanup-impersonation usa a autenticacao de cron
existente e continua operando com FEATURE_IMPERSONATE=false. O indice composto
status + cleanup_after esta versionado em firestore.indexes.json. A consulta e limitada
por tenant, inclui tenants inativos e exclui tombstones cleaned. Endpoint e indice sao
locais; publicacao, agendamento e retencao posterior continuam para operacao humana.
Nenhuma infraestrutura foi criada nesta revisao.

Reuso do custom token continua possivel ate o prazo de troca. Registro fechado ou
vencido impede recuperar acesso CRM. Vincular apenas auth_time nao prova uso unico,
pois dois logins podem ocorrer no mesmo segundo. Nao declarar uso unico sem protocolo
especifico; ele permanece fora da implementacao minima aprovada.

## 10. Arquivos implementados e validacao

| Arquivos | Mudanca implementada |
|---|---|
| main.py, impersonation.py, impersonation_views.py | Emissao/registro/end/cron seguros; HTTP/polling com janelas e autorizacao final |
| impersonation_identity.py, auth.py, config.py, firebase_admin_client.py | Namespace/contrato e helpers estritos, sem alterar identidade original |
| firestore.rules | Todo acesso temporario direto negado em tenant/staging/flat/plataforma, sem mudar grants normais |
| superadmin_main.py | Negacao defensiva do namespace temporario; sem recurso cross-tenant |
| frontend/src/firebase.ts, CrmContext.tsx, Impersonation.tsx, types.ts | Boot, contrato, limpeza e protecao de reload/respostas atrasadas |
| tools/sim_impersonate.py, tools/sim_impersonate_views.py e emuladores | Identidade/ciclo de vida, TTL/fechamento final, janelas/backup/IDOR/normalizacao e deny-all direto |
| ADR 0014, handoff e CLAUDE.md | D1 original substituida apos aprovacao explicita do usuario |

Antes de ativar, exigir os gates existentes e testes adicionais:

1. Token tem UID diferente do alvo/admin; troca em Auth Emulator cria somente conta
   temporaria. Atualizar perfil/senha ou excluir essa conta nao altera o alvo.
2. UID reservado sem imp, com nova credencial/provider, claims incompletos ou registro
   divergente nao entra no CRM, auto-provisionamento, grants permissivos ou app B.
3. UID real com imp antigo e rejeitado; normal sem imp continua funcionando.
4. Backend nega escrita e leitura HTTP fora do escopo/prazo ou apos fechamento, inclusive
   quando consulta/lookup final demoram. Firestore nega todo SDK/REST/listener temporario
   desde o inicio, incluindo staging wildcard, flat, registro e plataforma.
5. Reproduzir Meus top-50, pool, Equipe/perfil custom, IDOR, backup, mudanca de dono,
   paginacao e abertura sem unread/autoassign. Perfil e conta alvo intactos.
6. Refresh, troca repetida do link, tentativa de listener direto, reconexao, aba suspensa, reload e
   resposta atrasada nao renovam prazo nem carregam sessao normal na aba temporaria.
7. Cleanup mockado cobre UserNotFound, retries e falhas parciais; registro/UID/ambiente
   divergente implica nao excluir nada. Nenhuma chamada pode atingir UID real.
8. Auditar emissao/encerramento sem token/PII nos logs tecnicos; falha na auditoria de
   inicio impede acesso. Contar leituras auxiliares e verificar limites das rules.

Validacao historica do transporte direto: py_compile, os sete sims existentes, sim_impersonate
(244 asserts, zero falhas), npm ci e build final TypeScript/Vite passaram. O gate de
emulador **falhou**: listener aberto recebeu evento 1,259 s apos expires_at. Nova consulta
getDocFromServer foi negada e fechar registro invalidou o listener. O requisito de prazo
duro da D6 ampliada continua descumprido; nao substituir essa evidencia pelos passes dos
mocks/build. Tambem foram observadas 24 entregas indevidas de backup nas 12 consultas reais, para normal e
preview, nos prefixos prod/staging apenas do emulador. E um mismatch LGPD preexistente
herdado pelo modo novo no teste local, sem verificacao de producao. Emuladores usam dados
locais, sem ADC ou acesso aos projetos/dados reais do CRM. Ferramentas/dependencias
publicas foram baixadas e o CLI leu MOTD publico, sem credenciais/API de dados CRM.
Naquela etapa o runtime foi congelado, sem commits, e a divergencia foi apresentada
ao usuario. A revisao HTTP foi depois aprovada; os resultados acima sao historicos
e nao demonstram o novo transporte. Ver os gates vigentes na entrega.
Publicacao de codigo/rules/indice e agendamento continuam passos humanos posteriores.
Os comandos IAM do handoff permanecem somente referencia; nao foram executados.

## 11. Estado da sequencia aprovada

1. Contrato aprovado: sessao autoritativa, encerramento proprio, ausencia de email Auth
   copiado e cleanup apos duas horas.
2. Desenho antigo substituido no codigo; spec/ADR atualizados, feature desligada.
3. Gates antigos de TTL do listener e backup reprovados; usuario aprovou substituir o
   transporte temporario por HTTP/polling15s e deny-all nas rules. Novos gates locais
   passaram; resultados detalhados na entrega, sem substituir staging.
4. Revisao/publicacao humana de rules/infra e teste de staging antes de considerar ativacao.

Alternativa anteriormente considerada: servir toda leitura por proxy no backend, sem nova conta
Firebase. Evitaria o ciclo de contas temporarias, mas substituiria listeners diretos e
exigiria reproduzir consultas/paginacao/realtime em outro caminho, reduzindo a fidelidade
do diagnostico. Foi rejeitada na decisao anterior. A revisao posterior combina identidade
temporaria com transporte HTTP e foi aprovada explicitamente apos o diagnostico local;
nao restaura autenticacao no UID real nem dispensa registro/cleanup.
