import { daysAgoText, daysInStageText } from "./format";
import type { BotOutcome, CardBadges, FunnelSignals, Labeled } from "./types";

// Selos do card/drawer: SEMPRE com texto (cor so reforca). Derivados do que o
// backend ja calculou; nada aqui e persistido.
export type BadgeTone = "warning" | "danger" | "success" | "info" | "neutral";
export type Badge = { key: string; text: string; tone: BadgeTone; title?: string };

export const BOT_OUTCOME_LABELS: Record<BotOutcome, string> = {
  agendado: "Bot: agendou",
  link_enviado: "Bot: enviou link",
  duvida_respondida: "Bot: dúvida respondida",
  sem_interesse: "Bot: sem interesse",
};

export function buildBadges(input: { signals: FunnelSignals; badges: CardBadges; reason?: Labeled | null; tasksVisible: boolean }): Badge[] {
  const { signals, badges, reason, tasksVisible } = input;
  const list: Badge[] = [];
  if (signals.stale) {
    list.push(signals.stale_kind === "patient_silence"
      ? { key: "stale", text: "Parado: paciente sem escrever", tone: "warning", title: `Última mensagem do paciente ${daysAgoText(signals.patient_idle_days)}` }
      : { key: "stale", text: "Parado: tempo na etapa", tone: "warning", title: daysInStageText(signals.days_in_stage) });
  }
  // Sem acesso ao follow-up nenhum selo de tarefa e exibido (contrato).
  if (tasksVisible && signals.task_overdue) list.push({ key: "task_overdue", text: "Tarefa atrasada", tone: "danger" });
  if (tasksVisible && signals.no_next_action) list.push({ key: "no_next_action", text: "Sem próxima ação", tone: "warning" });
  if (signals.new_activity) list.push({ key: "new_activity", text: "Mensagem nova do paciente", tone: "info" });
  if (reason) list.push({ key: "reason", text: `Motivo: ${reason.label}`, tone: "neutral" });
  if (badges.with_bot) list.push({ key: "with_bot", text: "Com o bot", tone: "neutral" });
  if (badges.lgpd_pending) list.push({ key: "lgpd_pending", text: "Sem aceite LGPD", tone: "warning" });
  if (badges.commercial_blocked) list.push({ key: "commercial_blocked", text: "Recusa comercial", tone: "danger", title: "Não realizar novas retomadas comerciais" });
  if (badges.bot_outcome && BOT_OUTCOME_LABELS[badges.bot_outcome]) {
    list.push({ key: "bot_outcome", text: BOT_OUTCOME_LABELS[badges.bot_outcome], tone: badges.bot_outcome === "sem_interesse" ? "neutral" : "success", title: "Registro do bot neste ciclo: só sugestão, a etapa não muda sozinha" });
  }
  return list;
}
