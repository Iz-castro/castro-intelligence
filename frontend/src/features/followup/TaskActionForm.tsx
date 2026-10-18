import { useId, useRef, useState, type FormEvent } from "react";
import type { Auth } from "firebase/auth";
import { actOnTask } from "./api";
import { ScheduleField } from "./ScheduleField";
import { formatMoment, localInput, localToIso, scheduleProblem } from "./time";
import { RESULT_LABELS, type ActionBody, type FollowupSettings, type FollowupTask, type QueueDefinition } from "./types";
import { isAccessDenied, requestError, useOperationId } from "./useOperation";

export type ActionMode = "reschedule" | "attempt" | "complete" | "cancel" | "refuse_specific" | "assign";
const TITLES: Record<ActionMode, string> = { reschedule: "Reagendar sem registrar tentativa", attempt: "Registrar tentativa realizada", complete: "Concluir o objetivo desta tarefa", cancel: "Cancelar esta tarefa", refuse_specific: "Encerrar este acompanhamento", assign: "Alterar responsável da tarefa" };

export function TaskActionForm({ auth, task, mode, settings, queues, otherTasks, onSaved, onCancel, onAccessDenied }: {
  auth: Auth; task: FollowupTask; mode: ActionMode; settings: FollowupSettings | null; queues: QueueDefinition[]; otherTasks: FollowupTask[];
  onSaved: (task: FollowupTask) => void; onCancel: () => void;
  onAccessDenied?: (reason: unknown) => void;
}) {
  const id = useId();
  const [due, setDue] = useState("");
  const [occurredAt, setOccurredAt] = useState(() => localInput(new Date(), settings?.timezone));
  const [method, setMethod] = useState("phone");
  const [result, setResult] = useState(mode === "attempt" ? "not_reached" : "action_done");
  const [finish, setFinish] = useState<"pending" | "reschedule" | "complete">("reschedule");
  const [appointmentKind, setAppointmentKind] = useState("");
  const [keepAssigned, setKeepAssigned] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [reason, setReason] = useState("");
  const [assignee, setAssignee] = useState(task.assignee_user_id ? String(task.assignee_user_id) : "");
  const [sharedTask, setSharedTask] = useState("");
  const [performed, setPerformed] = useState(false);
  const [bothPerformed, setBothPerformed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const operationId = useOperationId();
  const scheduling = mode === "reschedule" || (mode === "attempt" && finish === "reschedule");
  const completing = mode === "complete" || (mode === "attempt" && finish === "complete");
  const unanswered = task.unanswered_attempts ?? task.unanswered_attempt_count ?? 0;
  const reviewNeeded = Boolean(task.review_required || unanswered + (mode === "attempt" && result === "not_reached" ? 1 : 0) >= 3);
  const needsReviewConfirmation = (mode === "attempt" && (task.review_required || unanswered >= 3)) || (scheduling && reviewNeeded);
  const confirmation = task.type === "confirmacao_consulta";
  const pairCandidates = otherTasks.filter((entry) => entry.id !== task.id && entry.status === "pending" &&
    entry.contact_id === task.contact_id && Boolean(task.appointment_ref) && entry.appointment_at && entry.appointment_at === task.appointment_at &&
    (entry.appointment_ref || "") === (task.appointment_ref || "") &&
    ((task.type === "confirmacao_consulta" && entry.type === "lembrete_consulta") || (task.type === "lembrete_consulta" && entry.type === "confirmacao_consulta")) && entry.can_modify !== false &&
    (entry.due_at === task.due_at || (new Date(entry.due_at).getTime() <= Date.now() && new Date(task.due_at).getTime() <= Date.now())));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    setError("");
    try {
      const body: ActionBody = { action: mode, version: task.version };
      if (mode === "attempt") {
        body.occurred_at = localToIso(occurredAt, settings?.timezone);
        if (new Date(String(body.occurred_at)).getTime() > Date.now()) throw new Error("Uma tentativa não pode ter data futura.");
        body.result = result; body.method = method;
        if (result === "scheduled") { if (!appointmentKind) throw new Error("Informe se foi marcada consulta ou procedimento/tratamento."); body.appointment_kind = appointmentKind; }
        body.complete = finish === "complete";
        if (completing && result === "not_reached") throw new Error("Sem resposta mantém o acompanhamento pendente. Escolha reagendar ou manter a tarefa aberta.");
      }
      if (needsReviewConfirmation) {
        if (!reviewed) throw new Error("Revise o histórico e a abordagem antes de continuar após três tentativas sem resposta.");
        body.reviewed_after_three = true;
      }
      if (scheduling) {
        if (task.contact_purpose !== "internal") {
          const problem = scheduleProblem(due, settings);
          if (problem) throw new Error(problem);
        }
        const dueAt = localToIso(due, settings?.timezone);
        if (new Date(dueAt).getTime() <= Date.now()) throw new Error("Escolha um próximo prazo futuro.");
        body[mode === "attempt" ? "next_due_at" : "due_at"] = dueAt;
        body.keep_assigned = keepAssigned;
        if (reviewNeeded && !reviewed) throw new Error("Revise o histórico e a abordagem antes de continuar após três tentativas sem resposta.");
        if (reviewed) body.reviewed_after_three = true;
      }
      if (completing) {
        if (!performed) throw new Error("Confirme que o objetivo desta tarefa foi efetivamente cumprido.");
        body.result = result;
        if (result === "scheduled") {
          if (!appointmentKind) throw new Error("Informe se foi marcada consulta ou procedimento/tratamento.");
          body.appointment_kind = appointmentKind;
        }
        if (sharedTask && mode === "attempt") {
          const paired = pairCandidates.find((entry) => entry.id === sharedTask);
          if (!paired || !bothPerformed) throw new Error("Confira o mesmo compromisso na agenda e confirme que as duas ações foram efetivamente cumpridas.");
          body.shared_task_ids = [paired.id];
          body.shared_task_versions = { [paired.id]: paired.version };
          body.shared_actions_confirmed = true;
        }
      }
      if (mode === "cancel") {
        if (!reason.trim()) throw new Error("Informe um motivo operacional curto.");
        body.reason = reason.trim();
      }
      if (mode === "refuse_specific" && !performed) throw new Error("Confirme que a recusa se limita a este acompanhamento.");
      if (mode === "assign") {
        body.assignee_user_id = assignee ? Number(assignee) : null;
      }
      lock.current = true; setBusy(true);
      onSaved(await actOnTask(auth, task.id, body, operationId({ task_id: task.id, ...body })));
    } catch (cause) { if (isAccessDenied(cause)) onAccessDenied?.(cause); setError(requestError(cause)); }
    finally { lock.current = false; setBusy(false); }
  }

  return <form className="fu-action-form" onSubmit={submit} aria-label={TITLES[mode]}>
    <div className="fu-section-heading"><h4>{TITLES[mode]}</h4><button type="button" className="fu-button" disabled={busy} onClick={onCancel}>Voltar</button></div>
    {error && <div className="fu-notice fu-notice--danger" role="alert">{error}</div>}
    <fieldset disabled={busy}>
      {mode === "attempt" && <>
        <div className="fu-grid-two"><label className="fu-field" htmlFor={`${id}-when`}><span>Quando tentou efetivamente *</span><input id={`${id}-when`} required type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} /></label><label className="fu-field" htmlFor={`${id}-method`}><span>Meio de contato</span><select id={`${id}-method`} value={method} onChange={(event) => setMethod(event.target.value)}><option value="phone">Ligação</option><option value="whatsapp">WhatsApp</option><option value="other">Outro</option></select></label></div>
        <p className="fu-help">Registre somente o contato realmente feito por você. O registro não envia mensagens.</p>
      </>}
      {(mode === "attempt" || mode === "complete") && <label className="fu-field" htmlFor={`${id}-result`}><span>Resultado observado *</span><select id={`${id}-result`} value={result} onChange={(event) => { setResult(event.target.value); if (event.target.value === "not_reached" && finish === "complete") setFinish("reschedule"); setPerformed(false); setBothPerformed(false); }}>{Object.entries(RESULT_LABELS).filter(([key]) => ["action_done", "customer_replied", "scheduled", ...(mode === "attempt" ? ["not_reached"] : [])].includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
      {result === "scheduled" && (mode === "attempt" || mode === "complete") && <label className="fu-field" htmlFor={`${id}-kind`}><span>O que foi marcado? *</span><select id={`${id}-kind`} required value={appointmentKind} onChange={(event) => setAppointmentKind(event.target.value)}><option value="">Selecione</option><option value="consultation">Nova consulta</option><option value="procedure">Procedimento / tratamento</option></select><small>A equipe verifica a agenda oficial. Agendar não comprova contratação ou pagamento.</small></label>}
      {mode === "attempt" && <label className="fu-field" htmlFor={`${id}-finish`}><span>Próxima ação</span><select id={`${id}-finish`} value={finish} onChange={(event) => { setFinish(event.target.value as typeof finish); setPerformed(false); }}><option value="reschedule">Registrar e reagendar a mesma tarefa</option><option value="pending">Somente registrar; manter pendente</option>{result !== "not_reached" && <option value="complete">Registrar e concluir o objetivo resolvido</option>}</select><small>Registrar sem resposta não encerra o acompanhamento.</small></label>}
      {needsReviewConfirmation && <div className="fu-notice fu-notice--warning"><strong>Revise o histórico e a abordagem antes de continuar.</strong><span>Três tentativas sem resposta não encerram a tarefa ou exigem aprovação da gestora.</span><label className="fu-check" htmlFor={`${id}-review`}><input id={`${id}-review`} type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} /><span>Revisei o histórico e a abordagem para continuar este acompanhamento.</span></label></div>}
      {scheduling && <>
        <ScheduleField auth={auth} value={due} onChange={setDue} settings={settings} internal={task.contact_purpose === "internal"} consultation={task.type === "confirmacao_consulta" || task.type === "lembrete_consulta"} appointmentValue={task.appointment_at ? localInput(task.appointment_at, settings?.timezone) : undefined} />
        <label className="fu-check" htmlFor={`${id}-keep`}><input id={`${id}-keep`} type="checkbox" checked={keepAssigned} onChange={(event) => setKeepAssigned(event.target.checked)} /><span>Manter comigo (exceção)</span></label>
        <p className="fu-help">Padrão: devolver à fila ao reagendar. Isso altera somente a tarefa, sem transferir o contato, encerrar atendimento ou liberar a Val.</p>
      </>}
      {completing && <>
        <label className="fu-check" htmlFor={`${id}-performed`}><input id={`${id}-performed`} type="checkbox" checked={performed} onChange={(event) => setPerformed(event.target.checked)} /><span>{confirmation ? "Obtive a confirmação do paciente para esta consulta e o objetivo está cumprido." : "O objetivo desta tarefa foi efetivamente cumprido."}</span></label>
        <p className="fu-help">Uma tentativa sem resposta ou uma pergunta sem retorno não confirma presença. Concluir esta tarefa preserva os demais objetivos e o Ganho financeiro.</p>
        {mode === "attempt" && pairCandidates.length > 0 && result !== "not_reached" && <div className="fu-shared">
          <label className="fu-field" htmlFor={`${id}-shared`}><span>Mesmo contato cumpriu também confirmação/lembrete?</span><select id={`${id}-shared`} value={sharedTask} onChange={(event) => { setSharedTask(event.target.value); setBothPerformed(false); }}><option value="">Concluir somente esta tarefa</option>{pairCandidates.map((entry) => <option key={entry.id} value={entry.id}>{entry.title} — {formatMoment(entry.due_at, settings?.timezone)}</option>)}</select></label>
          {sharedTask && <label className="fu-check" htmlFor={`${id}-both`}><input id={`${id}-both`} type="checkbox" checked={bothPerformed} onChange={(event) => setBothPerformed(event.target.checked)} /><span>Conferi o mesmo compromisso no ProDoctor e as duas ações foram efetivamente cumpridas neste contato, na situação de última hora ou coincidência após ajuste de calendário.</span></label>}
          <p className="fu-help">Uma tentativa real e duas conclusões humanas, com histórico preservado. Lembrete ainda futuro de outro caso continua pendente.</p>
        </div>}
      </>}
      {(mode === "cancel" || mode === "refuse_specific") && <>
        <p className="fu-notice">{mode === "refuse_specific" ? "Registre que o paciente recusou apenas este orçamento ou acompanhamento. Outras tarefas, consultas e preferências do contato serão preservadas." : "Cancela somente esta tarefa e preserva o histórico. Não encerra o paciente ou outras tarefas."}</p>
        {mode === "cancel" ? <label className="fu-field" htmlFor={`${id}-reason`}><span>Motivo operacional *</span><input id={`${id}-reason`} required maxLength={120} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: Ação deixou de ser necessária" /><small>Sem dados clínicos ou cópias de mensagens.</small></label> : <label className="fu-check" htmlFor={`${id}-specific`}><input id={`${id}-specific`} type="checkbox" checked={performed} onChange={(event) => setPerformed(event.target.checked)} /><span>O paciente recusou somente este orçamento ou acompanhamento, sem pedir o fim de todos os contatos comerciais.</span></label>}
      </>}
      {mode === "assign" && <>
        <p className="fu-help">Fila de origem: <strong>{queues.find((entry) => entry.key === task.queue_key)?.label || task.queue_key}</strong>. Para mudar a fila, use Editar contexto.</p>
        <label className="fu-field" htmlFor={`${id}-assignee`}><span>Responsável somente pela tarefa</span><select id={`${id}-assignee`} value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">Devolver à fila compartilhada</option>{(task.eligible_assignees || []).map((entry) => <option key={entry.id} value={entry.id}>{entry.display_name}</option>)}</select></label>
        <p className="fu-help">A lista contém pessoas elegíveis para este contato. Atribuir tarefa não concede acesso nem transfere o atendimento ou a posse do contato.</p>
      </>}
    </fieldset>
    <div className="fu-form-actions"><button className="fu-button" type="button" disabled={busy} onClick={onCancel}>Voltar</button><button className={`fu-button ${mode === "cancel" || mode === "refuse_specific" ? "fu-button--danger" : "fu-button--primary"}`} type="submit" disabled={busy}>{busy ? "Salvando…" : "Confirmar registro"}</button></div>
  </form>;
}
