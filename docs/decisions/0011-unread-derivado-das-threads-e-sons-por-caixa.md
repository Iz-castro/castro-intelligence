# ADR 0011 — `unread_count` do contato e DERIVADO das threads; beep/alarme so sobre o que a caixa mostra

- Data: 2026-08-21
- Status: aceito (Fase 1 implementada; backfill = Fase 2)
- Contexto: `docs/internal/2026-08-21-diagnostico-alarme-sonoro.md`

## Problema

Existem dois contadores de nao-lido: `wa_contacts.unread_count` (contato, cross-canal) e
`wa_conversations.unread_count` (thread). Todo inbound incrementa os dois. Desde a Fase 2C
(2026-05-04) o frontend marca leitura POR THREAD (`POST /api/wa/conversation/{id}/read`), que
zerava so a thread; o contador do contato so era zerado pelo endpoint legado por contato, que o
frontend nao usa quando ha thread. Resultado: o campo do contato virou catraca de mao unica
(hubloc: ~1.5k contatos presos).

Os efeitos de som do frontend (beep de nova mensagem e alarme repetitivo por setor) liam
exatamente esse campo, sobre o array cru `contacts` (janela de `wa_contacts`: pool sem dono de
qualquer setor + meus, sem filtro de `bot_completed`), enquanto a sidebar deriva tudo de
`wa_conversations` com filtros por caixa. Operador comum ouvia alarme perpetuo por leads em fase
de bot que ele nao pode ver nem abrir (caixa Bot e so admin/supervisor), e o alarme re-armava
(tocava) a cada publish do snapshot, refresh de token e ao abrir Configuracoes.

## Decisao

1. **Fonte da verdade do nao-lido = THREAD.** O campo do contato continua existindo (compat da
   API `/api/wa/contacts`, endpoint legado), mas passa a ser **derivado**: `recompute_wa_contact_unread`
   grava `wa_contacts.unread_count := soma(unread_count das threads do contato)` e e chamado por
   `mark_wa_conversation_read_by_id` (apos zerar a thread) e pelo endpoint de read quando a thread ja
   esta zerada mas o contato nao (cura o drift ao abrir a conversa). Backfill one-shot do estoque:
   `scripts/backfill_contact_unread_from_threads.py` (dry-run default, undo JSON, idempotente).
2. **Sons avaliam so o que o usuario ve.** Beep e alarme usam `novosConversations + meusConversations`
   (ja filtradas por `bot_completed`, setor, backup, dono, `pool_mode`) e o `unread_count` da thread.
   Mensagem em Equipe/Bot/Backup nao toca som (admin inclusive) — decisao de produto: som e pra
   conversa que o usuario tem que responder.
3. **Alarme sem re-arme por identidade.** Deps primitivas + refs: toca na hora quando uma thread
   NOVA entra no conjunto "atrasado" e a cada 30 s enquanto houver alguma; para quando o conjunto
   esvazia. Nenhum som antes de `/api/settings/system` responder (`settingsLoaded`): os defaults do
   frontend nao valem como configuracao.

## Consequencias

- Admin que contava com beep de mensagens da Equipe deixa de ouvir (documentado na aba Notificacoes).
- `+1 query (threads do contato) +1 write` por "abrir conversa"; sem full-scan.
- O endpoint de read por thread segue sem `_require_contact_access` (pre-existente); a cura nova
  so grava um contador derivado — follow-up de hardening, nao bloqueante.
- Fase 3 (separada): caixas do admin com targets proprios (pool sem dono + minhas) em vez de
  dependerem da janela global top-300.
