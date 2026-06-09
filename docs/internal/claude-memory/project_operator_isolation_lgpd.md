---
name: project-operator-isolation-lgpd
description: Operador comum ve SO contatos/conversas proprios + pool sem dono; NUNCA por departamento. 3 camadas devem ficar em sincronia.
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c0bbcb0-2d9d-4a43-a772-008691e003aa
---

Modelo de visibilidade de contatos/conversas no CRM (tenant hubloc):
- **admin/supervisor**: veem tudo do tenant.
- **operador comum (role 'operador')**: ve SO o que esta atribuido a ele
  (`assigned_to`/`assigned_to_uid` == ele) OU sem dono (`assigned_to_uid`
  == '' ou null = pool/fila). **NUNCA por departamento.**

Em jun/2026 corrigimos um vazamento LGPD: havia uma clausula
`department_id == <meu depto>` que deixava um operador ver contatos E
conversas de TODOS os colegas do mesmo departamento — vazava a agenda
pessoal (coexistence, sincronizada do celular via smb_app_state_sync, toda
atribuida ao dono) entre operadores (ex.: 175 contatos da aline visiveis p/
danielle no dept 2; 474 do joaobosco p/ 3 colegas no dept 5/almoxarifado).

A clausula existia em **3 camadas que precisam ficar SEMPRE em sincronia**
(se mexer em visibilidade de contato/conversa, conferir as 3):
1. Backend `get_wa_contacts_scoped_for_user` (database_firestore.py) — usado
   por `get_wa_contacts_visible_to` (/api/wa/contacts) e /api/wa/contacts/all.
2. Frontend `buildContactSnapshotTargets` + `buildConversationSnapshotTargets`
   (CrmContext.tsx) — targets de onSnapshot do Firestore.
3. `firestore.rules` `canSeeContactScoped(tid)` (governa wa_contacts E
   wa_conversations da subcolecao tenants/{tid}/...). A funcao morta
   `canSeeConversation` foi removida.

**Nao reintroduzir escopo por departamento.** A fila/queue compartilhada e o
pool `assigned_to_uid==''` (global), nao o departamento.

Deploy do dia: imagem `lgpd-ddcfb69` (rev castro-crm-00134-fqf) fechou o uso
via app; rules publicadas pelo Rafa no console (gcloud nao tem permissao de
leitura na Firebase Rules API — 403 — entao a verificacao foi via console +
conteudo do arquivo + rodar a funcao corrigida contra prod: danielle->0
contatos da aline). Ver [[project-deploy-script-desatualizado]].

**Auditoria adversarial (workflow) achou que o vazamento por departamento era
1 instancia de um padrao maior:** varios endpoints REST escopavam so por
tenant (get_current_user SO autentica; ids enumeraveis; Admin SDK ignora
rules). Adicionado helper `_require_contact_access(contact, current_user)` em
main.py (admin/supervisor tudo; operador comum so contato proprio/assigned_to
ou pool sem dono -> 403) aplicado em 11 endpoints REST (messages, transcribe,
conversations, contact detail, qualify, declared-name, read, delete, restore,
transfer-history). Rev `castro-crm-00135-p9w` (commit cebd367). Confirmado em
prod: /api/wa/contact/{id} retorna 200/403 misto (gate barrando cross-operador).

**PENDENTE (proximo round):** (1) `wa_messages` rules — o app le mensagens via
Web SDK (CrmContext.tsx:1041), entao a rule (firestore.rules:212 `ownsTenant`)
deixa qualquer operador ler TODAS as mensagens via query direta; fix exige
denormalizar assigned_to_uid nos docs de mensagem + backfill + atualizar no
transfer. (2) Negar coleções legadas (wa_messages flat, messages internas).
(3) GC por participante (adiado — feature nao usada ainda). (4) Backfill de 361
conversas coexistence orfas de dono (assigned_to_uid vazio mas contato tem
dono, canal removido) que poluem a fila global 'Novos' — conversa deve herdar
assigned_to/uid do contato; corrigir tambem o write-path (history sync /
upsert_wa_conversation nao espelha o dono do contato na conversa).
  - **Jun/2026 (sessao do izael):** o sintoma reapareceu (leads da Helenice/
    Jaqueline em 'Novos' das contas admin). Causa confirmada: o filtro de
    'Novos' (frontend context/CrmContext.tsx ~522) so checava conv.assigned_to
    (dono do ATENDIMENTO), nao contact.assigned_to (dono do LEAD). Aplicada
    MITIGACAO de frontend (commit ada85eb): 'Novos' passa a exigir tambem
    contact.assigned_to vazio (commit ada85eb, rev castro-crm-00138). CAVEAT:
    so esconde do 'Novos'; sem mensagem nova a thread fica orfa.
    FIX DE ORIGEM FEITO (2026-06-04): write-path em save_wa_message
    (database_firestore.py:1820) herda o dono do contato — guard de orfa em
    upsert_wa_conversation impede pisar em transferencia/takeover (commit
    8d1dd0e, rev castro-crm-00139). Backfill aplicado em prod via
    scripts/_backfill_conversation_orphan_owner.py: 168 conversas orfas
    herdaram o dono (undo salvo, re-dry-run convergiu synced:0).
    AINDA PENDENTE: o item (1) wa_messages rules (ownsTenant) — maior vetor
    de leak de PII entre operadores; nao mexido hoje.
