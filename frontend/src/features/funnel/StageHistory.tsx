import { formatDateTime } from "./format";
import type { HistoryItem } from "./types";

const APPOINTMENT_LABELS: Record<string, string> = { consultation: "consulta", procedure: "procedimento" };
const RULE_LABELS: Record<string, string> = {
  recent_untouched: "contato recente ainda sem atendimento humano",
  in_reception: "atendimento na recepção com mensagem recente do paciente",
  legacy_outcome: "desfecho registrado no atendimento anterior",
  open_human: "conversa humana recente",
  reopen_opt_out: "pediu para encerrar a retomada",
};

function itemTitle(item: HistoryItem): string {
  if (item.event_type === "crm_funnel_entered") return "Entrada no funil";
  if (item.event_type === "crm_stage_reason_changed") return item.via === "close" ? "Motivo corrigido no encerramento" : "Motivo corrigido";
  if (item.event_type === "crm_stage_migrated") return "Classificação inicial (migração)";
  if (item.event_type === "crm_stage_migration_reverted") return "Classificação inicial desfeita";
  if (item.via === "close") return "Desfecho no encerramento do atendimento";
  if (item.entry_kind === "triage") return "Classificação no funil";
  if (item.entry_kind === "reactivation") return "Reativação";
  return "Mudança de etapa";
}

function actorText(item: HistoryItem): string {
  if (item.synthetic) return "Entrada automática";
  const actor = item.actor;
  if (!actor) return "Equipe";
  if (actor.type === "migration") return "Migração";
  // Automacoes por evento (handoff do agente de IA, 1a resposta da equipe).
  if (actor.type === "system") return "Automático";
  return actor.name || (actor.user_id ? `Pessoa #${actor.user_id}` : "Equipe");
}

export function StageHistory({ items, nextCursor, busy, error, onMore, emptyText = "Nenhuma mudança de etapa registrada." }: {
  items: HistoryItem[]; nextCursor: string | null; busy: boolean; error: string; onMore?: () => void; emptyText?: string;
}) {
  return <div className="fn-history">
    {error && <p className="fn-notice fn-notice--danger" role="alert">{error}</p>}
    {!items.length && !error && !busy && <p className="fn-help">{emptyText}</p>}
    {items.length > 0 && <ol>{items.map((item) => {
      const from = item.from_label || item.from_stage;
      const to = item.to_label || item.to_stage;
      return <li key={`${item.id}-${item.event_type}`}>
        <span className={`fn-history-dot${item.synthetic ? " fn-history-dot--synthetic" : ""}`} aria-hidden="true" />
        <div>
          <strong>{itemTitle(item)}</strong>
          <p>{formatDateTime(item.occurred_at)} · {actorText(item)}</p>
          {/* Desfazer da migracao chega com to_stage null: "X → Sem etapa". */}
          {item.event_type !== "crm_stage_reason_changed" && (from || to) && <p>{from ? `${from} → ` : item.synthetic ? "" : "Sem etapa → "}{to || "Sem etapa"}</p>}
          {item.from_reason && <p>Motivo anterior: {item.from_reason.label}</p>}
          {item.reason && <p>Motivo: {item.reason.label}</p>}
          {item.reason_note && <p className="fn-history-note">Detalhe: {item.reason_note}</p>}
          {item.appointment_kind && <p>Compromisso: {APPOINTMENT_LABELS[item.appointment_kind] || "registrado"}</p>}
          {item.rule_id && <p>Regra da migração: {RULE_LABELS[item.rule_id] || item.rule_id}</p>}
        </div>
      </li>;
    })}</ol>}
    {busy && <p className="fn-help" role="status">Carregando histórico…</p>}
    {nextCursor && onMore && !busy && <button type="button" className="fn-button" onClick={onMore}>Carregar mais histórico</button>}
  </div>;
}
