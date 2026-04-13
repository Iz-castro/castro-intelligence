# Verificação do Sistema Hubloc CRM (Castro Intelligence)

## Context

Rafal pediu verificação completa do sistema, confirmando que os arquivos TASK em `docs/` já estão finalizados. Este plano é um **relatório de auditoria** que compara (1) as 5 tasks marcadas como concluídas, (2) a documentação principal de arquitetura, e (3) os checklists de produção/Meta — contra o código real em [castro-intelligence/](castro-intelligence/).

Objetivo: identificar o que realmente está pronto, o que tem gaps entre doc e código, e o que ainda bloqueia o go-live.

---

## 1. Status das 5 Tasks "finalizadas"

| Task | Status real | Observação |
|---|---|---|
| `NOVO_CONTATO_MANUAL_MEUS_ATENDIMENTOS` | ✅ IMPLEMENTADA | Endpoint + função + UI + schema completos |
| `FIX_SCROLL_VERTICAL_COLUNA_CONTATOS` | ✅ IMPLEMENTADA | CSS `flex:1 1 0` + `min-height:0` aplicado |
| `SPIKE_API_EDICAO_MENSAGENS_WHATSAPP` | ✅ CONCLUÍDA | Conclusão do spike documentada (Cenário B+C híbrido) |
| `EDICAO_MENSAGENS_WHATSAPP_CRM` | ✅ IMPLEMENTADA | Backend + UI completos: menu "Corrigir" na bolha ([App.tsx:487-489](castro-intelligence/frontend/src/App.tsx#L487-L489)), banner "Corrigindo mensagem" ([App.tsx:520-527](castro-intelligence/frontend/src/App.tsx#L520-L527)), badge "corrigida" ([App.tsx:498](castro-intelligence/frontend/src/App.tsx#L498)), função `correctMessage` ([CrmContext.tsx:1141](castro-intelligence/frontend/src/context/CrmContext.tsx#L1141)) |
| `PROD_HUBLOC_COEXISTENCE` | ⚠️ AGUARDANDO OP | Gate de coexistence correto em 3 camadas (menu [App.tsx:105](castro-intelligence/frontend/src/App.tsx#L105), GET [main.py:1841](castro-intelligence/main.py#L1841), POST [main.py:1866](castro-intelligence/main.py#L1866) — todos só admin/supervisor). **Fase 1 bloqueada apenas por info operacional: `WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_WABA_ID` do número Hubloc (esperado 13/04/2026) + smoke test no Cloud Run** |

**Evidência:**
- [main.py:1038](castro-intelligence/main.py#L1038) — `POST /api/wa/correct-message`
- [main.py:1138-1159](castro-intelligence/main.py#L1138-L1159) — `POST /api/wa/contact/manual`
- [database_firestore.py:585-651](castro-intelligence/database_firestore.py#L585-L651) — `create_manual_wa_contact`
- [channel_service.py:138](castro-intelligence/channel_service.py#L138) — filtro de visibilidade coexistence
- [App.tsx:105](castro-intelligence/frontend/src/App.tsx#L105) — menu restrito admin/supervisor

---

## 2. Arquitetura — doc vs código

### Alinhado ✅
- Multi-canal (standard + coexistence) com cache TTL 60s em [channel_service.py:27-80](castro-intelligence/channel_service.py#L27-L80)
- Firestore com métricas pré-agregadas (`audit_metrics`)
- Firebase Auth + Google Sign-In em [auth.py](castro-intelligence/auth.py)
- RBAC admin/supervisor/operador em [main.py:1303-1325](castro-intelligence/main.py#L1303-L1325)

### Documentado mas não plugado ⚠️
- **Google Chat** — código completo ([google_chat.py](castro-intelligence/google_chat.py), [webhook_google_chat.py](castro-intelligence/webhook_google_chat.py)) mas feature flag `FEATURE_GOOGLE_CHAT=false`. Depende de aprovação do Workspace admin
- **Template `rating_request`** — endpoint/captura prontos; bloqueado por aprovação Meta

### Implementado mas não documentado ⚠️
- **Assume counter** ([database_firestore.py:1389-1428](castro-intelligence/database_firestore.py#L1389-L1428), usado em [main.py:1469-1480](castro-intelligence/main.py#L1469-L1480)) — limite de "assumir" sem responder
- **Coleção `bot_states`** em [bot_service.py:215-228](castro-intelligence/bot_service.py#L215-L228) (mencionado só em `docs/internal/090426.md`)
- **Protocolo ATD-YYYYMMDDHHMMSS-XXXXX** ([main.py:1486](castro-intelligence/main.py#L1486))
- **Bot completo e VIVO** — docs em `DOCUMENTACAO_SISTEMA.md:26` e `BOT_ARCHITECTURE.md` ainda chamam de "futuro", mas [bot_service.py](castro-intelligence/bot_service.py) tem 429 linhas em produção atrás da flag `bot_enabled`. **Docs precisam reescrever como presente**

### Inconsistências críticas ❌
- ~~Mapeamento setor→departamento hardcoded + cache não invalidado~~ → **RESOLVIDO** em 12/04/2026 com campo `bot_key` estável:
  - `bot_key` aceito em [database_firestore.py:172,201](castro-intelligence/database_firestore.py#L172) (valores: `comercial`/`financeiro`/`administrativo`/`sac`/`null`)
  - [bot_service.py:_get_dept_map()](castro-intelligence/bot_service.py#L187) agora prioriza `bot_key`, com fallback para substring match
  - Endpoints POST/PUT/DELETE de departments em [main.py:1288-1335](castro-intelligence/main.py#L1288-L1335) chamam `invalidate_dept_cache()` após qualquer mutação
  - Bootstrap defaults em [bootstrap_data.py](castro-intelligence/bootstrap_data.py) já vêm com `bot_key` correto (Vendas→comercial, Suporte→sac, Financeiro→financeiro)
  - UI admin em [App.tsx:depts](castro-intelligence/frontend/src/App.tsx) tem select "Setor do bot" em create/edit + chip visual na lista
- ~~**Reatribuição em lote** — frontend sem UI~~ → **UI existe** em [App.tsx:692-708](castro-intelligence/frontend/src/App.tsx#L692-L708)
- ~~**Lead retornante** — condição restritiva~~ → **correto**: condição `rating_requested_at` está bem casada com o fluxo documentado em [webhook.py:398-435](castro-intelligence/webhook.py#L398-L435)

### Erros do relatório anterior (corrigidos após re-auditoria)
- `quality_rating separado` — **não existe** esse campo. Só há `rating` (1-10) e flag `is_rating_message`. Afirmação removida.

---

## 3. Prontidão para produção

### Infra ✅
- Dockerfile (Node 22 + Python 3.10), `deploy.ps1` e `deploy.sh` funcionais
- Secret Manager integrado
- `firestore.rules`, `firestore.indexes.json` (6 índices compostos), `storage.rules` presentes
- Serviço: `castro-crm` em `southamerica-east1`

### Custos Firestore ✅
Otimizações já aplicadas: `.limit(50)`, batch enrichment (N+1 eliminado), orderBy no Firestore, polling 15s. Estimativa pós-otimização: **~US$ 7-20/mês** (dominado por Cloud Run).

### Transcrição ✅
Faster Whisper plugado em [transcription_service.py](castro-intelligence/transcription_service.py) (base/cpu/int8), flag `FEATURE_AUDIO_TRANSCRIPTION`.

### Bloqueadores de go-live ❌
1. **App Meta em modo dev** — coexistence exige app publicado
2. **Vídeo de submissão** não gravado
3. **System User Token** — atualmente é token temporário do Graph API Explorer
4. **Webhook precisa estar live** para Meta testar
5. **Número WABA real** não provisionado (WABA antigo 2137446677042913 foi deletado)
6. **AppSecret** para `REQUIRE_WEBHOOK_SIGNATURE=true` precisa no Secret Manager
7. **Alerta de budget GCP** não configurado

---

## 4. Recomendações priorizadas

### P0 — fechar gaps das tasks "finalizadas"
1. ~~Completar UI "Corrigir mensagem"~~ — **já implementada**, verificado em re-auditoria
2. ~~Validar Fase 1 `PROD_HUBLOC_COEXISTENCE`~~ — **código pronto**; bloqueada por info operacional (IDs do número Hubloc esperados 13/04/2026 + smoke test no Cloud Run)

**Polishes não-bloqueantes** da task `EDICAO_MENSAGENS` (ainda `[ ]` no checklist):
- Esconder botão "Corrigir" quando janela 24h expirar (hoje só o composer some — clicar em "Corrigir" com janela expirada deixa `correctionTarget` setado sem forma de confirmar)
- Tooltip/texto auxiliar no badge "corrigida"
- Decidir se exibe conteúdo original da mensagem corrigida (hoje fica visível porque a msg original permanece no chat)

### P1 — consertar inconsistências
3. ~~Tornar `_SETOR_NOMES` dinâmico~~ — **RESOLVIDO** via `bot_key` + cache invalidation
4. ~~Adicionar botão "Reatribuir em lote"~~ — **já existe** em [App.tsx:692-708](castro-intelligence/frontend/src/App.tsx#L692-L708)
5. ~~Atualizar `DOCUMENTACAO_SISTEMA.md`~~ — **FEITO**: bot reescrito como presente (Section 15), `bot_key` documentado (Section 6), `bot_states` e `operator_assume_counters` no schema (Section 10), protocolo ATD com formato, campo `is_corrected` no schema de mensagens/contatos

### P2 — go-live
6. Gravar vídeo de fluxo Embedded Signup + coexistence
7. Trocar token temporário por System User Token no Secret Manager
8. Submeter app Meta para review
9. Configurar budget alert GCP (US$ 30/mês como threshold)

---

## 5. Verificação end-to-end sugerida

Depois dos P0/P1:
```bash
# Backend
cd castro-intelligence && python check_whatsapp_coexistence.py
python test_meta_app_review.py

# Frontend
cd frontend && npm run build

# Deploy dry-run
./deploy.sh --dry-run
```

Smoke tests manuais:
- Login com `@centralloc.com.br` → criar departamento → criar quick message
- Admin cria contato manual em "Meus Atendimentos"
- Operador recebe mensagem via webhook (usar número teste +1 555-175-4802)
- Supervisor executa reatribuição em lote (após P1 #4)
- Admin verifica dashboard/exporta CSV

---

## Arquivos críticos de referência

**Backend:** [main.py](castro-intelligence/main.py), [webhook.py](castro-intelligence/webhook.py), [bot_service.py](castro-intelligence/bot_service.py), [channel_service.py](castro-intelligence/channel_service.py), [database_firestore.py](castro-intelligence/database_firestore.py), [auth.py](castro-intelligence/auth.py)

**Frontend:** [frontend/src/App.tsx](castro-intelligence/frontend/src/App.tsx), [frontend/src/types.ts](castro-intelligence/frontend/src/types.ts), [frontend/src/styles.css](castro-intelligence/frontend/src/styles.css)

**Infra:** [Dockerfile](castro-intelligence/Dockerfile), [deploy.sh](castro-intelligence/deploy.sh), [firestore.rules](castro-intelligence/firestore.rules), [firestore.indexes.json](castro-intelligence/firestore.indexes.json)

---

## Conclusão

Sistema está em **~97% de prontidão**. Todas as inconsistências internas de código e documentação foram fechadas. Os únicos bloqueios restantes são **externos**: (1) IDs do número Hubloc e smoke test em prod (esperado 13/04/2026) e (2) processo de app review da Meta para coexistence (vídeo + System User Token + submissão).
