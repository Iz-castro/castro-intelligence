import { useEffect, useId, useRef, useState } from "react";
import type { Auth } from "firebase/auth";
import { sendJson } from "../../api";
import type { FollowupSettings } from "./types";
import { FOLLOWUP_TIMEZONE, formatMoment, localInput, localToIso, scheduleProblem, shortcutDate } from "./time";
import { requestError } from "./useOperation";

type Props = {
  auth: Auth;
  value: string;
  onChange: (value: string) => void;
  settings: FollowupSettings | null;
  internal?: boolean;
  consultation?: boolean;
  disabled?: boolean;
  label?: string;
  appointmentValue?: string;
};

export function ScheduleField({ auth, value, onChange, settings, internal, consultation, disabled, appointmentValue, label = "Próximo prazo combinado" }: Props) {
  const id = useId();
  const problem = value && !internal ? scheduleProblem(value, settings) : "";
  let preview = "";
  if (value) {
    try { preview = formatMoment(localToIso(value, settings?.timezone), settings?.timezone); }
    catch { preview = "Data inválida"; }
  }
  return (
    <div className="fu-schedule">
      <label className="fu-field" htmlFor={id}>
        <span>{label} <span aria-hidden="true">*</span></span>
        <input id={id} type="datetime-local" required value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} aria-describedby={`${id}-hint ${id}-preview`} />
      </label>
      <div className="fu-shortcuts" aria-label="Atalhos de prazo">
        <button type="button" disabled={disabled} onClick={() => onChange(localInput(new Date(Date.now() + 60 * 60 * 1000), settings?.timezone))}>Em 1 hora</button>
        {[1, 2, 7].map((days) => <button type="button" key={days} disabled={disabled} onClick={() => onChange(shortcutDate(days, settings))}>{days === 1 ? "Amanhã" : `Em ${days} dias`}</button>)}
      </div>
      <p className="fu-help" id={`${id}-hint`}>A data combinada com o paciente tem prioridade. Horários em {settings?.timezone || FOLLOWUP_TIMEZONE}. Atalhos precisam de revisão.</p>
      {value && <p id={`${id}-preview`} className={`fu-preview ${problem ? "fu-preview--warning" : ""}`} aria-live="polite">Prazo escolhido: <strong>{preview}</strong>{problem && <span>{problem}</span>}</p>}
      {!internal && !settings?.configured && <p className="fu-notice fu-notice--warning">Calendário pendente: a gestão deve configurar os dias e as faixas de contato.</p>}
      {consultation && <ConsultationGuide auth={auth} settings={settings} onChoose={onChange} disabled={disabled} appointmentValue={appointmentValue} />}
    </div>
  );
}

type Suggestion = { nominal_at: string; suggested_at: string | null; reason: string; use_current_contact?: boolean; late_notice?: boolean; hours: number };
const SUGGESTION_REASON: Record<string, string> = {
  configuration_required: "A gestão precisa configurar os dias e horários de contato.",
  previous_workday: "Fim de semana ou feriado: sugestão no dia permitido anterior, para sua confirmação.",
  nominal: "Prazo de referência, confira e confirme o horário antes de salvar.",
  choose_permitted_time: "Horário fora da faixa em dia útil. Escolha manualmente um horário permitido antes da consulta.",
  late_booking: "O prazo já passou. Se já estiver falando com o paciente, registre o que foi realizado. Caso contrário, revise o primeiro horário permitido antes da consulta.",
  needs_team_decision: "Não há horário permitido disponível antes da consulta. Sinalize a pendência à equipe para decisão humana.",
  no_available_time: "Não há sugestão disponível no calendário configurado. Revise com a equipe.",
};

function ConsultationGuide({ auth, settings, onChoose, disabled, appointmentValue }: Pick<Props, "auth" | "settings" | "disabled" | "appointmentValue"> & { onChoose: (value: string) => void }) {
  const id = useId();
  const [ownConsultation, setOwnConsultation] = useState("");
  const consultation = appointmentValue === undefined ? ownConsultation : appointmentValue;
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  useEffect(() => { sequence.current++; setSuggestions([]); setError(""); return () => { sequence.current++; }; }, [consultation, settings?.version]);
  let consultationPreview = "";
  if (consultation) {
    try { consultationPreview = formatMoment(localToIso(consultation, settings?.timezone), settings?.timezone); }
    catch { consultationPreview = "Confira a data e a hora da consulta."; }
  }

  async function calculate() {
    if (busy || !consultation) return;
    const request = ++sequence.current;
    setBusy(true); setError(""); setSuggestions([]);
    try {
      const appointment = localToIso(consultation, settings?.timezone);
      if (new Date(appointment).getTime() <= Date.now()) throw new Error("A consulta informada já passou. Confira a agenda oficial.");
      const results = await Promise.allSettled([72, 24].map(async (hours) => ({ ...await sendJson<Omit<Suggestion, "hours">>(auth, "/api/followup/suggestion", { appointment_at: appointment, type: hours === 72 ? "confirmacao_consulta" : "lembrete_consulta" }), hours })));
      const completed: Suggestion[] = [];
      const failures: string[] = [];
      for (const result of results) {
        if (result.status === "fulfilled") completed.push(result.value);
        else failures.push(requestError(result.reason));
      }
      if (request === sequence.current) { setSuggestions(completed); if (failures.length) setError(failures.join(" ")); }
    } catch (reason) { if (request === sequence.current) setError(requestError(reason)); }
    finally { setBusy(false); }
  }

  return (
    <details className="fu-guide">
      <summary>Ajuda para confirmação (72h) e lembrete (24h)</summary>
      <p>Confira a consulta no ProDoctor. Este cálculo apenas sugere prazos; não cria agenda, envia mensagem ou conclui tarefas.</p>
      {appointmentValue === undefined ? <label className="fu-field" htmlFor={id}><span>Data e hora da consulta na agenda oficial</span><input id={id} type="datetime-local" value={consultation} disabled={disabled || busy} onChange={(event) => setOwnConsultation(event.target.value)} /></label> : <p className="fu-help">{consultation ? `Consulta informada: ${consultationPreview}` : "Informe a data e a hora da consulta no campo acima."}</p>}
      <button className="fu-button" type="button" disabled={disabled || busy || !consultation} onClick={() => void calculate()}>{busy ? "Calculando…" : "Consultar sugestões de prazo"}</button>
      {error && <p className="fu-notice fu-notice--danger" role="alert">{error}</p>}
      {suggestions.map(({ hours, nominal_at, suggested_at, reason }) => <div className="fu-guide-result" key={hours}>
        <strong>{hours === 72 ? "Confirmação — 72h" : "Lembrete — 24h"}</strong>
        <span>Referência: {formatMoment(nominal_at, settings?.timezone)}</span>
        <p>{SUGGESTION_REASON[reason] || "Revise a sugestão com a equipe antes de salvar."}</p>
        {suggested_at ? <button type="button" disabled={disabled} className="fu-button" onClick={() => onChoose(localInput(suggested_at, settings?.timezone))}>Usar {formatMoment(suggested_at, settings?.timezone)}</button> : <span className="fu-help">Escolha humana necessária; nenhum prazo foi alterado.</span>}
      </div>)}
      <p className="fu-help">Um contato pode cumprir as duas ações do mesmo compromisso nas exceções aprovadas, com registro humano de ambas e uma tentativa real. Um lembrete ainda futuro é preservado. Apenas tentar contato não confirma presença.</p>
    </details>
  );
}
