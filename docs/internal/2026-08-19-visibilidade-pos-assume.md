# Fix — operador B continua vendo a conversa depois que A assume (Hubloc)

> **Atualização 2026-08-21:** o fix descrito aqui foi entregue no commit `3aa9d05` (20/08) — a
> "seção final" de deploy citada abaixo não existe neste documento. Dos follow-ups P1–P10, só o
> **P2 saiu em parte**: `POST /api/wa/conversation/{id}/read` ganhou autorização (thread minha /
> pool / takeover meu, senão `_require_contact_access`) na Fase 1 do ADR 0011 (21/08); `/takeover`
> e `/return` continuam sem o guard. P1 e P3–P10 seguem abertos.

**Data:** 19/08/2026 · **Pedido por:** Rafael · **Executado por:** Claude (Castro Intelligence)
**Relato do PO:** no hubloc, operador A abre uma conversa em "Novos Leads", operador B abre a
mesma, A clica "Assumir atendimento" e **B continua vendo toda a conversa de A**. Esperado: fechar pra B.

---

## Resumo executivo

1. **Os dados de prod estão certos.** Nos 25 últimos `WA_ASSUME` do hubloc, contato **e** thread ficam
   com `assigned_to`+`assigned_to_uid` do operador (0 drift; 0 contatos com dono sem uid; pool atual =
   3 threads). Todos os 13 usuários têm `firebase_uid`. Hubloc = `legacy`, entrega `snapshot`.
2. **No caminho mais simples (B clicou na linha de Novos e é operador comum), o código já fechava** —
   a thread sai dos 3 targets do listener de B e o guard de seleção órfã zera a seleção. O sintoma
   aparece quando **alguma camada continua entregando a thread pra B**:
   - **B é admin/supervisor** (hubloc tem 4: Rafael, Izael, castrointelligence e **Helenice, id 6, que opera
     a fila**) — a janela global continua entregando o doc e **nada** no código fechava o painel de quem não é
     dono. Candidato mais provável pro relato.
   - **B abriu pelo picker "+" (agenda).** Em tenant legacy, `POST /api/wa/conversation/open`
     **auto-atribuía a thread a quem abria** sem tocar o contato (sem RBAC, sem 409, sem audit/system
     message). O lead sumia de "Novos" de todo mundo, o `assume` de A depois carimbava contato=A e
     deixava **thread=B** (guard "só atribui thread sem dono") — B continuava dono da thread e via tudo.
   - **Cópias estáticas** (`extraConversations` do picker, `pagedConversations` do "Carregar mais") nunca
     recebem atualização do listener; somadas a `extraContacts` que **engolia 403** na revalidação, seguravam
     `selectedThreadId` + `selectedContact` e o listener de `wa_messages` (que as rules liberam pra qualquer
     operador do tenant) continuava streamando a conversa de A.
3. **Fix em camadas** (abaixo), validado por `py_compile`, `sim_bot_flow` (56), `sim_cx_flow` (167),
   `sim_reception_flow` (**93**, 2 cenários novos) e `npm run build`.

## O que mudou

### Frontend (`frontend/src/context/CrmContext.tsx`)
- **Watcher de dono da thread aberta:** se a thread selecionada **muda** de dono pra outro usuário
  (não eu, não sou dono do lead, não sou handler de takeover), fecha o chat, limpa as camadas estáticas
  e avisa ("Atendimento assumido por X" / "transferido para X"). Vale pra **todos os papéis** (admin em
  Novos também fecha; reabre pela Equipe). Abrir uma thread que **já** é de outro (Equipe/intervenção) não fecha.
- **Listener de doc da thread selecionada** (1 por seleção): mantém fresca a cópia estática
  (picker/"Carregar mais") e, quando as rules negam a leitura (`permission-denied` = saiu do escopo),
  fecha o chat.
- **`extraContacts` despeja a cópia** quando a revalidação toma 403/404 (antes mantinha nome/telefone/notas
  do lead alheio até o fim da sessão).
- `assumeContact` manda `conversation_id` da thread aberta.

### Backend
- `POST /api/wa/assume/{id}` (`main.py`): aceita `{conversation_id}` (valida que é do contato), grava a
  system message **nessa** thread (com `channel_id`) e chama **`assign_orphan_threads_to_lead_owner`**
  (`database_firestore.py`): toda thread não-backup do contato **sem dono** herda o operador
  explicitamente — antes dependia do efeito colateral da system message na thread de
  `contact.channel_id` (grudado no 1º canal) dentro de um `try/except` que engole falha. Threads já
  de outro operador (coex/takeover) **não** são roubadas.
- `POST /api/wa/conversation/open` (picker): em legacy, só auto-atribui a thread se o **lead já é meu**.
  Lead da **pool** aberto pelo picker fica órfão até o "Assumir atendimento" explícito (mesma UX de
  Novos; botão aparece). Reception segue nunca atribuindo (ADR 0010). **Mudança de comportamento
  visível:** quem abria lead da pool pela agenda e mandava template direto agora precisa clicar
  "Assumir" antes (antes era um "assume" silencioso, sem audit).

## Rodada 2 da revisão adversarial (concluída no mesmo dia)

As 7 verificações que caíram no limite de sessão + a síntese rodaram à tarde (workflow `wf_09b49bff-47e`,
8/8 ok). Resultado consolidado das **32 verificações**:

- **Nenhum dos 7 achados pendentes foi refutado** (4 bugs confirmados contra o código pré-fix; 3 planos de
  repro/observação/teste validados com correções). O fix cobre os 4 bugs (2 "sim", 2 "parcial").
- **Ranking final de causa provável do relato:** (1) B admin/supervisor — era *design*, nada fechava o painel
  (Helenice id 6 opera a fila); (2) cópias estáticas (picker/"Carregar mais") + `extraContacts` engolindo 403;
  (3) picker roubando a thread em legacy (único caso em que B também **escrevia**); amplificador universal:
  rules de `wa_messages` abertas + listener de mensagens sem teardown por escopo.
- **P0 encerrado — backfill DESNECESSÁRIO:** varredura read-only nos 3 tenants: 215 divergências
  thread-dono×lead-dono no hubloc, das quais 201 = split coex **por design** (dono do número), 13 = transferências
  de thread (Fase 3B, por design) e **1** no canal standard (contato 7351) que o transfer_log explica: thread
  transferida pra Aline 22/06 e lead reatribuído pra Helenice 23/06 ("Lead convertido retornou") — legítimo,
  threads fechadas. **Zero threads roubadas pelo picker.** Resíduo conhecido: 1 doc com `assigned_to=1` e
  `assigned_to_uid=""` (canal 4, contato 4458) — invisível na UI, mas legível por qualquer operador via rules;
  corrigir = carimbar o uid do user 1 (1 write, pendente de ok).
- **P5 aplicado no mesmo diff:** `/api/admin/reassign-lead` agora chama `assign_orphan_threads_to_lead_owner`
  (threads **órfãs** acompanham o novo dono; thread com dono não é movida — "reatribuir o Lead sem mover os
  atendimentos" preservado) e o audit ganha `| threads=N`.
- **Gaps do fix apontados pelos verificadores** (aceitos/conhecidos): forward-only (não havia o que backfillar —
  ver P0); o `try/except` do carimbo ainda responde 200 com `threads=-1` (P6); o watcher não pega thread que
  **fica órfã** por falha do carimbo (mitigado: caminho explícito + audit); `ensure_permission` segue ausente no
  `/conversation/open` (inócuo pós-fix: só auto-atribui lead já meu).
- **Regressões de produto a validar com o PO:** (a) legacy: abrir lead da pool pelo "+" e enviar direto agora
  exige clicar "Assumir" antes (403 sem isso); (b) admin/supervisor perde o chat aberto quando a thread muda de
  dono (reabre pela Equipe); (c) lead da pool aberto pelo picker não silencia mais o bot (resumo CX só no assume).
- **Teste manual mínimo antes do deploy** (2 contas, ~20 min): (1) operador×operador clique simples → chat de B
  fecha ≤3s com toast; (2) B pelo "+" → thread segue órfã, envio 403, assume de A fecha o chat de B; (3) B=admin →
  fecha e reabre pela Equipe; (4) coex: assume de A não rouba thread do B e chat do handler não fecha;
  (5) transferência A→B fecha no A e não no B; (6) audit `WA_ASSUME ... | conv=... | threads>=1`; (7) smoke
  varizemed (reception intocado).

## Decisões do PO (2026-08-20) e fechamento

- **(a) aprovada** — pergunta do PO: "na janela de 24h teria que assumir pra mandar template?" Resposta: o
  gate é de **posse**, não de janela (`/api/wa/send-template` passa pelo mesmo `_check_conv_send_permission`,
  main.py:2088). Lead **da pool** aberto pelo picker exige "Assumir" antes de qualquer envio (texto ou
  template, dentro ou fora das 24h). Contato **criado** manualmente não muda (criador vira dono → envia direto).
- **(b) aprovada** — admin/supervisor também perde o chat aberto quando a thread muda de dono (reabre pela Equipe).
- **Resíduo P0 corrigido em prod (2026-08-20):** thread canal 4 do contato 4458 recebeu o `assigned_to_uid`
  do user 1 (1 write idempotente; verificado antes/depois).
- ADR 0010 emendado (tabela do `conversation/open` em legacy); roadmap ganhou os follow-ups P1–P10.
- Deploy: ver seção final.

## Não confirmado empiricamente / follow-ups
- **Premissa do listener de doc:** que o Firestore entrega `permission-denied` quando o doc da thread
  sai do escopo do operador (comportamento documentado; não reproduzi em prod porque exigiria
  escrever um doc sintético). Se não entregar, os caminhos picker/"Carregar mais" ficam como estavam
  (status quo) — os caminhos admin e listener-vivo não dependem disso.
- **Papel real de A e B no relato** (se B = admin, era "por design" até hoje).
- Achados laterais do workflow (não corrigidos hoje): `GET /media/{subdir}/{file}` **sem auth**
  (`main.py:463-472`; precisa URL assinada, `<img src>` não manda header); `POST /conversation/{id}/read`,
  `/return` e `/takeover` sem `_require_contact_access`; toggle `enviar_mensagem_qualquer_thread` em
  perfil de role operador dá ação sem leitura; rules de `wa_messages` liberam qualquer operador do
  tenant (não endurecível por `assigned_to_uid` denormalizado: mensagens antigas do lead carregam `""` da pool).
- ~~Revisão adversarial incompleta~~ → **concluída na rodada 2** (acima). Pendências priorizadas
  (síntese): P1 `GET /media` sem auth (M/alto); P2 `_require_contact_access` em `/conversation/{id}/read|takeover|return`
  (S/médio-alto — o `/takeover` inclusive escapa do watcher novo); P3 rules de `wa_messages` (L/decisão de
  produto); P4 listener de lista sem re-subscribe no erro (M); P6 assume responder 200 com `threads=-1` (S);
  P7 teto de role nos toggles de supervisão (S); P8 TTL das camadas estáticas não-selecionadas (M);
  P9 assimetria 50 contatos×300 conversas (S/M); P10 guard de carimbo sem `firebase_uid` (S).
