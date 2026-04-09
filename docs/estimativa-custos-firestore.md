# Estimativa de Custos Firestore - Castro Intelligence CRM

**Data:** 2026-04-09
**Versao:** Modelo Coexistence (3 contas) - Pos-otimizacao

---

## 1. Volume Operacional (Teto Conservador)

| Metrica | Valor |
|---------|-------|
| Contas WhatsApp Coexistence | 3 (operadores com numeros proprios) |
| Leads por mes | 2.500 (baseado no recorde historico de 2.358 leads - set/2025) |
| Mensagens por mes | 70.000 mensagens trocadas via WhatsApp (total entre as 3 contas) |
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
| Outbound via CRM | ~955 (60%) |
| Outbound via celular (smb_message_echoes) | ~636 (40%) |
| Novos leads por dia | 114 |
| Conversas abertas por atendente/dia | ~25 |

> **Nota Coexistence:** No modo coexistence, operadores podem enviar mensagens
> tanto pelo CRM quanto pelo celular. Estimamos que ~40% das mensagens outbound
> sao enviadas pelo celular e ecoadas para o CRM via webhook `smb_message_echoes`.

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
| **smb_message_echoes (check dedup + get contact)** | 636 x 2 | 1.272 |
| **smb_app_state_sync (get contact, 3 contas)** | 3 x 30 | 90 |
| Outros (departments, users, channels - cacheados) | - | 500 |
| **Total por dia** | | **~77.160** |

### Reads por Mes

| Periodo | Total |
|---------|-------|
| **Mensal (22 dias uteis)** | **~1.700.000** |
| Faixa gratuita Blaze (por dia) | 50.000 |
| Faixa gratuita Blaze (por mes, 30 dias) | 1.500.000 |
| **Reads cobrados por mes (estimativa)** | **~200.000** |

> **Nota:** O maior consumidor de reads (41% do total) e o snapshot de contatos
> reagindo a cada mensagem recebida/enviada. Cada mensagem atualiza o campo
> `last_message_at` do contato, disparando 1 read por atendente conectado.
> Isso se aplica igualmente a mensagens do CRM e do celular (via echo).

---

## 3. Escritas (Writes) - Estimativa Diaria

| Origem | Calculo | Writes/dia |
|--------|---------|------------|
| Mensagem inbound (save msg + update contact) | 1.591 x 2 | 3.182 |
| Mensagem outbound via CRM (save msg + update contact + audit) | 955 x 3 | 2.865 |
| **Mensagem outbound via celular/echo (save msg + update contact)** | 636 x 2 | 1.272 |
| Novos contatos | 114 | 114 |
| Status webhooks (msg update + status doc, 3x por outbound) | 4.773 x 2 | 9.546 |
| mark_wa_conversation_read (batch updates) | 10 x 25 x 4 | 1.000 |
| **smb_app_state_sync (upsert contacts, 3 contas)** | 3 x 30 | 90 |
| Transferencias, qualificacoes, outros | - | 200 |
| **Total por dia** | | **~18.269** |

### Writes por Mes

| Periodo | Total |
|---------|-------|
| **Mensal (22 dias uteis)** | **~402.000** |
| Faixa gratuita Blaze (por dia) | 20.000 |
| Faixa gratuita Blaze (por mes, 30 dias) | 600.000 |
| **Writes cobrados por mes** | **0 (dentro da faixa gratuita)** |

---

## 4. Armazenamento Firestore

| Item | Calculo | Total/mes |
|------|---------|-----------|
| Documentos de mensagens | 70.000 x ~500 bytes | ~35 MB |
| Documentos de contatos | 2.500 x ~1 KB | ~2,5 MB |
| Documentos de canais (channels) | 3 x ~2 KB | desprezivel |
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
| **Firestore Writes** | 402.000 | 600.000/mes | 0 |
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
| Webhooks de 3 contas coexistence | Trafego adicional marginal (~1.000 requests/dia extras) |
| Estimativa com trafego baixo-medio | ~US$ 5-15/mes |

### Custo Total Estimado

| Periodo | Cenario 20% midia | Cenario 60% midia |
|---------|-------------------|-------------------|
| **Mes 1** | ~US$ 5-15 | ~US$ 5-15 |
| **Mes 6** | ~US$ 6-16 | ~US$ 7-17 |
| **Mes 12** | ~US$ 7-17 | ~US$ 9-19 |

> **Nota:** O custo dominante continua sendo o Cloud Run, nao o Firestore.
> A adicao de 3 contas coexistence tem impacto marginal nos custos Firebase,
> pois o volume total de mensagens permanece o mesmo - apenas distribuido
> entre 3 numeros em vez de 1. Os webhooks extras (smb_message_echoes,
> smb_app_state_sync) adicionam ~1.300 reads e ~1.360 writes por dia.

---

## 8. Consideracoes Especificas do Coexistence

### Webhooks adicionais por conta

Cada conta coexistence gera webhooks extras alem dos padrao:

| Webhook | Descricao | Impacto Firestore |
|---------|-----------|-------------------|
| `smb_message_echoes` | Msgs enviadas pelo celular ecoadas para o CRM | 2 reads + 2 writes por msg |
| `smb_app_state_sync` | Contatos editados no celular sincronizados | 1 read + 1 write por contato |
| `account_update` | Eventos de conexao/desconexao | Desprezivel |
| `history` | Importacao unica de 180 dias de historico | One-time (nao recorrente) |

### Importacao de historico (one-time por conta)

| Metrica | Por conta | Total (3 contas) |
|---------|-----------|------------------|
| Mensagens importadas (180 dias) | ~12.000 | ~36.000 |
| Writes (save msg + update contact) | ~24.000 | ~72.000 |
| Reads (check dedup) | ~12.000 | ~36.000 |
| Duracao estimada | 1-2 horas | 3-6 horas |

> **Nota:** A importacao de historico e um evento unico por conta e nao
> afeta os custos recorrentes mensais. Os ~72.000 writes extras ficam
> dentro da faixa gratuita se feitos em dias separados.

### Rate limits

| Modo | MPS (mensagens por segundo) |
|------|----------------------------|
| Cloud API padrao | 80 MPS |
| **Coexistence** | **20 MPS por conta** |
| Total (3 contas) | 60 MPS combinado |

> Com 3.182 msgs/dia em 8h de operacao, o throughput medio e ~0,11 MPS.
> O limite de 20 MPS por conta e mais que suficiente.

---

## 9. Otimizacoes Implementadas (Referencia)

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
| Writes/mes | ~500.000 | ~402.000 | -20% |
