# Revisao aprovada - TTL do Ver como com leituras pelo backend

**Data:** 2026-10-14. **Status:** APROVADA pelo usuario, implementada e validada localmente. Todos os gates passaram; feature desligada por default e aceite de staging posterior.

Esta proposta complementa a [identidade separada](REVISAO_IMPERSONATE_IDENTIDADE_SEPARADA.md).
O usuario autorizou trocar apenas o transporte da aba temporaria para HTTP e polling de
15 s, mantendo as sessoes normais. O runtime foi validado localmente, com
FEATURE_IMPERSONATE=false. Nao houve deploy, push nem acesso aos projetos/dados reais do
CRM. Gates da implementacao anterior nao demonstram este contrato; os resultados novos
aprovados estao na [entrega](ENTREGA_IMPERSONATE_READONLY.md).

## Motivo para a nova decisao

Nos testes locais com Firestore Emulator 1.19.8 e 1.22, um listener aberto antes do
vencimento recebeu evento novo depois do TTL. Uma consulta nova depois do prazo foi
negada, e fechar o registro tambem invalidou acesso. Portanto, nao basta testar fresh
reads nem supor que request.time encerre um stream aberto exatamente no vencimento.
O resultado foi observado em emulador; nao foi executado teste equivalente em producao.

Trocar o UID protege a conta Firebase original, mas nao resolve esse comportamento
do transporte. O timer do browser tambem nao e uma garantia server-side: pode atrasar
em abas suspensas ou ser removido pelo cliente.

Outro teste encontrou consultas reais de Meus/pool que retornam documentos backup,
apesar de get individual ser negado. As queries nao filtram is_backup, e a condicao
resource.data.get('is_backup', false) nao comprovou a exclusao no teste de listagem.
Isso ocorreu para principal normal e temporario nos prefixos prod/staging do emulador;
nao e uma verificacao dos dados ou regras atualmente publicados em producao.

## Decisao aprovada

**Somente a aba Ver como le dados CRM por HTTP autenticado e polling.** Sessoes normais
mantem seus listeners Firestore, queries e funcionamento atuais. UID temporario, registro
autoritativo, custom token em memoria, auditoria, encerramento proprio e cleanup continuam.

As rules negam TODA leitura e escrita direta de identidades temporarias, incluindo
prod, staging, flat, wildcard, plataforma e registro. UID reservado sem imp e UID real
com imp antigo continuam negados. O Admin SDK do backend pode consultar Firestore,
mas o servico aplica explicitamente tenant, alvo, role/toggles e exclusao de backup;
nao delega essa protecao a filtros React ou a uma query client-side.

Nao basta ligar o polling existente: /api/wa/conversations usa janela global e depois
filtra; isso nao reproduz as janelas separadas do snapshot do operador. O transporte
temporario precisa de endpoints estreitos com as mesmas consultas de origem.

## Contrato HTTP aprovado

Novas rotas, exclusivamente GET/HEAD, sem nome/telefone/tag em URL:

| Rota | Parametros aceitos | Resultado |
|---|---|---|
| /api/impersonation/view/snapshot | Nenhum seletor de identidade ou path | Janelas de contatos/threads por target, saturacao por target, perfil efetivo, read_at e expires_at |
| /api/impersonation/view/page | scope=mine/pool/all/unread; view em enum; limite inteiro da paginacao atual | Camada estatica equivalente a Carregar mais/Nao lidas, com saturacao por target |
| /api/impersonation/view/messages | contact_id numerico, channel_id numerico quando houver thread e limite atual de mensagens | Historico autorizado, mesma ordenacao e janela; sem read/autoassign |
| /api/impersonation/view/thread | contact_id e channel_id numericos | Apenas thread existente, para picker e watcher de dono; nunca cria/atribui |
| /api/impersonation/view/internal-chat | kind=conversations/messages; conversation_id numerico no segundo caso | Janela equivalente ao chat interno atual, sem mark-read |

Tenant, UID efetivo, role e perfil sempre vem da sessao validada. Nao aceitar collection,
path Firestore, UID arbitrario, expressao de query, operador ou ordenacao fornecida pelo
browser. O backend deriva o ID canonico da thread pelo contato/canal; nao coloca wa_id
no novo contrato de URL. Parametros desconhecidos ou scopes nao autorizados sao rejeitados.

Manter allowlist positiva de rotas/methods de visualizacao. Alem das cinco novas rotas,
enumerar as leituras ja usadas pelas telas: session/client-config, operators, departments,
admin/channels, settings/system, settings/user, contato por ID, contacts/all e picker,
admin/perfis-acesso, conflitos/protocolo, templates/billing, dashboard/ratings/export,
monitor/fila/metricas, configuracao de signup e status de lote. A implementacao deve
registrar os paths exatos e seus parametros, sem liberar por prefixo; RBAC existente
continua obrigatorio. As rotas antigas contacts/conversations/messages de transporte
nao substituem as janelas novas e nao devem ser um caminho alternativo para o temporario.

Preservar exatamente os tres POSTs de consulta aprovados: picker/search, picker/by-tag
e reopen-batch/preview, com termos/tags no body. POST /api/impersonation/end continua
limitado aos metadados da propria sessao. Cron de cleanup usa autenticacao de cron,
nao e uma excecao para o token temporario. Demais mutacoes e GET/HEAD de auditoria do
monitor continuam negados. Toda resposta de visualizacao recebe private, no-store.

## Janelas, isolamento e backup

| Leitura | Consulta de origem que precisa ser preservada |
|---|---|
| Contatos | Targets mine (UID do alvo), pool '' e pool null; is_archived==0, last_message_at desc, limite50 por target; all de50 somente com canSeeAll |
| Threads | Mesmos tres targets, last_message_at desc e limite50; com canSeeAll, all de300 e target backup existente |
| Mais de Meus/pool | Mesmos filtros, limites crescentes50,100,150...; pool consulta '' e null separadamente |
| Mais de Equipe | Somente canSeeAll; janela global300,600,900... |
| Nao lidas | Scope permitido da caixa, unread_count>0, unread_count desc + last_message_at desc, janelas de50 crescentes |
| Mensagens | Thread selecionada ou fallback legado por contato, timestamp_wa desc, limite inicial10 e incremento15; retorno normalizado em ordem cronologica |
| Perfil e dono | Perfil efetivo do alvo em cada ciclo; thread aberta revalidada para detectar perda de dono/escopo |

canSeeAll continua exigindo role privilegiada E toggle ver_todos_leads. Nunca ampliar
acesso por departamento. Dedupe, merge, limites e flags de saturacao seguem a mesma
semantica atual; nao aplicar corte global500/2000 antes de separar os targets.

O servidor nao serializa nem hidrata backup para principal sem permissao. Campo
is_backup ausente continua significando falso, para nao excluir registros legados;
nao substituir isso por where is_backup==false, que excluiria documentos sem o campo.
Para preservar a janela efetivamente exibida hoje, consultar o mesmo top-N de origem
e remover backups antes da entrega, sem preencher silenciosamente com itens mais
antigos. Retornar apenas o booleano de saturacao necessario, sem dados dos itens negados.
Uma politica de reposicao para obter N itens elegiveis seria outra alteracao de janela.
Se houver cursor, ele deve ser opaco e validado; nao expor IDs/PII dos backups removidos
na resposta ou no cursor. A paginacao por limites crescentes atual pode ser preservada.

Owner/tenant/backup sao controles do servidor. Filtros visuais como qualificacao,
bot_completed, setor da caixa e tags continuam seguindo a UI do alvo; eles nao podem
substituir autorizacao. As consultas normais que apresentaram o comportamento de backup
preexistente ficam fora desta revisao: nao enfraquecer rules nem corrigir globalmente
as sessoes normais sem uma decisao separada. Registrar essa pendencia explicitamente.

Reaproveitar indices tenant-scoped das consultas atuais. Qualquer indice novo precisa
ser declarado e revisado em firestore.indexes.json; nunca substituir falta de indice
por full-scan. Nao introduzir teto de paginacao silencioso que altere a evidencia.

## Prazo, latencia e respostas tardias

Latencia aprovada: intervalo fixo de 15000 ms para a aba temporaria, centralizado em config.py.
Primeira carga, abertura de thread e Atualizar consultam imediatamente; depois, um ciclo
por vez a cada15s, sem requests sobrepostos. A UI informa "Atualizacao a cada15s" e
"Ultima atualizacao HH:MM:SS"; nao apresenta o modo como realtime. Falha mostra dados
antigos como desatualizados e nao dispara retry agressivo. Configuracao efetiva deve
chegar pelo client-config. Sons tambem ficam sujeitos a essa latencia.

Validar contrato, registro, alvo ativo e prazo no inicio E imediatamente antes de
entregar a resposta, inclusive nas leituras antigas allowlistadas e nos tres POSTs de
consulta. Resultado obtido antes do TTL mas pronto depois dele recebe401 sem dados.
Nao reutilizar apenas a validacao salva na entrada do middleware; falha de registry
nega acesso, sem cache de autorizacao. Cache de dados nao pode renovar ou contornar o TTL.
Preferir respostas limitadas e bufferizadas; nenhum stream longo fica liberado por uma
unica validacao inicial. Download CSV tambem exige a validacao final antes do corpo.

HTTP ja autorizado pode estar em transito quando o prazo vence. No browser, revalidar
deadline/geracao/selecionado antes de aplicar qualquer resultado; cancelar fetches e
descartar respostas tardias. End/expiracao/focus/visibility/online continuam limpando
estado, listeners e referencias, com signOut. Reload conserva apenas marcador nao
secreto e nunca restaura o admin na aba temporaria. Nenhum fallback para Firestore e
permitido se polling falhar ou transportPref escolher snapshot.

## Limites e custo

Polling aumenta leituras e pode atualizar a tela ate15s depois do operador normal.
Preservando as janelas originais, um ciclo de snapshot consulta ate150 contatos e
150 threads para operador; para supervisor com canSeeAll, ate200 contatos e
50+50+50+300+Nbackup threads. Sao envelopes teoricos, sem dedupe de cobranca e sem
medicao de custo real: os mesmos documentos podem ser cobrados em mais de um target e
novamente a cada15s. Perfil, registro, catalogos, mensagens e paginacao somam leituras.
O target dedicado where is_backup==true nao possui limite no frontend original e foi
preservado; portanto, nao se afirma que todas as queries tem cap. Evitar scans integrais
de fallback nao elimina esse target indexado. Antes de ativar, o responsavel precisa
avaliar custo/latencia por sessao e o volume de backups. Nao reduzir janela nem ampliar
cache de autorizacao silenciosamente para esconder o custo. A perda de realtime e o
tradeoff aprovado, sem alterar o funcionamento do operador normal.

O backend atual serve URLs conhecidas de midia sem get_current_user, por path/prefixo
global. Esta proposta nao revoga retroativamente essas URLs nem capturas/copias ja
recebidas. Se o requisito incluir revogar acesso a midia conhecida no TTL, isso exige
outra mudanca aprovada em serve_media/armazenamento/URLs; nao anunciar essa garantia
como efeito do polling. O TTL proposto controla novas autorizacoes de dados CRM.

## Arquivos e criterios de aceite

| Arquivos | Implementacao local validada |
|---|---|
| main.py, novo servico de leitura, impersonation.py | Cinco rotas estreitas, autorizacao final por resposta, scopes/backup/janelas e allowlist exata; preservar emissao/end/cleanup |
| firestore.rules | Negar toda leitura/escrita temporaria em todos os caminhos; manter politica normal |
| config.py e client-config | Intervalo efetivo explicito, centralizado e visivel |
| firebase.ts, CrmContext.tsx, api.ts, InternalChatPanel.tsx | Impersonate sem Firestore; polling separado, abort/geracao/deadline; queries/logica normal preservadas |
| Impersonation.tsx, types.ts e estilos | Latencia/ultima atualizacao/desatualizacao honestas, mantendo faixa e controles disabled |
| sims, emuladores, ADR/handoff/entrega | Provar o contrato revisado e registrar pendencias do caminho normal/midia |

Aceite minimo:

1. Nenhuma chamada getDoc/getDocs/onSnapshot no modo temporario, mesmo com preferencia
   snapshot, offline/reconexao ou falha HTTP. SDK/REST direto e negado antes/depois do TTL.
2. Fixtures com mais de50 por target e mais de300 globais reproduzem IDs/ordem/janelas
   visiveis, pool, paginacao, nao-lidas, operador e supervisor com perfil custom.
3. Backup mine/pool/null nunca e entregue ao operador; campo ausente e permitido; provar
   selecao top-N sem reposicao silenciosa e nenhuma ampliacao por setor/ID enumerado.
4. Query lenta que cruza o TTL ou fechamento devolve401 sem payload; browser descarta
   respostas que chegaram tarde. Refresh/reuso do token nao renova prazo.
5. Sessao normal mantem SDK/realtime, UID/query/menus atuais. Conta real, unread,
   atribuicao e last_login do alvo continuam intactos; tres POSTs de consulta funcionam.
6. Testar end online/offline, aba suspensa, reload, mudanca de dono/role/perfil, ausencia
   de indice e falha de registry; nenhuma rota cai em scan/fallback amplo ou escrita.
7. Rodar todos os gates existentes, novo sim de leitura/janelas e emuladores. Build e
   sims da implementacao atual nao substituem esses testes. Publicacao e aceite humano
   de staging continuam posteriores; nenhuma infraestrutura sera executada nesta proposta.
