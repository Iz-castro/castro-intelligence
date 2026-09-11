# Picker v2.1 — agenda paginada com busca indexada aprimorada

> **Status em 2026-09-11: PROPOSTA TÉCNICA / NÃO IMPLEMENTADO.**
> Este documento evolui o desenho do
> [Picker v2](PICKER_V2_AGENDA_PAGINADA.md) e deve ser usado como referência
> para a implementação. O v2 original fica preservado como histórico.
>
> O código atual ainda abre o modal por
> `loadAllContacts()` → `ensureAllContactsLoaded()` →
> `GET /api/wa/contacts/all?limit=10000`. Portanto, além do full scan
> por sessão, contatos além dos primeiros 10 mil não entram no cache local e
> não podem ser encontrados pelo picker.

## Objetivo numa frase

Entregar uma busca de contatos mais útil que a proposta no v2 — nome pelo
começo de qualquer palavra, telefone exato/pelo começo/pelo final e ranking
determinístico — mantendo paginação estável, isolamento LGPD e um orçamento de
poucas dezenas de leituras por interação.

## Decisão recomendada

Implementar primeiro uma solução **Firestore Standard nativa**, chamada aqui de
v2.1:

- listagem paginada em blocos de 50;
- busca por prefixo do nome completo;
- busca por prefixo de qualquer palavra de todos os aliases de nome;
- telefone normalizado com correspondência exata, começo nacional/local e
  final;
- ranking e deduplicação no backend;
- filtros de dono e qualificação aplicados no servidor antes do
  `limit`;
- cursor composto e opaco;
- escopo próprio + pool em uma única query;
- busca inicialmente sem paginação, limitada aos 50 melhores resultados.

Não adotar agora n-grams, busca vetorial, Firestore Enterprise nem motor externo.
Essas opções ficam como evolução condicionada a métricas reais de uso.

## 1. Problemas que o v2.1 precisa resolver

### 1.1 Full scan e teto invisível de 10 mil

O `NewContactModal` chama `loadAllContacts(search)`. O
`CrmContext` carrega `/api/wa/contacts/all?limit=10000` uma
vez por sessão e todas as buscas seguintes são feitas no navegador.

Consequências:

- milhares de reads ao abrir o picker;
- transferência e memória proporcionais ao tamanho da agenda;
- o custo se repete por tenant e por sessão;
- numa agenda com 15 mil contatos, aproximadamente 5 mil ficam fora da busca
  local;
- filtros e busca dependem de a agenda completa estar carregada.

### 1.2 `name_tokens` exato ainda é limitado

O v2 propôs:

```json
"name_tokens": ["joao", "silva"]
```

Isso encontra `silva`, mas não `sil` ou
`silv`. O v2.1 troca esse campo por prefixos limitados de cada
palavra.

### 1.3 O v2 perderia aliases pesquisáveis hoje

A busca atual verifica `display_name`, `declared_name` e
`whatsapp_profile_name`. Se o índice novo usar apenas o nome efetivo,
um nome declarado pode esconder o nome do perfil do WhatsApp da busca.

O índice do v2.1 deve considerar todos os aliases válidos, deduplicados.

### 1.4 Filtros client-side ficam incorretos com paginação

Hoje `ownerFilter` e `qualFilter` filtram a lista completa
no navegador. Com páginas de 50, o filtro poderia produzir uma página vazia
mesmo existindo resultados nas páginas seguintes.

Todos os filtros devem participar da query do backend e da identidade do
cursor.

### 1.5 Próprios + pool hoje são três streams

O escopo atual do operador combina:

1. `assigned_to == user_id`;
2. `assigned_to_uid == ""`;
3. `assigned_to_uid == null`.

Aplicar `limit(50)` em cada stream pode custar até 150 reads e exige
um cursor por stream mais merge ordenado. O v2.1 deve canonicalizar o escopo
antes de publicar o endpoint.

### 1.6 Cursor apenas por `sort_key` é ambíguo

Duas pessoas podem ter o mesmo nome. Usar somente:

```text
startAfter("0_joao silva")
```

pode repetir ou pular contatos. A ordem deve incluir o ID do documento como
desempate.

### 1.7 Cache e renderização atuais podem ficar caros ou desatualizados

O cache integral não é invalidado por todos os caminhos de renome, qualificação,
atribuição e sincronização. Além disso, o modal pode renderizar até 10 mil
botões de uma vez. O v2.1 elimina ambos os problemas ao consultar dados atuais e
renderizar somente a página ou o resultado limitado.

## 2. Contrato funcional para o usuário

### Ao abrir o picker

- carregar no máximo 50 contatos;
- manter nomes antes de registros sem nome útil;
- ordenar alfabeticamente;
- mostrar `Ver mais` enquanto houver outra página;
- não chamar `/api/wa/contacts/all`.

### Ao pesquisar nomes

| Entrada | Resultado esperado |
|---|---|
| `jo` | encontra João Silva |
| `joao` | encontra João Silva, com ou sem acento |
| `sil` | encontra João Silva |
| `silva` | encontra João Silva |
| `jo sil` | encontra nomes cujas palavras casem com os dois prefixos |
| `ilv` | não garantido nesta versão |
| `silvaa` | não garantido nesta versão |

### Ao pesquisar telefones

| Entrada | Estratégia |
|---|---|
| `+55 (31) 98344-0484` | normalizar e tentar correspondência exata |
| `3198344` | começo do número nacional |
| `8344` | começo da parte local |
| `0484` | final do telefone |

Caracteres `+`, espaço, `( )`, `-` e
`.` devem ser ignorados na classificação numérica.

### Regra comunicável

> Busque pelo começo do nome ou sobrenome. No telefone, você pode usar o número
> completo, o começo da parte local ou os últimos dígitos.

## 3. Campos indexáveis em `wa_contacts`

Todos os campos abaixo são derivados e devem ser produzidos por uma única função
pura, usada no write-path e no backfill.

| Campo | Exemplo | Finalidade |
|---|---|---|
| `sort_key` | `0_joao silva` | paginação alfabética; nomes antes de telefones |
| `name_normalized` | `joao silva` | prefixo do nome efetivo |
| `name_prefixes` | `["jo","joa","joao","si","sil","silv","silva"]` | prefixo de qualquer palavra/alias |
| `phone_e164_digits` | `5531983440484` | telefone canônico sem `+`; exato e prefixo internacional |
| `phone_national` | `31983440484` | prefixo com DDD |
| `phone_local` | `983440484` | prefixo da parte local |
| `wa_id_reversed` | `4840443891355` | busca pelos últimos dígitos |
| `search_schema_version` | `1` | reconciliação e futuros backfills |

Além disso, o backfill deve canonicalizar campos já existentes usados como
filtros:

| Campo | Valores canônicos no v2.1 |
|---|---|
| `assigned_to_uid` | UID do dono; `""` para pool; `__backup__` para backup |
| `assigned_to` | ID numérico do dono ou `null` |
| `qualification` | sempre preenchido; legado vazio vira `novo` |
| `is_archived` | inteiro `0` ou `1`, nunca ausente |
| `is_backup` | booleano, nunca ausente |

### 3.1 Normalização de nomes

Criar helpers centrais, por exemplo:

```python
normalize_search_text(value: str) -> str
build_contact_search_fields(contact: dict) -> dict
```

Regras:

1. `casefold()`;
2. Unicode NFKD;
3. remover marcas de acento;
4. converter pontuação e separadores em espaço;
5. colapsar espaços;
6. remover espaços nas extremidades.

Exemplos:

| Original | Normalizado |
|---|---|
| `João da Silva` | `joao da silva` |
| `D'Ávila` | `d avila` |
| `Ana-Maria` | `ana maria` |
| `  CLÍNICA   SÃO JOSÉ  ` | `clinica sao jose` |

O nome efetivo para `name_normalized` e `sort_key` continua
seguindo:

```text
declared_name || whatsapp_profile_name || display_name
```

Porém, `name_prefixes` deve ser a união dos prefixos encontrados em:

- `declared_name`;
- `whatsapp_profile_name`;
- `display_name`, somente se for distinto e não for apenas telefone.

### 3.2 Limites de prefixos

Para impedir fan-out de índices e abuso por nomes anormais:

- mínimo de 2 caracteres por prefixo;
- máximo de 15 caracteres por prefixo;
- máximo de 12 palavras somando todos os aliases;
- máximo de 100 prefixos únicos por contato;
- máximo de 120 caracteres normalizados por alias;
- ordenar e deduplicar o array para backfill idempotente.

Se uma palavra pesquisada tiver mais de 15 caracteres, usar os 15 primeiros
para buscar candidatos e validar a palavra inteira no backend.

Exemplo:

```text
João Silva
→ jo, joa, joao, si, sil, silv, silva
```

Não gerar todos os substrings nem n-grams nesta versão.

### 3.3 Regra de `sort_key`

```text
nome útil presente  → "0_" + name_normalized
sem nome útil       → "1_" + phone_e164_digits
```

Considerar nome útil quando houver pelo menos uma letra após a normalização,
mesmo que o original comece por emoji, número ou pontuação. Isso trata nomes
como `3M Equipamentos` melhor que a regra `startswith(letter)`.

### 3.4 Normalização de telefone

Separar dois conceitos:

- normalização de número completo, reutilizando a regra brasileira existente
  (`normalize_br_phone` e variantes com/sem nono dígito);
- normalização de termo parcial, que apenas remove máscara e classifica o
  formato, sem inventar DDD, país ou nono dígito.

O write-path deve calcular:

```text
phone_e164_digits = wa_id canônico, somente dígitos
phone_national    = número sem o 55 quando aplicável
phone_local       = últimos 8 ou 9 dígitos, conforme o número canônico
wa_id_reversed    = reverse(phone_e164_digits)
```

## 4. Escopo LGPD canônico

### 4.1 Invariante após o backfill

| Situação | `assigned_to` | `assigned_to_uid` |
|---|---:|---|
| Lead de operador | ID numérico | UID Firebase não vazio |
| Pool/fila | `null` | `""` |
| Backup | conforme origem | `__backup__` |

Após a reconciliação não devem existir contatos ativos com:

- `assigned_to_uid == null`;
- `assigned_to_uid` ausente;
- `assigned_to` preenchido e `assigned_to_uid == ""`;
- UID que não corresponda ao `assigned_to`.

### 4.2 Query de operador

O operador comum passa a usar uma única query lógica:

```python
where("assigned_to_uid", "in", [firebase_uid, ""])
```

Isso substitui os três streams atuais. Durante a migração, regras e código
legados podem continuar aceitando `null`, mas o endpoint v2.1 só deve
ser habilitado depois de a reconciliação provar zero documentos legados.

### 4.3 Autoridade

- o backend deriva tenant, UID, ID numérico e privilégios da sessão;
- operador comum não pode ampliar escopo enviando `owner_id`;
- `owner_id` só é aceito para quem passa
  `can_see_all_tenant`;
- o operador solicitado deve pertencer ao tenant atual;
- `_require_contact_access` permanece obrigatório em
  `/api/wa/conversation/open`, pois a posse pode mudar entre a busca e
  o clique;
- o Admin SDK ignora Firestore Security Rules: o endpoint é responsável por
  toda autorização.

## 5. API

Separar paginação de busca. A busca usa POST para evitar nome/telefone na URL,
histórico do navegador e logs automáticos de request.

### 5.1 Listagem paginada

```http
GET /api/wa/contacts/picker?page_size=50&cursor=<token>&owner_id=<id>&qualification=<valor>
```

Parâmetros:

| Parâmetro | Regra |
|---|---|
| `page_size` | default 50; mínimo 1; máximo 50 |
| `cursor` | opcional; token opaco, autenticado e versionado |
| `owner_id` | opcional e somente privilegiado |
| `qualification` | opcional; enum canônico |

Resposta:

```json
{
  "contacts": [],
  "next_cursor": "opaque-token-or-null",
  "has_more": true,
  "mode": "page"
}
```

Buscar `page_size + 1` documentos para calcular
`has_more`, retornar apenas `page_size` e cobrar no máximo
51 leituras de documentos de contato por página. Leituras auxiliares e de
entradas de índice devem ser medidas separadamente.

### 5.2 Busca

```http
POST /api/wa/contacts/picker/search
Content-Type: application/json
```

Body:

```json
{
  "q": "sil",
  "limit": 30,
  "owner_id": null,
  "qualification": null
}
```

Validação:

- nome: mínimo 2 caracteres normalizados;
- telefone parcial: mínimo 4 dígitos;
- `limit`: default 30, máximo 50;
- termo vazio ou curto: HTTP 400 com mensagem utilizável pela UI;
- `owner_id` por operador comum: HTTP 403;
- rate limit, se acionado: HTTP 429;
- nunca registrar `q` cru.

Resposta:

```json
{
  "contacts": [
    {
      "id": 123,
      "display_name": "João Silva",
      "phone_formatted": "(31) 98344-0484",
      "qualification": "novo",
      "assigned_to": null,
      "assigned_name": "",
      "channel_id": 4,
      "match_kind": "name_token_prefix"
    }
  ],
  "mode": "search",
  "truncated": false
}
```

A resposta deve conter apenas os campos necessários ao card e à abertura da
conversa. Não retornar notas, tags, dados de consentimento ou outros campos do
documento completo.

### 5.3 Por que a busca não será paginada inicialmente

Uma busca pode unir nome completo, prefixo de palavra, telefone local e sufixo.
Não existe um único cursor Firestore que represente corretamente esse merge.

No v2.1:

- cada ramo tem limite próprio;
- o backend deduplica e ranqueia;
- retorna até 50;
- `truncated=true` orienta a interface a pedir mais caracteres.

Paginar busca fica fora do escopo até existir necessidade medida. Se for
implementada depois, o cursor precisará guardar uma posição por ramo e o estado
do merge.

## 6. Planejador de busca e orçamento de reads

Definir um orçamento global, por exemplo:

```python
SEARCH_CONTACT_DOCUMENT_BUDGET = 50
```

O código não pode executar quatro queries independentes com
`limit(50)`. Cada ramo recebe apenas parte do saldo restante.

Esse orçamento cobre snapshots de `wa_contacts` e point reads
auxiliares como `wa_contact_index`. Toda query vazia tem cobrança
mínima e certas query shapes também podem cobrar entradas de índice; por isso o
valor faturado deve ser validado com Query Explain e Monitoring, não inferido
somente pelo tamanho da resposta.

### 6.1 Classificação

Depois de `strip()`:

- se contém letras, modo nome;
- se contém apenas dígitos e caracteres de máscara telefônica, modo telefone;
- qualquer outro termo inválido retorna 400;
- empresa alfanumérica como `3M` é nome porque contém letra.

### 6.2 Busca por nome

Ramo A — prefixo do nome efetivo:

```text
name_normalized >= "jo"
name_normalized <= "jo\uf8ff"
limit(25)
```

Ramo B — prefixo de qualquer palavra/alias:

```text
name_prefixes array_contains "sil"
limit(25)
```

Para múltiplas palavras:

1. normalizar e separar os termos;
2. escolher o prefixo mais longo/seletivo para o
   `array_contains`;
3. filtrar no backend exigindo que todas as palavras digitadas sejam prefixo de
   alguma palavra de qualquer alias;
4. marcar `truncated=true` se o limite de candidatos impedir
   conclusão segura.

Não usar `array-contains-any` para representar AND: sua semântica é
OR.

### 6.3 Busca por telefone

Ordem:

1. número completo: tentar lookup exato pelo `wa_contact_index`
   existente;
2. escolher um prefixo compatível com o formato:
   - país presente → `phone_e164_digits`;
   - DDD presente → `phone_national`;
   - parte local → `phone_local`;
3. consultar também o sufixo por
   `reverse(q_digits)` em `wa_id_reversed`;
4. repartir o saldo entre prefixo e sufixo;
5. deduplicar pelo ID do contato.

O lookup exato também passa pela mesma checagem de tenant, visibilidade,
arquivado e backup. Um número existente, mas sem acesso, deve ser
indistinguível de um número inexistente.

### 6.4 Ranking determinístico

Ordenar resultados da busca por:

1. `phone_exact`;
2. `declared_name_exact`;
3. `whatsapp_profile_name_exact`;
4. `name_full_prefix`;
5. `name_token_prefix`;
6. `phone_national_prefix`;
7. `phone_local_prefix`;
8. `phone_suffix`;
9. `sort_key`;
10. ID do documento.

Dentro do mesmo nível, nome declarado pode preceder alias do WhatsApp.

## 7. Paginação estável

### 7.1 Ordem

```text
orderBy("sort_key", ASC)
orderBy(documentId(), ASC)
```

O cursor lógico contém:

```json
{
  "v": 1,
  "last_sort_key": "0_joao silva",
  "last_document_id": "123",
  "tenant_id": "hubloc",
  "scope_fingerprint": "...",
  "filters_fingerprint": "...",
  "expires_at": "..."
}
```

O token enviado ao navegador deve ser autenticado e opaco. Como
`last_sort_key` contém nome ou telefone, preferir criptografia
autenticada, não apenas Base64. O token deve:

- expirar;
- ser vinculado ao tenant e ao usuário/escopo;
- ser vinculado a `owner_id` e `qualification`;
- rejeitar alteração de versão ou assinatura;
- retornar 400 para cursor inválido, sem expor conteúdo interno.

### 7.2 Mudança durante a paginação

Uma alteração de nome pode mover um contato entre páginas. Para esta versão:

- aceitar essa consistência de navegação;
- deduplicar IDs no frontend;
- zerar resultados e cursor sempre que busca ou filtro mudar;
- não prometer snapshot congelado da agenda.

## 8. Filtros aplicados antes do `limit`

Toda query começa excluindo:

```text
is_archived == 0
is_backup == false
```

Depois aplica:

- escopo da sessão;
- `owner_id`, se privilegiado;
- `qualification`, se presente;
- campo de busca ou ordenação;
- `limit`.

Nunca filtrar dono, qualificação, arquivado ou backup apenas sobre os 50
documentos já retornados.

O fallback atual de qualificação vazia para `novo` deixa de existir
na query: o backfill deve preencher `qualification="novo"` antes.

## 9. Matriz de queries e índices

Os índices definitivos devem ser versionados em
`firestore.indexes.json`. Não depender apenas de comandos manuais ou
links de erro do console.

### 9.1 Dimensões de acesso/filtro

Planejar somente as combinações que a interface realmente oferece:

1. privilegiado sem filtros;
2. privilegiado por `owner_id`;
3. privilegiado por `qualification`;
4. privilegiado por dono + qualificação;
5. operador por `assigned_to_uid in [uid, ""]`;
6. operador por escopo + qualificação.

Todas incluem `is_archived` e `is_backup`.

### 9.2 Campos de ordenação/range

Cruzar as dimensões necessárias com:

- `sort_key` para página;
- `name_normalized` para prefixo do nome efetivo;
- `name_prefixes ARRAY_CONTAINS` para palavra/alias;
- `phone_e164_digits`;
- `phone_national`;
- `phone_local`;
- `wa_id_reversed`.

Cuidados:

- um índice composto admite no máximo um campo array;
- consultas com `array_contains` precisam de índices próprios;
- `documentId()` é o desempate do cursor;
- igualdade, `in`, array e range geram combinações distintas;
- não criar cegamente o produto cartesiano: implementar as query shapes, rodar
  testes no emulador/staging e versionar apenas os índices usados;
- usar Query Explain em staging para conferir entradas varridas.

### 9.3 Ordem de deploy

1. incluir os índices no arquivo versionado;
2. publicar no projeto correto;
3. aguardar todos ficarem `READY`;
4. executar smoke tests das seis dimensões acima;
5. somente então habilitar o endpoint para usuários.

Código antes de índice pode causar `FAILED_PRECONDITION` para
operadores.

## 10. Write-path

### 10.1 Helper único

Evitar cálculos duplicados em endpoints. Toda criação ou mudança relevante deve
passar pelo mesmo helper que gera os campos de busca.

Cobrir, no mínimo:

- criação por webhook/state sync em `upsert_wa_contact`;
- atualização de `whatsapp_profile_name`;
- canonização de `wa_id`;
- criação manual;
- preenchimento de nome em contato existente;
- `update_wa_contact_declared_name`;
- arquivar/desarquivar;
- atribuir, transferir, devolver à pool e devolver ao bot;
- importações e contatos de backup.

Campos derivados devem ser escritos no mesmo update dos campos-fonte sempre que
possível.

### 10.2 Mudança parcial de nome

Para recalcular aliases corretamente, uma atualização parcial precisa conhecer
o documento atual. Centralizar essa leitura/mescla; não tentar formar
`name_prefixes` apenas com o campo novo.

### 10.3 Versão

`search_schema_version=1` em todos os contatos reconciliados.
Mudanças futuras na normalização incrementam a versão e permitem localizar
documentos que precisam de novo backfill.

## 11. Backfill e reconciliação

Criar script dedicado, por exemplo:

```text
scripts/backfill_contact_picker_v21.py
```

Requisitos:

- `--tenant` obrigatório e validado;
- `--dry-run` como default;
- `--apply` explícito;
- idempotente;
- lotes abaixo do limite do Firestore;
- só escrever documento cujo resultado realmente mudou;
- contadores por campo e por anomalia;
- não imprimir nome ou telefone;
- checkpoint/reexecução segura;
- resumo final com total lido, alterado, ignorado e falhas.

O backfill também deve:

- preencher `is_archived=0` quando ausente;
- preencher `is_backup=false` quando ausente;
- preencher `qualification="novo"` quando vazia/ausente;
- resolver `assigned_to_uid` a partir do usuário dono;
- transformar pool `null`/ausente em `""`;
- preservar `__backup__`;
- registrar anomalias de dono sem usuário/UID para correção antes do cutover.

### Gate obrigatório de dados

Não habilitar v2.1 até que, por tenant:

- 100% dos contatos esperados tenham `search_schema_version=1`;
- 100% tenham todos os campos usados em `where`/
  `orderBy`;
- zero contatos ativos estejam com estado de dono/UID inconsistente;
- amostras de nomes e telefones tenham sido comparadas com a busca atual.

## 12. Frontend — `NewContactModal`

### Estado sugerido

Separar:

- `inputValue`: o que está no campo;
- `submittedQuery`: termo da resposta vigente;
- `contacts`;
- `nextCursor`;
- `mode`: `page | search`;
- `loadingInitial`;
- `loadingMore`;
- `searching`;
- `truncated`;
- `requestSequence` ou `AbortController`.

As funções de consulta expostas pelo contexto devem ter identidade estável
(`useCallback`) ou viver em um hook dedicado. Caso contrário, um
render global pode reiniciar o efeito e abrir consultas desnecessárias.

### Interação

- abrir → primeira página;
- nome com pelo menos 2 caracteres ou telefone com pelo menos 4 dígitos;
- debounce recomendado de 350 ms;
- Enter dispara imediatamente;
- cancelar request anterior;
- resposta antiga nunca substitui resposta mais nova;
- manter indicação visual de “Buscando...” sem apresentar resultado antigo
  como se correspondesse ao texto novo;
- limpar termo retorna à primeira página;
- mudar dono/qualificação limpa lista e cursor e refaz a consulta;
- `Ver mais` existe apenas no modo página;
- busca truncada mostra: “Muitos resultados. Digite mais caracteres.”;
- destacar visualmente o nome/palavra ou trecho do telefone que casou;
- mostrar responsável e canal quando isso ajudar a distinguir homônimos;
- exibir nome na ordem `declared_name || whatsapp_profile_name ||
  display_name || phone_formatted`, sem trocar um nome encontrado por
  “Contato”;
- preservar navegação por teclado e foco;
- em erro, oferecer retry sem apagar silenciosamente resultados válidos.

O modal nunca deve montar mais cards do que o limite retornado pelo endpoint.

Placeholder recomendado:

> Nome, sobrenome ou telefone

Texto auxiliar:

> Use ao menos 2 letras ou 4 números.

### Contador

Não mostrar o número carregado como se fosse o total filtrado.

Opções:

- página: “50 contatos exibidos” e botão `Ver mais`;
- busca completa: “N resultados”;
- busca truncada: “50+ resultados”.

O `count_only=1` da sidebar permanece inalterado e nunca volta a
carregar a agenda.

### Cache

Cache curto em memória pode usar:

```text
tenant + user_scope + mode + normalized_query + owner + qualification + cursor
```

Limpar ao criar, renomear, atribuir, arquivar ou desarquivar contato. Cache não
é requisito para o primeiro release.

## 13. LGPD, segurança e logs

- usar POST com JSON para o termo de busca;
- responder `Cache-Control: private, no-store`;
- nunca registrar nome, telefone, prefixos ou cursor descriptografado;
- telemetria registra apenas modo, tamanho do termo em faixa, número de ramos,
  resultados, truncamento, duração e estimativa de reads;
- vincular cursor a tenant, usuário/escopo e filtros;
- limitar page size e search limit no backend, ignorando valores maiores;
- aplicar rate limit por tenant + UID se houver abuso;
- auditar uso de eventual busca completa privilegiada;
- manter `_require_contact_access` no clique;
- testes cross-tenant são obrigatórios;
- exclusão/anonimização LGPD deve remover também os campos derivados;
- exportação não precisa expor `name_prefixes` ou números auxiliares,
  pois são dados técnicos derivados.

## 14. Observabilidade

Criar métricas sem PII:

- `picker_page_requests_total`;
- `picker_search_requests_total{mode}`;
- `picker_results_returned`;
- `picker_zero_results_total{mode}`;
- `picker_search_truncated_total{mode}`;
- `picker_query_duration_ms`;
- `picker_contact_reads_estimated`;
- `picker_403_total`;
- `picker_400_cursor_total`;
- `picker_failed_precondition_total`;
- seleção de contato após busca, apenas como contador agregado.

Não usar o termo pesquisado como label, atributo de trace ou texto de log.

Alertas/gates iniciais:

- qualquer `FAILED_PRECONDITION`;
- p95 acima de 600 ms por período sustentado;
- mais de 75 reads estimados numa interação;
- aumento inesperado de 403;
- modal chamando `/contacts/all?limit=10000`.

## 15. Testes

### 15.1 Unitários — normalização

- João / JOAO / joao;
- D’Ávila, Ana-Maria e espaços repetidos;
- emoji antes do nome;
- empresa iniciada por número;
- aliases declarado e WhatsApp;
- palavra de 1 caractere;
- limites de 15 caracteres, 12 palavras e 100 prefixos;
- idempotência e `search_schema_version`.

### 15.2 Unitários — telefone

- E.164 com `+55`;
- máscara brasileira;
- DDD + móvel;
- fixo de 8 dígitos;
- começo local;
- final de 4 ou mais dígitos;
- variante brasileira com/sem nono dígito;
- termo curto rejeitado;
- entrada mista inválida.

### 15.3 Ranking e merge

- telefone exato vence sufixo;
- nome completo vence prefixo de palavra;
- declarado vence alias em empate;
- mesmo contato vindo de dois ramos aparece uma vez;
- limite global nunca passa de 50 candidatos lidos/retornados conforme o
  orçamento definido;
- ordem final é determinística.

### 15.4 Permissões

Matriz:

| Perfil | Próprio | Pool | Outro operador | Backup | Arquivado |
|---|---:|---:|---:|---:|---:|
| Operador | sim | sim | não | não | não |
| Supervisor/admin | sim | sim | sim | não no picker | não |

Testar ainda:

- dois tenants;
- `owner_id` de outro tenant;
- operador enviando `owner_id`;
- contato transferido entre busca e clique;
- número exato existente, mas proibido, sem vazamento de existência.

### 15.5 Paginação

- 0, 1, 49, 50, 51 e múltiplo exato de 50 contatos;
- muitos contatos com o mesmo `sort_key`;
- nenhuma duplicação entre páginas no fluxo normal;
- última página;
- cursor adulterado, expirado e de outro filtro/usuário/tenant;
- nome alterado durante a paginação;
- filtro muda e cursor é zerado.

### 15.6 Frontend

- debounce;
- Enter imediato;
- cancelamento de resposta anterior;
- loading inicial e `Ver mais`;
- retry;
- resultado truncado;
- teclado/foco;
- nenhuma chamada a `loadAllContacts`/
  `ensureAllContactsLoaded` pelo modal.

### 15.7 Staging com Firestore real

- índices READY;
- página como admin;
- página como operador;
- filtro de dono;
- filtro de qualificação;
- nome completo;
- começo de sobrenome;
- telefone completo;
- começo local;
- final do telefone;
- Query Explain nas query shapes;
- medir reads e latência;
- abrir cada resultado e conferir autorização.

Como não existe suíte pytest versionada, criar um simulador dedicado
(`tools/sim_picker_v21.py`) e manter também o smoke de staging.

## 16. Plano de execução

1. **Helpers puros + testes:** normalização, prefixos, telefone e ranking.
2. **Write-path:** dual-write de todos os campos derivados e canonicalização do
   escopo.
3. **Backfill dry-run:** executar por tenant e revisar anomalias.
4. **Backfill apply + reconciliação:** atingir os gates de 100%.
5. **Índices:** versionar, publicar e esperar READY.
6. **Backend:** endpoints de página e busca, autorização, cursor e métricas.
7. **Teste em staging:** funcional, LGPD, Query Explain e custo.
8. **Frontend sob feature flag:** modal novo sem remover ainda o fallback.
9. **Canário:** privilegiado, depois um operador, depois tenant inteiro.
10. **Expansão por tenant:** observar p95, erros, reads e zero-result.
11. **Estabilização:** remover do modal a dependência de
    `loadAllContacts`; manter `/all` apenas para usos
    administrativos explícitos.

Não fazer shadow full-scan em produção para comparar resultados, pois isso
reintroduziria justamente o custo eliminado. Comparação deve ocorrer em staging
ou sobre amostra offline controlada.

## 17. Rollback e kill switch

Feature flag por tenant:

```text
picker_v21_enabled = false | true
```

Rollback:

- desabilitar flag e voltar o modal ao fluxo anterior;
- não remover campos derivados nem índices durante o incidente;
- endpoint antigo e `count_only=1` continuam disponíveis;
- corrigir dados/índice/backend e reabilitar por tenant.

O fallback para full scan é temporário e não deve voltar a ser acionado pela
sidebar.

## 18. Critérios de aceite

- abrir picker não faz full scan;
- abertura lê no máximo 51 documentos de contato;
- busca respeita o orçamento global e nunca executa vários
  `limit(50)` sem coordenação;
- `sil` encontra João Silva;
- busca funciona por nome declarado e perfil do WhatsApp;
- telefone funciona completo, por começo nacional/local e por final;
- acentos, caixa e máscara não alteram o resultado;
- contatos acima do antigo teto de 10 mil são encontráveis;
- filtros de dono e qualificação são aplicados antes do `limit`;
- homônimos não são pulados nem repetidos pela paginação normal;
- operador vê somente próprios + pool;
- backup e arquivados nunca aparecem;
- nenhum termo cru aparece em URL, logs ou traces;
- contato transferido após a busca continua protegido no clique;
- todos os contatos novos/alterados recebem campos de
  `search_schema_version=1`;
- índices estão READY antes do cutover;
- `count_only=1` da sidebar não regride.

## 19. Fora do escopo e gatilho para v3

Não fazem parte do v2.1:

- substring arbitrária no meio da palavra;
- tolerância automática a erro ortográfico;
- busca semântica/vetorial;
- pesquisa em notas ou conteúdo de mensagens;
- paginação do merge de busca;
- migração de edição do Firestore;
- sincronização com motor externo.

Reavaliar Firestore Enterprise ou um serviço como Algolia/Typesense se métricas
mostrarem:

- muitas buscas sem resultado seguidas de correção ortográfica;
- demanda frequente por trecho no meio da palavra;
- necessidade de múltiplas palavras com ranking rigoroso;
- necessidade de facetas complexas além de dono e qualificação.

Firestore Enterprise possui busca textual nativa, mas exige outra edição,
índices e modelo de cobrança. A decisão deve ser arquitetural e financeira, não
um detalhe do picker. Busca vetorial não é indicada para identificar pessoas ou
telefones: esse lookup deve ser determinístico.

## 20. Arquivos previstos

- `database_firestore.py`: helpers, write-path e queries;
- `main.py`: contratos e endpoints;
- `frontend/src/context/CrmContext.tsx`: cliente paginado/search;
- `frontend/src/App.tsx`: `NewContactModal`;
- `firestore.indexes.json`: índices compostos versionados;
- `firestore.rules`: retirada futura do legado
  `assigned_to_uid == null`, somente após backfill;
- `scripts/backfill_contact_picker_v21.py`: migração;
- `tools/sim_picker_v21.py`: simulação/testes.

## Referências oficiais

- Consultas e limitações:
  <https://firebase.google.com/docs/firestore/query-data/queries>
- Paginação por cursor:
  <https://firebase.google.com/docs/firestore/query-data/query-cursors>
- Índices e limites:
  <https://firebase.google.com/docs/firestore/query-data/index-overview>
- Custos e uso de cursor em vez de offset:
  <https://firebase.google.com/docs/firestore/pricing>
- Query Explain:
  <https://cloud.google.com/firestore/docs/query-explain>
- Busca textual no Firestore Enterprise:
  <https://firebase.google.com/docs/firestore/enterprise/text-search>
