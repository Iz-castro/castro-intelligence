import { useId, useRef, useState, type FormEvent } from "react";
import type { Auth } from "firebase/auth";
import { actOnTask, createTask } from "./api";
import { ScheduleField } from "./ScheduleField";
import { FOLLOWUP_TIMEZONE, localInput, localToIso, scheduleProblem } from "./time";
import { TASK_TYPES, type ContactPurpose, type FollowupSettings, type FollowupTask, type QueueDefinition } from "./types";
import { isAccessDenied, requestError, useOperationId } from "./useOperation";

type ContactOption = { id: number; display_name: string; declared_name?: string };
type Props = {
  auth: Auth;
  task?: FollowupTask;
  contactId?: number | null;
  contacts: ContactOption[];
  settings: FollowupSettings | null;
  queues: QueueDefinition[];
  onSaved: (task: FollowupTask) => void;
  onCancel: () => void;
  accessChecking?: boolean;
  onAccessDenied?: (reason: unknown) => void;
};

export function TaskEditor({ auth, task, contactId, contacts, settings, queues, onSaved, onCancel, accessChecking, onAccessDenied }: Props) {
  const id = useId();
  const [chosenContact, setChosenContact] = useState(task?.contact_id || contactId || 0);
  const [type, setType] = useState(task?.type || "retorno");
  const [title, setTitle] = useState(task?.title || "");
  const [description, setDescription] = useState(task?.description || "");
  const [purpose, setPurpose] = useState<ContactPurpose>(task?.contact_purpose || "commercial");
  const [due, setDue] = useState(task ? localInput(task.due_at, settings?.timezone) : "");
  const [queue, setQueue] = useState(task?.queue_key || queues[0]?.key || "reception");
  const [appointment, setAppointment] = useState(task?.appointment_at ? localInput(task.appointment_at, settings?.timezone) : "");
  const [appointmentRef, setAppointmentRef] = useState(task?.appointment_ref || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const operationId = useOperationId();
  const selected = contacts.find((contact) => contact.id === chosenContact);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    setError("");
    try {
      if (!chosenContact) throw new Error("Escolha o contato deste acompanhamento.");
      if (!title.trim()) throw new Error("Informe a ação a realizar.");
      if (appointmentRef && !/^[A-Za-z0-9_.:-]{1,160}$/.test(appointmentRef.trim())) throw new Error("Use uma referência simples do compromisso: letras, números, ponto, hífen, dois-pontos ou sublinhado, sem espaços.");
      if (!task && purpose !== "internal") {
        const problem = scheduleProblem(due, settings);
        if (problem) throw new Error(problem);
      }
      const dueAt = localToIso(due, settings?.timezone || FOLLOWUP_TIMEZONE);
      if (!task && new Date(dueAt).getTime() <= Date.now()) throw new Error("Escolha um próximo prazo futuro. Tentativas já realizadas são registradas no histórico.");
      const appointmentFields = type === "confirmacao_consulta" || type === "lembrete_consulta" ? {
        appointment_at: localToIso(appointment, settings?.timezone), appointment_ref: appointmentRef.trim() || undefined,
      } : {};
      if ("appointment_at" in appointmentFields && new Date(String(appointmentFields.appointment_at)).getTime() <= new Date(dueAt).getTime()) throw new Error("A confirmação ou o lembrete precisa ocorrer antes da consulta. Reagende o prazo primeiro, se necessário.");
      const fields = { title: title.trim(), description: description.trim(), queue_key: queue, ...appointmentFields };
      const body = { ...fields, type, contact_purpose: purpose, due_at: dueAt, queue_key: queue, ...appointmentFields };
      lock.current = true;
      setBusy(true);
      const request = task ? { action: "update", version: task.version, ...fields } : { contact_id: chosenContact, ...body };
      const saved = task
        ? await actOnTask(auth, task.id, { action: "update", version: task.version, ...fields }, operationId(request))
        : await createTask(auth, request, operationId(request));
      onSaved(saved);
    } catch (reason) { if (isAccessDenied(reason)) onAccessDenied?.(reason); setError(requestError(reason)); }
    finally { lock.current = false; setBusy(false); }
  }

  return (
    <form className="fu-form" hidden={accessChecking} onSubmit={submit} aria-label={task ? "Editar tarefa" : "Nova tarefa"}>
      <div className="fu-section-heading"><div><p className="fu-eyebrow">Acompanhamento humano</p><h3>{task ? "Editar tarefa" : "Criar próxima ação"}</h3></div><button type="button" className="fu-button" disabled={busy} onClick={onCancel}>Voltar</button></div>
      {error && <div className="fu-notice fu-notice--danger" role="alert">{error}</div>}
      <fieldset disabled={busy}>
        {task || contactId ? <p className="fu-contact-name">Contato: <strong>{task?.contact?.declared_name || task?.contact?.display_name || selected?.declared_name || selected?.display_name || `Contato #${chosenContact}`}</strong></p> : <label className="fu-field" htmlFor={`${id}-contact`}><span>Contato *</span><select id={`${id}-contact`} required value={chosenContact || ""} onChange={(event) => setChosenContact(Number(event.target.value))}><option value="">Selecione um contato acessível</option>{contacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.declared_name || contact.display_name || `Contato #${contact.id}`}</option>)}</select><small>Também é possível criar a tarefa pelo cartão do contato no CRM.</small></label>}
        <div className="fu-grid-two">
          <label className="fu-field" htmlFor={`${id}-type`}><span>Tipo de ação *</span><select id={`${id}-type`} disabled={Boolean(task)} value={type} onChange={(event) => { setType(event.target.value); if (!task) setPurpose(TASK_TYPES.find((entry) => entry.value === event.target.value)?.purpose || "commercial"); }}>{TASK_TYPES.map((entry) => <option key={entry.value} value={entry.value}>{entry.label}</option>)}{task && !TASK_TYPES.some((entry) => entry.value === task.type) && <option value={task.type}>{task.type}</option>}</select></label>
          <label className="fu-field" htmlFor={`${id}-queue`}><span>Fila de trabalho *</span><select id={`${id}-queue`} value={queue} onChange={(event) => setQueue(event.target.value)}>{queues.filter((entry) => entry.active || entry.key === queue).map((entry) => <option key={entry.key} value={entry.key}>{entry.label}</option>)}</select></label>
        </div>
        <label className="fu-field" htmlFor={`${id}-title`}><span>O que precisa ser feito? *</span><input id={`${id}-title`} required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Ex.: Retornar na data combinada" /></label>
        <label className="fu-field" htmlFor={`${id}-purpose`}><span>Finalidade desta ação *</span><select id={`${id}-purpose`} disabled value={purpose}><option value="commercial">Retomada comercial</option><option value="service">Serviço / consulta já marcada</option><option value="internal">Ação interna, sem contato</option></select><small>A finalidade corresponde ao tipo de ação e não pode ser usada para contornar uma recusa comercial.</small></label>
        {(type === "confirmacao_consulta" || type === "lembrete_consulta") && <>
          <div className="fu-grid-two">
            <label className="fu-field" htmlFor={`${id}-appointment`}><span>Data/hora da consulta no ProDoctor *</span><input id={`${id}-appointment`} type="datetime-local" required value={appointment} onChange={(event) => setAppointment(event.target.value)} /></label>
            <label className="fu-field" htmlFor={`${id}-appointment-ref`}><span>Referência do compromisso (opcional)</span><input id={`${id}-appointment-ref`} maxLength={100} value={appointmentRef} onChange={(event) => setAppointmentRef(event.target.value)} placeholder="Identificador na agenda, sem detalhe clínico" /><small>Use a mesma referência nas duas tarefas para registrar um contato que cumpra confirmação e lembrete.</small></label>
          </div>
          {task && <p className="fu-help">Confira a alteração na agenda oficial. Atualizar este compromisso preserva o prazo e as outras tarefas; revise confirmação/lembrete relacionados separadamente.</p>}
        </>}
        {!task ? <ScheduleField auth={auth} value={due} onChange={setDue} settings={settings} internal={purpose === "internal"} consultation={type === "confirmacao_consulta" || type === "lembrete_consulta"} appointmentValue={appointment} disabled={busy} /> : <p className="fu-help">Para mudar o prazo, use Reagendar. Mudar a fila não transfere o contato ou altera a responsável da tarefa.</p>}
        <label className="fu-field" htmlFor={`${id}-description`}><span>Contexto operacional (opcional)</span><textarea id={`${id}-description`} rows={3} maxLength={300} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Somente o necessário para a colega executar a ação." /><small>Não inclua diagnóstico, sintomas, laudos ou cópias da conversa.</small></label>
      </fieldset>
      <p className="fu-help">A tarefa não envia mensagem, assume atendimento ou altera a disponibilidade da Val. Novas tarefas são compartilhadas na fila.</p>
      <div className="fu-form-actions"><button type="button" className="fu-button" disabled={busy} onClick={onCancel}>Cancelar edição</button><button className="fu-button fu-button--primary" type="submit" disabled={busy}>{busy ? "Salvando…" : task ? "Salvar alterações" : "Criar tarefa"}</button></div>
    </form>
  );
}
