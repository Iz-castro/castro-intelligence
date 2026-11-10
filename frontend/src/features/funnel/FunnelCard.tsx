import { memo, useId } from "react";
import { LeadTemperatureDot, leadTemperatureText } from "../../components/LeadTemperatureDot";
import { buildBadges } from "./badges";
import { daysAgoText, daysInStageText, formatDateTime } from "./format";
import type { FunnelCard as FunnelCardData } from "./types";

type Props = {
  card: FunnelCardData;
  canMove: boolean;
  onOpen: (contactId: number, trigger: HTMLElement) => void;
  onMove: (card: FunnelCardData, trigger: HTMLElement) => void;
};

// Card do quadro: so a lista branca do backend (nunca qualification, notas,
// tags ou telefone). Abrir = drawer so-leitura; mover = dialogo confirmado.
export const FunnelCard = memo(function FunnelCard({ card, canMove, onOpen, onMove }: Props) {
  const id = useId();
  const badges = buildBadges({ signals: card.signals, badges: card.badges, reason: card.reason, tasksVisible: card.tasks_visible });
  const task = card.tasks_visible ? card.next_task : null;
  return <article className={`fn-card${card.signals?.stale ? " is-stale" : ""}`} aria-labelledby={`${id}-name`} data-fn-card={card.contact_id}>
    <h4 className="fn-card-name" id={`${id}-name`}>
      <button type="button" className="fn-card-open" onClick={(event) => onOpen(card.contact_id, event.currentTarget)}><span className="fn-sr">Abrir </span>{card.display_name || `Contato #${card.contact_id}`}</button>
    </h4>
    <p className="fn-card-temperature"><LeadTemperatureDot temperature={card.lead_temperature || undefined} decorative />{leadTemperatureText(card.lead_temperature)}</p>
    <ul className="fn-card-facts">
      <li><span className="fn-fact-label">Dono do lead:</span> {card.owner?.name || "sem dono"}</li>
      <li>{daysInStageText(card.signals?.days_in_stage)}</li>
      <li><span className="fn-fact-label">Última mensagem do paciente:</span> {card.last_inbound_at ? daysAgoText(card.signals?.patient_idle_days) : "nenhuma"}</li>
      {card.tasks_visible && <li><span className="fn-fact-label">Próxima tarefa:</span> {task ? <>{task.title} · <span className={task.overdue ? "fn-overdue" : undefined}>{formatDateTime(task.due_at)}{task.overdue ? " (atrasada)" : ""}</span></> : "nenhuma pendente"}</li>}
    </ul>
    {badges.length > 0 && <ul className="fn-badges" aria-label="Selos">{badges.map((badge) => <li key={badge.key} className={`fn-badge fn-badge--${badge.tone}`} title={badge.title}>{badge.text}</li>)}</ul>}
    {canMove && <button type="button" className="fn-card-move" onClick={(event) => onMove(card, event.currentTarget)}>Mover para…<span className="fn-sr"> {card.display_name}</span></button>}
  </article>;
});
