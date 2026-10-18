import { useCallback, useEffect, useRef, useState } from "react";
import type { Auth } from "firebase/auth";
import { ApiError } from "../../api";
import { actOnTask, loadActivities, loadTask, loadTasks } from "./api";
import { PreferenceEditor } from "./PreferenceEditor";
import { ReadOnlyContext } from "./ReadOnlyContext";
import { TaskActionForm, type ActionMode } from "./TaskActionForm";
import { formatMoment, localInput, scheduleProblem } from "./time";
import { EVENT_LABELS, RESULT_LABELS, isCommercialBlocked, taskTypeLabel, type FollowupActivity, type FollowupSettings, type FollowupTask, type QueueDefinition } from "./types";
import { isAccessDenied, requestError, useOperationId } from "./useOperation";
import { useAccessSignal } from "./useAccessSignal";

type Props = {
  auth: Auth; taskId: string; settings: FollowupSettings | null; queues: QueueDefinition[]; currentUserId?: number;
  canManageTeam: boolean; canRegisterPreference: boolean; canReactivatePreference: boolean;
  onChanged: () => void; onEdit: (task: FollowupTask) => void; onSelectTask: (id: string) => void;
  onOpenContact?: (id: number) => void; onBack: () => void;
};

export function TaskDetail({ auth, taskId, settings, queues, currentUserId, canManageTeam, canRegisterPreference, canReactivatePreference, onChanged, onEdit, onSelectTask, onOpenContact, onBack }: Props) {
  const [task, setTask] = useState<FollowupTask | null>(null);
  const [activities, setActivities] = useState<FollowupActivity[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [otherTasks, setOtherTasks] = useState<FollowupTask[]>([]);
  const [othersMore, setOthersMore] = useState(false);
  const [mode, setMode] = useState<ActionMode | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [reload, setReload] = useState(0);
  const [contextOpen, setContextOpen] = useState(false);
  const [checkingAccess, setCheckingAccess] = useState(false);
  const [accessNotice, setAccessNotice] = useState("");
  const lock = useRef(false);
  const sequence = useRef(0);
  const operationId = useOperationId();
  const latestTask = useRef<FollowupTask | null>(null);
  latestTask.current = task;
  const accessSignal = useAccessSignal(task?.contact_id, task?.conversation_id);
  const observedSignal = useRef<string | null>(null);
  const invalidated = useRef(false);
  const preferenceChanged = useCallback((active: boolean) => { setBlocked(active); }, []);
  const invalidateAccess = useCallback((reason: unknown) => {
    sequence.current++; setTask(null); setActivities([]); setOtherTasks([]); setContextOpen(false); setMode(null); setCheckingAccess(false); setError(requestError(reason));
    if (!invalidated.current) { invalidated.current = true; onChanged(); }
  }, [onChanged]);

  useEffect(() => {
    const request = ++sequence.current;
    let cancelled = false;
    setLoading(true); setCheckingAccess(false); setTask(null); setActivities([]); setOtherTasks([]); setError(""); setHistoryError(""); setMode(null); setHistoryCursor(null); setOthersMore(false);
    void loadTask(auth, taskId).then(async (value) => {
      if (cancelled || sequence.current !== request) return;
      setTask(value); setBlocked(isCommercialBlocked(value)); setLoading(false);
      const [history, related] = await Promise.allSettled([
        loadActivities(auth, taskId),
        loadTasks(auth, { contact_id: value.contact_id, group: "all" }),
      ]);
      if (cancelled || sequence.current !== request) return;
      if (history.status === "fulfilled") { setActivities(history.value.items); setHistoryCursor(history.value.next_cursor || null); }
      else if (isAccessDenied(history.reason)) { invalidateAccess(history.reason); return; }
      else setHistoryError(requestError(history.reason));
      if (related.status === "fulfilled") { setOtherTasks(related.value.items.filter((entry) => entry.id !== taskId)); setOthersMore(Boolean(related.value.next_cursor)); }
      else if (isAccessDenied(related.reason)) { invalidateAccess(related.reason); return; }
      else setHistoryError((current) => [current, "Não foi possível consultar as outras pendências do contato."].filter(Boolean).join(" "));
    }).catch((reason) => {
      if (!cancelled && sequence.current === request) { setError(requestError(reason)); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, [auth, taskId, reload, invalidateAccess]);

  const hasTask = Boolean(task);
  useEffect(() => {
    if (!hasTask) return;
    let cancelled = false;
    let checking = false;
    const metadataChanged = observedSignal.current !== null && observedSignal.current !== accessSignal;
    observedSignal.current = accessSignal;
    async function checkAccess(hideWhileChecking = false) {
      if (checking || document.visibilityState !== "visible") return;
      checking = true;
      const request = sequence.current;
      if (hideWhileChecking) setCheckingAccess(true);
      try {
        const fresh = await loadTask(auth, taskId);
        if (cancelled || request !== sequence.current) return;
        if (fresh.version !== latestTask.current?.version) {
          setMode(null); setContextOpen(false); setAccessNotice("A tarefa foi alterada. Os dados foram atualizados; revise antes de continuar."); setReload((value) => value + 1);
        } else {
          setTask(fresh);
          if (fresh.can_modify === false) { setMode(null); setAccessNotice("A responsabilidade ou a permissão mudou. Consulte a gestão para alterar esta tarefa."); }
        }
      } catch (reason) {
        if (cancelled || request !== sequence.current) return;
        if (hideWhileChecking || (reason instanceof ApiError && [401, 403, 404].includes(reason.status))) {
          sequence.current++;
          setTask(null); setActivities([]); setOtherTasks([]); setContextOpen(false); setMode(null); setError(requestError(reason));
          if (!invalidated.current) { invalidated.current = true; onChanged(); }
        } else setAccessNotice("Não foi possível revalidar os dados agora. Atualize antes de continuar.");
      } finally {
        checking = false;
        if (!cancelled) setCheckingAccess(false);
      }
    }
    if (metadataChanged) { setCheckingAccess(true); void checkAccess(true); }
    const timer = window.setInterval(() => void checkAccess(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [auth, taskId, hasTask, accessSignal, onChanged]);

  async function simpleAction(action: string) {
    if (!task || lock.current) return;
    lock.current = true; setBusy(true); setError("");
    const payload = { action, version: task.version };
    try { await actOnTask(auth, task.id, payload, operationId({ task_id: task.id, ...payload })); onChanged(); setReload((value) => value + 1); }
    catch (reason) { if (isAccessDenied(reason)) invalidateAccess(reason); else setError(requestError(reason)); }
    finally { lock.current = false; setBusy(false); }
  }

  async function moreHistory() {
    if (!historyCursor || historyBusy) return;
    const request = sequence.current;
    setHistoryBusy(true); setHistoryError("");
    try {
      const page = await loadActivities(auth, taskId, historyCursor);
      if (request !== sequence.current) return;
      setActivities((current) => [...current, ...page.items.filter((entry) => !current.some((existing) => existing.id === entry.id))]);
      setHistoryCursor(page.next_cursor || null);
    } catch (reason) { if (request === sequence.current) { if (isAccessDenied(reason)) invalidateAccess(reason); else setHistoryError(requestError(reason)); } }
    finally { if (request === sequence.current) setHistoryBusy(false); }
  }

  if (loading) return <div className="fu-empty" role="status">Carregando tarefa…</div>;
  if (!task) return <div className="fu-form"><p className="fu-notice fu-notice--danger" role="alert">{error || "Não foi possível carregar esta tarefa."}</p><div className="fu-inline"><button className="fu-button" onClick={onBack}>Voltar à lista</button><button className="fu-button" onClick={() => setReload((value) => value + 1)}>Tentar novamente</button></div></div>;

  const canModify = task.can_modify ?? task.can_edit ?? task.can_manage ?? (canManageTeam || !task.assignee_user_id || task.assignee_user_id === currentUserId);
  const inQueue = task.assignment_mode === "queue" || !task.assignee_user_id;
  const pending = task.status === "pending";
  const contactName = task.contact?.declared_name || task.contact?.display_name || `Contato #${task.contact_id}`;
  const commercialBlocked = blocked && task.contact_purpose === "commercial";
  const conflict = pending && task.contact_purpose !== "internal" ? scheduleProblem(localInput(task.due_at, settings?.timezone), settings) : "";
  const queueName = queues.find((entry) => entry.key === task.queue_key)?.label || task.queue_key;

  return <div className="fu-detail">
    {checkingAccess && <p className="fu-help" role="status">Revalidando o acesso ao contato…</p>}
    <div hidden={checkingAccess}>
    {accessNotice && <p className="fu-notice fu-notice--warning" role="status">{accessNotice}</p>}
    <div className="fu-section-heading"><div><p className="fu-eyebrow">{contactName}</p><h3>{task.title}</h3></div><button className="fu-button" type="button" disabled={busy} onClick={() => setReload((value) => value + 1)}>Atualizar</button></div>
    {error && <p className="fu-notice fu-notice--danger" role="alert">{error}</p>}
    <div className="fu-tags"><span className={`fu-tag ${task.status === "pending" && new Date(task.due_at).getTime() < Date.now() ? "fu-tag--warning" : ""}`}>{task.status === "completed" ? "Concluída" : task.status === "cancelled" ? "Cancelada" : new Date(task.due_at).getTime() < Date.now() ? "Atrasada" : "Pendente"}</span><span className="fu-tag">{taskTypeLabel(task.type)}</span><span className="fu-tag">{task.contact_purpose === "commercial" ? "Comercial" : task.contact_purpose === "service" ? "Serviço" : "Interna"}</span>{task.contact?.lead_temperature && <span className="fu-tag">Interesse IA: {task.contact.lead_temperature}</span>}</div>
    <dl className="fu-meta"><div><dt>Prazo</dt><dd>{formatMoment(task.due_at, settings?.timezone)}</dd></div><div><dt>Fila</dt><dd>{queueName}</dd></div><div><dt>Responsável pela tarefa</dt><dd>{inQueue ? "Compartilhada na fila" : task.assignee_name || (task.assignee_user_id === currentUserId ? "Você" : `Pessoa #${task.assignee_user_id}`)}</dd></div><div><dt>Tentativas realizadas</dt><dd>{task.attempt_count ?? "Consulte o histórico"}</dd></div>{task.appointment_at && <div><dt>Consulta na agenda oficial</dt><dd>{formatMoment(task.appointment_at, settings?.timezone)}</dd></div>}</dl>
    {task.description && <p className="fu-description">{task.description}</p>}
    {task.response_received && <p className="fu-notice fu-notice--success" role="status">{task.response_label || "Paciente respondeu após a referência desta tarefa."} A tarefa permanece pendente até decisão humana.</p>}
    {(conflict || task.calendar_conflict) && <p className="fu-notice fu-notice--warning">O prazo conflita com o calendário atual. Revise com a equipe; o prazo existente foi preservado.{conflict && <span>{conflict}</span>}</p>}
    {commercialBlocked && <p className="fu-notice fu-notice--warning"><strong>Não executar nova retomada comercial.</strong><span>A preferência do paciente impede novas abordagens. Revise esta pendência sem cancelar consultas ou outras tarefas.</span></p>}
    <div className="fu-inline"><button type="button" className="fu-button" aria-expanded={contextOpen} onClick={() => setContextOpen((value) => !value)}>{contextOpen ? "Recolher contexto" : "Consultar contexto do contato"}</button>{onOpenContact && <button type="button" className="fu-button" onClick={() => onOpenContact(task.contact_id)}>Abrir contato no CRM</button>}</div>
    {contextOpen && <ReadOnlyContext auth={auth} contactId={task.contact_id} conversationId={task.conversation_id} />}
    <p className="fu-help">Responsabilidade da tarefa é separada da posse do contato e do atendimento. Consultar ou registrar a tarefa não assume a conversa nem muda a Val.</p>
    {pending && !mode && <div className="fu-actions" aria-label="Ações da tarefa">
      {inQueue && canModify && !commercialBlocked && <button className="fu-button fu-button--primary" type="button" disabled={busy} onClick={() => void simpleAction("take")}>Pegar tarefa</button>}
      {canModify && !inQueue && <button className="fu-button" type="button" disabled={busy} onClick={() => void simpleAction("return_to_queue")}>Devolver à fila</button>}
      {canModify && !commercialBlocked && <><button className="fu-button" type="button" onClick={() => setMode("attempt")}>Registrar tentativa</button><button className="fu-button" type="button" onClick={() => setMode("reschedule")}>Reagendar</button><button className="fu-button" type="button" onClick={() => setMode("complete")}>Concluir objetivo</button><button className="fu-button" type="button" onClick={() => onEdit(task)}>Editar contexto</button></>}
      {canModify && canManageTeam && <button className="fu-button" type="button" onClick={() => setMode("assign")}>Redistribuir tarefa</button>}
      {canModify && task.contact_purpose === "commercial" && <button className="fu-button" type="button" onClick={() => setMode("refuse_specific")}>Encerrar este acompanhamento</button>}
      {canModify && <button className="fu-button fu-button--danger" type="button" onClick={() => setMode("cancel")}>Cancelar tarefa</button>}
      {!canModify && <p className="fu-help">Esta tarefa está com outra pessoa. A gestão autorizada pode redistribuir respeitando o acesso ao contato.</p>}
    </div>}
    {mode && <TaskActionForm key={`${task.id}-${task.version}-${mode}`} auth={auth} task={task} mode={mode} settings={settings} queues={queues} otherTasks={otherTasks} onCancel={() => setMode(null)} onAccessDenied={invalidateAccess} onSaved={() => { setMode(null); onChanged(); setReload((value) => value + 1); }} />}
    <PreferenceEditor auth={auth} contactId={task.contact_id} canRegister={canRegisterPreference} canReactivate={canReactivatePreference} onChanged={preferenceChanged} onAccessDenied={invalidateAccess} />
    <section className="fu-related"><h4>Outras pendências do contato</h4>{otherTasks.length ? <ul>{[...otherTasks].sort((left, right) => left.due_at.localeCompare(right.due_at) || left.id.localeCompare(right.id)).map((entry) => <li key={entry.id}><button className="fu-related-task" type="button" onClick={() => onSelectTask(entry.id)}><strong>{entry.title}</strong><span>{formatMoment(entry.due_at, settings?.timezone)}</span></button></li>)}</ul> : <p className="fu-help">Nenhuma outra pendência acessível nesta consulta.</p>}{othersMore && <p className="fu-help">Há mais pendências. Consulte a lista do contato para continuar a navegação.</p>}</section>
    <section className="fu-history"><h4>Histórico da tarefa</h4>{historyError && <p className="fu-notice fu-notice--danger" role="alert">{historyError}</p>}{!activities.length && !historyError && <p className="fu-help">Carregando histórico ou nenhum evento acessível.</p>}<ol>{activities.map((activity) => <HistoryEntry key={activity.id} activity={activity} timezone={settings?.timezone} />)}</ol>{historyCursor && <button type="button" className="fu-button" disabled={historyBusy} onClick={() => void moreHistory()}>{historyBusy ? "Carregando…" : "Carregar mais histórico"}</button>}</section>
    </div>
  </div>;
}

function HistoryEntry({ activity, timezone }: { activity: FollowupActivity; timezone?: string }) {
  const data = activity.data || {};
  const result = typeof data.result === "string" ? data.result : typeof data.result_code === "string" ? data.result_code : "";
  const changedDue = typeof data.due_at === "string" ? data.due_at : typeof data.new_due_at === "string" ? data.new_due_at : "";
  const kind = typeof data.appointment_kind === "string" ? data.appointment_kind : typeof data.scheduled_kind === "string" ? data.scheduled_kind : "";
  return <li><span className="fu-history-dot" aria-hidden="true" /><div><strong>{EVENT_LABELS[activity.event_type] || "Alteração registrada"}</strong><p>{formatMoment(activity.occurred_at || activity.recorded_at, timezone)} · {activity.actor_name || activity.actor_display_name || (activity.actor_user_id ? `Pessoa #${activity.actor_user_id}` : "Equipe")}</p>{result && <p>{RESULT_LABELS[result] || "Resultado registrado"}</p>}{kind && <p>{kind === "consultation" ? "Nova consulta" : kind === "procedure" ? "Procedimento / tratamento" : "Categoria de compromisso registrada"}</p>}{changedDue && <p>Próximo prazo: {formatMoment(changedDue, timezone)}</p>}{typeof data.reason === "string" && <p>{data.reason}</p>}{activity.recorded_at && activity.occurred_at && activity.recorded_at.slice(0, 16) !== activity.occurred_at.slice(0, 16) && <small>Registrado em {formatMoment(activity.recorded_at, timezone)}</small>}{typeof data.attempt_id === "string" && activity.event_type !== "task_attempted" && <small>Vinculada a uma tentativa já registrada.</small>}</div></li>;
}
