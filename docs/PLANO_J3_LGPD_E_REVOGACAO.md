> Consolidado em 2026-07-31/08-01 (workflow: 3 mapeadores do codigo real -> 2 designs independentes [compliance-first vs MVP pragmatico] -> juiz). Contexto: varizemed EM PRODUCAO com dado de saude desde 2026-07-29 — J-3 deixou de ser gate pre-go-live e virou remediacao viva.

# PLANO EXECUTÁVEL CONSOLIDADO — J-3 (cripto de campo + TTL/retenção + auditoria de leitura + DPA) + D8 (revogação de consentimento)

> **Status em 2026-08-21:** plano ainda **NÃO implementado** — conferido no código de hoje: `crypto_fields.py` não existe; `config.py` não tem `PENDING_RESOLVED_TTL_DAYS`/`PENDING_FAILED_TTL_DAYS`/`FEATURE_READ_AUDIT`/`FIELD_CRYPTO_KEYS`/`BOT_STATE_TTL_DAYS`; `apply_cx_snapshot_on_assume` continua gravando a cópia integral do snapshot em `cx_summary_emitted`; o `log_audit` de `WA_SEND` ainda leva `content[:80]`; não existem `CONTACTS_EXPORT`/`WA_THREAD_VIEW` nem scripts `j3_*`; e **nenhum endpoint grava `lgpd_revoked`** (F1/D8 segue pendente). O que já está no código são os dois guards D8 antecipados pela ADR 0010 (ver item 1.6): hidratação em `bot_service.py` e `release_lead_to_bot` em `database_firestore.py`, cobertos por `tools/sim_cx_flow.py` e `tools/sim_reception_flow.py`. As decisões J1-J13 seguem pendentes do PO.
> ⚠ As âncoras `arquivo:linha` desta página são do commit `6b24ee1` e **estão defasadas** (hoje: `_get_bot_state:238` / `_set_bot_state:246` / `_clear_bot_state:250` em `bot_service.py`; `revert_lead_to_sale_owner:1971` / `return_contact_to_bot:2006` / `release_lead_to_bot:2127` em `database_firestore.py`) — reconferir contra o arquivo antes de editar.

**Base:** branch `develop`, commit `6b24ee1`. Âncoras re-verificadas no HEAD em 2026-07-31 (`_get_bot_state:236` / `_set_bot_state:244` / `_clear_bot_state:248`, comparação de idempotência do resumo em `bot_service.py:957-958`, gravação da cópia integral em `:983-985`, `mark_event_attempt` em `pending_events.py:120` / `mark_event_failed:136` / `delete_pending_event:148`, `revert_lead_to_sale_owner:1801` / `return_contact_to_bot:1829` em `database_firestore.py`, e confirmado que `user_first_input` NÃO aparece na lista de limpeza do `database_firestore.py`).

**Contexto que muda tudo:** o tenant `varizemed` está EM PRODUÇÃO desde 2026-07-29 processando dado de saúde real (`user_symptom` em resumos, texto bruto de paciente em `wa_messages`). J-3 deixou de ser gate pré-go-live e virou **remediação viva**. E a Fase 2 do `docs/PLANO_MODELOS_CRM_E_PLANOS.md` (retorno-ao-bot no fechamento clinic) está consolidada e prestes a ser canariada — **os guards D8 têm que entrar ANTES ou NO MESMO patch dela, nunca depois** (sem eles, todo fechamento clinic devolve contato revogado ao funil do CX automaticamente).

Disciplina de deploy sempre a do CLAUDE.md: `gcloud run deploy castro-crm --source C:\Rafael\castro-intelligence --region us-west1 --project project-4a851bf9-f475-418c-800 --quiet` → descobrir a revisão nova por `revisions list --sort-by "~metadata.creationTimestamp"` (nunca pelo texto do deploy) → promover por NOME com `update-traffic --to-revisions <REV>=100` → smoke `GET /` 200 + `GET /api/client-config` 200.

---

## Veredito do juiz

**Espinha = Design B (MVP pragmático).** Motivos: (i) ordenação por dependência explícita com fases genuinamente independentes (minimização antes de cripto reduz o alvo de todas as frentes seguintes); (ii) módulo de cripto mais simples e mais seguro operacionalmente (prefixos `encj:`/`encs:`, `decrypt_maybe` com tolerância total a legado, fail-safe "snapshot ilegível = sem snapshot" sem stacktrace com dado); (iii) análise de rollback VERIFICADA no código (revisão velha lendo `cx_snapshot` cifrado degrada para "sem resumo no assume" via o `isinstance(snap, dict)` — sem crash); (iv) limpeza do `user_first_input` também no pós-aceite/replay (o A só limpava na recusa — o B fecha o ciclo de vida inteiro); (v) `lgpd_revoked_at` como string ISO consistente com `lgpd_consent_at` (não é campo TTL; Timestamp nativo do A criaria inconsistência de tipo no mesmo bloco de campos).

**Enxertos do Design A (superiores, incorporados):**
1. **Cloud Audit Logs DATA_READ + sink BigQuery no DIA 0** (F0-infra, sem deploy) — não esperar a fase de auditoria; é config de IAM e é a única cobertura do caminho client SDK.
2. **Rules hardening de `wa_messages` vira FASE do plano (F4), não decisão eternamente aberta** — o risco CRÍTICO do snapshot (qualquer operador ativo lê qualquer mensagem do tenant via cliente Firestore artesanal, `firestore.rules:254-260`) torna o audit de leitura estruturalmente furado; recomendação SIM com gate de custo (J5).
3. **Guard de revogado DENTRO de `return_contact_to_bot` (ValueError)**, não só nos endpoints — qualquer caller futuro herda a proteção; o fluxo legítimo de reabertura limpa `lgpd_revoked` antes.
4. **Endpoint de re-aceite admin-only entregue JUNTO do D8** — sem ele, engano operacional (revogar o contato errado) exige cirurgia manual no console, o que é pior trilha do que um `LGPD_CONSENT_REOPENED` auditado.
5. **`FEATURE_FIELD_CRYPTO_WRITE` em 2 passos** (deploy 3a = leitor tolerante inerte; 3b = flag on) por cima do módulo do B — rollback trivial por construção.
6. **TTL do pending mais curto (7d resolved / 30d failed)** — é payload BRUTO da Meta com texto de paciente; 30/90 do B é retenção demais para dado de saúde cru fora do perímetro tenant-scoped.
7. **`PROTOCOL_VIEW`/`TRANSCRIBE_REQUEST`/`CONTACTS_EXPORT` auditados** (o B omitia transcribe).
8. **`J3_RETRO_SCRUB` como trilha da própria limpeza retroativa** + gate jurídico para reescrever `detail` de `WA_SEND` antigos.
9. **Políticas operacionais imediatas (F0.4)**: staging proibido para dado real; congelar `/api/admin/export` nos tenants clínica até a auditoria entrar; registrar data de corte em `docs/internal/`.

**Rejeitado do A:** HKDF por tenant como default (evolução, decisão J6 — 1 chave master MultiFernet basta para o MVP e o secret é único de qualquer forma); cripto antes da auditoria/D8 na ordem (D8 e trilha de leitura têm mais valor jurídico por diff e D8 tem prazo externo — o canário da Fase 2); `lgpd_revoked_at` Timestamp.

---

## Visão das fases (cada uma deployável e independente)

| Fase | Conteúdo | Tipo | Depende de |
|---|---|---|---|
| F0 | Minimização/estancamento: audit sem conteúdo, hash no emitted, ciclo de vida do `user_first_input`, snapshot zerado pós-assume, carimbo `expire_at` em pending, audit de export | deploy A | nada |
| F0-infra | DATA_READ+sink, policy TTL pending, exemptions de índice, políticas operacionais | console/gcloud, SEM deploy | nada (policy TTL só age após F0) |
| F1 | **D8 completo**: modelo, endpoint revoke + reopen, RBAC, gates builtin/CX, UI | deploy A (rules intactas) | nada; **antes ou junto do canário `medical_clinic`** |
| F2 | Auditoria de leitura app-level: `WA_THREAD_VIEW` + protocol + transcribe, com flag | deploy A | nada |
| F3 | Cripto Fernet de `bot_states` (3a leitor / 3b escrita) | deploy A + secret | F0 (hash reduz o alvo) |
| F4 | Rules: escopo de leitura de `wa_messages` | deploy de RULES isolado | J5 aprovada; validar no SAC |
| F5 | TTL `bot_states` clinic + retenção prontuário (`wa_messages`/GCS) | código+gcloud | **hidratação Fase 2 do PLANO_MODELOS em prod** + J1/J2 |
| FR | Retroativo: sweep do dado acumulado desde 29/07 | scripts one-off | F0 (pra não re-sujar); J9 |
| FD | DPA/RIPD/ADRs + tarefas fora do repo (Dialogflow/ValMemory) | docs/console | paralelo |

Gates de TODA fase com código: `.venv\Scripts\python.exe -m py_compile main.py webhook.py bot_service.py lgpd_bot.py database_firestore.py config.py tenant_service.py channel_service.py` + `tools\sim_bot_flow.py` + `tools\sim_cx_flow.py` exit 0 + `npm run build` em `frontend/` + deploy/promoção por NOME + smoke.

---

# (a) Mudanças ordenadas por arquivo/função

## FASE 0 — Minimização e estancamento (deploy 1; custo NEGATIVO)

Fecha os dois CRÍTICOS que não precisam de decisão de PO e reduz o alvo de todas as fases seguintes.

**0.1 `main.py` — parar de gravar conteúdo clínico no `audit_log` (CRÍTICO):**
- `:1775` (`WA_SEND`): trocar `f"Para {wa_id}: {content[:80]}"` por `f"contact={contact_id} conv={conversation_id} len={len(content)}"` — zero conteúdo, zero telefone em claro (quem precisar do telefone resolve pelo contato, já escopado).
- `:2260` (`WA_REOPEN_SENT`): remover nome do paciente → `contact={id}`.
- `:2441/:2454` (`CONTACT_MANUAL_CREATE`/`DECLARED_NAME`): `redact_phone`/`redact_name` de `pii_redaction.py` no detail.

**0.2 `webhook.py:305`:** `choice[:40]` → logar só `len(choice)` + classificação (texto livre do cliente nunca vai pro Cloud Logging).

**0.3 `bot_service.py` — matar a duplicação do sintoma:**
- Helper novo `_snap_hash(snap: dict) -> str` perto de `_cx_snapshot` (~`:844`): `hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()`.
- `apply_cx_snapshot_on_assume`: em `:983-985` gravar `{"cx_summary_emitted": _snap_hash(snap), "cx_summary_emitted_pid": pid}` em vez da cópia integral; a comparação de `:957-958` vira: `emitted = state.get("cx_summary_emitted"); emitted_h = _snap_hash(emitted) if isinstance(emitted, dict) else str(emitted or "")` → comparar com `_snap_hash(snap)` + pid (tolerância a doc legado com dict).
- **No MESMO `_set_bot_state` pós-emissão: `"cx_snapshot": None`** — o resumo já foi materializado na thread e `human_active=True` silencia o bot; o snapshot não tem mais leitor. Fecha o buraco do caminho assume/self-service em que o sintoma ficava PARA SEMPRE. Idempotência preservada: chamadas subsequentes veem `cx_snapshot=None` → `isinstance` falha → no-op; o hash cobre corrida entre instâncias.
- Hash SHA-256 não é reversível → fica em claro; some 1 das 2 cópias permanentes do sintoma.

**0.4 Ciclo de vida do `user_first_input` (texto bruto PRÉ-consentimento):**
- `lgpd_bot.py` ramo refused (`:223-226`): acrescentar `state["user_first_input"] = None` — texto coletado antes do consentimento NÃO sobrevive à recusa.
- `bot_service.py` `_process_cx_message` pós-aceite (região `:667`, após consumir `first_cx_text` no replay): gravar `user_first_input: None` no mesmo `_set_bot_state` do turno (o replay já serviu; a sessão CX tem o texto).
- `database_firestore.py:1864-1870` (`return_contact_to_bot`): adicionar `"user_first_input": None` à lista de limpeza. **Coordenação:** o `release_lead_to_bot` da Fase 2 do PLANO_MODELOS (item 6, passo 1) deve NASCER com `user_first_input: None` na lista — corrigir aquele plano ao implementar.
- Builtin: `_finalize_bot` já deleta o doc inteiro (`_clear_bot_state:248`) — ok.

**0.5 `pending_events.py` + `config.py` — carimbo de expiração:**
- `config.py`: `PENDING_RESOLVED_TTL_DAYS` (env, default **7**) e `PENDING_FAILED_TTL_DAYS` (default **30**), lidas 1x no import.
- `mark_event_attempt` (`:120`): quando `success`, incluir `"expire_at": utcnow() + timedelta(days=PENDING_RESOLVED_TTL_DAYS)` — **datetime NATIVO, nunca `.isoformat()`** (string = policy que nunca deleta, falha silenciosa).
- `mark_event_failed` (`:136`): idem com `PENDING_FAILED_TTL_DAYS`.
- `save_pending_event` NÃO carimba: evento ainda pendente jamais expira (invariante zero-perda preservada).

**0.6 `main.py:4207-4244` (`/api/admin/export`):** `log_audit(user["id"], "CONTACTS_EXPORT", f"formato={fmt} registros={n}")` — 1 write por export, evento raro, sem flag. Minimização do payload = J7.

**Compat de rollback F0 (documentar e aceitar):** revisão velha lendo `cx_summary_emitted` como string re-emite o resumo 1x no próximo assume (dict != string) — duplicata benigna de system message.

## FASE 0-INFRA — console/gcloud, sem deploy (executar em paralelo à F0)

**0i.1 Policy TTL em `pending_webhook_events`** (flat global → grupo `castro_crm_pending_webhook_events`; rodar DEPOIS da F0 promovida, mas é inofensivo antes — só age em docs com o campo):
```
gcloud firestore fields ttls update expire_at --collection-group=castro_crm_pending_webhook_events --enable-ttl --database="(default)" --project=project-4a851bf9-f475-418c-800
gcloud firestore fields ttls list --database="(default)" --project=project-4a851bf9-f475-418c-800
gcloud firestore operations list --project=project-4a851bf9-f475-418c-800
```
Staging tem grupo próprio (`castro_crm_staging_pending_webhook_events`) — policy separada opcional (dado real é proibido lá por política).

**0i.2 Cloud Audit Logs DATA_READ do Firestore + sink (enxerto do A — dia 0):** habilitar Data Access (DATA_READ) para `firestore.googleapis.com` na política IAM de audit do projeto Oregon. É o ÚNICO mecanismo que enxerga os reads do client SDK (onSnapshot/Listen); identidade Firebase vai em `protoPayload.authenticationInfo.thirdPartyPrincipal` (JWT com claim `tenant_id` → filtrável por tenant). Sink pro BigQuery (dataset `firestore_data_access`, us-west1; aproveita o sink já deferido pro `audit_logs_system` — `HANDOFF_IAP_E_TENANT2.md:244`). Retenção default de 30d do `_Default` NÃO sustenta trilha LGPD. Monitorar ingestão no 1º mês (estimativa 1-4 GiB/mês, free tier 50 GiB; rajadas de Listen podem surpreender — alarme antes de assumir custo zero).

**0i.3 Exemptions de índice (`fieldOverrides`):** desabilitar single-field index de `wa_messages.content`, `wa_messages.transcription`, `bot_states.cx_snapshot`, `bot_states.cx_summary_emitted`, `bot_states.user_first_input`, `wa_contacts.notes`, `wa_contacts.bot_notes` — **grep antes** confirmando que nenhum aparece em `.where()`/`order_by` (`lead_temperature` FICA indexado). Aplicar via `gcloud firestore indexes fields update <campo> --collection-group=<grupo> --disable-indexes` (firebase CLI ausente na máquina — memória) e refletir em `firestore.indexes.json`. Ganhos: menos 1 cópia física do dado sensível + writes mais baratos na coleção de maior volume.

**0i.4 Políticas operacionais (registrar em `docs/internal/YYYY-MM-DD.md`):** (a) proibido dado real em staging (`castro_crm_staging` no MESMO Firebase com rules permissivas); (b) congelar uso de `/api/admin/export` nos tenants clínica até F2 em prod; (c) data de corte: tudo gravado antes da FR permanece em PITR/backup por 7 dias após a limpeza.

## FASE 1 — D8: revogação de consentimento (deploy próprio; ANTES ou JUNTO do canário `medical_clinic`)

**1.1 `rbac.py`:**
- `PERMISSION_CATALOG` (`:48-78`), grupo Lead: `("Lead", "registrar_revogacao_lgpd", "Registrar revogacao de consentimento LGPD")`. NÃO reusar `editar_dono_lead` (roteamento != compliance).
- Seeds: `perfil_admin` automático (`:121`, todos True); adicionar ao set do `perfil_supervisor` (`:128-145`); `perfil_operador` NÃO (J3).
- **Fallback de role pré-Fase-5 (`:216`):** mapear a chave nova para admin+supervisor — senão tenant sem perfis semeados nega a ação ao supervisor.
- ⚠ **Rebase (ADR 0010, 2026-08-04):** o catálogo/seeds JÁ ganharam o toggle `assumir_atendimento` (Modo Recepção) — as âncoras de linha acima deslocaram ~1-2 linhas; conferir contra o arquivo atual antes de editar.

**1.2 `database_firestore.py` — `revoke_lgpd_consent(contact_id, revoked_by_user_id, note)` (nova, ao lado de `return_contact_to_bot:1829`), FAIL-CLOSED** (contraste deliberado com `_record_lgpd_consent` best-effort — falha silenciosa aqui = bot seguindo a coletar dado de saúde de revogado):
1. `contact = _get_doc("wa_contacts", contact_id)`; inexistente → `None` (404 no caller); `lgpd_revoked` já True → `"already"` (409 no caller).
2. **`bot_states/{contact_id}` PRIMEIRO** (merge, SEM try/except): `{lgpd_consent: False, lgpd_status: "revoked", user_first_input: None, cx_snapshot: None, cx_summary_emitted: None, cx_summary_emitted_pid: None}` — mata funil CX em voo (`handle_lgpd` lê SÓ o state, `lgpd_bot.py:191-196`; um `lgpd_consent=True` em voo venceria o contato). Se o passo 2 falhar depois, o state já bloqueia o bot — falha na direção segura.
3. **Contato POR ÚLTIMO (commit-point,** padrão `_persist_lead_temperature`): merge dos campos da tabela (b).
4. `log_audit(revoked_by_user_id, "LGPD_CONSENT_REVOKED", f"contato {id} | politica {ver}")` — **SEM o texto do motivo** (pode citar contexto clínico; fica só no contato). Best-effort como todo audit.
5. System message best-effort DEPOIS do commit: `insert_transfer_system_message(contact_id, "Revogacao de consentimento LGPD registrada pelo atendimento.", None, advance_recency=False)` — `advance_recency=False` obrigatório (memória: recência inflada).

**1.3 `database_firestore.py` — guard em `return_contact_to_bot` (`:1829`, enxerto do A):** no topo, `if contact.get("lgpd_revoked"): raise ValueError("lgpd_revoked")` — qualquer caller futuro herda; o fluxo de reopen limpa o campo antes.

**1.4 `main.py` — endpoints:**
- `POST /api/wa/contact/{contact_id}/lgpd-revoke` (molde `:3867-3880`): `ensure_permission(user, "registrar_revogacao_lgpd")` (sem `_require_contact_access` — supervisor revoga sobre lead de qualquer operador; RBAC é o gate, confirmar em J3) + `get_wa_contact` + 404; body `{note: str}` obrigatório, `len(note.strip())>=5` senão 422; `None`→404, `"already"`→409, exceção→500 (fail-closed), sucesso→200 com contato atualizado.
- `POST /api/wa/contact/{contact_id}/lgpd-reopen` (enxerto do A; **role `admin` estrita**, padrão `main.py:677` — mesmo racional do D6): merge no contato `{lgpd_revoked: False, lgpd_reopened_at: ISO, lgpd_reopened_by_user_id, lgpd_consent: None, lgpd_consent_at: None, lgpd_policy_version: None}` + delete do `bot_states` → o aviso LGPD renasce DO ZERO com a versão VIGENTE (fail-closed D1 vale no re-aceite) + `log_audit("LGPD_CONSENT_REOPENED", ...)`. O vocabulário comum de aceite (SIM) NUNCA destrava revogação.
- Endpoint individual `POST /api/wa/contact/{id}/return-to-bot` (`:3874`): capturar `ValueError("lgpd_revoked")` → **409** com mensagem clara; bulk (`:3925-3927`): pular revogados e reportar `skipped_lgpd_revoked: [ids]`.

**1.5 `bot_service.py` — gates (o check fica SEMPRE antes do `handle_lgpd`;** cair no ramo `lgpd_consent is False` do `lgpd_bot.py:199-213` re-ofereceria o botão SIM e o revogado reativaria o funil com um toque):
- `_process_cx_message`, no gate `:632-637`: `if contact.get("lgpd_revoked"): return None`; repetir no re-check pós-turno (`:703-720`, contato já relido — custo zero; revogação durante DetectIntent em voo não pode responder).
- `process_bot_message` (builtin), após `:332`: mesmo check → `return None` (vale pra todo tenant).
- `session_params` (`:694-698`): trocar `"lgpd_consent": True` hardcoded por `bool(contact.get("lgpd_consent") is True and not contact.get("lgpd_revoked"))` — defesa em camada no agente (caminho futuro sem os gates herda a proteção; custo zero, contato já carregado).

**1.6 Patch da Fase 2 do PLANO_MODELOS (no MESMO patch dela, quando entrar):**
- `release_lead_to_bot` (item 6): guard `lgpd_revoked → return None` ao lado dos guards `is_backup` (`:173` do plano) — caller cai no `revert_lead_to_sale_owner`; fechamento continua funcionando, só não devolve ao bot.
- Hidratação (item 9, `bot_service.py` entre `:643` e `:651`): acrescentar `and not contact.get("lgpd_revoked")` à condição — cinto e suspensório sobre o `lgpd_consent is True` (protege contra prova re-gravada por corrida e contra bot_states expirado por TTL na F5).
- ✅ **JÁ FEITO (ADR 0010, 2026-08-05):** os itens 6 e 9 foram antecipados com gate `pool_mode=reception` e AMBOS os guards acima já estão no código (`release_lead_to_bot` com `lgpd_revoked → None`; hidratação com `not contact.get("lgpd_revoked")`), cobertos por sims (`sim_reception_flow` cenário 11; `sim_cx_flow` cenário q). A F1 só precisa passar a GRAVAR o campo `lgpd_revoked` — o enforcement já herda. O caso de sim nº 8/9 desta lista tem equivalente rodando.

**1.7 Frontend:**
- `frontend/src/types.ts`: `:58` união de permissões + `lgpd_revoked?`, `lgpd_revoked_at?` no tipo Contact (~`:180`); `normalization.ts` (~`:55/:134`) normaliza os campos novos.
- `CrmContext.tsx`: action `revokeLgpdConsent(contactId, note)` chamando o POST + refetch/atualização otimista do contato.
- `App.tsx` `detail-panel` (`:1426-1467`), card "Qualificação": botão "Registrar revogação LGPD" (danger) gated `can("registrar_revogacao_lgpd")`, confirm forte + motivo obrigatório; chip "LGPD revogada" no header (molde do chip de rating `:1440-1448`); **desabilitar "Devolver ao bot"** (`:1454-1455`) e a option `return_to_bot` do bulk (`:1527`) quando `lgpd_revoked`.
- `firestore.rules`: NENHUMA mudança nesta fase (campos novos viajam pelas rules existentes; escrita é backend-only).

## FASE 2 — Auditoria de leitura app-level (deploy)

- `config.py`: `FEATURE_READ_AUDIT` (env bool, default true) — freio por env.
- `main.py`: `_thread_view_seen: dict[tuple[int,int], float]` + helper `_should_log_thread_view(user_id, contact_id, window_s=1800)` (padrão do cache de auth `auth.py:50`; poda lazy pra não crescer sem teto).
- `GET /api/wa/messages/{contact_id}` (`:1408-1426`), após `_require_contact_access`: `log_audit(uid, "WA_THREAD_VIEW", f"contact={cid}")` com dedup — ponto por onde TODA visualização de dossiê passa ≥1x (primeira página via REST, `CrmContext.tsx:1364/1593`).
- `GET /api/admin/protocol/{pid}` (`:2795-2819`): `PROTOCOL_VIEW` sem dedup (volume baixo, devolve timeline com o resumo clínico).
- Transcribe (`:1429/:1477`): `TRANSCRIBE_REQUEST` com `message_id` (gera dado clínico novo).
- NUNCA contador sequencial (hotspot documentado `database_firestore.py:2571-2575`); doc-id automático como o `log_audit` atual. Rejeitado por design: audit por doc lido (~750k writes/mês, recria o write-side que as frentes de custo eliminaram, sem ganho probatório sobre app-level + DATA_READ).

## FASE 3 — Cripto de campo Fernet em `bot_states` (deploy em 2 passos + secret)

Escopo realista AGORA: **`bot_states` apenas** — cliente negado nas rules (`firestore.rules:271-273`), sem listener no frontend, funil único `_get_bot_state:236`/`_set_bot_state:244` (o único write direto fora do funil, `db:1864`, só ZERA campos — não precisa cifrar), campos opacos nunca em `where()`/`order_by`. **`wa_messages.content` NÃO entra** — o onSnapshot da timeline lê o doc cru (`CrmContext.tsx:1318-1324`); cifrar = re-arquitetura da timeline (J6). `lead_temperature` fica em claro (derivado não-sensível — `PLANO_LEAD_TEMPERATURE.md:119-125`).

- **`crypto_fields.py` (novo, raiz, `# -*- coding: utf-8 -*-`):** lê `FIELD_CRYPTO_KEYS` (CSV de chaves Fernet urlsafe-base64) via `config.py`; `MultiFernet` (primeira cifra, todas decifram → rotação sem big-bang); `encrypt_json(obj) -> "encj:..."`, `encrypt_str(s) -> "encs:..."`, `decrypt_maybe(value)`: prefixo reconhecido → decifra (+`json.loads` no `encj:`); sem prefixo/dict/None → retorna como está (tolerância total a legado — nenhuma migração obrigatória). Chave inválida/ausente na decifra → warning SEM o valor + retorna `None` (fail-safe: snapshot ilegível = "sem snapshot", nunca stacktrace com dado).
- **`config.py`:** `FIELD_CRYPTO_KEYS` (lida 1x) + `FEATURE_FIELD_CRYPTO_WRITE` (default `false`, enxerto do A).
- **`bot_service.py`:** `_CRYPTO_STATE_KEYS = ("cx_snapshot", "user_first_input")` (o `cx_summary_emitted` já virou hash na F0 — não precisa); `_set_bot_state` cifra os presentes e não-None quando flag on (`None` passa direto — limpezas continuam byte-idênticas); `_get_bot_state` aplica `decrypt_maybe` SEMPRE (leitor entra no deploy 3a). Cobre todos os leitores (assume, temperatura, resumo, replay) sem tocar mais nada.
- **Operação:** secret `field-crypto-keys` no Secret Manager (`Fernet.generate_key()`), ligar UMA vez com `gcloud run services update castro-crm --update-secrets FIELD_CRYPTO_KEYS=field-crypto-keys:latest --region us-west1 --project project-4a851bf9-f475-418c-800` (deploys `--source` puros preservam depois — pegadinha do CLAUDE.md). **Deploy 3a:** secret + leitor, flag off (inerte). **Deploy 3b:** `FEATURE_FIELD_CRYPTO_WRITE=true`.
- **Scripts:** `scripts/j3_reencrypt_bot_states.py` (dry-run default; cifra plaintext remanescente — dezenas/centenas de docs) e `scripts/j3_clear_encrypted_states.py` (dry-run; zera campos cifrados caso rollback longo pra revisão pré-F3 seja necessário). Rollback verificado: revisão velha lendo `encj:` degrada para "sem resumo no assume" via `isinstance(snap, dict)` — sem crash. Perda da chave = perda do dado cifrado → manter 2 versões do secret + procedimento de rotação documentado.
- Evolução (J6, não bloqueia): HKDF por tenant ou KMS envelope por tenant (revogação real de chave + Cloud Audit Logs de uso + IAM de quem decifra) com prefixo `encj2:`.

## FASE 4 — Rules: escopo de leitura de `wa_messages` (deploy de RULES isolado; gated J5)

Hoje `firestore.rules:254-260` deixa qualquer operador ativo do tenant ler QUALQUER `wa_message` não-backup via cliente Firestore artesanal — fora do alcance de qualquer audit app-level. Mudança: leitura exige privilegiado OU `get(/databases/$(db)/documents/castro_crm_tenants/$(tid)/wa_conversations/$(resource.data.conversation_id))` aplicando o MESMO predicado do `canSeeContactScoped` (`:249-252`): `assigned_to_uid == uid` OU pool sem dono; `is_backup` continua privilegiado. Espelhar na seção staging (`:343-441`).
- A query do frontend filtra por `conversation_id` único → o `get()` é determinístico e cacheado por request: **+1 read por abertura/attach de listener**, não por doc (~+1-2% dos reads).
- Compat: o frontend só assina mensagens da conversa ABERTA (alcançada via picker/pool/Meus) → nenhuma quebra esperada; validar V5 antes de publicar em prod. Rollback = republicar o ruleset anterior (versionado).
- ⚠ **Modo Recepção (ADR 0010, 2026-08-04):** o ramo "pool sem dono" do predicado é **VITAL** — tenant com `pool_mode=reception` (varizemed) opera com ~todas as threads sem dono; "otimizar" a F4 removendo esse ramo cega a Recepção inteira (todo operador perde leitura de tudo). Corolário de compliance: num tenant reception a F4 entrega ~zero isolamento efetivo (o pool é o caminho normal) — registrar como risco aceito no DPA/RIPD e considerar na justificativa de custo da J5.

## FASE 5 — TTL `bot_states` clinic + retenção do prontuário (gated)

**PRÉ-REQUISITO INEGOCIÁVEL:** hidratação da prova pelo CONTATO (Fase 2 do PLANO_MODELOS, item 9) em prod com sign-off do canário. TTL apaga o DOC inteiro — sem hidratação, paciente re-toma o aviso a cada expiração; e a recusa expirada faz a hidratação confiar só no contato (é por isso que a revogação D8 grava `lgpd_consent=False` NO CONTATO, fonte da hidratação).
- `config.py`: `BOT_STATE_TTL_DAYS` (default 90, J1).
- `bot_service.py` `_set_bot_state` (`:244`): `expire_at = utcnow() + timedelta(days=BOT_STATE_TTL_DAYS)` **somente quando** `crm_model_from_doc(get_tenant(tid)) == "medical_clinic"` (`get_tenant` cacheado 60s — zero read extra no caminho quente).
- Policy: `gcloud firestore fields ttls update expire_at --collection-group=bot_states --enable-ttl ...` — o grupo cobre prod+staging+todos os tenants (prefixo só existe na raiz, `firestore_common.py:138-145`), mas **só docs COM o campo expiram** → o carimbo seletivo É a retenção por tenant. NUNCA carimbar hubloc/`is_backup`. Não rodar o gcloud antes do sign-off da hidratação.
- `wa_messages`/`transcription` + mídia GCS: NÃO implementar sem J2 (prazo do DPA; "prontuário some da UI" é decisão de negócio). Mecânica reservada: `expire_at` em `save_wa_message` só tenant clínica e NUNCA `is_backup`; GCS via Object Lifecycle por prefixo do tenant, MESMO prazo (senão mídia órfã/mensagem sem mídia). Carimbo indevido em massa é irreversível após PITR 7d — script sempre dry-run default.
- `audit_log`/`audit_logs_system`/BQ: **SEM TTL curto** (trilha LGPD sobrevive; prazo no DPA, J1).
- TTL não é controle de acesso: doc legível até ~72h pós-expiração — somar a folga em qualquer promessa do DPA.

## FASE R — Retroativo (dado acumulado em prod desde 29/07)

`scripts/j3_retro_sweep.py` (novo; **dry-run default**, `--apply` explícito, `--tenant varizemed --tenant varizemed-test`, ADC + `set_tenant_context` por tenant). Ações nesta ordem:
1. **`bot_states`:** por doc: (a) `cx_summary_emitted` presente (resumo já materializado) OU contato com `bot_completed`/`assigned_to` → merge `{cx_snapshot: None, cx_summary_emitted: <hash ou None>, user_first_input: None}` (pid mantém); (b) `lgpd_status=="refused"` → `user_first_input: None`. **NÃO tocar funil ativo** (`lgpd_status=="awaiting"` ou contato sem dono/sem `bot_completed` com `last_message_at` < 48h).
2. **`pending_webhook_events`:** `.where("status","in",["resolved","failed"])` server-side → `expire_at = utcnow()+24h` (a policy da F0-infra deleta; payloads com texto de paciente somem em ≤ ~4 dias).
3. **`audit_log`:** `.where("action","==","WA_SEND")` → reescrever `detail` para o formato minimizado da F0.1 (preserva user/action/created_at); idem `WA_REOPEN_SENT`. Rodar TAMBÉM no hubloc (vazamento existe lá). Registrar `log_audit(0, "J3_RETRO_SCRUB", f"{n} docs sanitizados | acao=WA_SEND")` — a limpeza da trilha vira ela mesma trilha. **Gated por J9** (jurídico valida minimizar trilha existente; alternativa: exportar original cifrado pra cold storage antes).
4. Relatório final só com CONTAGENS (nunca conteúdo). Depois da F3b: rodar `j3_reencrypt_bot_states.py`.

**Cópias que o sweep NÃO alcança (documentar no DPA):** PITR/backups (expiram ~7d após o sweep — agendar verificação); `persistentLocalCache` (IndexedDB) nas máquinas dos operadores — instrução operacional de limpeza de site-data; índices — resolvido pelas exemptions 0i.3.

**Fora do repo (gate formal do go-live — donos: PO + dev IA da clínica; J11):** (a) Dialogflow CX: criar ENVIRONMENT versionado e apontar `settings.ai.environment_id` (sai do DRAFT — fecha também o vetor do bug dos params de 29/07) — ✅ **FEITO no tenant `varizemed`** (troca versionada por `scripts/set_cx_environment.py`, runbook + histórico em `docs/deploy/TROCAR_ENVIRONMENT_VAL.md`; `varizemed-test` segue no DRAFT por design); segue pendente ajustar interaction logging/retention do agente + Cloud Logging do projeto do agente; (b) ValMemory `val-castrochat`: TTL de `user_symptom`/`handoff_summary` (functions da clínica, já listado em `PLANO_TENANT_TESTE_VARIZEMED_CX.md:254-259`); (c) lembrar: `varizemed-test` compartilha o MESMO agente — testes geram dado no agente de produção; limpar sessões/histórico após validação.

## FASE D — Papelada (paralelo)

ADRs em `docs/decisions/` para J1-J13 decididas; atualizar `docs/compliance/LGPD_RoPA_RIPD_INTERNO.md` (R-7 ganha o fluxo D8; R-11 DPA); DPA Varizemed com: retenções (com folga +72h do TTL), residência us-west1, PITR 7d, IndexedDB, subprocessadores (Google/Meta/Dialogflow), staging proibido pra dado real, controles compensatórios de `wa_messages` plaintext (rules F4 + DATA_READ + at-rest + exemptions de índice + isolamento 3 camadas).

---

# (b) Modelo de dados exato

| Coleção/doc | Campo | Tipo/valor | Fase | Compat/observação |
|---|---|---|---|---|
| `pending_webhook_events` | `expire_at` | **Timestamp nativo** (datetime) | F0 | só em resolved (+7d) / failed (+30d); pendente NUNCA; policy no grupo `castro_crm_pending_webhook_events` |
| `bot_states/{contact_id}` | `cx_summary_emitted` | dict → **string sha256 (64 hex)** | F0 | leitura tolera dict legado (hash on-the-fly); revisão velha re-emite 1 resumo (benigno) |
| `bot_states/{contact_id}` | `user_first_input` | zerado em recusa/pós-replay/retornos/revogação | F0/F1 | builtin já deleta o doc no finalize |
| `bot_states/{contact_id}` | `cx_snapshot` | `None` pós-emissão do resumo no assume | F0 | idempotência via `isinstance` + hash |
| `bot_states/{contact_id}` | `lgpd_status` | valor novo `"revoked"` (≠ `"refused"` re-consentível); `lgpd_consent: False` | F1 | espelho obrigatório do contato (state vence no `handle_lgpd`) |
| `bot_states/{contact_id}` | `cx_snapshot`/`user_first_input` | cifrados `encj:`/`encs:` (string) | F3 | só com `FEATURE_FIELD_CRYPTO_WRITE=true`; leitor tolerante desde 3a; `None` nunca cifrado |
| `bot_states/{contact_id}` | `expire_at` | Timestamp; SÓ `crm_model=="medical_clinic"` | F5 | gated pela hidratação Fase 2 em prod; default 90d (J1) |
| `wa_contacts/{id}` | `lgpd_revoked` | bool True (ausência = nunca revogado) | F1 | terminal pro bot; só o reopen admin limpa |
| `wa_contacts/{id}` | `lgpd_revoked_at` | string ISO (consistente com `lgpd_consent_at`; NÃO é campo TTL) | F1 | |
| `wa_contacts/{id}` | `lgpd_revoked_by_user_id` | int | F1 | |
| `wa_contacts/{id}` | `lgpd_revocation_note` | string (motivo/como o titular pediu) | F1 | **fica SÓ no contato — nunca vai pro audit** |
| `wa_contacts/{id}` | `lgpd_policy_version_at_revocation` | string (cópia da versão vigente na prova revogada) | F1 | |
| `wa_contacts/{id}` | `lgpd_consent` | passa a `False` no mesmo merge da revogação | F1 | hidratação Fase 2 exige `is True` → bloqueia por construção; **prova original `lgpd_consent_at`/`lgpd_policy_version` PRESERVADA** |
| `wa_contacts/{id}` | `lgpd_reopened_at` (ISO), `lgpd_reopened_by_user_id` | no reopen admin: `lgpd_revoked: False`, prova ZERADA (`lgpd_consent/at/policy_version: None`) + delete do `bot_states` | F1 | aviso renasce com versão VIGENTE |
| `audit_log` (tenant) | actions novas: `CONTACTS_EXPORT`, `LGPD_CONSENT_REVOKED`, `LGPD_CONSENT_REOPENED`, `WA_THREAD_VIEW`, `PROTOCOL_VIEW`, `TRANSCRIBE_REQUEST`, `J3_RETRO_SCRUB`; `WA_SEND`/`WA_REOPEN_SENT`/`CONTACT_*` sem conteúdo/PII | — | F0-FR | doc-id automático, NUNCA contador sequencial |
| `config.py` | `PENDING_RESOLVED_TTL_DAYS=7`, `PENDING_FAILED_TTL_DAYS=30`, `FEATURE_READ_AUDIT=true`, `FIELD_CRYPTO_KEYS=""`, `FEATURE_FIELD_CRYPTO_WRITE=false`, `BOT_STATE_TTL_DAYS=90` | env | F0-F5 | lidas 1x no import (convenção do repo) |
| `rbac.py` | permissão `registrar_revogacao_lgpd` (grupo Lead) | — | F1 | seeds admin+supervisor; fallback role `:216` |
| `firestore.indexes.json` | `fieldOverrides` (7 exemptions da 0i.3) | — | F0-infra | via gcloud |
| `firestore.rules` | F4 apenas: leitura de `wa_messages` escopada via `get()` da conversa | — | F4 | nenhuma outra fase toca rules |

**Retroativo do dado já acumulado:** coberto pela FASE R (bot_states scrub + pending carimbo + audit scrub) — os campos novos NUNCA são backfillados (`lgpd_revoked` ausente = semanticamente "nunca revogado"; `cx_summary_emitted` dict legado é lido por tolerância até o sweep converter).

---

# (c) Casos de simulador

**`tools/sim_cx_flow.py`** (os 47 atuais seguem verdes; asserts sobre o STORE mockado):
1. `emitted_vira_hash` — assume → `cx_summary_emitted` é string 64-hex; 2º assume NÃO re-emite; doc legado com dict emitted também não re-emite (hash on-the-fly).
2. `snapshot_zerado_pos_assume` — pós-emissão `cx_snapshot is None`; temperatura/resumo saíram corretos ANTES do zero; picker/takeover subsequentes = no-op sem resumo duplicado.
3. `recusa_limpa_first_input` — recusa LGPD → `user_first_input is None` no state persistido.
4. `aceite_replay_limpa_first_input` — aceite → replay consumido → campo zerado no mesmo turno.
5. `revogado_bot_mudo_cx` — contato `lgpd_revoked=True` → msg → `CX_CALLS` não cresce, nenhuma reply, nenhum botão LGPD, nenhum write de state.
6. `revogado_sim_nao_reconsente` — state `{lgpd_consent: False, lgpd_status: "revoked"}` + msg "SIM" → mudo (prova que o gate fica ANTES do `handle_lgpd`).
7. `revogacao_mata_funil_em_voo` — state com `lgpd_consent=True` (sessão CX ativa) → revogar → próxima msg não chama CX (espelho no state venceu).
8. `revogado_nao_hidrata` (junto do patch Fase 2) — prova True no contato + `lgpd_revoked=True`, state vazio → hidratação não grava accepted, CX não chamado.
9. `revogado_fechamento_clinic_nao_volta` (junto do patch Fase 2) — clinic + revogado → `set_attendance_status("fechado_manual")` → `release_lead_to_bot` retorna None → `revert_lead_to_sale_owner` aplicado, `bot_completed` segue True.
10. `revoke_fail_closed` — mock do merge do contato levantando exceção → `revoke_lgpd_consent` PROPAGA (assert raises); state já espelhado = bot mudo (lado certo do erro).
11. `session_params_valor_real` — contato revogado/sem prova → `lgpd_consent` injetado no CX é False (assert no payload capturado do mock).
12. `cripto_roundtrip` — chave de teste no env + flag on → store contém `encj:`/`encs:` nos 2 campos; `_get_bot_state` devolve idêntico; assume/resumo/temperatura iguais.
13. `cripto_legado_plaintext` — doc com dict plaintext → leitura normal; token de chave errada → snapshot tratado como vazio, sem exceção, warning sem valor.
14. `cripto_flag_off_le_cifrado` — flag off → writes novos plaintext, mas doc cifrado continua legível (prova do deploy 3a/3b).
15. `pending_expire_at` — `mark_event_attempt(success=True)` grava `expire_at` datetime ~7d; `mark_event_failed` ~30d; `save_pending_event` NÃO grava.
16. `expire_at_so_clinic` (F5) — `_set_bot_state` em tenant clinic grava `expire_at` datetime; tenant rental não ganha o campo.

**`tools/sim_bot_flow.py`** (builtin; ~44 atuais seguem verdes):
17. `revogado_builtin_mudo` — `lgpd_revoked` → `process_bot_message` retorna None antes do `handle_lgpd` (nem aviso).
18. `return_to_bot_recusa_revogado` — `return_contact_to_bot` levanta `ValueError("lgpd_revoked")`.
19. `recusa_builtin_limpa_first_input`.
20. `audit_sem_conteudo` — fluxo com envio de operador → nenhum `log_audit` capturado contém texto da mensagem nem wa_id em claro.

---

# (d) Roteiro de validação — tenant "Castro Intelligence SAC" (varizemed-test, prod) + critério de go-live

⚠ O SAC usa o MESMO agente CX do tenant real — limpar sessões/histórico do agente após os testes. Sempre número de teste próprio, nunca paciente real. Cada fase: deploy promovido por NOME + smoke antes de validar.

- **V0 (F0):** conversa nova → aceite → qualificação → assume: console Firestore mostra `cx_summary_emitted` hash + `cx_snapshot=None` + `user_first_input` zerado pós-aceite; reabrir picker/takeover → resumo NÃO duplica. Enviar msg como operador → `audit_log.WA_SEND` sem conteúdo/telefone. Recusar LGPD noutro número → `user_first_input` zerado. Forçar evento pending → resolved → doc ganha `expire_at` datetime.
- **V0i (F0-infra):** `fields ttls list` mostra policy ACTIVE; docs resolved antigos deletados em ~24-72h (métrica TTL no Monitoring); `indexes fields list` mostra exemptions; 1 entry DATA_READ no Logging com `thirdPartyPrincipal` carregando claim `tenant_id`; ingestão diária <2 GiB (alarme).
- **V1 (F1, E2E de revogação):** contato com aceite prévio → SUPERVISOR registra revogação (motivo obrigatório) → console: `lgpd_revoked=True` + `lgpd_consent=False` + prova original intacta; `bot_states.lgpd_status="revoked"` + campos sensíveis zerados; audit `LGPD_CONSENT_REVOKED` SEM motivo; system message sem subir recência. Msg nova do "paciente" → bot MUDO (zero `[BOT-CX]` nos logs); "SIM" → segue mudo. OPERADOR comum: botão ausente + POST → 403. UI: chip "LGPD revogada", "Devolver ao bot" desabilitado; `POST /return-to-bot` → 409; bulk pula e reporta. ADMIN reopen → aviso LGPD renasce com versão vigente + `LGPD_CONSENT_REOPENED`. (Quando a Fase 2 canariar: fechar atendimento clinic de revogado → lead volta pro sale_owner, NÃO pro bot.)
- **V2 (F2):** abrir thread → 1 `WA_THREAD_VIEW`; reabrir <30min → nenhum doc novo; export → `CONTACTS_EXPORT`; protocolo → `PROTOCOL_VIEW`; consulta BigQuery devolve entries DATA_READ do operador filtráveis por tenant.
- **V3 (F3):** deploy 3a → nada muda (flag off); 3b → conversa nova → console mostra `encj:` no `cx_snapshot`; assume → resumo com Sintoma correto na thread; contato ANTIGO plaintext → assume funciona (tolerância); drill de rollback: flag off → writes plaintext + docs cifrados legíveis.
- **V4 (F4):** com token de operador comum, cliente Firestore artesanal lendo `wa_messages` de conversa com dono alheio → PERMISSION_DENIED; UI normal (thread própria + pool) intacta; reads não inflam além de +1/abertura.
- **V5 (F5):** `bot_states` novo do clinic tem `expire_at` (~90d); doc hubloc não tem; doc retro-datado some em <72h.
- **V6 (FR):** sweep dry-run no SAC → conferir contagens → `--apply` → spot-check: states de atendimentos fechados sem snapshot/first_input; WA_SEND antigos minimizados; pending resolved com `expire_at`.
- **Monitorar 48h por fase:** pending ~0 (tripwire), logs `[BOT-CX]`/`no_channel`, reads/writes vs baseline do billing (nenhuma fase pode inflar), ingestão do Logging.

**Critério de GO-LIVE da Varizemed real (todos obrigatórios):**
1. F0+F0-infra+F1+F2+F3 em prod, validadas no SAC, 48h estáveis cada.
2. Guards D8 comprovadamente no patch da Fase 2 do PLANO_MODELOS (sims 8-9 verdes) ANTES de ligar `medical_clinic` na Varizemed.
3. F4 publicada (ou J5 formalmente decidida como risco aceito com DATA_READ compensatório registrado no DPA).
4. FR executada nos 2 tenants varizemed + verificação pós-PITR (7d) agendada.
5. Tarefas fora do repo fechadas (J11): agente fora do DRAFT (environment versionado), retention/logging do Dialogflow ajustados, TTL ValMemory, política de staging assinada.
6. DPA Varizemed assinado com retenções (folga +72h), residência, subprocessadores e controles compensatórios; RIPD atualizada.
7. `settings.ai.lgpd_policy_version` REAL configurada no tenant (pré-condição D1 do PLANO_MODELOS).
8. F5 (`bot_states` TTL) NÃO bloqueia o go-live — entra depois da hidratação Fase 2 estabilizada; registrar como pendência datada no DPA.

---

# (e) Custo Firestore estimado por frente e riscos aceitos

| Frente | Custo (us-west1, ordem de grandeza) |
|---|---|
| F0 minimização | **Negativo** (menos bytes gravados, menos entradas de índice) |
| F0-infra TTL pending | Deletes ~US$0,01-0,02/100k sobre centenas/mês ≈ US$0 |
| F0-infra exemptions | Reduzem custo de write de `wa_messages` (maior volume do sistema) |
| F0-infra DATA_READ | 1-4 GiB/mês → free tier 50 GiB (US$0); BQ storage ~US$0,02/GiB/mês; monitorar 1º mês |
| F1 D8 | ~4 writes por revogação (evento raríssimo) + 1 audit; ZERO reads novos (gates usam contato já carregado) |
| F2 read audit | 9-30k writes/mês ≈ US$0,03-0,10/mês |
| F3 cripto | Zero rede/ops (Fernet local ~µs); secret US$0,06/versão/mês; payload ~1,3x num doc frio |
| F4 rules | +1 read por abertura/attach de listener (~+1-2% dos reads) |
| F5 TTL clinic | Deletes normais sobre volume pequeno ≈ US$0 |
| FR sweep | <1k writes one-off |
| **Total J-3** | **< US$5/mês** — nenhum read novo em caminho quente; invariantes de custo do CLAUDE.md preservadas. Validar tabela de preços vigente antes de registrar compromissos no ADR/DPA |

**Riscos aceitos (registrar no RIPD/DPA):**
1. `wa_messages.content`/`transcription` permanecem plaintext no Firestore (controles compensatórios: rules F4, DATA_READ, at-rest do Google, exemptions, isolamento LGPD 3 camadas) — re-arquitetura da timeline é J6.
2. Trilha app-level de leitura é parcial por construção (onSnapshot não passa pelo backend) — DATA_READ cobre; buraco documentado até F4 publicada.
3. TTL não é controle de acesso (doc legível até ~72h pós-expiração) e deletes sobrevivem em PITR 7d.
4. IndexedDB (persistentLocalCache) nas máquinas dos operadores retém mensagens — mitigação operacional, não técnica.
5. Chave Fernet única no env da revisão (comprometimento expõe o cifrado; rotação = MultiFernet + re-encrypt) — evolução KMS é J6.
6. Rollback da F0 re-emite 1 resumo por contato (duplicata benigna).
7. Temperatura derivada de sintoma visível na pool pré-assume (derivado não-sensível — classificação registrada, precedente PLANO_LEAD_TEMPERATURE).
8. Colaterais MÉDIOS sem código nesta leva: `wa_transfer_log` (reason/summary livres), `gc_messages` (DMs amplas + saída pro Workspace), `media_assets` (chunks amplos) — J12.
9. `varizemed-test` compartilha agente CX do tenant real — testes geram dado no agente de produção (limpeza pós-teste obrigatória).

---

# (f) DECISÕES PENDENTES DO PO (registrar como ADRs em `docs/decisions/`)

1. **J1 — Prazos de retenção:** pending resolved 7d / failed 30d; `bot_states` clinic 90d (só pós-hidratação); `audit_log` + trilha BQ ≥5 anos / ≥18 meses. Toda promessa no DPA soma folga de +72h do TTL. Aprovar números.
2. **J2 — Retenção do prontuário (`wa_messages`/`transcription`/mídia GCS):** reter permanente (defesa/prontuário) ou expirar — prazo vem do DPA; define também se o histórico importado (D7) entra na mesma retenção (`is_backup` NUNCA expira por default). Sem decisão → sem TTL nessas coleções (risco residual registrado).
3. **J3 — Quem revoga:** admin+supervisor (recomendado) vs incluir operador comum; e confirmar revogação registrável sobre lead de outro operador (proposto: sim — RBAC é o gate, sem `_require_contact_access`).
4. **J4 — Re-aceite pós-revogação:** terminal + reopen admin-only auditado `LGPD_CONSENT_REOPENED` (recomendado, art. 11 — já implementado na F1) vs titular re-aceita com SIM (descaracteriza revogação formal; não recomendado). Definir antes de treinar a clínica.
5. **J5 — Rules de `wa_messages` (F4):** aprovar +1 read/abertura para fechar o CRÍTICO do snapshot (recomendado: SIM) vs risco aceito documentado com DATA_READ compensatório vs timeline 100% backend (projeto grande, ligado a J6).
6. **J6 — Evolução de cripto:** Fernet master (MVP desta entrega) vs HKDF por tenant vs KMS envelope por tenant (revogação real de chave + audit de uso — recomendado quando houver 2+ clínicas); e cifrar `wa_messages` um dia = decisão de arquitetura da timeline.
7. **J7 — Export:** minimizar JSON (allowlist de campos) e/ou restringir a role admin em tenant clínica (audit `CONTACTS_EXPORT` já entra sem decisão).
8. **J8 — Relatório art. 18:** consulta BigQuery documentada em `docs/compliance/` (recomendado começar) vs endpoint `GET /api/admin/lgpd/access-report` (ADR 0002).
9. **J9 — Sweep retroativo:** aprovar as 4 ações da FR — em especial reescrever `detail` de `WA_SEND` antigos (jurídico valida minimizar trilha existente, com `J3_RETRO_SCRUB` como registro; alternativa: export original cifrado pra cold storage antes) — e a data de execução.
10. **J10 — DPA Varizemed:** residência us-west1 (sem região BR no setup atual — aceitar e registrar, ou abrir projeto de migração southamerica-east1), PITR 7d, IndexedDB, subprocessadores (Google/Meta/Dialogflow), staging proibido pra dado real (política escrita).
11. **J11 — Tarefas fora do repo (donos e prazos como gate formal):** environment versionado do agente (sair do DRAFT) — ✅ **FEITO para `varizemed` desde 2026-07-31 (val-5.0; troca mais recente 2026-08-21, val-5.0.3)** (`scripts/set_cx_environment.py` + `docs/deploy/TROCAR_ENVIRONMENT_VAL.md`; `varizemed-test` segue no DRAFT) —, interaction logging/retention do Dialogflow + Cloud Logging do projeto do agente, TTL da ValMemory (`val-castrochat`, functions da clínica), limpeza de IndexedDB nas máquinas que atenderam varizemed.
12. **J12 — Colaterais MÉDIOS:** `wa_transfer_log`, `gc_messages`, `media_assets` — aceitar com registro no RIPD ou puxar alguma para o escopo J-3.
13. **J13 — Import do histórico clínico (D7):** só DEPOIS de F3+F5 prontos (cripto/TTL cobrindo o import) e com flag de revogado/recusado da base legada no script (senão o re-ask LGPD re-engaja quem já disse não). Confirmar sequência.

**Regra de ouro da integração:** os guards D8 (`lgpd_revoked` na hidratação e no `release_lead_to_bot`) entram no MESMO patch da Fase 2 do PLANO_MODELOS se ela for implementada antes da F1 — nunca depois do rollout clinic na Varizemed real. Sem commit/push sem pedido explícito (convenção do repo).
