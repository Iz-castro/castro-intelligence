---
name: project-backup-inbox-feature
description: "Caixa \"Backup\" (aba admin/supervisor) com historico importado dos JSONs do WhatsApp; como importar e o que falta pro import real dos 500."
metadata: 
  node_type: memory
  type: project
  originSessionId: dab2543b-9e4a-40cf-88c3-3d467d17781b
---

Feature "caixa Backup" (CRM hubloc) — VALIDADA E2E em 2026-06-07 com JSON de
teste. Importa o historico de conversas dos ~500 JSONs em `backup hubloc/`
(export da extensao WhatsApp Web, PII, GITIGNORED) pra uma aba **Backup** visivel
SO a admin/supervisor.

**Como funciona:**
- Marcador `is_backup=true` + `assigned_to_uid="__backup__"` (sentinela) nas
  conversas/contatos/mensagens de backup -> isola o operador em 3 camadas
  (snapshot targets, firestore.rules canSeeContactScoped + wa_messages, REST).
- **Append ao vivo:** quando o cliente do backup manda msg nova, o webhook
  ANEXA na conversa do backup (sobe pro topo + badge nao-lida), NAO vai pra
  Novos — `upsert_wa_conversation` (merge=True) ja preserva o marcador (contato
  backup tem assigned_to=None -> auto-assign nao dispara). Zero mudanca no webhook.
- **Graduacao:** atribuir/transferir (assign_wa_conversation) limpa `is_backup`,
  define a vendedora de origem (sale_owner via [[project-standard-channel-migration]]
  ADR 0008) e a conversa sai do Backup -> vira atendimento do operador.
- Conversa de backup e read-only (channel_active=False) ate o cliente voltar.
- helpers backup-aware em database_firestore.py: `create_backup_contact`,
  `upsert_backup_conversation`, `write_backup_message` (sem protocolo/unread/
  auto-close/metricas). Commits 80dfd43 + 884cf42, rev castro-crm-00151.

**Importador:** `scripts/import_backup_hubloc.py`
- `--dir "backup_test" --dry-run` (so conta) | `--confirm` (grava).
- Resolve o canal pelo NOSSO numero (Phone das msgs de saida "Você"/true_).
  -> **precisa do canal STANDARD do 3351-7604 EXISTIR** (pos-embed) p/ o import
  real; senao usa um canal de teste. (No teste usei 7195-7758/canal 2.)
- `normalize_br_phone` canoniza o wa_id (nono digito) nos DOIS lados (import e
  webhook) -> msg ao vivo de `9XXXXXXXX` casa com backup `XXXXXXXX` (vira
  `55319XXXXXXXX`). conversation_id deterministico `{channel_id}__{wa_id}`.
- Idempotente (dedup por "backup_"+Message Id). Preserva timestamps (ordem) e o
  prefixo `*Nome Operador:*` (a supervisora ve quem atendeu).

**PARA O IMPORT REAL DOS 500 (amanha, pos-embed do 3351-7604):**
1. Conectar o comercial 3351-7604 como standard (vira canal id novo).
2. **PUBLICAR as firestore.rules no console do Firebase** (operador nao le
   is_backup) — gcloud NAO tem permissao de publicar rules. Sem isso, as
   MENSAGENS de backup (Vetor B) ficam legiveis por operador via query direta.
3. `./.venv/Scripts/python.exe -m scripts.import_backup_hubloc --dir "backup hubloc" --confirm`
   (rodar --dry-run antes p/ ver contagens + colisoes).
4. Limpar o backup de TESTE antes (contato/conversa do numero de teste (mascarado)).

**Gotcha:** o frontend remonta Conversation com lista fixa de campos
(`normalizeConversation`, normalization.ts) — campo novo (is_backup, channel_active)
SOME se nao for adicionado la. Mesma classe de bug que ja mordeu 2x.

Modelo de UX: supervisora percorre o Backup, prioriza quem mandou msg nova
(badge), e reatribui uma a uma (sem auto-assign — decisao do cliente).
