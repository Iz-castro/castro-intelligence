import { useId, useRef, useState, type FormEvent } from "react";
import type { Auth } from "firebase/auth";
import { saveSettings } from "./api";
import type { FollowupSettings, HourRange } from "./types";
import { requestError, useOperationId } from "./useOperation";

const DAYS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira"];

export function SettingsEditor({ auth, settings, onSaved, onCancel }: {
  auth: Auth; settings: FollowupSettings; onSaved: (settings: FollowupSettings) => void; onCancel: () => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState<FollowupSettings>(() => ({ ...settings, queues: settings.queues.map((queue) => ({ ...queue })), contact_hours: Object.fromEntries(Object.entries(settings.contact_hours).map(([day, ranges]) => [day, ranges.map(([start, end]) => [start, end] as HourRange)])), holidays: [...settings.holidays] }));
  const [holiday, setHoliday] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const lock = useRef(false);
  const operationId = useOperationId();

  function changeRanges(day: number, ranges: HourRange[]) {
    setDraft((current) => ({ ...current, contact_hours: { ...current.contact_hours, [String(day)]: ranges } }));
    setSavedMessage("");
  }

  function addHoliday() {
    if (!holiday) return;
    if (!draft.holidays.includes(holiday)) setDraft((current) => ({ ...current, holidays: [...current.holidays, holiday].sort() }));
    setHoliday(""); setSavedMessage("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    setError(""); setSavedMessage("");
    try {
      const labels = draft.queues.map((queue) => queue.label.trim());
      if (labels.some((label) => !label)) throw new Error("Informe os nomes das filas.");
      if (new Set(labels.map((label) => label.toLocaleLowerCase("pt-BR"))).size !== labels.length) throw new Error("Use um nome diferente para cada fila.");
      let rangeCount = 0;
      for (let day = 0; day < 5; day++) {
        const ranges = [...(draft.contact_hours[String(day)] || [])].sort(([a], [b]) => a.localeCompare(b));
        for (let index = 0; index < ranges.length; index++) {
          const [start, end] = ranges[index];
          if (!/^\d{2}:\d{2}$/.test(start) || !/^\d{2}:\d{2}$/.test(end) || start >= end) throw new Error(`Confira a faixa de ${DAYS[day].toLocaleLowerCase("pt-BR")}: início deve ser anterior ao fim.`);
          if (index && ranges[index - 1][1] > start) throw new Error(`Há faixas sobrepostas em ${DAYS[day].toLocaleLowerCase("pt-BR")}.`);
          rangeCount++;
        }
      }
      if (!rangeCount) throw new Error("Configure ao menos uma faixa de contato em dia útil.");
      if (draft.preferred_time && !Object.values(draft.contact_hours).some((ranges) => ranges.some(([start, end]) => start <= draft.preferred_time! && draft.preferred_time! < end))) throw new Error("O horário preferido precisa pertencer a uma faixa de contato.");
      const payload = { ...draft, queues: draft.queues.map((queue) => ({ ...queue, label: queue.label.trim() })), contact_hours: { ...draft.contact_hours, "5": [], "6": [] }, configured: true };
      lock.current = true; setBusy(true);
      const saved = await saveSettings(auth, payload, operationId(payload));
      setDraft(saved); setSavedMessage("Configuração salva. Prazos de tarefas existentes foram preservados.");
      onSaved(saved);
    } catch (reason) { setError(requestError(reason)); }
    finally { lock.current = false; setBusy(false); }
  }

  return <form className="fu-form" onSubmit={submit} aria-label="Configurar dias e horários de follow-up">
    <div className="fu-section-heading"><div><p className="fu-eyebrow">Configuração da clínica</p><h3>Dias e horários de contato</h3></div><button className="fu-button" type="button" disabled={busy} onClick={onCancel}>Voltar às tarefas</button></div>
    <p className="fu-help">Estas faixas orientam contatos de follow-up. O expediente e os avisos da Val são independentes. Fuso: {draft.timezone}.</p>
    {error && <div className="fu-notice fu-notice--danger" role="alert">{error}</div>}
    {savedMessage && <div className="fu-notice fu-notice--success" role="status">{savedMessage}</div>}
    <fieldset disabled={busy}>
      <legend>Filas de trabalho</legend>
      <div className="fu-grid-two">{draft.queues.map((queue, index) => <label className="fu-field" htmlFor={`${id}-queue-${index}`} key={queue.key}><span>Nome da fila {index + 1}</span><input id={`${id}-queue-${index}`} required maxLength={40} value={queue.label} onChange={(event) => { const label = event.target.value; setDraft((current) => ({ ...current, queues: current.queues.map((entry) => entry.key === queue.key ? { ...entry, label } : entry) })); setSavedMessage(""); }} /></label>)}</div>
      <p className="fu-help">Renomear preserva a fila, suas tarefas e o histórico. Não muda setores ou acesso aos contatos.</p>
    </fieldset>
    <fieldset disabled={busy}>
      <legend>Dias e faixas permitidos</legend>
      {DAYS.map((day, dayIndex) => {
        const ranges = draft.contact_hours[String(dayIndex)] || [];
        return <div className="fu-day" key={day}><div className="fu-day-heading"><strong>{day}</strong>{!ranges.length && <span className="fu-muted">Sem contato</span>}<button type="button" className="fu-button" disabled={ranges.length >= 4} onClick={() => changeRanges(dayIndex, [...ranges, ["", ""]])}>Adicionar faixa</button></div>
          {ranges.map(([start, end], rangeIndex) => <div className="fu-time-range" key={rangeIndex}>
            <label htmlFor={`${id}-${dayIndex}-${rangeIndex}-start`}><span>Início</span><input id={`${id}-${dayIndex}-${rangeIndex}-start`} type="time" required value={start} onChange={(event) => changeRanges(dayIndex, ranges.map((range, index) => index === rangeIndex ? [event.target.value, range[1]] : range))} /></label>
            <label htmlFor={`${id}-${dayIndex}-${rangeIndex}-end`}><span>Fim</span><input id={`${id}-${dayIndex}-${rangeIndex}-end`} type="time" required value={end} onChange={(event) => changeRanges(dayIndex, ranges.map((range, index) => index === rangeIndex ? [range[0], event.target.value] : range))} /></label>
            <button type="button" className="fu-button" aria-label={`Remover faixa ${rangeIndex + 1} de ${day}`} onClick={() => changeRanges(dayIndex, ranges.filter((_, index) => index !== rangeIndex))}>Remover</button>
          </div>)}
        </div>;
      })}
      <p className="fu-help">Sábados e domingos permanecem sem contato. Terça, quarta e quinta são uma preferência, sem excluir segunda e sexta.</p>
      <label className="fu-field fu-field--short" htmlFor={`${id}-preferred`}><span>Horário preferido dos atalhos (opcional)</span><input id={`${id}-preferred`} type="time" value={draft.preferred_time || ""} onChange={(event) => { setDraft((current) => ({ ...current, preferred_time: event.target.value || null })); setSavedMessage(""); }} /></label>
    </fieldset>
    <fieldset disabled={busy}>
      <legend>Feriados e recessos</legend>
      <div className="fu-inline"><label className="fu-field" htmlFor={`${id}-holiday`}><span>Data sem contato</span><input id={`${id}-holiday`} type="date" value={holiday} onChange={(event) => setHoliday(event.target.value)} /></label><button type="button" className="fu-button" disabled={!holiday} onClick={addHoliday}>Adicionar data</button></div>
      {draft.holidays.length ? <ul className="fu-holidays">{draft.holidays.map((date) => <li key={date}><span>{date.split("-").reverse().join("/")}</span><button type="button" className="fu-button" aria-label={`Remover data sem contato ${date.split("-").reverse().join("/")}`} onClick={() => { setDraft((current) => ({ ...current, holidays: current.holidays.filter((entry) => entry !== date) })); setSavedMessage(""); }}>Remover</button></li>)}</ul> : <p className="fu-help">Nenhuma data sem contato cadastrada. O calendário não importa feriados automaticamente.</p>}
    </fieldset>
    <p className="fu-notice">Salvar não move prazos, cancela tarefas ou altera o atendimento da Val. Conflitos em tarefas existentes exigem revisão humana.</p>
    <div className="fu-form-actions"><button type="button" className="fu-button" disabled={busy} onClick={onCancel}>Voltar</button><button type="submit" className="fu-button fu-button--primary" disabled={busy}>{busy ? "Salvando…" : "Salvar dias e horários"}</button></div>
  </form>;
}
