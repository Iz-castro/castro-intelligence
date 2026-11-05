# ADR 0015 — Funil comercial: etapa no contato (`crm_stage`), histórico em `crm_activities`

**Data:** 2026-10-25 (emenda em 2026-10-28) · **Status:** aceito pelo PO com a emenda de 28/10
(implementação local atrás de `FEATURE_FUNNEL=false` e habilitação por tenant) · **Plano:**
[`docs/funil_crm_varizemed.md`](../funil_crm_varizemed.md).

## Contexto

O follow-up F1 resolve "o que fazer agora" por contato, mas a gestão da Varizemed precisa ver "onde
cada contato está na jornada" e "como a operação está performando" sem abrir lead por lead (reunião
de 21/10). O código não tinha etapa comercial; `qualification` é um enum operacional global, gate da
reabertura e do fechamento, com nomes que colidem com as etapas propostas; a temperatura da IA já
existe como `lead_temperature`.

## Decisão

1. **Nova fase.** O funil (Kanban + painel gerencial) entra agora; isso emenda o §2 do plano do
   follow-up, que excluía Kanban e "nova classificação de lead" da F1.
2. **Etapa = dimensão comercial apenas**, em campos planos de `wa_contacts` (`crm_stage*`,
   `crm_funnel_entered_at`, `crm_cohort_month`, `crm_max_reached_order`), escritos só pelo backend.
   Substitui a hipótese `commercial_status` do plano do follow-up; `relationship_status` /
   `relationship_reason` continuam separados e futuros. Uma etapa por contato (Opportunity futura).
3. **Histórico append-only em `crm_activities`** (`crm_stage_changed`, `crm_stage_reason_changed`,
   `crm_stage_migrated`, `crm_stage_migration_reverted`, `task_id=None`), com campos de topo para
   métricas (`from_stage`, `to_stage`, `stage_reason`, `from_reason`, `entry_kind`). O **motivo não
   fica no contato** (o doc é legível via SDK pela pool e a categoria pode ser dado de saúde); o
   contato aponta a Activity vigente. A rota de atividades do follow-up deixa de devolver esses
   eventos.
4. **Independência:** a etapa nunca escreve `qualification`, bot, dono, tags, LGPD, opt-out, recusa
   comercial, threads ou mensagens, nem cria/conclui tarefa; e nenhum desses fluxos move a etapa.
5. **Movimento manual** com permissão (`mover_etapa_funil`; Convertido também
   `confirmar_conversao_funil`), concorrência otimista por `crm_stage_version` e recibo idempotente.
   **Emenda à Decisão 5 do follow-up:** "Agendado" passa a existir como etapa do funil, só por ação
   humana; o resultado `scheduled` da tarefa e o `bot_outcome` da Val continuam sem mover nada
   (no máximo sugestão de um clique).
6. **Única automação: entrada no funil** na 1ª mensagem ao vivo do cliente (canal `standard`), na
   criação manual e na graduação de backup, no mesmo write existente (zero escrita extra no
   webhook), com a habilitação decidida uma vez por payload. Paciente que já conversava entra em
   "A classificar". Exceção explícita ao "movimento manual inicialmente": sem ela, contato novo
   sumiria do Kanban.
7. **Catálogo por tenant** por template em `tenants/{tid}.settings.funnel` (sem `if tenant`); chaves
   estáveis, desativar em vez de remover; config ausente = funil desligado.
8. **Migração mínima**: só regras determinísticas (`recent_untouched`; `open_human` e
   `reopen_opt_out` opt-in após dry-run); **reafirma** a decisão anterior de não mapear `convertido`,
   `nao_convertido`, arquivo ou fechamento automaticamente; recusa comercial não vira "Não
   convertido" (Decisão 6); o resto vai para "A classificar".
9. "Parado" é sinal derivado por etapa, nunca etapa nem campo persistido.

## Alternativas consideradas

- **Derivar etapas de `qualification`/thread:** rejeitada — `em_atendimento` é gravado sem humano,
  `convertido` não significa pagamento e os ciclos de bot resetam estados.
- **Coleção própria de funil por contato:** rejeitada — exigiria denormalizar dono/escopo (risco nas
  3 camadas de isolamento LGPD) e seria uma entidade Lead paralela.
- **Etapa em `wa_conversations`:** rejeitada — uma thread por canal; a jornada é do paciente.
- **Motivo no contato:** rejeitada — exposição via SDK de categoria de saúde à pool.
- **Intake com Activity no webhook:** rejeitada — escrita extra antes do ACK da Meta.
- **Métricas só por eventos:** insuficiente para a pirâmide; adotadas coortes por
  `crm_cohort_month` + maior etapa alcançada.

## Emenda de 28/10/2026 (decisões do PO)

1. **Etapas da Varizemed** (template `clinic_v1`): Novo contato (conversando com a Val, 1ª
   interação) → Em atendimento (na recepção) → Aguardando retorno → **Cliente Agendado** (marcou
   consulta) → **Paciente em acompanhamento** (fez tratamento e deve voltar); Não convertido (com
   motivo), **Não qualificado** (spam, golpe) e A classificar. Saem Compareceu e Convertido (pago).
   **Conversão = marcar consulta** (substitui "pagamento confirmado no ProDoctor" no funil). Quem
   agenda pelo link da Val é confirmado pela equipe quando chega à clínica (selo + sugestão de um
   clique).
2. **Automações por evento explícito** (substitui o item 6 original, que só tinha a entrada): o
   handoff da Val e a 1ª resposta humana pelo CRM levam a Em atendimento, só a partir de Novo
   contato/A classificar, no mesmo write existente, com Activity de sistema gravada à parte
   (best-effort). Criação manual pela equipe entra direto em Em atendimento. Nunca regridem etapa.
3. **Uma classificação só** (substitui o item 4 original): o modal "Encerrar atendimento" passa a
   escolher a etapa do funil, e **toda mudança manual de etapa grava também o desfecho legado
   equivalente** em `qualification` (Cliente Agendado/Paciente → convertido; Não convertido/Aguardando
   retorno → nao_convertido; Não qualificado → nao_qualificado; Em atendimento → em_atendimento), para
   a reabertura em lote, as caixas e o gate do fechamento continuarem coerentes. Automações, entrada
   automática e migração não escrevem `qualification`. "Qualificado" deixa de ser oferecido na
   Varizemed; a Hub Loc segue com o fluxo legado.
4. **Migração** (substitui o item 8 original quanto aos desfechos): aproveita desfechos antigos,
   exceto Qualificado — convertido → Cliente Agendado; nao_convertido → Não convertido (motivo não
   registrado); nao_qualificado → Não qualificado; qualificado → A classificar. A decisão anterior de
   não mapear desfechos foi tomada quando "convertido" do funil significava pagamento; com conversão =
   marcar consulta, o mapeamento passa a ser semanticamente correto. `open_human` vira `in_reception`
   (atendimento aberto com mensagem real recente → Em atendimento), ligada por padrão e com precedência
   sobre o desfecho antigo (o relatório mostra os conflitos); `reopen_opt_out` segue opt-in.
5. **Nomes e textos editáveis pela clínica** (tela "Etapas", permissão `gerenciar_config_sistema`,
   doc `system_settings/funnel`); chaves continuam estáveis.
6. **RBAC:** sai `confirmar_conversao_funil`; entra `ver_contatos_agente_funil` (coluna Novo contato),
   desligada para operadoras.

## Ajustes de 05/11/2026 (revisão depois da integração com o `develop`)

1. **Paciente que volta:** o encerramento volta a exigir o desfecho também quando a etapa atual é
   aberta ou perdida (Aguardando retorno, Não convertido), coberto pela permissão de fechar; ganho e
   Não qualificado seguem fechando direto (trocar exige `mover_etapa_funil`).
2. **Desfechos para quem fecha:** `GET /api/funnel/config` aceita `ver_funil` OU
   `fechar_atendimento_manual`; as demais rotas seguem exigindo `ver_funil`. Sem isso, perfil que
   fecha sem ver o funil gravava só o legado.
3. **Corrida automação × mudança manual** (merge sem precondição no caminho quente): aceita como
   resíduo documentado (plano, seção 9). A Activity de automação passa a ter id por contato + versão
   de origem (sem o evento): handoff e 1ª resposta simultâneos contam 1 movimento.
4. As tarefas no card seguem o follow-up ligado **por tenant** (`tenant_followup_enabled`, do
   `develop`).

## Consequências

- 12 índices compostos novos (publicar READY antes de ligar).
- Operadores veem no quadro só o próprio escopo + pool; a coluna Novo contato (pool em fase de
  bot) só aparece com `ver_contatos_agente_funil`, desligada no seed do operador (emenda, item 6;
  resolve a decisão pendente 13).
- Scripts legados que regravam/copiam contatos (`_dedupe_contacts.py`, export/import de anotações)
  precisam incluir `crm_*` antes de qualquer uso.
- A Hub Loc fica desligada até ter template próprio; as chaves de RBAC do funil ficam ocultas no
  editor de perfis de tenant sem funil.
