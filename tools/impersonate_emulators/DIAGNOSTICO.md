# Diagnostico local: historico e contrato atual de impersonate

**Contrato atual: gate local APROVADO, 779 verificacoes, zero falhas, exit 0.**
Apos os achados abaixo, o usuario aprovou que Ver como consulte dados CRM
exclusivamente pelo backend com polling de 15s. As rules agora negam TODO acesso
direto temporario, mesmo antes do TTL e com sessao valida. A secao 3 registra
esse gate separadamente; ela nao converte o resultado anterior em aprovado nem
substitui os gates de prazo/janelas/backup do novo transporte HTTP.

## Historico: contrato anterior reprovado

Na revisao anterior, em 2026-10-14 (horario local), `npm.cmd test` terminou com
codigo 1. O runtime foi congelado para discutir os achados antes de mudar o contrato.

Foram concluidas **149 verificacoes positivas** antes do assert de TTL falhar.
Separadamente, as consultas equivalentes as do frontend produziram **24
observacoes de entrega indevida de backups**. O assert dessas consultas ficava
depois do teste de listener; a primeira excecao de TTL impediu que ele fosse
alcancado naquela execucao. Os asserts foram preservados enquanto se investigava
o desenho anterior, sem declarar o gate aprovado.

## Ambiente e reproducao

Somente Auth e Firestore Emulators no projeto ficticio `demo-impersonate`, com
dados sinteticos. `castro_crm` e `castro_crm_staging` sao apenas nomes de colecoes
nesse emulador. Nenhum projeto Firebase/GCP real foi consultado ou alterado.

| Componente | Versao usada |
| --- | --- |
| Node | 22.22.1 |
| npm | 11.12.0 |
| Java | Eclipse Temurin JRE 21.0.12.1+1 |
| firebase-tools | 15.31.0 |
| Firestore Emulator | 1.22.0 |
| firebase | 11.10.0 |
| firebase-admin | 13.4.0 |
| @firebase/rules-unit-testing | 4.0.1 |

JAR `cloud-firestore-emulator-v1.22.0.jar`, 136707194 bytes, SHA-256 conferido
contra o metadado instalado do Firebase CLI:

```text
9b6498b7f62714d67f48f59b3818883cd682dbcd46b9f59511de81c97bb5166c
```

Comandos PowerShell para reproduzir a partir da raiz do worktree:

```powershell
cd tools/impersonate_emulators
npm.cmd ci --cache .cache/npm
npm.cmd test
```

O runner carrega as rules versionadas em `../../firestore.rules`, remove
credenciais ADC e tokens do ambiente filho, fixa projeto e endpoints locais e
bloqueia HTTP(S) fora de loopback. A unica excecao HTTP(S) e a URL publica exata
do JAR da versao instalada, para permitir o download do binario na primeira
execucao. O runner tambem desativa a consulta de mensagem do dia do Firebase CLI.
Auth usa 127.0.0.1:9099; Firestore, 127.0.0.1:8080; hub, 127.0.0.1:4400; logging,
127.0.0.1:4500. Dependencias, JRE, JAR e logs locais sao ignorados pelo Git.

## 1. Listener aberto entrega alteracao depois do TTL

O teste anterior criava sessao valida com `ttl_seconds=300`, `created_at=expires_at-300s`
e vencimento aproximadamente cinco segundos a frente. Claims, registry e perfil
do alvo obedecem ao contrato. Isso exercita o limite minimo aprovado sem esperar
cinco minutos por execucao. O token do contexto de rules tem `auth_time` coerente
com a criacao da sessao.

Sequencia na versao anterior de `test.mjs`, funcao `expiryListener`:

1. Abrir `onSnapshot` em `departments/sample` antes de vencer e receber `sim`.
2. Esperar ate `expires_at + 1200ms` e gravar `evento-apos-expiracao` com o bypass
   exclusivamente local de seed do teste.
3. Capturar o valor e `Date.now()` de cada callback. Ha espera maxima de seis
   segundos para a entrega ou erro; nao e apenas uma expectativa de erro ausente.
4. Criar outro documento e outro contexto e executar `getDocFromServer` com os
   mesmos claims vencidos: a leitura e negada.
5. Alterar o registry para `closed` e atualizar o documento observado: o listener
   que estava aberto recebe `permission-denied` e termina.
6. Exigir que nenhum valor novo tenha sido entregue apos o TTL: o assert falha.

Evidencia da ultima execucao com JAR 1.22.0 (UTC; dados ficticios):

| Evento | Epoch em ms | UTC | Diferenca para expires_at |
| --- | --- | --- | --- |
| Callback inicial, valor `sim` | 1792026682537 | 2026-10-15T01:11:22.537Z | -4463ms |
| `expires_at` | 1792026687000 | 2026-10-15T01:11:27.000Z | 0 |
| Callback novo, valor `evento-apos-expiracao` | 1792026688259 | 2026-10-15T01:11:28.259Z | **+1259ms** |

Trecho da saida, sem tokens nem dados reais:

```text
INTEGRACAO: listener aberto antes do TTL
OK listener recebe dado antes de vencer
DIAGNOSTICO listener: {"denied":false,"deliveredAfterExpiry":true,"events":[{"value":"sim","received_at_ms":1792026682537,"expiry_ms":1792026687000},{"value":"evento-apos-expiracao","received_at_ms":1792026688259,"expiry_ms":1792026687000}]}
OK contexto/documento novos apos TTL negados
OK fechamento do registry invalida listener ja aberto
FALHOU: ERR_ASSERTION listener nao entrega dados novos apos TTL
```

O mesmo comportamento havia sido observado com firebase-tools 14.11.1 e
Firestore Emulator 1.19.8. A repeticao em 1.22.0 exclui somente a hipotese de que
bastava atualizar essa versao antiga. A negacao da consulta nova evita confundir
o achado com leitura de cache local. A invalidacao por `closed` demonstra que a
dependencia do registry consegue invalidar esse listener; isso nao comprova que
o prazo absoluto sozinho faca o mesmo.

A documentacao oficial descreve avaliacao de Security Rules antes da entrega de
atualizacoes, mas nao resolve, por si so, o comportamento temporal observado
neste teste: [consultas em tempo real](https://firebase.google.com/docs/firestore/real-time_queries_at_scale).
Nao foi verificado o comportamento de producao. O resultado local nao deve ser
promovido a uma conclusao de falha de producao nem convertido em gate aprovado.

## 2. Consultas do frontend entregam documentos de backup

A funcao `probeFrontendShapes` reproduz as consultas em
`frontend/src/context/CrmContext.tsx`: contatos com `assigned_to_uid`,
`is_archived == 0`, `orderBy(last_message_at, desc)` e `limit(50)`; conversas com
`assigned_to_uid`, a mesma ordenacao e limite. As consultas atuais nao incluem
`where(is_backup, ==, false)`.

Para cada colecao foram semeados um documento comum e um backup com o mesmo
dono: alvo, pool vazio e pool nulo. Todos os backups tem `is_backup: true`.
O seed pertence ao mesmo tenant sintetico, sem alterar as rules para diagnosticar.

Em **ambos** os prefixes (`castro_crm` e `castro_crm_staging`) e **ambas** as
colecoes (`wa_contacts` e `wa_conversations`), o resultado foi:

| Filtro assigned_to_uid | IDs entregues ao principal normal | IDs entregues ao preview |
| --- | --- | --- |
| UID do alvo | `mine`, **`backup`** | `mine`, **`backup`** |
| String vazia | `pool`, **`backup-pool`** | `pool`, **`backup-pool`** |
| null | `null`, **`backup-null`** | `null`, **`backup-null`** |

Total: 12 consultas por principal, 24 entregas de resultado contendo backup.
A leitura direta de documento de backup pelo preview foi negada na matriz. A
consulta com filtro de backup explicito tambem passou na matriz, mas essa
consulta auxiliar nao representa a shape atual do frontend e nao substitui o
teste acima. O comparador normal foi executado com as rules atuais; nao houve
execucao de servico real nem comparacao com uma publicacao anterior.

Ha uma issue aberta no repositorio oficial sobre `resource.data` parcial na
avaliacao de consultas do emulador e permissao indevida em testes de campos
ausentes: [firebase-tools #4420](https://github.com/firebase/firebase-tools/issues/4420).
Ela e uma pista de investigacao para o uso de
`resource.data.get('is_backup', false)`, **nao uma causa demonstrada** deste caso.
A documentacao exige que a consulta respeite as restricoes de regras sobre seu
resultado potencial: [regras e consultas](https://firebase.google.com/docs/firestore/security/rules-query).
Nao foram adicionados filtros ao frontend nem removida a protecao de backups.

## O que passou e o que permanece pendente

As 149 verificacoes positivas incluem prod/staging, UID efetivo, perfil ativo,
mudanca de role/perfil, isolamento de tenant/ambiente, escritas negadas, registry
server-only inclusive para cliente normal staging, namespace reservado sem
claims e dados de plataforma negados. A integracao Auth local tambem comprovou
que alteracoes de perfil/email/senha e exclusao da conta temporaria preservam a
conta e a senha originais; relogin sem claims permanece negado; refresh nao
estende `imp_exp`.

O gate daquele desenho **permaneceu vermelho** por TTL do listener e pela evidencia de
backups nas consultas reais. O contrato nao foi substituido por logout
cooperativo do frontend, limpeza tardia, teste estatico ou remocao de assert.
Os resultados foram discutidos antes de retomar mudancas de runtime. Nao houve deploy, publicacao de
rules, IAM, comandos gcloud, nem execucao contra dados reais.

O runner encerrou Auth, Firestore, hub e logging apos a falha. A verificacao local
posterior nao encontrou processo `java` nem portas 8080, 9099, 4400, 4500 ou 9150
em estado de escuta em 127.0.0.1.

## 3. Contrato aprovado depois do diagnostico: nenhum Firestore direto

O usuario aprovou a mudanca descrita em
[REVISAO_IMPERSONATE_TTL_BACKEND.md](../../docs/REVISAO_IMPERSONATE_TTL_BACKEND.md):
a aba temporaria passa a consultar o backend com polling, em vez de assinar
dados CRM diretamente no Firestore. Sessao normal conserva seu transporte e
grants atuais. A identidade Auth descartavel, registro/end/cleanup e protecao da
conta original permanecem.

As rules foram simplificadas: removidos todos os helpers de UID efetivo,
validacao de registro/perfil/prazo e ramos de leitura preview. Todo grant passa
por um principal normal, sem UID `imp_ro_*` e sem marcador `imp`; o marcador
malformado tambem nao autoriza acesso normal. O caminho normal sem `imp` ou com
`imp:false` conserva os grants existentes. O registro continua server-only para
todos os clientes, inclusive no wildcard normal staging. O indice de cleanup
continua necessario para o backend e nao concede acesso client-side.

Novo gate executado com as mesmas versoes e comando desta documentacao:

```text
LIMITACAO NORMAL: 12 consultas preexistentes entregaram backup; preview direto sempre negado
OK sessao ativa: listener negado sem receber snapshot
OK apos encerramento: listener negado sem receber snapshot
OK token TTL curto inicia antes de vencer
OK antes do TTL: listener negado sem receber snapshot
OK apos TTL: listener negado sem receber snapshot
OK deleteUser temporario nao exclui conta original
OK senha original do alvo continua valida
RESULTADO: 779 verificacoes, 0 falhas (Auth + Firestore locais)
Script exited successfully (code 0)
```

A matriz exige negacao de leitura e escrita para preview operador e supervisor
em documentos tenant-scoped, perfil proprio, contatos/threads mine/pool/colega/
backup, mensagens, settings, auditoria, midia/chunks, colecoes nao previstas,
outro tenant/ambiente, flat, plataforma e registro/descendentes. Consultas globais,
as 12 shapes reais do frontend e consultas com filtro backup explicito tambem
sao negadas ao temporario. UID real com `imp`, namespace reservado sem claims,
claims/registro divergentes e tentativa de herdar super_admin permanecem negados.

A integracao troca custom token por ID token no Auth Emulator e testa o SDK e
REST reais contra o Firestore Emulator. GET, runQuery, PATCH e DELETE retornam
403 em sessao ativa, apos refresh, apos fechamento do registro e apos o TTL.
Listeners recebem `permission-denied` sem entregar qualquer snapshot, inclusive
antes do TTL. Atualizar perfil/email/senha e excluir as contas descartaveis
preserva a conta e senha originais. Relogin password sem claims nunca habilita
os grants normais; refresh mantem o prazo original.

O achado de backups nas **12 consultas normais** continua registrado, fora do
escopo aprovado. O teste preserva e verifica os grants normais, sem exigir
permitir esse resultado ao preview nem declarar corrigido o caminho normal.
A ausencia de dados backup no polling e o TTL antes da serializacao HTTP sao
responsabilidade dos gates do backend, nao uma conclusao deste harness.

O runner encerrou todos os emuladores ao concluir. A verificacao posterior nao
encontrou processo Java nem portas locais 8080, 9099, 4400, 4500 ou 9150 em escuta.
Publicacao de rules/IAM/infra e aceite humano em staging continuam pendentes;
nenhum acesso aos dados/projetos reais foi feito para obter este resultado.
