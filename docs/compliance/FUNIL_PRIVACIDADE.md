# Funil comercial: dados gravados e pedidos de privacidade

O funil comercial (ADR 0015) acrescenta dados operacionais ao contato existente e
eventos à coleção existente `tenants/{tenant_id}/crm_activities` (prefixo real de
`FIRESTORE_COLLECTION_PREFIX`). Não há coleção nova nem cópia de conversa,
transcrição, planilha ou dado clínico.

**No contato (`wa_contacts`)**, legível por quem já acessa o contato (inclusive via
SDK, conforme as rules atuais): `crm_stage` (etapa), `crm_stage_version`,
`crm_stage_changed_at`, `crm_stage_source`, `crm_stage_activity_id` (ponteiro),
`crm_stage_changed_by_user_id`/`_uid`, `crm_funnel_entered_at`, `crm_cohort_month`
e `crm_max_reached_order`; numa mudança manual de etapa, também o desfecho legado equivalente em
`qualification` (que já existia). O **motivo de não conversão não fica no contato**: uma
categoria como "Indicação médica" pode revelar dado de saúde e o doc do contato é
lido pela pool da recepção.

**Nos eventos `crm_stage_*` de `crm_activities`** (sem acesso pelo SDK do navegador
em produção ou staging): etapa de origem/destino, motivo (categoria do catálogo),
autor, data e, só no motivo "Outro", um texto curto (≤120 caracteres) com o aviso
na tela "não registre dados clínicos". A nota livre só é devolvida a gestores com
visão do tenant e ao próprio autor. A rota de atividades do follow-up não devolve
esses eventos; eles saem só pela API do funil, com a permissão `ver_funil`.

O arquivamento do contato não apaga etapa nem histórico. Não há rotina de
eliminação física: um pedido de privacidade segue o mesmo processo descrito em
[`FOLLOWUP_PRIVACIDADE.md`](FOLLOWUP_PRIVACIDADE.md) — validar identidade,
finalidade e autorização da clínica; para correção ou eliminação, abranger pelo
`tenant_id` e `contact_id` exatos os campos `crm_*` do contato **e todos** os
eventos `crm_stage_*` (inclusive os de migração e de undo), além das tarefas e
atividades do follow-up. Não deixar eventos órfãos nem reproduzir o conteúdo
removido.

Acesso/portabilidade autorizados: `GET /api/funnel/contacts/ID` e
`GET /api/funnel/contacts/ID/history` (seguir `next_cursor` até o fim), por usuário
com visão do tenant. O acesso depende de `FEATURE_FUNNEL`, da habilitação do tenant
e das permissões; com o funil desligado, os dados continuam no Firestore e o
processo administrativo usa o mesmo recorte.

O funil **não** envia mensagens, não altera consentimento LGPD, opt-out ou recusa
comercial, e não amplia acesso: quem vê o card já podia ver o contato. A RoPA da
clínica deve citar o funil como organização interna do atendimento comercial
(finalidade, categorias de motivo e quem acessa) antes da habilitação em produção.
