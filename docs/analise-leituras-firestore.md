# Analise de Leituras Excessivas no Firestore

**Data:** 2026-03-21
**Contexto:** 2 usuarios testando o sistema geraram 80.000+ leituras no Firestore, ultrapassando a faixa gratuita de 50.000.

---

## 1. Resumo do Problema

Com apenas 2 usuarios (voce e seu irmao) testando o CRM e conversando entre si, o sistema consumiu mais de 80 mil leituras no Firestore em poucas horas. Isso e extremamente alto comparado ao Varizemed, que usa polling a cada 10 segundos e dificilmente atinge esse numero.

**Por que o Castro gasta mais que o Varizemed?**

Nao e por causa da integracao direta com a Meta (vs Twilio). O custo de leituras do Firestore nao tem relacao com o provedor de WhatsApp. O problema esta em **como o codigo le dados do Firestore** -- tanto no frontend quanto no backend.

---

## 2. Causas Raiz Identificadas

### 2.1 Snapshot de Contatos SEM LIMITE (Frontend)

**Arquivo:** `frontend/src/App.tsx`, linha 532-536

```typescript
onSnapshot(
  query(collection(bundle.db, config.firestore.collections.wa_contacts),
    orderBy("last_message_at", "desc")),  // <-- SEM .limit()
  (snap) => setContacts(snap.docs.map(...))
);
```

**Problema:** O snapshot escuta TODOS os contatos da colecao. Cada vez que qualquer contato muda (nova mensagem, status, etc.), o Firestore re-envia TODOS os documentos. Com 50 contatos, cada atualizacao = 50 leituras.

**Correcao sugerida:** Adicionar `.limit(30)` e implementar paginacao com `startAfter()` para scroll infinito.

---

### 2.2 Snapshot de Mensagens SEM LIMITE (Frontend)

**Arquivo:** `frontend/src/App.tsx`, linha 539-547

```typescript
onSnapshot(
  query(collection(bundle.db, config.firestore.collections.wa_messages),
    where("contact_id", "==", selectedContactId)),  // <-- SEM .limit()
  (snap) => setMessages(snap.docs.map(...).sort(...))
);
```

**Problema:** Escuta TODAS as mensagens de um contato. Se o contato tem 500 mensagens, cada update dispara 500 leituras. Alem disso, toda vez que o usuario troca de conversa (linha 570, `selectedContactId` no array de dependencias), o listener antigo e destruido e um novo e criado, causando uma nova leitura completa.

**Correcao sugerida:** Adicionar `.limit(20)` com `orderBy("created_at", "desc")` e usar `startAfter()` para scroll.

---

### 2.3 Leitura DUPLA de Contatos no Backend (API)

**Arquivo:** `main.py`, linhas 613-619

```python
@app.get("/api/wa/contacts")
async def wa_contacts(current_user):
    contacts = get_all_wa_contacts()      # Le TODOS os contatos
    unread_counts = get_wa_unread_count()  # Le TODOS os contatos DE NOVO
    for c in contacts:
        c["unread"] = unread_counts.get(c["id"], 0)
    return {"contacts": contacts}
```

**Detalhando:**
- `get_all_wa_contacts()` (`database_firestore.py:494-499`) chama `_all_docs("wa_contacts")` que faz `.stream()` na colecao inteira.
- `get_wa_unread_count()` (`database_firestore.py:708-710`) faz EXATAMENTE o mesmo `.stream()` na mesma colecao.

**Resultado:** 1 chamada a `/api/wa/contacts` = **2x leituras de todos os contatos**.

**Correcao sugerida:** Calcular unread_count dentro de `get_all_wa_contacts()` para evitar a leitura duplicada.

---

### 2.4 Enrichment N+1 em Contatos (Backend)

**Arquivo:** `database_firestore.py`, linhas 475-499

```python
def get_all_wa_contacts(include_archived=False):
    rows = [row for row in _all_docs("wa_contacts") if row]  # Le N contatos
    # ...
    return [_enrich_contact(row) for row in rows]  # Para CADA contato...

def _enrich_contact(row):
    users = _user_map([row.get("assigned_to")])           # +1 leitura (usuario)
    departments = _department_map([row.get("department_id")])  # +1 leitura (departamento)
```

**Problema classico N+1:** Para cada contato, faz 2 leituras individuais (usuario + departamento). Com 30 contatos = 30 + 60 = **90 leituras** por chamada.

**Correcao sugerida:** Coletar todos os `user_ids` e `department_ids` unicos ANTES do loop, fazer uma unica consulta batch, e entao enriquecer.

---

### 2.5 Leitura TRIPLA de Mensagens ao Abrir Conversa

**Arquivo:** `main.py`, linhas 622-626

```python
@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(contact_id, current_user):
    messages = get_wa_conversation(contact_id)      # Le TODAS as mensagens
    mark_wa_conversation_read(contact_id)            # Le TODAS as mensagens DE NOVO
    return {"messages": messages}
```

**Detalhando:**
- `get_wa_conversation()` (`database_firestore.py:657-680`): Faz `.where("contact_id", "==", contact_id).stream()` -- le TODAS as mensagens, depois aplica limit/offset em Python (nao no Firestore!).
- `mark_wa_conversation_read()` (`database_firestore.py:713-722`): Faz a MESMA query novamente para atualizar o status.

**Resultado:** 1 clique em conversa = **2x leitura de todas as mensagens do contato** + N escritas individuais.

**Correcao sugerida:**
1. Aplicar `.limit()` e `.order_by()` direto na query do Firestore, nao em Python.
2. Passar os docs ja lidos para `mark_wa_conversation_read()` em vez de re-consultar.
3. Usar batch writes para atualizar status.

---

### 2.6 Fallback de Polling a Cada 5 Segundos

**Arquivo:** `frontend/src/App.tsx`, linhas 551-561
**Arquivo:** `config.py`, linha 79

Quando o modo snapshot nao esta ativo, o frontend faz polling:

```typescript
intervalId = window.setInterval(() => { void tick(); }, config.polling_interval_ms || 5000);
```

Cada `tick()` chama:
- `/api/wa/contacts` (2x leitura completa de contatos + N+1 enrichment)
- `/api/wa/messages/{id}` (2x leitura completa de mensagens)

**Com 2 usuarios, a cada 5 segundos durante 1 hora:**
- 2 usuarios x 720 intervalos = 1.440 chamadas de API
- Cada chamada = ~70-100 leituras
- **Total estimado: 100.000 - 144.000 leituras/hora**

---

## 3. Calculo Estimado de Leituras

### Cenario: Modo Snapshot ativo, 2 usuarios, 30 contatos, ~100 mensagens por contato

| Operacao | Leituras | Frequencia | Total/hora |
|----------|----------|------------|------------|
| Snapshot contatos (sem limit) | 30 por update | ~60x/hora | 1.800 |
| Snapshot mensagens (sem limit) | 100 por update | ~120x/hora | 12.000 |
| Troca de conversa (re-subscribe) | 100 | ~20x/hora | 2.000 |
| API /wa/contacts (refresh) | 90 (30 + 30 + 30x enrichment) | ~20x/hora | 1.800 |
| API /wa/messages (abrir + mark read) | 200 | ~20x/hora | 4.000 |
| **Subtotal por usuario** | | | **~21.600** |
| **Total 2 usuarios** | | | **~43.200** |

Somando interacoes reais (envio de mensagens, atualizacoes de status da Meta, etc.), chegar a 80.000 e perfeitamente explicavel.

### Cenario: Modo Polling (se cair para polling)

O consumo sobe drasticamente para **100.000+/hora** como calculado na secao 2.6.

---

## 4. Comparacao com Varizemed

| Aspecto | Varizemed | Castro Intelligence |
|---------|-----------|---------------------|
| Modo de atualizacao | Polling 10s | Snapshot (ou polling 5s) |
| Leitura de contatos | 1 query com limit | `.stream()` sem limit (colecao inteira) |
| Leitura de mensagens | 1 query com limit | `.stream()` sem limit + re-leitura para mark_read |
| Enrichment | JOIN no SQL ou query otimizada | N+1 (1 read por contato para user + dept) |
| Leitura duplicada | Nao | Sim (contatos lidos 2x, mensagens lidas 2x) |
| Indices compostos | Sim | Nao |

**Conclusao:** O Varizemed e mais eficiente nao pelo Twilio, mas porque as queries sao otimizadas com limits, joins e sem leituras duplicadas.

---

## 5. Sobre a Integracao Direta com a Meta

A integracao direta com a Meta (vs Twilio) **nao causa mais leituras no Firestore**. O webhook da Meta escreve 1 documento por mensagem recebida -- igual ao Twilio. O problema esta exclusivamente no **padrao de leitura** do codigo.

O que a integracao direta com a Meta pode causar de diferente:
- **Mais webhooks de status** (sent, delivered, read) que geram escritas extras na colecao `wa_message_status`.
- Cada status update no Firestore **dispara os snapshots** sem limit, causando re-leitura cascata.

---

## 6. Plano de Otimizacao Recomendado

### Prioridade 1 - Impacto Imediato

1. **Adicionar `.limit()` nos snapshots do frontend** (App.tsx linhas 533 e 540)
2. **Eliminar leitura duplicada** de contatos em `/api/wa/contacts` (main.py linha 616)
3. **Aplicar `.limit()` e `.order_by()` direto na query Firestore** em `get_wa_conversation()` em vez de ler tudo e paginar em Python
4. **Reutilizar docs ja lidos** em `mark_wa_conversation_read()` em vez de re-consultar

### Prioridade 2 - Otimizacao Estrutural

5. **Resolver N+1 no enrichment**: Coletar IDs unicos, fazer batch read, cachear
6. **Criar indices compostos** no Firestore (ex: `wa_messages` por `contact_id` + `created_at`)
7. **Aumentar intervalo de polling** de fallback de 5s para 15-30s
8. **Implementar cache local** de usuarios e departamentos (mudam raramente)

### Prioridade 3 - Arquitetura

9. **Desnormalizar dados**: Incluir `assigned_to_name` e `department_name` direto no documento do contato (elimina enrichment)
10. **Mover unread_count** para campo no documento do contato (ja existe, mas `get_wa_unread_count` ignora e re-le tudo)

---

## 7. Sobre os IDs Numericos Sequenciais (1, 2, 3...)

Voce mencionou que os documentos estao nomeados com numeros sequenciais. Isso vem do sistema de contadores em `castro_crm__meta/counters`:

```python
def next_sequence(collection_name):
    # Incrementa atomicamente o contador e retorna o proximo ID
```

**Isso e uma pratica valida?** Para este caso sim, mas tem desvantagens:
- Dificulta queries por range (ex: "contatos criados depois de X")
- Nao aproveita o ID automatico do Firestore que ja e unico e ordenavel
- O contador centralizado pode ser gargalo em alta concorrencia

**Recomendacao:** Para novas features, considerar usar `doc.id` auto-gerado pelo Firestore ou IDs baseados em timestamp. Os IDs numericos atuais nao precisam ser migrados -- funcionam bem para o volume atual.
