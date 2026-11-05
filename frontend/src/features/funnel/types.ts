// Espelho dos payloads de /api/funnel (contrato do funil, secao 3). O backend
// e a fonte da verdade: etapa, motivo, escopo e capacidades chegam prontos.

export type StageKind = "open" | "won" | "lost" | "excluded" | "triage";
export type StaleKind = "patient_silence" | "time_in_stage" | "task";
export type StageSource = "user" | "intake" | "graduation" | "migration" | "system" | string;
export type BoardOrder = "desc" | "asc";
export type Labeled = { key: string; label: string };
export type Owner = { user_id: number; name: string };
export type AppointmentKind = "consultation" | "procedure";
export type SuggestionSource = "bot_outcome" | "task_result";

export type FunnelStage = {
  key: string;
  label: string;
  kind: StageKind;
  order: number;
  requires_reason: boolean;
  manual_target: boolean;
  milestone: boolean;
  appointment_kind: boolean;
  stale: { kind: StaleKind; days?: number | null } | null;
  // Texto explicativo (a clinica edita na aba "Etapas"; ja vem resolvido).
  description?: string;
  // Decisoes do PO de 28/10 (contrato v2). Todos opcionais: payload sem o
  // campo degrada para o fluxo antigo (modal legado, etapa sempre visivel).
  // close_outcome = desfecho oferecido no "Encerrar atendimento";
  // legacy_qualification = qualification que o backend grava junto na
  // mudanca manual; visibility_permission = toggle que mostra a etapa no
  // quadro; default_* = textos do template (base do "restaurar padrão").
  close_outcome?: boolean;
  legacy_qualification?: string | null;
  visibility_permission?: string | null;
  // `visible` = a etapa aparece no QUADRO deste usuario (o /config lista
  // todas; o /board omite as invisiveis). Ausente = visivel.
  visible?: boolean;
  default_label?: string;
  default_description?: string;
  // Opcional no template (validate_change aceita), mas o GET /config de hoje
  // NAO expoe: sem a lista, a UI oferece todos os motivos ativos.
  reason_keys?: string[];
  active: boolean;
};

export type FunnelReason = {
  key: string;
  label: string;
  hint?: string;
  allows_note: boolean;
  selectable: boolean;
  active: boolean;
  default_label?: string;
};

export type FunnelCatalog = {
  template: string;
  template_label: string;
  version: number;
  // Versao dos textos da clinica (system_settings/funnel) e se o template
  // grava o desfecho legado junto da etapa ("uma classificação só").
  overrides_version?: number;
  legacy_qualification_sync?: boolean;
  stages: FunnelStage[];
  reasons: FunnelReason[];
  kpis: { booked_stage?: string; won_stage?: string };
};

export type FunnelCapabilities = {
  can_move: boolean;
  can_dashboard: boolean;
  privileged: boolean;
  followup: boolean;
  // can_configure = gerenciar_config_sistema (aba "Etapas");
  // can_see_agent_contacts = ver_contatos_agente_funil. Ausente = false.
  can_configure?: boolean;
  can_see_agent_contacts?: boolean;
};

export type FunnelConfig = { catalog: FunnelCatalog; capabilities: FunnelCapabilities };

export type FunnelSignals = {
  days_in_stage: number | null;
  patient_idle_days: number | null;
  stale: boolean;
  stale_kind: StaleKind | null;
  task_overdue: boolean;
  no_next_action: boolean;
  new_activity: boolean;
};

export type BotOutcome = "agendado" | "link_enviado" | "duvida_respondida" | "sem_interesse";

export type CardBadges = {
  with_bot: boolean;
  lgpd_pending: boolean;
  commercial_blocked: boolean;
  bot_outcome: BotOutcome | null;
};

// _task_view do backend: due_at/queue_key/assignee_name podem vir null
// (tarefa sem prazo legivel, sem fila ou ainda sem responsavel).
export type TaskSummary = {
  id: string;
  title: string;
  due_at: string | null;
  overdue: boolean;
  queue_key: string | null;
  assignee_name: string | null;
};

// Card do quadro: lista branca do backend (sem notas, tags, telefone ou LGPD;
// sem qualification).
export type FunnelCard = {
  contact_id: number;
  display_name: string;
  lead_temperature: string | null;
  lead_temperature_at: string | null;
  stage: string;
  stage_version: number;
  // _iso() do backend: null quando o campo falta ou e ilegivel.
  stage_changed_at: string | null;
  stage_source: StageSource | null;
  owner: Owner | null;
  last_inbound_at: string | null;
  last_activity_at: string | null;
  signals: FunnelSignals;
  badges: CardBadges;
  reason: Labeled | null;
  next_task: TaskSummary | null;
  tasks_visible: boolean;
};

export type BoardFilters = { order: BoardOrder; ownerId: number | null; mine: boolean };

export type BoardColumnPayload = {
  stage: string;
  label: string;
  kind: StageKind;
  active: boolean;
  count: number;
  stale_count: number | null;
  cards: FunnelCard[];
  next_cursor: string | null;
};

export type BoardResponse = {
  generated_at: string;
  scope: { privileged: boolean; owner_id: number | null; mine: boolean; order: BoardOrder };
  columns: BoardColumnPayload[];
};

export type StagePage = { stage: string; cards: FunnelCard[]; next_cursor: string | null };

// Etapa atual no shape do drawer (tambem volta no POST de mudanca). `kind`
// null = etapa fora do catalogo atual; datas/origem podem faltar no doc.
export type StageState = {
  key: string;
  label: string;
  kind: StageKind | null;
  version: number;
  changed_at: string | null;
  source: StageSource | null;
  entered_at: string | null;
  reason: Labeled | null;
  reason_note: string | null;
  appointment_kind: AppointmentKind | null;
};

// GET /contacts/{id}/stage: revalidacao leve do drawer (so o contato e a
// Activity apontada). Mesma autorizacao do drawer: 404 = acesso perdido.
// Campos opcionais de proposito: payload incompleto vira recarga completa
// (nunca "nada mudou" por falta de dado).
export type ContactStageCheck = {
  stage: StageState | null;
  version?: number;
  can_move?: boolean;
  write_scope?: boolean;
};

export type HistoryItem = {
  id: string;
  event_type: string;
  occurred_at: string | null;
  actor: { type: string; user_id: number | null; name: string } | null;
  from_stage: string | null;
  from_label: string | null;
  to_stage: string | null;
  to_label: string | null;
  reason: Labeled | null;
  from_reason: Labeled | null;
  reason_note?: string | null;
  appointment_kind: AppointmentKind | null;
  entry_kind: "move" | "triage" | "reactivation" | null;
  rule_id: string | null;
  // "close" = desfecho escolhido no "Encerrar atendimento" (Activity com
  // data.via). Opcional: o historico de hoje ainda nao expoe.
  via?: string | null;
  synthetic: boolean;
};

export type HistoryPage = { items: HistoryItem[]; next_cursor: string | null };

export type StageSuggestion = { to_stage: string; source: "bot_outcome"; label: string };

export type ContactFunnel = {
  contact: {
    id: number;
    display_name: string;
    lead_temperature: string | null;
    lead_temperature_at: string | null;
    owner: Owner | null;
    bot_completed: boolean;
    is_archived: number | boolean;
  };
  stage: StageState | null;
  badges: CardBadges;
  signals: FunnelSignals;
  history: HistoryPage;
  tasks: TaskSummary[] | null;
  suggestions: StageSuggestion[];
  capabilities: { can_move: boolean; write_scope: boolean };
};

// Linha de thread do GET de contexto (mesmo contrato do follow-up): doc da
// conversa ja autorizado pelo backend.
export type ContextThread = Record<string, unknown> & {
  id: string;
  contact_id?: number;
  channel_id?: number | null;
  channel_label?: string;
  unread_count?: number;
  unread?: number;
};

export type ContactContext = { contact: Record<string, unknown>; conversations: ContextThread[] };

export type MoveStageBody = {
  to_stage: string;
  expected_version: number;
  reason: string | null;
  reason_note: string | null;
  appointment_kind: AppointmentKind | null;
  operation_id: string;
  suggested_by: SuggestionSource | null;
};

export type MoveStageResponse = {
  contact_id: number;
  stage: StageState;
  replayed: boolean;
  activity_id: string;
};

// `funnel` do POST /api/wa/conversation/{id}/set-attendance (contrato v2,
// decisao 2): o desfecho do encerramento E a etapa. Sem qualification no
// corpo; o backend grava o legado equivalente.
export type CloseFunnelBody = {
  to_stage: string;
  expected_version: number;
  reason: string | null;
  reason_note: string | null;
  appointment_kind: AppointmentKind | null;
  operation_id: string;
};

// Textos da clinica (GET/PUT /api/funnel/settings; gerenciar_config_sistema).
// *_labels/*_descriptions = so o que difere do padrao do template.
export type FunnelSettingsStage = { key: string; default_label: string; default_description: string };
export type FunnelSettingsReason = { key: string; default_label: string };

export type FunnelSettings = {
  version: number;
  template: string;
  stage_labels: Record<string, string>;
  stage_descriptions: Record<string, string>;
  reason_labels: Record<string, string>;
  stages: FunnelSettingsStage[];
  reasons: FunnelSettingsReason[];
};

export type FunnelSettingsBody = {
  version: number;
  stage_labels: Record<string, string>;
  stage_descriptions: Record<string, string>;
  reason_labels: Record<string, string>;
};

// detail do 409 stale_version.
export type StaleCurrent = {
  stage: string | null;
  version: number;
  changed_at: string | null;
  changed_by_user_id: number | null;
  changed_by_name: string | null;
};

export type DashboardStage = { stage: string; label: string; kind: StageKind; count: number; stale_count: number | null };

// reached = LIQUIDO (sem os contatos hoje em etapa de exclusao, como
// Descartado); reached_gross = com eles. Payload antigo: so reached (bruto).
export type CohortLevel = { stage: string; label: string; reached: number; reached_gross?: number };

export type Cohort = {
  entered: number;
  // Contatos da coorte hoje em etapa kind=excluded e a base das taxas
  // (entered - excluded). Opcionais: payload antigo nao traz.
  excluded?: number;
  entered_net?: number;
  // Conta a coorte inteira (com os descartados).
  lgpd_accepted: number | null;
  levels: CohortLevel[];
  closed_without_booking: number;
};

export type ReasonCount = { reason: string; label: string; count: number };

// month/previous = entradas em etapa de perda por movimento (move e
// reactivation); *_triage = classificacao de antigos/sem etapa (entry_kind
// triage). Correcoes de motivo ja aplicadas. *_triage opcionais (payload
// antigo). truncated vale para o stream inteiro.
export type DashboardReasons = {
  month: ReasonCount[];
  previous: ReasonCount[];
  month_triage?: ReasonCount[];
  previous_triage?: ReasonCount[];
  truncated: boolean;
};

export type DashboardData = {
  month: string;
  previous_month: string;
  generated_at: string;
  cached: boolean;
  current: { stages: DashboardStage[]; with_stage: number; unknown_stage: number };
  cohort: { month: Cohort; previous: Cohort };
  movements: { stage: string; label: string; month: number; previous: number }[];
  triage: { month: number; previous: number };
  reactivations: { month: number; previous: number };
  reasons: DashboardReasons;
  notes: string[];
};
