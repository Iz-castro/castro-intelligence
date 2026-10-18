export type TaskView = "overdue" | "today" | "upcoming" | "completed" | "cancelled" | "all";
export type TaskScope = "mine" | "queue" | "team" | "contact";
export type ContactPurpose = "commercial" | "service" | "internal";
export type TaskStatus = "pending" | "completed" | "cancelled";
export type QueueDefinition = { key: string; label: string; active: boolean };
export type HourRange = [string, string];

export type FollowupSettings = {
  version: number;
  timezone: string;
  queues: QueueDefinition[];
  contact_hours: Record<string, HourRange[]>;
  holidays: string[];
  preferred_time: string | null;
  configured: boolean;
};

export type FollowupContact = {
  id: number;
  display_name?: string;
  declared_name?: string;
  lead_temperature?: string;
  commercial_contact_block?: { active?: boolean; version?: number } | boolean | null;
  commercial_contact_blocked?: boolean;
};

export type FollowupTask = {
  id: string;
  contact_id: number;
  contact?: FollowupContact | null;
  conversation_id?: string | null;
  type: string;
  title: string;
  description?: string;
  contact_purpose: ContactPurpose;
  due_at: string;
  status: TaskStatus;
  version: number;
  queue_key: string;
  assignment_mode?: "queue" | "user";
  assignee_user_id?: number | null;
  assignee_uid?: string | null;
  assignee_name?: string;
  created_at?: string;
  created_by_name?: string;
  attempt_count?: number;
  unanswered_attempt_count?: number;
  response_received?: boolean;
  response_label?: string;
  response_anchor_at?: string;
  commercial_blocked?: boolean;
  can_edit?: boolean;
  can_manage?: boolean;
  can_take?: boolean;
  calendar_conflict?: boolean | string;
  result_code?: string;
  cancel_reason?: string;
  can_modify?: boolean;
  unanswered_attempts?: number;
  review_required?: boolean;
  appointment_at?: string | null;
  appointment_ref?: string | null;
  eligible_assignees?: { id: number; display_name: string }[];
};

export type FollowupActivity = {
  id: string;
  event_type: string;
  task_id?: string | null;
  actor_user_id?: number | null;
  actor_name?: string;
  actor_display_name?: string;
  actor_uid?: string;
  occurred_at?: string;
  recorded_at?: string;
  operation_id?: string;
  data?: Record<string, unknown>;
};

export type Page<T> = { items: T[]; next_cursor?: string | null; has_more?: boolean };
export type ActionBody = { action: string; version: number; [key: string]: unknown };

export const TASK_TYPES = [
  { value: "retorno", label: "Retorno", purpose: "commercial" },
  { value: "sem_resposta", label: "Retorno sem resposta", purpose: "commercial" },
  { value: "orcamento", label: "Acompanhamento de orçamento", purpose: "commercial" },
  { value: "confirmacao_consulta", label: "Confirmação de consulta", purpose: "service" },
  { value: "lembrete_consulta", label: "Lembrete de consulta", purpose: "service" },
  { value: "recuperacao", label: "Recuperação", purpose: "commercial" },
  { value: "internal", label: "Ação interna", purpose: "internal" },
] as const;

export const RESULT_LABELS: Record<string, string> = {
  action_done: "Ação realizada",
  not_reached: "Sem resposta / não atendeu",
  customer_replied: "Contato realizado",
  scheduled: "Agendou",
  no_longer_interested: "Recusa deste acompanhamento",
  confirmed: "Presença confirmada pelo paciente",
  reminder_done: "Lembrete realizado",
};

export const EVENT_LABELS: Record<string, string> = {
  task_created: "Tarefa criada",
  task_updated: "Tarefa editada",
  task_taken: "Tarefa pega",
  task_assigned: "Responsabilidade alterada",
  task_attempted: "Tentativa realizada",
  task_rescheduled: "Prazo alterado",
  task_completed: "Objetivo concluído",
  task_cancelled: "Tarefa cancelada",
  commercial_contact_preference_changed: "Preferência comercial registrada",
};

export const VIEW_LABELS: Record<TaskView, string> = {
  overdue: "Atrasadas", today: "Hoje", upcoming: "Próximas", completed: "Concluídas", cancelled: "Canceladas", all: "Pendentes",
};

export function isCommercialBlocked(task: FollowupTask): boolean {
  const preference = task.contact?.commercial_contact_block;
  return Boolean(task.commercial_blocked || task.contact?.commercial_contact_blocked ||
    (typeof preference === "boolean" ? preference : preference?.active));
}

export function taskTypeLabel(value: string): string {
  return TASK_TYPES.find((entry) => entry.value === value)?.label || value;
}
