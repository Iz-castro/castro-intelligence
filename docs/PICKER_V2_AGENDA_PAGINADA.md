# Picker v2 — agenda paginada com busca indexada

> **Status:** desenho aprovado pelo PO em 2026-07-18; implementação agendada.
> **Motivação:** [docs/INVESTIGACAO_READS_FIRESTORE_2026-07.md](INVESTIGACAO_READS_FIRESTORE_2026-07.md)
> (o Fix #1 — contador via aggregate count, commit `f8f2b03`, rev `00077-xer` —
> matou o dreno da sidebar; o picker `+` ainda paga full scan 1× por sessão).
> **Gate recomendado:** entregar ANTES do go-live da Varizemed real (agenda
> estimada de 15-20k pacientes → um full scan lá custa 3× o dreno diário
> inteiro do Hubloc).

## Objetivo numa frase

O picker nunca mais lê a agenda inteira — toda interação vira query indexada
custando dezenas de reads, **independente do tamanho da agenda** (constante
com 6k ou 60k contatos). É o que torna o padrão sustentável em multi-tenant:
o billing do Firestore é por projeto; cada tenant novo hoje replica o
full-scan na mesma fatura.

## Estado atual (o que muda)

- `NewContactModal` ([frontend/src/App.tsx](../frontend/src/App.tsx) ~187) abre →
  `loadAllContacts()` → `ensureAllContactsLoaded()`
  ([CrmContext.tsx](../frontend/src/context/CrmContext.tsx) ~2004, single-flight +
  cache em state) → `GET /api/wa/contacts/all?limit=10000` →
  full scan (privilegiado: 6.5k docs; operador: queries escopadas, aline ~2.7k).
- Busca: substring client-side sobre o cache, 5 campos, a cada tecla (debounce
  250ms). Instantânea e poderosa — mas exige a lista inteira em memória.
- Ordenação: computada em Python ([main.py](../main.py) `_sort_key` ~1157):
  contatos COM nome real primeiro, alfabético; telefones depois. **Não é
  paginável** — não existe como campo.

## 1. Mudança de dados — campos novos em `wa_contacts`

Gravados no write-path + backfill one-off nos existentes:

| Campo | Exemplo (João Silva, wa_id 5531983440484) | Serve pra |
|---|---|---|
| `sort_key` | `"0_joao silva"` (tem nome real) / `"1_5531983440484"` (só telefone) | ordenar paginado (nomes→telefones, alfabético) **e** busca de nome por prefixo |
| `wa_id_reversed` | `"4840443891355"` | busca de telefone por SUFIXO (prefixo do invertido = final do original) |
| `name_tokens` (opcional, recomendado) | `["joao", "silva"]` | achar por palavra exata ("silva" → João Silva) via `array_contains` |

Regras do `sort_key`:
- nome efetivo = `declared_name || whatsapp_profile_name || display_name`
  (mesma precedência do `_sort_key` atual), lowercase, sem acentos
  (normalizar NFD e remover combining marks — busca "joao" tem que achar "João").
- prefixo `"0_"` se o nome efetivo começa com letra; `"1_" + wa_id` caso contrário.

## 2. Queries por interação

**Abrir o picker (1ª página):**
```
wa_contacts.orderBy("sort_key").limit(50)                      → 50 reads
```

**"Ver mais" (cursor nativo):**
```
...orderBy("sort_key").startAfter(<sort_key do último>).limit(50) → 50 reads
```

**Busca no Enter** — o backend classifica o input:
- **Só dígitos** (`83440484`): inverte → prefixo no invertido:
  ```
  where("wa_id_reversed", ">=", "48404438")
    .where("wa_id_reversed", "<=", "48404438\uf8ff")           → ~1-5 reads
  ```
- **Tem letras** (`jo`): prefixo no sort_key:
  ```
  where("sort_key", ">=", "0_jo").where("sort_key", "<=", "0_jo\uf8ff")
    .limit(50)                                                 → até 50 reads
  ```
  (+ `where("name_tokens", "array_contains", "silva")` como segunda query,
  merge client-side, se `name_tokens` for adotado)

**Operador comum:** MESMAS queries compostas com o escopo LGPD existente
(`assigned_to == id` / `assigned_to_uid in ("", None)`) — espelha
`get_wa_contacts_scoped_for_user` ([database_firestore.py](../database_firestore.py)
~1830). Isolamento inalterado. Exige os índices compostos abaixo.

## 3. Índices compostos necessários

Só o caminho do operador precisa (igualdade + range/orderBy):
- `wa_contacts (assigned_to ASC, sort_key ASC)`
- `wa_contacts (assigned_to_uid ASC, sort_key ASC)`
- (se busca por telefone escopada) `(assigned_to ASC, wa_id_reversed ASC)` e
  `(assigned_to_uid ASC, wa_id_reversed ASC)`

⚠️ **ORDEM DE DEPLOY CRÍTICA** (lição da frente de listeners, 2026-06-23):
publicar os índices e **ESPERAR ficarem READY antes de subir o código** —
senão o picker do operador quebra com FAILED_PRECONDITION. Criar via
`gcloud firestore indexes composite create` (firebase CLI não está instalado
nesta máquina; `--field-config` precisa de aspas no PowerShell).
Caminho privilegiado usa só índices single-field automáticos — funciona já.

## 4. Backend

Novo endpoint `GET /api/wa/contacts/picker` (o `/all` fica para
export/admin/escape hatch):
- `?cursor=<sort_key>&page_size=50` → modo página.
- `?q=<termo>` → modo busca (classificador dígitos/letras acima).
- Resposta: `{contacts: [...], next_cursor: str|null, mode: "page"|"search"}`.
- Privilegiado vs operador: mesma bifurcação `can_see_all_tenant` de hoje.
- `count_only=1` do `/all` (Fix #1) permanece — contador da sidebar não muda.

## 5. Frontend (`NewContactModal`)

- Abrir → 1ª página (50) + botão "Ver mais" enquanto `next_cursor`.
- Busca deixa de ser por tecla: **Enter ou botão** dispara `?q=` (1 query por
  busca). Placeholder honesto: _"Nome (começo) ou final do telefone"_.
- Remove dependência de `loadAllContacts`/cache de agenda inteira no modal
  (o cache/single-flight continuam existindo pra quem mais usar o `/all`).
- Filtro por operador (`ownerFilter`, só privilegiado) hoje é client-side
  sobre a lista completa → no v2 vira `?owner=<id>` server-side (query
  `assigned_to == id` + orderBy — mesmo índice composto do operador).

## 6. Trade-offs de busca (aprovados pelo PO em 2026-07-18)

| Operador digita | Hoje (substring) | v2 |
|---|---|---|
| `83440484` (local completo) | ✅ | ✅ sufixo |
| `0484` (últimos dígitos) | ✅ | ✅ sufixo |
| `8344` (INÍCIO da parte local) | ✅ | ❌ |
| `jo` → João Silva | ✅ | ✅ prefixo |
| `silva` → João Silva | ✅ | ✅ (só com name_tokens) |
| `ilv` (meio da palavra) | ✅ | ❌ |

Regra comunicável: **telefone busca pelo FINAL, nome pelo COMEÇO (ou palavra
inteira)**. Escape hatch opcional: botão "busca completa" (privilegiado) caindo
no `/all` atual.

## 7. Custos

| Cenário | Hoje | v2 |
|---|---|---|
| Abrir picker (Hubloc 6.5k) | 6.518 reads | 50 |
| Abrir picker (Varizemed ~15k) | ~15.000 | 50 |
| Uma busca | 0 (cache já pago) | ~5-50 |
| Sessão típica (abrir + 2 buscas) | 6.5-15k | ~100-150 |
| 10 tenants × uso diário | ~100k+/dia | ~1-2k/dia |

## 8. Plano de execução (ordem)

1. **Write-path:** gravar `sort_key`/`wa_id_reversed`(/`name_tokens`) no
   `upsert_wa_contact` (+ pontos de escrita de nome: declared_name etc.).
2. **Backfill:** script one-off dry-run/apply (molde dos scripts do incidente:
   assert de tenant, contadores, idempotente). ~6.5k writes no Hubloc.
3. **Índices compostos** → esperar READY (`gcloud firestore indexes composite list`).
4. **Endpoint `/picker`** + testes (sim script: página, cursor, busca dígitos,
   busca letras, escopo operador — paridade com `get_wa_contacts_scoped_for_user`).
5. **Frontend modal** (npm build).
6. **Staging → prod** (fluxo padrão: tag staging → validar → revisão 0% →
   health → cutover; ver praxe dos deploys de 2026-07-16/18).
7. **Verificação:** abrir picker como admin e como operador; buscar por final
   de telefone e por prefixo de nome; conferir "Ver mais"; medir no Monitoring
   que abertura de picker não gera mais pico de reads.

## Verificação de sucesso

- Nenhuma interação do picker excede ~50 reads (vs 6.5k hoje).
- Operador comum continua vendo SÓ próprios + pool (isolamento LGPD intacto).
- Busca por final de telefone e começo de nome funciona nos dois perfis.
- `wa_contacts` novos/atualizados saem com os campos preenchidos.
