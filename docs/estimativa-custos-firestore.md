# Estimativa de Custos Firestore - Castro Intelligence CRM

**Data:** 2026-03-21
**Versao:** Pos-otimizacao (snapshots com limit, cache, batch reads, queries filtradas)

---

## 1. Volume Operacional (Teto Conservador)

| Metrica | Valor |
|---------|-------|
| Leads por mes | 2.500 (baseado no recorde historico de 2.358 leads - set/2025) |
| Mensagens por mes | 70.000 mensagens trocadas via WhatsApp |
| Media de mensagens por lead | 28 mensagens |
| Atendentes simultaneos | 8 a 10 |
| Dias uteis por mes | 22 |
| Horas de operacao por dia | 8h |

### Derivados Diarios

| Metrica | Valor |
|---------|-------|
| Mensagens por dia | 3.182 |
| Mensagens inbound (50%) | 1.591 |
| Mensagens outbound (50%) | 1.591 |
| Novos leads por dia | 114 |
| Conversas abertas por atendente/dia | ~25 |

---

## 2. Leituras (Reads) - Estimativa Diaria

| Origem | Calculo | Reads/dia |
|--------|---------|-----------|
| Snapshot contatos (carga inicial + reconexoes) | 10 atendentes x 8 loads x 50 docs | 4.000 |
| Snapshot contatos (updates em tempo real) | 3.182 msgs x 10 listeners | 31.820 |
| Snapshot mensagens (abrir conversa) | 10 x 25 aberturas x 50 docs | 12.500 |
| Snapshot mensagens (novas msgs na conversa ativa) | ~3.182 x 1 listener | 3.182 |
| API /wa/messages (load inicial + contact + operators) | 10 x 25 x 54 | 13.500 |
| mark_wa_conversation_read (query filtrada) | 10 x 25 x 3 nao-lidas | 750 |
| Webhook inbound (upsert contact + check msg + get contact) | 1.591 x 3 | 4.773 |
| Webhook status (sent/delivered/read, 3x por outbound) | 4.773 x 1 | 4.773 |
| Outros (departments, users - cacheados) | - | 500 |
| **Total por dia** | | **~75.800** |

### Reads por Mes

| Periodo | Total |
|---------|-------|
| **Mensal (22 dias uteis)** | **~1.670.000** |
| Faixa gratuita Blaze (por dia) | 50.000 |
| Faixa gratuita Blaze (por mes, 30 dias) | 1.500.000 |
| **Reads cobrados por mes (estimativa)** | **~170.000** |

> **Nota:** O maior consumidor de reads (42% do total) e o snapshot de contatos
> reagindo a cada mensagem recebida/enviada. Cada mensagem atualiza o campo
> `last_message_at` do contato, disparando 1 read por atendente conectado.

---

## 3. Escritas (Writes) - Estimativa Diaria

| Origem | Calculo | Writes/dia |
|--------|---------|------------|
| Mensagem inbound (save msg + update contact) | 1.591 x 2 | 3.182 |
| Mensagem outbound (save msg + update contact + audit) | 1.591 x 3 | 4.773 |
| Novos contatos | 114 | 114 |
| Status webhooks (msg update + status doc, 3x por outbound) | 4.773 x 2 | 9.546 |
| mark_wa_conversation_read (batch updates) | 10 x 25 x 4 | 1.000 |
| Transferencias, qualificacoes, outros | - | 200 |
| **Total por dia** | | **~18.815** |

### Writes por Mes

| Periodo | Total |
|---------|-------|
| **Mensal (22 dias uteis)** | **~414.000** |
| Faixa gratuita Blaze (por dia) | 20.000 |
| Faixa gratuita Blaze (por mes, 30 dias) | 600.000 |
| **Writes cobrados por mes** | **0 (dentro da faixa gratuita)** |

---

## 4. Armazenamento Firestore

| Item | Calculo | Total/mes |
|------|---------|-----------|
| Documentos de mensagens | 70.000 x ~500 bytes | ~35 MB |
| Documentos de contatos | 2.500 x ~1 KB | ~2,5 MB |
| Status + audit + transfer log + outros | - | ~10 MB |
| **Crescimento mensal** | | **~50 MB** |

| Periodo | Armazenamento acumulado |
|---------|------------------------|
| 3 meses | ~150 MB |
| 6 meses | ~300 MB |
| 12 meses | ~600 MB |
| Faixa gratuita Blaze | 1 GB |

---

## 5. Cloud Storage (Midia - Imagens, Audios, Videos)

### Cenario 1: 20% das mensagens com midia

| Metrica | Valor |
|---------|-------|
| Arquivos por mes | 14.000 |
| Tamanho medio por arquivo | ~300 KB |
| Armazenamento por mes | ~4,2 GB |
| Acumulado em 12 meses | ~50 GB |

### Cenario 2: 60% das mensagens com midia (teto conservador)

| Metrica | Valor |
|---------|-------|
| Arquivos por mes | 42.000 |
| Tamanho medio por arquivo | ~300 KB |
| Armazenamento por mes | ~12,6 GB |
| Acumulado em 12 meses | ~151 GB |

> **Nota:** Cloud Storage (Blaze) oferece 5 GB gratuitos. Acima disso,
> o custo e de ~US$ 0,026/GB/mes para a regiao southamerica-east1.

---

## 6. Resumo para Calculadora Blaze

| Recurso | Valor mensal | Faixa gratuita | Excedente |
|---------|-------------|----------------|-----------|
| **Firestore Reads** | 1.700.000 | 1.500.000/mes | ~200.000 |
| **Firestore Writes** | 420.000 | 600.000/mes | 0 |
| **Firestore Deletes** | ~0 | 600.000/mes | 0 |
| **Firestore Storage** | +50 MB/mes | 1 GB total | 0 (1o ano) |
| **Cloud Storage (20%)** | +4,2 GB/mes | 5 GB total | Apos 2o mes |
| **Cloud Storage (60%)** | +12,6 GB/mes | 5 GB total | Apos 1o mes |

---

## 7. Custo Estimado Mensal (Blaze Pay-as-you-go)

### Firestore

| Item | Calculo | Custo/mes (USD) |
|------|---------|-----------------|
| Reads excedentes | 200.000 x US$ 0,06 / 100.000 | ~US$ 0,12 |
| Writes | Dentro da faixa gratuita | US$ 0,00 |
| Storage | Dentro da faixa gratuita (1o ano) | US$ 0,00 |
| **Subtotal Firestore** | | **~US$ 0,12** |

### Cloud Storage

| Item | Cenario 20% | Cenario 60% |
|------|-------------|-------------|
| Armazenamento (mes 6, acumulado) | 25 GB x US$ 0,026 | 75 GB x US$ 0,026 |
| Custo mensal (mes 6) | ~US$ 0,65 | ~US$ 1,95 |
| Armazenamento (mes 12, acumulado) | 50 GB x US$ 0,026 | 151 GB x US$ 0,026 |
| Custo mensal (mes 12) | ~US$ 1,30 | ~US$ 3,93 |

### Cloud Run

| Item | Valor |
|------|-------|
| CPU + Memoria | Depende do trafego; min-instances=0 reduz custo ocioso |
| Estimativa com trafego baixo-medio | ~US$ 5-15/mes |

### Custo Total Estimado

| Periodo | Cenario 20% midia | Cenario 60% midia |
|---------|-------------------|-------------------|
| **Mes 1** | ~US$ 5-15 | ~US$ 5-15 |
| **Mes 6** | ~US$ 6-16 | ~US$ 7-17 |
| **Mes 12** | ~US$ 7-17 | ~US$ 9-19 |

> **Nota:** O custo dominante e o Cloud Run, nao o Firestore.
> O Firestore com as otimizacoes implementadas fica praticamente
> dentro da faixa gratuita ou com excedente insignificante.

---

## 8. Otimizacoes Implementadas (Referencia)

As seguintes otimizacoes foram aplicadas para atingir estes numeros:

1. **Snapshots com limit(50)** no frontend (contatos e mensagens)
2. **Cache em memoria** para usuarios e departamentos (evita N+1)
3. **Batch enrichment** em get_all_wa_contacts (coleta IDs antes de enriquecer)
4. **Query filtrada** em mark_wa_conversation_read (so le mensagens nao-lidas inbound)
5. **Batch writes** em mark_wa_conversation_read (em vez de updates individuais)
6. **Limit + orderBy no Firestore** em get_wa_conversation (paginacao no banco, nao em Python)
7. **Eliminacao de leitura duplicada** no endpoint /api/wa/contacts (removido get_wa_unread_count separado)
8. **Polling fallback** aumentado de 5s para 15s
9. **Indices compostos** criados para queries com where + orderBy

### Sem estas otimizacoes (estimativa anterior)

| Recurso | Antes | Depois | Reducao |
|---------|-------|--------|---------|
| Reads/mes | ~5.000.000+ | ~1.700.000 | -66% |
| Writes/mes | ~500.000 | ~414.000 | -17% |
