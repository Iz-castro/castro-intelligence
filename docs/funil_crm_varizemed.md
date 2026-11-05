# Funil comercial no Castro Intelligence CRM — proposta e entrega (Varizemed)

**Revisão:** 25/10/2026, atualizada em 28/10 com as decisões do PO (seção 10 e emenda do ADR 0015).
**Frente:** `feature/funil`, worktree próprio, a partir de `develop` (1ff4005).
**Status:** proposta revisada (5 revisões adversariais) e implementação **local** atrás de
`FEATURE_FUNNEL=false` + habilitação por tenant. Sem push, deploy, índice publicado ou escrita em
produção. Entrega, testes e cobertura dos 24 critérios na seção 14. Decisão registrada no
[ADR 0015](decisions/0015-funil-comercial-crm-stage.md).
**Fontes:** pedido do PO de 25/10 (funil integrado ao follow-up); reunião com Cristina de 21/10
(anotações do Gemini, sem PII reproduzida); [plano do follow-up](followup_crm_varizemed.md)
(seções 3, 5, 7, 8 e 16); ADRs 0003 e 0008–0014; código deste worktree; análise do CSV comercial já
registrada no plano do follow-up (§4 — o CSV original não está no worktree e não foi relido).

Marcadores: **[OBSERVADO NO CÓDIGO]**, **[DECISÃO DO PO]**, **[PEDIDO DE CRISTINA — 21/10]**,
**[HIPÓTESE]** (desenho adotado, sujeito a validação) e **[DECISÃO PENDENTE n]** (seção 10).

> Regra principal (PO): **Follow-up** responde "o que fazer agora"; **Funil** responde "onde o
> contato está na jornada"; **Dashboard** responde "como a operação está performando".

**[PEDIDO DE CRISTINA — 21/10]** Em resumo: ver de longe "quem entrou, quem está sendo atendido,
quem parou, quem agendou, quem encerrou sem agendar e por quê", em colunas por categoria, sem
clicar lead por lead; pirâmide invertida (oi → aceitou o termo → continuou → agendou → veio →
pagou); comparar o mês com o anterior; pacientes antigos também fazem parte do CRM; quem "não
quer mais" vai para uma caixa de não convertidos, sem sumir.

---

## 1. O que o código tem hoje (revisão)

| Fato **[OBSERVADO NO CÓDIGO]** | Onde | Consequência para o funil |
|---|---|---|
| Não existe etapa comercial, Kanban nem `crm_stage`. "funil" no código é o fluxo do bot | busca em py/ts/tsx/rules/json | Nome técnico `crm_stage`; na UI, "Funil comercial" |
| FRIO/MORNO/QUENTE da IA é **`lead_temperature`** (+ `lead_temperature_at`), calculada no handoff do CX | `lead_temperature.py`, `bot_service.py` | Reutilizada e só exibida ("não informada" se ausente). Nenhum campo de temperatura novo |
| `qualification` é **outro** enum, global: `novo`, `em_atendimento`, `qualificado`, `nao_qualificado`, `convertido`, `nao_convertido` | `config.py` | Colide em nome com 4 das 7 etapas propostas (seção 3) |
| `qualification` é **gate**: público da reabertura em lote, gate do fechamento, caixas Bot/Novos/NQ, aviso de espera, reroute legado | `database_firestore.py`, `main.py`, `CrmContext.tsx` | Na Varizemed, a mudança manual de etapa grava o desfecho legado equivalente para esses gates seguirem coerentes (emenda de 28/10); nenhum fluxo legado move a etapa |
| `em_atendimento` é gravado sem humano (auto-assign coex, inclusive agenda; "novo contato" do picker) e `return_contact_to_bot` volta tudo para `novo` | `database_firestore.py` | Não serve para derivar etapa |
| O ciclo do atendimento vive na **thread**; em `reception` todo fechamento chama `release_lead_to_bot`, que zera `bot_outcome` | `database_firestore.py`, ADR 0010 | Etapa independente desses ciclos; `bot_outcome` vale por ciclo (só sugestão) |
| Todo write de runtime em `wa_contacts` é `set(..., merge=True)`; só as 3 criações (e `_dedupe_contacts.py`) fazem `set` completo | varredura do repo | Campos novos no contato não são sobrescritos por fluxos existentes |
| Query com igualdade/orderBy não retorna doc sem o campo (lição do `is_backup` no picker v2.1) | picker v2.1 | Todo contato do funil precisa nascer com a etapa ou receber backfill |
| O picker v2.1 pagina contatos no servidor com escopo LGPD (`is_archived==0`, `is_backup==False`, operador `assigned_to_uid in [uid, ""]`) | `picker_contacts_query` | Mesmo escopo nas colunas do Kanban |
| F1 do follow-up: `crm_tasks` + `crm_activities` (append-only, REST-only nas rules), versão + `operation_id` + recibo + guards na transação | `followup_*.py`, `firestore.rules` | Histórico de etapa vai para `crm_activities` (sem coleção nova) |
| `/api/wa/conversation/open` materializa thread, grava recência, pode auto-atribuir e chama `mark_human_active` (cala a Val) | `main.py` | O funil **nunca** usa esse caminho |
| Não há fonte de agenda, comparecimento ou pagamento no código (ProDoctor é externo) | busca | Cliente Agendado e Paciente em acompanhamento são **manuais** (encerramento ou quadro) |
| O doc do contato é legível via SDK por todo o escopo (na recepção, quase toda a pool) | `firestore.rules` | O **motivo** de não conversão não fica no contato (pode ser dado de saúde) |
| O Monitor (porte do painel da Hub Loc) só existe para `hubloc` e lê mensagens (~31 mil docs/30 dias) | `monitor_service.py` | O painel do funil não varre mensagens: `count()` e coortes |
| `FEATURE_FOLLOWUP` e seeds de RBAC são globais | `config.py`, `rbac.py` | Flag global **e** habilitação por tenant |

## 2. Onde a etapa é persistida

**[HIPÓTESE → implementado]** Campos **planos** no próprio contato (`wa_contacts`). Não existe
entidade Lead nova nem coleção de funil.

| Campo | Semântica |
|---|---|
| `crm_stage` | Chave estável da etapa atual (catálogo do tenant) |
| `crm_stage_version` | Concorrência otimista **só da etapa** (as escritas do webhook no contato não geram conflito falso) |
| `crm_stage_changed_at` | Entrada na etapa atual (datetime UTC, nunca nulo nem string). Na migração = última mensagem do paciente |
| `crm_stage_source` | `user`, `intake` (entrada automática), `graduation` (backup graduado), `migration`, `rule:handoff` / `rule:human_reply` (automações da seção 11) |
| `crm_stage_activity_id` | Ponteiro para a Activity que definiu a etapa/motivo atual (o motivo **não** fica no contato) |
| `crm_stage_changed_by_user_id` / `_uid` | Autor humano da última mudança |
| `crm_funnel_entered_at` + `crm_cohort_month` | 1ª entrada no funil e o mês (fuso da clínica) — gravados uma vez; base das coortes |
| `crm_max_reached_order` | Maior etapa de funil já alcançada (monotônica) — base da pirâmide "alcançou ≥ etapa" |

Por que no contato: a jornada é do paciente (um contato tem uma thread por canal); o escopo LGPD
do operador já é expresso e indexado em campos do contato; coleção própria exigiria denormalizar
dono/escopo e seria uma "entidade Lead paralela". Campos planos evitam que o merge profundo deixe
subchaves velhas.

**Histórico** em `crm_activities` (mesma coleção do follow-up, `task_id=None`):

| `event_type` | Quando | Conta em "movimentos do mês"? |
|---|---|---|
| `crm_stage_changed` | Mudança manual (quadro, cartão ou encerramento, este com `data.via=close`) e automações por evento (`actor_type=system`) | Sim, exceto `entry_kind=triage` (classificação de antigos, mostrada à parte) |
| `crm_stage_reason_changed` | Correção do motivo sem mudar de etapa | Não; corrige o motivo da entrada original (`corrects_entry_id`/`corrects_month`) |
| `crm_stage_migrated` | Classificação inicial pelo script de migração | Não |
| `crm_stage_migration_reverted` | Undo do script | Não |

Campos de topo indexáveis: `from_stage`, `to_stage`, `stage_reason`, `from_reason`, `entry_kind`
(`move`, `triage`, `reactivation`). `data` controlado: `reason_note` (só "Outro", ≤120 caracteres),
`appointment_kind` (consulta/procedimento, opcional em Cliente Agendado), `stage_version`, `source`,
`suggested_by`, `legacy_qualification` (desfecho legado gravado junto) e `via`. O evento é o próprio recibo idempotente (`stage_<sha256(tenant|stage|uid|contato|op)>`).
Nenhum conteúdo de mensagem, nota clínica, nome ou telefone. O histórico de etapa **não** sai pela
rota de atividades do follow-up (que passou a filtrá-lo): só pela rota do funil, com `ver_funil`.

**Entrada automática ("intake")** — necessária para que nenhum contato novo suma do Kanban
(critério 20; as demais automações estão na seção 11). Zero escrita extra: os campos vão no write
que o código já faz.
- O webhook decide a habilitação **uma vez por payload** (cache do tenant, mesmo bloco protegido do
  buffer) e passa o catálogo explicitamente ao `upsert_wa_contact`; nada é lido por mensagem.
- Só mensagem **ao vivo do cliente** em canal `standard` (configurável): agenda (`state_sync`),
  histórico importado, eco do celular do dono, clique de controle, reação, mensagem de sistema,
  backup, `lgpd_revoked` e canal de outro tenant **não** entram. Mídia que a Cloud API não
  interpreta (`unsupported`, `ephemeral`/visualização única) e a abertura do chat
  (`request_welcome`, se a mensagem de boas-vindas da Meta for ligada) **contam** como entrada.
- Contato **novo** (ou da agenda, sem conversa anterior) → **Novo contato**; entrada e coorte com a
  hora real da mensagem (reprocessamento de pending não vira entrada de hoje) e
  `crm_stage_changed_at` no mesmo instante de `last_inbound_at` (o selo "mensagem nova" não acende
  com a própria mensagem de entrada). Contato que **já conversava** antes (há `last_inbound_at`
  anterior) → **A classificar**: paciente antigo não conta como lead novo do mês.
- Criação manual pela equipe → **Em atendimento** (a equipe iniciou a conversa); backup graduado
  (reatribuição do lead ou transferência com "levar o lead", inclusive de thread viva de contato
  ainda backup) → A classificar.
- Etapa existente nunca é sobrescrita; exceção no cálculo = sem etapa (o script recupera depois).
- Sem Activity nesse caminho (seria escrita antes do ACK da Meta): o histórico mostra a entrada a
  partir de `crm_funnel_entered_at` (item sintético).
- Resíduo aceito: se a 1ª coisa que um contato sem conversa anterior manda é uma **reação** ou
  mensagem de sistema, `last_inbound_at` já fica gravado e o 1º texto dele entra em A classificar
  (raro; a equipe move).

## 3. Conflitos com estados atuais e como foram resolvidos

| Proposta | Conflito | Resolução |
|---|---|---|
| "qualification FRIO/MORNO/QUENTE" | É `lead_temperature` no código | Reuso só para exibir |
| NEW "Novo" | `qualification=novo` no filtro do chat | **[DECISÃO DO PO — 28/10]** "Novo contato" = conversando com a Val, 1ª interação |
| IN_SERVICE "Em atendimento" | `qualification=em_atendimento` | **[DECISÃO DO PO — 28/10]** "Em atendimento" = na recepção (handoff); entra sozinho no handoff ou na 1ª resposta humana |
| Qualificado + Convertido | `qualification=convertido` = "consulta marcada"; Ganho = pagamento (Cristina, 08/10) | **[DECISÃO DO PO — 28/10]** juntam em **"Cliente Agendado"** = marcou consulta, a conversão do funil |
| Paciente que volta | Não havia etapa | **[DECISÃO DO PO — 28/10]** **"Paciente em acompanhamento"** (fez tratamento e deve voltar) |
| Spam/número errado | Distorceria "encerram sem agendar" | **[DECISÃO DO PO — 28/10]** **"Não qualificado"**, fora das métricas de conversão |
| NON_CONVERTED "Não convertido" | `qualification=nao_convertido` | Mantido, com motivo obrigatório |
| AWAITING_FOLLOWUP | Pode duplicar "tem tarefa pendente" | **[DECISÃO DO PO — 28/10]** mantida; o "parado" vem da tarefa |
| SCHEDULED / ATTENDED / CONVERTED (pago) | Sem fonte de comparecimento/pagamento | **[DECISÃO DO PO — 28/10]** saem; Cliente Agendado cobre a conversão |
| Duas classificações (desfecho + etapa) | Operadora classificaria duas vezes | **[DECISÃO DO PO — 28/10]** uma classificação só: o encerramento escolhe a etapa e toda mudança manual grava o desfecho legado equivalente |
| "Parado" | Já há 3 noções de espera | Sinal derivado por etapa (seção 4), nunca etapa |
| "Classificar não convertidos" (reunião) | Encerrar não prova desinteresse (46 de 71 tinham conversa de agendamento); recusa comercial ≠ não conversão (Decisão 6) | Migração com regras determinísticas e desfechos antigos (seção 8) |
| F1 do follow-up excluía Kanban e "nova classificação de lead" | Mudança de fase | Registrada no ADR 0015 |

Independência: mover etapa **não** escreve `bot_completed`, `human_active`, dono, `sale_owner`,
tags, `reopen_*`, `lgpd_*`, `commercial_contact_block`, threads ou mensagens; não envia WhatsApp; não
cria, conclui nem cancela tarefa. **A única escrita fora de `crm_*` é o desfecho legado
(`qualification`)**, e só em mudança MANUAL de etapa (quadro, cartão ou modal de encerrar), para a
reabertura em lote, as caixas e o gate do fechamento continuarem coerentes. Entrada automática,
automações e migração nunca escrevem `qualification`. `release_lead_to_bot`, `return_contact_to_bot`
e crons não tocam a etapa.

## 4. Modelo mínimo

**Catálogo por tenant, sem `if tenant`.** `funnel_catalog.py` (módulo puro) guarda templates de
etapas e motivos; chaves reservadas `new` (entrada) e `unclassified` (triagem). O tenant aponta o
template em `tenants/{tid}.settings.funnel` (mesmo doc e cache de `settings.ai`; o super-admin não
edita `settings`), com etapas/motivos inativos, limiares e tipos de canal da entrada automática
(Castro, por `scripts/set_tenant_funnel.py`). **Nomes e textos explicativos** das etapas e motivos
a clínica edita na tela "Etapas" do funil (permissão `gerenciar_config_sistema`, doc tenant-scoped
`system_settings/funnel`, com versão). Sem config habilitada = funil desligado (404).

Template `clinic_v1` **[DECISÃO DO PO — 28/10]** (nomes e textos renomeáveis sem migração):

| Ordem | Chave | Rótulo | Tipo | Como entra | Desfecho legado gravado | "Parado" |
|---|---|---|---|---|---|---|
| 10 | `new` | Novo contato | aberto (entrada) | sozinho, 1ª mensagem (conversando com a Val) | — | paciente sem escrever há 1 dia |
| 20 | `in_service` | Em atendimento | aberto | sozinho no handoff ou na 1ª resposta humana; contato criado pela equipe | em_atendimento (só manual) | paciente sem escrever há 2 dias |
| 30 | `awaiting_followup` | Aguardando retorno | aberto | manual / encerramento | nao_convertido | tarefa atrasada ou sem próxima ação |
| 40 | `scheduled` | Cliente Agendado | ganho (conversão) | manual / encerramento; link da Val confirmado na chegada | convertido | — |
| 50 | `loyal` | Paciente em acompanhamento | ganho | manual / encerramento | convertido | — |
| 60 | `non_converted` | Não convertido | perdido, **exige motivo** | manual / encerramento | nao_convertido | — |
| 70 | `disqualified` | Não qualificado | excluído | manual / encerramento | nao_qualificado | — |
| 90 | `unclassified` | A classificar | triagem (não é destino manual) | só antigos; vai sozinho para Em atendimento ao passar pela recepção | — | — |

A coluna Novo contato só aparece para quem tem `ver_contatos_agente_funil` (desligada para
operadoras): elas veem o que já chegou à recepção.

Motivos (`non_converted`): Não aceitou a proposta · Convênio não aceito · Preço · Distância ·
Questão financeira · Sem interesse · Sem resposta (decisão da equipe, nunca por silêncio) · Adiou
(sem data; com retorno combinado, use Aguardando retorno) · Não compareceu · Indicação médica (só a
categoria) · Outro (texto curto ≤120, só no histórico, com o aviso "não registre dados clínicos") ·
Motivo não registrado (só migração). As tags (Preço, Distância…) continuam como anotação livre; o
motivo é o dado oficial do relatório.

Selos derivados no card (nunca persistidos): *parado* (regra da etapa), *tarefa atrasada*,
*sem próxima ação*, *com a Val*, *sem aceite LGPD* (tenant com aviso no CRM), *recusa comercial*,
*Val: agendou/enviou link* (de `bot_outcome`, só sugestão) e *mensagem nova do paciente* em etapas
fechadas/triagem.

Relações:
```
wa_contacts ── crm_stage* (etapa atual)          lead_temperature (IA, só exibida)
     │                                            qualification (legado, espelha a etapa em mudança manual)
     ├── crm_activities crm_stage_* (histórico; motivo e nota livre só aqui)
     ├── crm_tasks + crm_activities task_* (follow-up, independente)
     └── wa_conversations → wa_messages (comunicação)
```

- **Funil × tarefas:** independentes. O card mostra a próxima tarefa pendente acessível (só para
  quem tem o follow-up) e o atraso.
- **Reativação:** sair de Não convertido/Não qualificado gera Activity `entry_kind=reactivation` com
  `from_stage`/`from_reason`; o motivo anterior permanece no histórico e no mês em que ocorreu.
- **Cliente Agendado e Paciente em acompanhamento não são terminais:** podem voltar a Em
  atendimento/Aguardando retorno (revisão anual, novo orçamento), sempre com Activity; a "maior etapa
  alcançada" não regride e as automações nunca os rebaixam.
- **`relationship_status`** (ativo/pausado/encerrado) continua futuro e separado; nada no modelo o
  impede. Não se deduz pausa de "Adiou".
- **Opportunity/Quote** continua futura. Limitação aceita: **uma etapa por contato**; quando houver
  Opportunity, ela terá etapa própria (mesmo catálogo) e a do contato representará o relacionamento
  ativo; as Activities ganham `opportunity_id` opcional sem reconstruir histórico.

## 5. APIs (`/api/funnel`, REST; o cliente nunca escreve direto)

Toda rota: `FEATURE_FUNNEL` → 404; claim de tenant = contexto; usuário relido (ativo, uid,
tenant); sessão "Ver como"/somente leitura → 403 (além do bloqueio do middleware); funil habilitado
no tenant → senão 404; `ver_funil`; tenant explícito em toda leitura; `no-store` por prefixo no
middleware (inclusive nos erros); limite de taxa por usuário nos GETs do quadro. Erros com
`{"detail": {"code", "message"}}`.

| Rota | Função |
|---|---|
| `GET /config` | Catálogo resolvido com os textos da clínica (todas as etapas, com `visibility_permission`/`visible`) + capacidades (`can_move`, `can_dashboard`, `can_configure`, `can_see_agent_contacts`, `privileged`, `followup`) |
| `GET /board?order=&owner_id=&mine=` | Colunas: total (`count()`), parados, 1ª página (20 cards) e cursor; etapa invisível ao usuário fica de fora, sem nenhuma consulta |
| `GET /stages/{stage}/cards?cursor=…` | Próximas páginas (cursor HMAC por valores, TTL 1 h); etapa invisível → 404 `unknown_stage` |
| `GET /contacts/{id}` | Drawer só-leitura: resumo, etapa, motivo, histórico, próximas tarefas, sugestões |
| `GET /contacts/{id}/stage` | Revalidação leve do drawer: etapa, versão e se ainda pode mover |
| `GET /contacts/{id}/history`, `/context`, `/messages` | Histórico paginado; conversas e mensagens autorizadas por thread (mesmo contrato do contexto do follow-up) |
| `POST /contacts/{id}/stage` | `{to_stage, expected_version, reason?, reason_note?, appointment_kind?, operation_id, suggested_by?}` |
| `GET /dashboard?month=AAAA-MM` | Painel gerencial (seção 6), cache de 2 min |
| `GET /settings`, `PUT /settings` | Textos da clínica (tela "Etapas"): nomes de etapas e motivos e textos explicativos; exige `gerenciar_config_sistema`; `PUT {version, stage_labels?, stage_descriptions?, reason_labels?}` com versão (409 `stale_version`), mapa enviado substitui o salvo e texto vazio volta ao padrão; cache de 30 s invalidado no PUT |

Escopo: privilegiado (`can_see_all_tenant`) vê o tenant; operador vê próprios + pool sem dono,
com `_require_contact_access` por linha; backup e arquivado ficam fora. **Mover exige** dono, pool
ou privilégio: quem acessa só por thread própria em outro canal (coex) vê a etapa, não move.
Card com lista branca de campos (sem notas, tags, telefone ou LGPD); contato sem nome aparece como
"Contato sem nome (final NNNN)". Erros de parâmetro também saem com `code` e sem eco do valor. A
próxima tarefa só aparece para quem tem o follow-up; se o lote de tarefas foi cortado e a tarefa de
um contato ficou incerta, o card sai sem selo de tarefa (`tasks_visible=false`) em vez de afirmar
"sem próxima ação".

**Mudança de etapa (transação):** recibo (replay idempotente; mesmo `operation_id` em outro
contato/payload → 409), contato, usuário, guards de acesso (com a normalização de UID legado do
follow-up), versão (`stale_version` → 409 com quem moveu e para onde) e a Activity apontada (motivo
atual). Grava `crm_*` no contato + a Activity no mesmo commit. Valida etapa/motivo/nota pelo
catálogo. Com `legacy_qualification_sync` (Varizemed), o mesmo merge grava o desfecho legado
equivalente (`qualification`; `converted_by_user_id` quando vira convertido), decidido sobre o doc lido
na transação; a Activity registra `data.legacy_qualification` e a auditoria `CONTACT_QUALIFY`
"(via funil)" só sai quando o legado muda.

**Encerramento (uma classificação só):** `POST /api/wa/conversation/{id}/set-attendance` aceita
`funnel = {to_stage, expected_version, reason, reason_note, appointment_kind, operation_id}` só com
`status=fechado_manual`; `to_stage` precisa ser desfecho de encerramento (`close_outcome`, senão 422
`stage_not_allowed`). A mudança passa pelo mesmo código do quadro (versão, recibo, Activity com
`data.via=close`, legado) ANTES de qualquer escrita do fechamento: 403/409/422 abortam sem fechar,
sem escrever e sem mensagem. Desfecho igual à etapa atual só sincroniza o legado. Se o contato ainda
não tem desfecho (etapa fora dos desfechos ou legado novo/em_atendimento), o toggle de fechar basta;
trocar um desfecho já registrado exige `mover_etapa_funil`, e o gate é rechecado dentro da transação
(409 `context_changed` se mudou). Backup ou arquivado: só o legado, pelo caminho antigo. Funil
desligado depois de a tela carregar → 409 `funnel_disabled` (não fecha). Sem `funnel` no corpo (Hub
Loc, front antigo) o fechamento legado fica intacto; a resposta ganha `funnel.stage`.

## 6. Telas

- **Entrada:** botão "Funil" na barra superior, só com flag + funil do tenant (`/api/session`) +
  `ver_funil`, fora do "Ver como" (nenhuma requisição é feita quando indisponível).
- **Quadro:** colunas na ordem do catálogo com total, "N parados" e etapas inativas que ainda têm
  contatos; cards com nome, temperatura, "Dono do lead", tempo na etapa, última mensagem do paciente,
  "Próxima tarefa" e selos com texto. Ordenação "mais recentes/mais antigos na etapa"; gestão filtra
  por dono, operador por "só meus"; busca pelo endpoint do picker; sem polling ("dados de HH:MM" +
  Atualizar). O card não mostra `qualification`.
- **Clique no card:** drawer só-leitura (não assume, não pega tarefa, não muda etapa, não reabre
  conversa, não cala a Val, não muda dono, não marca como lida), com revalidação de acesso; "Abrir
  conversa no chat" só para thread existente e autorizada, sem `/conversation/open`.
- **Mover para…:** diálogo de confirmação com o texto explicativo de cada etapa (motivo obrigatório
  em Não convertido; texto só em Outro; tipo de compromisso opcional em Cliente Agendado). Conflito
  mostra quem moveu e permite reaplicar. Arrastar-e-soltar fica para depois.
- **Textos explicativos:** botão ⓘ no cabeçalho de cada coluna e descrição sob cada opção do
  "Mover para…" e do encerramento.
- **Aba "Etapas"** (quem tem `gerenciar_config_sistema`): a clínica troca nomes de etapas e motivos
  e edita os textos explicativos (≤200 caracteres), com "restaurar padrão"; não cria nem remove etapas.
- **Encerrar atendimento (uma classificação só):** o "Desfecho" passa a ser a etapa do funil
  (Aguardando retorno, Cliente Agendado, Paciente em acompanhamento, Não convertido com motivo, Não
  qualificado); o CRM move o funil e grava o desfecho legado equivalente. Sem catálogo (Hub Loc), o
  modal antigo continua.
- **Painel do contato (chat):** cartão "Etapa do funil" ao lado da "Próxima ação" do follow-up
  ("Fora do funil" com "Incluir no funil" quando não há etapa). Na Varizemed, o antigo cartão
  "Qualificação" sai, o chip do cabeçalho mostra a etapa e o filtro da barra lateral usa as etapas.
- **Painel gerencial** (`ver_dashboard_funil` + visão do tenant), mês × mês anterior (de 2020-01 ao
  mês seguinte), fuso da clínica:
  - **Coorte do mês** (pirâmide): entraram → aceitaram o aviso LGPD (quando o CRM registra) →
    alcançaram Em atendimento → Cliente Agendado → Paciente em acompanhamento; e **encerraram sem
    agendar**. Os **Não qualificados** (spam, golpe) aparecem à parte e saem da base dos percentuais.
    Contatos antigos e backups graduados contam no mês do **primeiro contato**: meses já fechados
    podem crescer quando eles entram no funil.
  - **Agora no funil:** contagem por etapa e parados.
  - **Movimentos do mês** por etapa de destino; **classificação de antigos** e **reativações** à parte.
  - **Não convertidos por motivo** (motivo vigente, com correções aplicadas): uma tabela para os
    movimentos do mês e outra para a classificação de contatos antigos.
  - Barras e tabelas simples, sem BI.

## 7. Índices (COLLECTION; publicar READY antes do código, sem `--force`)

`wa_contacts`: (1–2) `crm_stage, is_archived, is_backup, crm_stage_changed_at DESC|ASC`;
(3–4) os mesmos com `assigned_to_uid` à frente; (5–6) `[assigned_to_uid,] crm_stage, is_archived,
is_backup, last_inbound_at`; (7) `crm_cohort_month, is_backup, crm_max_reached_order`;
(8) `crm_cohort_month, crm_stage, is_backup, crm_max_reached_order`; (9) `is_archived, is_backup, crm_stage`.
`crm_activities`: (10) `event_type, entry_kind, to_stage, occurred_at`; (11) `event_type, entry_kind,
occurred_at`; (12) `contact_id, event_type, occurred_at DESC`.
Um gate estático no simulador monta a matriz completa de consultas do repositório (escopo × ordem ×
regra de parado, coorte, eventos, histórico e tarefas) e confere cada uma contra o JSON.
Custo medido nos simuladores: quadro ≈ 230 leituras por carga sem tarefas, mais 1 por tarefa
pendente visível (pior caso ~1,6 mil); painel frio = ~62 agregações + 4 streams limitados
(entradas em perda e correções de motivo dos dois meses; pior caso ~12 mil docs), com cache de
2 min por mês e limite de taxa; mudança de etapa ≈ 8–12 leituras + 2 escritas; o drawer revalida a
cada 30 s por uma rota leve (contato + Activity apontada) e só recarrega o resto quando a etapa muda.

## 8. Migração dos contatos existentes

`scripts/classify_funnel_stage.py`: `--tenant` obrigatório, **dry-run por padrão** com trava de
escrita, `--yes` grava, relatório agregado sem PII (amostra de ids só com `--sample`), escrita
**por contato em transação** (nunca toca contato que já tem etapa — nem o que o intake ou um
usuário gravaram durante a execução), undo que só reverte o que a própria migração gravou e
ninguém mudou, Activity `crm_stage_migrated` com `rule_id`, datas coeridas para datetime UTC.

| Regra | Resultado | Padrão |
|---|---|---|
| Já tem etapa | ignora | sempre |
| Backup | fora do funil (entra ao ser graduado) | sempre |
| Revogação LGPD | fora do funil (mesma regra da entrada automática) | sempre |
| Nunca escreveu (agenda, histórico sem mensagem) | fora do funil | sempre |
| Canal fora dos tipos de entrada do tenant (ex.: só coexistence) | fora do funil (flag explícita inclui) | sempre |
| `recent_untouched`: com a Val (fase do bot: sem dono e sem `bot_completed`; `qualification=novo`; sem 1º contato humano **e sem outbound humano nas últimas 20 mensagens enviadas**), entrada real nos últimos 30 dias (linhagem ≥ 02/09) | Novo contato | **ligada** |
| `in_reception` (antiga `open_human`): na recepção (fora da fase do bot), com **atendimento aberto** e **mensagem real** do paciente (sem clique de avaliação) nos últimos 30 dias | Em atendimento | **ligada** |
| `legacy_outcome` **[DECISÃO DO PO — 28/10]**: desfecho já registrado — convertido → Cliente Agendado; nao_convertido → Não convertido (motivo não registrado); nao_qualificado → Não qualificado; qualificado → A classificar | conforme o desfecho | **ligada** |
| `reopen_opt_out`: clicou Encerrar, sem mensagem depois, **sem desfecho registrado** (esse caso fica com `legacy_outcome`), sem desfecho de agendamento da Val, **sem link de agendamento da Val em nenhum ciclo** e **sem recusa comercial ativa** | Não convertido / Motivo não registrado | opt-in |
| Todo o resto (recusa comercial, recusa LGPD, silêncio, Qualificado) | **A classificar** | sempre |

Precedência: `reopen_opt_out` > `in_reception` > `recent_untouched` > `legacy_outcome`, ou seja, o
estado atual prevalece sobre o desfecho antigo (atendimento aberto com mensagem real recente → Em
atendimento). O relatório mostra esses conflitos, os Qualificados enviados a A classificar e os
desfechos aplicados antes e depois da reforma das qualificações de 02/09/2026 (o desfecho não tem
data: vale a última mensagem do contato). A migração nunca escreve `qualification` (só a lê).

Os dois scripts exigem `FIRESTORE_PROJECT_ID` **e** `FIRESTORE_COLLECTION_PREFIX` explícitos no
ambiente (staging e prod compartilham o projeto; só o prefixo os separa). O relatório sai mesmo em
erro de leitura e mostra, por regra, quantos casados têm recusa comercial ativa e quantos têm sinal
de clique de controle. Contato sem `source_channel_type` (anterior aos canais tipados) conta como
`standard`; `--include-channel-types` inclui explicitamente outros tipos. Reaplicar uma migração
desfeita exige trocar a versão do conjunto de regras (`RULESET_VERSION`, hoje 2026-10-28); o
relatório rotula esses contatos como `revertido_antes`.

Não existem regras que inventem Paciente em acompanhamento nem motivos selecionáveis: nenhum desses
tem fonte confiável. Rollout: código com flag desligada → índices READY → dry-run e revisão do
relatório com o PO → `--yes` no `varizemed-test` e depois na `varizemed` → habilitar o tenant
(`set_tenant_funnel.py`) → novo dry-run até "a alterar: 0". Rodar fora do pico, com a rampa padrão.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Etapas manuais desatualizadas | Novo contato e Em atendimento automáticos por evento; o encerramento já classifica; selos derivados; sugestão de um clique (Val agendou) |
| Agendamento pelo link da Val não chega ao CRM | Selo "Val: enviou o link" + sugestão; a equipe confirma na chegada; integração com a agenda online fica para depois |
| Desfecho legado espelhado diverge da etapa (escrita parcial) | A etapa e o legado gravam no mesmo commit; automações e migração não tocam o legado; Hub Loc segue só com o legado |
| Corrida rara: o intake ou uma automação (handoff, 1ª resposta humana) grava (merge sem precondição) a partir de leitura feita dezenas de ms antes de uma mudança manual ou da migração no mesmo contato | Aceito. Só ocorre no mesmo instante da mudança (intake: 1º inbound após a habilitação; automação: só a partir de Novo contato/A classificar). Efeitos: a etapa volta a A classificar/Novo, `crm_max_reached_order` e a coorte são regravados e a versão continua 1 (o 409 não detecta); a Activity da mudança fica no histórico e uma nova mudança corrige. A migração em massa roda antes de habilitar o tenant e, em transação, nunca sobrescreve |
| Índice não publicado → `FAILED_PRECONDITION` | Publicar READY antes; gate estático de índices; sem fallback para full-scan |
| Custo de leitura | Sem polling; `count()`; páginas de 20; tarefas em lote; cache curto do painel; limite de taxa |
| Scripts legados (`_dedupe_contacts`, export/import de anotações) não conhecem `crm_*` | Registrado no ADR; revisar antes de qualquer uso |
| `SECRET_KEY` aleatório entre instâncias invalida cursor | Mesmo pré-requisito do follow-up: env fixa em prod |
| Contato legado com dono gravado só em `assigned_to` (`assigned_to_uid` vazio, operador pré-cadastrado que nunca tinha logado): as rules e as consultas escopadas o tratam como pool, mas o REST (e o funil) deriva o dono e nega | O total da coluna do operador pode ser maior que os cards visíveis; a coluna avisa "Alguns contatos desta etapa estão fora do seu acesso". Correção de causa (backfill de `assigned_to_uid`) muda a visibilidade do CRM inteiro e fica para decisão própria |
| A Val passar a "continuar = aceite" (`lgpd_by_agent`) | O degrau "aceitaram o aviso" da coorte deixa de ser medido no CRM (o painel informa) |

## 10. Decisões do PO

**Tomadas em 28/10/2026** (ver a emenda do ADR 0015):
1. Etapas, definições e nomes da seção 4, com "Paciente em acompanhamento" e textos explicativos
   editáveis pela clínica. Conversão = marcar consulta (Cliente Agendado); quem agenda pelo link da Val
   é confirmado pela equipe na chegada.
2. Mantida "Aguardando retorno"; saem Compareceu e Convertido (pago).
3. Uma classificação só: o encerramento escolhe a etapa e grava o desfecho legado equivalente.
4. Migração aproveita os desfechos antigos, exceto Qualificado (→ A classificar).
5. Limiares e permissões ajustáveis com o tempo; mover etapa começa com admin/supervisão e pode ser
   ligado ao perfil Operador em Perfis de acesso. Contatos com a Val ficam fora do quadro das
   operadoras (`ver_contatos_agente_funil`).
6. Motivos com "Não aceitou a proposta", "Convênio não aceito" e "Não compareceu"; tags continuam
   como anotação livre.
7. Abertura do chat (`request_welcome`) conta como entrada em Novo contato.

**Ainda em aberto (não bloqueiam a liberação):**
- Regra opt-in `reopen_opt_out` da migração (decidir depois de ver a simulação).
- "Orçamento apresentado" como etapa própria (hoje: Aguardando retorno + tarefa na fila Orçamentos).
- Excluir Não convertido/Não qualificado da reabertura em lote além do que o desfecho legado já faz.
- Hub Loc: desligada até ter template próprio (Novo lead, Proposta, Negociação, Contrato…).
- RoPA da clínica citando o funil (`docs/compliance/FUNIL_PRIVACIDADE.md`).

## 11. Automações

**Implementadas (28/10):** handoff da Val e 1ª resposta humana pelo CRM → Em atendimento, só a
partir de Novo contato/A classificar (`template["automations"]`), no mesmo write existente, com
Activity de sistema (`source=rule:<evento>`) gravada à parte, best-effort e idempotente; criação de
contato pela equipe entra em Em atendimento. Nunca regridem etapa nem escrevem `qualification`.
- **Handoff:** os dois pontos de finalização do bot (builtin `_finalize_bot` e CX
  `_finalize_cx_handoff`), por onde passam também fora do expediente, erro do motor, buffer CX e
  `lgpd_by_agent`. O contato só é relido quando o tenant tem funil.
- **1ª resposta humana:** contam os envios REST da equipe (texto, mídia, áudio, localização, template
  manual, inclusive a reabertura pontual, e a correção de mensagem). Não contam: eco do celular
  (coex), histórico importado, lote de reabertura, recibos e mensagens de sistema, a Val, o aviso
  automático do supervisor ao assumir e o aviso de espera da pool. "Retomar/Continuar" do template
  não é handoff: a primeira resposta da equipe move.

**Futuras, só com evento explícito e confiável:** agendamento confirmado pela agenda online/ProDoctor
→ Cliente Agendado. Resultado da tarefa e `bot_outcome` continuam **sugestões** de um clique.
Nunca: inferir por texto, link ou orçamento enviado, silêncio, ou IA movendo etapa sem política.

## 12. Fora do escopo desta etapa

Automation Engine, editor visual de pipeline, funis ilimitados pela UI, Opportunity completa,
financeiro, agenda integrada, campanhas, múltiplos tratamentos, BI avançado, envio por etapa, IA
movendo etapa, arrastar-e-soltar. Pedidos da reunião que ficam em outras frentes: mensagens
automáticas de 4 h, porte do Monitor (fila/parados) para a Varizemed, formato de data do calendário,
carregamento de conversas antigas, "Pegar tarefa abre o chat". O "CRM de novos e antigos" fica
**parcial**: backups do 2º número entram no funil quando graduados; ciclos anuais e campanhas, depois.

## 13. Contatos, histórico e privacidade

Ver [processo de privacidade do funil](compliance/FUNIL_PRIVACIDADE.md): o que é gravado, quem lê,
portabilidade/eliminação e o que nunca entra no histórico.

## 14. Entrega local — 26/10/2026

Código desta branch, sem commit, push, deploy, índice publicado ou acesso a produção.

**Backend:** `funnel_catalog.py` (puro: templates, regras, entrada automática, sinais),
`funnel_repository.py`, `funnel_service.py`, `funnel_routes.py`; entrada automática em
`webhook.py` e `database_firestore.py` (mesmo write); `FEATURE_FUNNEL` em `config.py`; 4 toggles em
`rbac.py`; em `main.py`, o router, `no-store` por prefixo, `feature_funnel` no client-config,
`funnel.enabled` no `/api/session` e o 422 com `code` no funil. No follow-up: autorizador com
permissão parametrizada e helper de visibilidade de thread, contexto/mensagens em helpers
compartilhados, "Ver como" negado também no serviço e `list_activities` sem eventos do funil.
**Índices:** 12 novos em `firestore.indexes.json` (nenhum removido).
**Frontend:** `features/funnel/` (quadro, coluna, card, drawer, diálogo de mover, histórico, busca,
painel gerencial, reducer, camadas de acessibilidade), `components/funnel/FunnelEntry.tsx` e
`FunnelStageCard.tsx` (com o aviso no modal de encerramento), `components/LeadTemperatureDot.tsx`
extraído; `api.ts` (erro estruturado), `normalization.ts`/`types.ts` (campos `crm_*`) e
`CrmContext.tsx` (`funnelEnabled`, `focusExistingConversation`). Painel carregado sob demanda.
**Scripts:** `scripts/set_tenant_funnel.py` e `scripts/classify_funnel_stage.py`.

**Gates executados em 26/10 (todos verdes):** `py_compile`; `sim_bot_flow` 76, `sim_cx_flow` 229,
`sim_reception_flow` 301, `sim_buffer_flow` 61, `sim_history_recency` 45, `sim_pool_wait_notice` 48,
`sim_monitor_flow` 73, `sim_followup_flow` 81, `sim_followup_api` 53,
`sim_commercial_contact_policy` 55, `sim_followup_send_guards`, `sim_impersonate` 306,
`sim_impersonate_views` 92, `sim_picker_v21` 93 (com `PYTHONIOENCODING=utf-8`; sem isso o console
cp1252 não imprime "✓" — preexistente), `sim_message_correction` 25; novos: `sim_funnel_flow` 312,
`sim_funnel_api` 167, `sim_funnel_intake` 163, `sim_funnel_migration` 230; frontend: `npm run build`,
`check_wa_format` 32, `sim_funnel_frontend` 352, `sim_followup_frontend` 19, `sim_followup_lifecycle` 25.
As correções da revisão foram provadas por mutação (cada teste novo falha sem a correção).

**Não verificado:** UI em navegador autenticado (layout, foco real, tema escuro), regras no emulador
do Firestore, índices reais publicados, e qualquer dado de produção (a migração só rodou contra
Firestore em memória).

| # | Critério do PO | Como é garantido | Prova |
|---|---|---|---|
| 1 | Contato existente recebe etapa | Migração (resto em A classificar); entrada de quem volta a escrever; "Incluir no funil" | `sim_funnel_migration`; `sim_funnel_intake`; `sim_funnel_flow` |
| 2 | Não interfere em qualification | Só campos `crm_*` são escritos | `sim_funnel_flow` (qualification/bot/dono/LGPD/tags intocados) |
| 3 | Não interfere em atendimento/bot | Nenhum outro doc muda; intake só acrescenta campos ao write existente | `sim_funnel_flow`; `sim_funnel_intake` (mesmas escritas com flag on/off); sims do bot/CX/recepção |
| 4 | Kanban lista por etapa | `/board` + `/stages/{s}/cards` paginados | `sim_funnel_flow` |
| 5 | Clicar card abre contexto | Drawer só-leitura | `sim_funnel_flow`, `sim_funnel_frontend` |
| 6 | Abrir card não assume | GETs não gravam; UI nunca chama `/conversation/open` | `sim_funnel_flow`, `sim_funnel_frontend` (guardas) |
| 7 | Mover altera só a etapa | 2 escritas: contato (`crm_*`) + Activity | `sim_funnel_flow` |
| 8 | Movimento gera Activity | `crm_stage_changed` com origem, destino, ator, data, motivo, `operation_id` | `sim_funnel_flow` |
| 9 | Conflito concorrente controlado | `crm_stage_version` + 409 com quem moveu; recibo idempotente | `sim_funnel_flow`, `sim_funnel_frontend` |
| 10 | Não convertido exige motivo | Catálogo + validação | `sim_funnel_flow`, `sim_funnel_api` |
| 11 | Motivo anterior fica após reativação | Activity append-only com `from_reason` | `sim_funnel_flow` |
| 12 | Reativado volta ao funil | `entry_kind=reactivation` | `sim_funnel_flow` |
| 13 | Tarefa pendente no card | Lote por `contact_id in`, autorização por thread | `sim_funnel_flow` |
| 14 | Tarefa vencida com indicador | `task_overdue` | `sim_funnel_flow`, `sim_funnel_frontend` |
| 15 | Concluir tarefa não muda etapa | O follow-up não escreve `wa_contacts` | `sim_followup_flow` (lista branca de escrita) |
| 16 | Mudar etapa não conclui tarefa | Nenhum doc de tarefa muda | `sim_funnel_flow` |
| 17 | Temperatura da IA na fonte atual | Card lê `lead_temperature` do contato | `sim_funnel_flow` |
| 18 | Painel coerente com o quadro | Mesmas contagens | `sim_funnel_flow` |
| 19 | Contagem respeita tenant/permissão | Escopo do operador; painel só com visão do tenant | `sim_funnel_flow`, `sim_funnel_api` |
| 20 | Sem etapa não some | Entrada automática, migração, colunas inativas com contatos, "Fora do funil" | `sim_funnel_intake`, `sim_funnel_migration`, `sim_funnel_flow`, `sim_funnel_frontend` |
| 21 | Sem dado clínico na Activity | Evento com lista branca; nota curta só em Outro; motivo fora do contato | `sim_funnel_flow` |
| 22 | Mover não envia WhatsApp | Nenhuma escrita além de `crm_*` + Activity | `sim_funnel_flow` |
| 23 | Mover não assume conversa | Threads intocadas | `sim_funnel_flow` |
| 24 | Nenhuma operação concede acesso | IDOR, escopo, thread-só não move, Ver como bloqueado | `sim_funnel_flow`, `sim_funnel_api` |

**Para liberar:** decisões da seção 10 → publicar os 12 índices (READY) → deploy com
`FEATURE_FUNNEL=false` → revisar perfis RBAC da Varizemed → dry-run da migração e revisão do
relatório com o PO → `--yes` no `varizemed-test`, depois na `varizemed` → `set_tenant_funnel.py
--enable` → `FEATURE_FUNNEL=true` → novo dry-run até "a alterar: 0" → conferência manual da UI.
