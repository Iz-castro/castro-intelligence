import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useCrm } from "../../context/CrmContext";
import { loadSettings, loadTask, loadTasks } from "./api";
import { SettingsEditor } from "./SettingsEditor";
import { TaskDetail } from "./TaskDetail";
import { TaskEditor } from "./TaskEditor";
import { formatMoment } from "./time";
import { VIEW_LABELS, isCommercialBlocked, taskTypeLabel, type FollowupSettings, type FollowupTask, type TaskScope, type TaskView } from "./types";
import { requestError } from "./useOperation";
import "./followup.css";

export type FollowupPanelProps = {
  contactId?: number | null;
  onClose: () => void;
  onOpenContact?: (id: number) => void;
  canManageSettings: boolean;
  canManageTeam: boolean;
};

export function FollowupPanel({ contactId, onClose, onOpenContact, canManageSettings, canManageTeam }: FollowupPanelProps) {
  const { bundle, sessionUser, contacts, contactsById, conversations, can } = useCrm();
  const id = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [settings, setSettings] = useState<FollowupSettings | null>(null);
  const [settingsError, setSettingsError] = useState("");
  const [view, setView] = useState<TaskView>(contactId ? "all" : "overdue");
  const [scope, setScope] = useState<TaskScope>(contactId ? "contact" : "queue");
  const [queue, setQueue] = useState("");
  const [items, setItems] = useState<FollowupTask[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [moreBusy, setMoreBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [editor, setEditor] = useState<"new" | FollowupTask | null>(null);
  const [editorAccessChecking, setEditorAccessChecking] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [accessRefresh, setAccessRefresh] = useState(0);
  const sequence = useRef(0);
  const moreLock = useRef(false);
  const auth = bundle?.auth;
  const ownershipSignal = JSON.stringify([
    contacts.map((entry) => [entry.id, entry.assigned_to, entry.assigned_to_uid, entry.is_archived]).sort((left, right) => String(left[0]).localeCompare(String(right[0]))),
    conversations.map((entry) => [entry.id, entry.assigned_to, entry.assigned_to_uid]).sort((left, right) => String(left[0]).localeCompare(String(right[0]))),
  ]);
  const previousOwnership = useRef(ownershipSignal);

  useEffect(() => {
    if (previousOwnership.current === ownershipSignal) return;
    previousOwnership.current = ownershipSignal;
    sequence.current++; setItems([]);
    const timer = window.setTimeout(() => setAccessRefresh((value) => value + 1), 150);
    return () => window.clearTimeout(timer);
  }, [ownershipSignal]);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onCloseRef.current(); }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex='0']")).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) { event.preventDefault(); panelRef.current.focus(); return; }
      const first = focusable[0]; const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !panelRef.current.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !panelRef.current.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    }
    const panel = panelRef.current;
    panel?.addEventListener("keydown", handleKey);
    return () => { panel?.removeEventListener("keydown", handleKey); if (previous?.isConnected) previous.focus(); };
  }, []);

  useEffect(() => {
    if (!auth) return;
    let cancelled = false;
    void loadSettings(auth).then((value) => { if (!cancelled) { setSettings(value); setSettingsError(""); } }).catch((reason) => { if (!cancelled) setSettingsError(requestError(reason)); });
    return () => { cancelled = true; };
  }, [auth, refresh]);

  useEffect(() => {
    if (!auth || !editor || editor === "new") return;
    const editorId = editor.id;
    let cancelled = false;
    let checking = false;
    setEditorAccessChecking(true);
    async function validateEditor() {
      if (checking || document.visibilityState !== "visible") return;
      checking = true;
      try {
        const current = await loadTask(auth!, editorId);
        if (!cancelled && current.can_modify === false) { setEditor(null); setSelectedTaskId(null); setError("A tarefa mudou de responsável ou saiu do seu acesso. Atualize a lista para continuar."); }
      } catch (reason) { if (!cancelled) { setEditor(null); setSelectedTaskId(null); setError(requestError(reason)); } }
      finally { checking = false; if (!cancelled) setEditorAccessChecking(false); }
    }
    void validateEditor();
    const timer = window.setInterval(() => void validateEditor(), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [auth, editor, refresh, ownershipSignal]);

  useEffect(() => {
    setScope(contactId ? "contact" : "queue"); setView(contactId ? "all" : "overdue"); setSelectedTaskId(null); setEditor(null); setSettingsOpen(false);
  }, [contactId]);

  useEffect(() => {
    if (!canManageTeam && scope === "team") setScope(contactId ? "contact" : "queue");
    if (!canManageSettings) setSettingsOpen(false);
  }, [canManageTeam, canManageSettings, scope, contactId]);

  useEffect(() => {
    if (!auth) return;
    let cancelled = false;
    const request = ++sequence.current;
    setLoading(true); setItems([]); setNextCursor(null); setError("");
    void loadTasks(auth, { view, scope, queue_key: queue, contact_id: contactId }).then((page) => {
      if (!cancelled && sequence.current === request) { setItems(page.items); setNextCursor(page.next_cursor || null); }
    }).catch((reason) => { if (!cancelled && sequence.current === request) setError(requestError(reason)); })
      .finally(() => { if (!cancelled && sequence.current === request) setLoading(false); });
    return () => { cancelled = true; };
  }, [auth, view, scope, queue, contactId, refresh, accessRefresh]);

  useEffect(() => {
    if (!auth) return;
    let cancelled = false;
    let polling = false;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || moreLock.current || polling) return;
      polling = true;
      const request = ++sequence.current;
      void loadTasks(auth, { view, scope, queue_key: queue, contact_id: contactId }).then((page) => {
        if (!cancelled && request === sequence.current) { setItems(page.items); setNextCursor(page.next_cursor || null); }
      }).catch((reason) => { if (!cancelled && request === sequence.current) { sequence.current++; setItems([]); setNextCursor(null); setError(requestError(reason)); } }).finally(() => { polling = false; });
    }, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [auth, view, scope, queue, contactId]);

  useEffect(() => {
    function refreshOnFocus() { if (document.visibilityState === "visible") setRefresh((value) => value + 1); }
    document.addEventListener("visibilitychange", refreshOnFocus);
    return () => document.removeEventListener("visibilitychange", refreshOnFocus);
  }, []);

  async function loadMore() {
    if (!auth || !nextCursor || moreLock.current) return;
    const request = ++sequence.current;
    moreLock.current = true; setMoreBusy(true); setError("");
    try {
      const page = await loadTasks(auth, { view, scope, queue_key: queue, contact_id: contactId, cursor: nextCursor });
      if (request !== sequence.current) return;
      setItems((current) => [...current, ...page.items.filter((entry) => !current.some((existing) => existing.id === entry.id))]);
      setNextCursor(page.next_cursor || null);
    } catch (reason) { if (request === sequence.current) { sequence.current++; setItems([]); setNextCursor(null); setError(requestError(reason)); } }
    finally { moreLock.current = false; setMoreBusy(false); }
  }

  const changed = useCallback(() => { setRefresh((value) => value + 1); }, []);
  const queues = settings?.queues || [];
  const contact = contactId ? contactsById.get(contactId) : null;
  const detailVisible = Boolean(selectedTaskId || editor || settingsOpen);

  function selectTask(taskId: string) { setSelectedTaskId(taskId); setEditor(null); setSettingsOpen(false); setNotice(""); }
  function saved(task: FollowupTask) { setEditor(null); setSelectedTaskId(task.id); setNotice("Tarefa salva. Nenhuma mensagem foi enviada."); changed(); }
  function back() { setSelectedTaskId(null); setEditor(null); setSettingsOpen(false); }

  return <div className="fu-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={`fu-panel ${detailVisible ? "fu-panel--detail" : ""}`} role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-subtitle`} tabIndex={-1} ref={panelRef}>
      <header className="fu-header"><div><p className="fu-eyebrow">Castro Intelligence CRM</p><h2 id={`${id}-title`}>Follow-up</h2><p id={`${id}-subtitle`}>Próxima ação, equipe e histórico no mesmo lugar.</p></div><button type="button" className="fu-close" ref={closeRef} onClick={onClose} aria-label="Fechar follow-up">✕</button></header>
      {!auth ? <p className="fu-empty" role="status">Aguardando a sessão autenticada…</p> : <>
        <div className="fu-toolbar"><div className="fu-context-title">{contactId ? <><strong>{contact?.declared_name || contact?.display_name || `Contato #${contactId}`}</strong><span>Tarefas acessíveis deste contato</span></> : <><strong>Fila de trabalho</strong><span>Contatos dentro do seu acesso atual</span></>}</div><div className="fu-inline"><button type="button" className="fu-button" onClick={changed} disabled={loading}>Atualizar</button>{canManageSettings && <button type="button" className="fu-button" aria-pressed={settingsOpen} onClick={() => { setSettingsOpen(true); setEditor(null); setSelectedTaskId(null); }}>Dias e horários</button>}<button type="button" className="fu-button fu-button--primary" disabled={!settings} onClick={() => { setEditor("new"); setSettingsOpen(false); setSelectedTaskId(null); setNotice(""); }}>Nova tarefa</button></div></div>
        {settingsError && <p className="fu-notice fu-notice--danger fu-panel-notice" role="alert">Não foi possível consultar a configuração: {settingsError} Use Atualizar para tentar novamente.</p>}
        {notice && <p className="fu-notice fu-notice--success fu-panel-notice" role="status">{notice}</p>}
        {!settings?.configured && settings && !settingsOpen && <p className="fu-notice fu-notice--warning fu-panel-notice">Os dias e horários de contato ainda precisam ser configurados pela gestão. Tarefas internas continuam disponíveis.</p>}
        <div className="fu-workspace">
          <aside className="fu-list-area" aria-label="Lista de tarefas">
            <div className="fu-views" aria-label="Prazos e estados">{(Object.keys(VIEW_LABELS) as TaskView[]).filter((key) => key !== "all" || contactId).map((key) => <button type="button" key={key} aria-pressed={view === key} className={view === key ? "is-active" : ""} onClick={() => { setView(key); setNotice(""); }}>{VIEW_LABELS[key]}</button>)}</div>
            <div className="fu-list-filters"><label htmlFor={`${id}-scope`}><span>Responsabilidade</span><select id={`${id}-scope`} value={scope} onChange={(event) => setScope(event.target.value as TaskScope)}>{contactId && <option value="contact">Todas acessíveis do contato</option>}<option value="queue">Na fila</option><option value="mine">Minhas</option>{canManageTeam && <option value="team">Equipe</option>}</select></label><label htmlFor={`${id}-queue`}><span>Fila</span><select id={`${id}-queue`} value={queue} onChange={(event) => setQueue(event.target.value)}><option value="">Todas as filas</option>{queues.map((entry) => <option key={entry.key} value={entry.key}>{entry.label}</option>)}</select></label></div>
            <div className="fu-list-scroll" aria-busy={loading}>
              {error && <p className="fu-notice fu-notice--danger" role="alert">{error}</p>}
              {loading ? <div className="fu-empty" role="status">Carregando tarefas…</div> : items.length ? <ul className="fu-task-list">{items.map((task) => <li key={task.id}><button className={`fu-task-row ${selectedTaskId === task.id ? "is-selected" : ""}`} type="button" aria-current={selectedTaskId === task.id ? "true" : undefined} onClick={() => selectTask(task.id)}><span className="fu-task-row-heading"><strong>{task.title}</strong>{task.response_received && <span className="fu-response-dot" aria-label="Paciente respondeu" />}</span><span className="fu-task-contact">{task.contact?.declared_name || task.contact?.display_name || contactsById.get(task.contact_id)?.display_name || `Contato #${task.contact_id}`}</span><span className="fu-task-date">{formatMoment(task.due_at, settings?.timezone)}</span><span className="fu-task-row-footer"><span>{queues.find((entry) => entry.key === task.queue_key)?.label || task.queue_key} · {taskTypeLabel(task.type)}</span><span>{task.attempt_count === undefined ? "" : `${task.attempt_count} tentativa${task.attempt_count === 1 ? "" : "s"}`}</span></span>{task.response_received && <span className="fu-task-response">{task.response_label || "Paciente respondeu após a referência da tarefa"}</span>}{isCommercialBlocked(task) && task.contact_purpose === "commercial" && <span className="fu-task-blocked">Sem nova abordagem comercial</span>}</button></li>)}</ul> : !error && <div className="fu-empty"><strong>Nenhuma tarefa nesta seleção</strong><p>Confira os outros prazos ou crie uma próxima ação combinada.</p></div>}
              {!loading && nextCursor && <button type="button" className="fu-button fu-load-more" disabled={moreBusy} onClick={() => void loadMore()}>{moreBusy ? "Carregando…" : "Carregar mais tarefas"}</button>}
            </div>
          </aside>
          <main className="fu-detail-area" aria-label="Detalhes do follow-up">
            {editor && editor !== "new" && editorAccessChecking && <p className="fu-help" role="status">Revalidando o acesso à tarefa…</p>}
            {detailVisible && <button type="button" className="fu-button fu-mobile-back" onClick={back}>← Voltar à lista</button>}
            {settingsOpen && settings ? <SettingsEditor key={settings.version} auth={auth} settings={settings} onSaved={(value) => { setSettings(value); setNotice("Dias e horários salvos. Os prazos existentes foram preservados."); changed(); }} onCancel={back} /> : editor ? <TaskEditor key={editor === "new" ? `new-${contactId || "all"}` : editor.id} auth={auth} task={editor === "new" ? undefined : editor} accessChecking={editor !== "new" && editorAccessChecking} contactId={contactId} contacts={contacts} settings={settings} queues={queues} onAccessDenied={(reason) => { sequence.current++; setEditor(null); setSelectedTaskId(null); setItems([]); setNextCursor(null); setError(requestError(reason)); }} onSaved={saved} onCancel={() => setEditor(null)} /> : selectedTaskId ? <TaskDetail key={`${selectedTaskId}-${refresh}`} auth={auth} taskId={selectedTaskId} settings={settings} queues={queues} currentUserId={sessionUser?.id} canManageTeam={canManageTeam} canRegisterPreference={can("registrar_recusa_comercial")} canReactivatePreference={can("reativar_contato_comercial")} onChanged={changed} onEdit={setEditor} onSelectTask={selectTask} onOpenContact={onOpenContact} onBack={back} /> : <div className="fu-welcome"><div className="fu-welcome-icon" aria-hidden="true">↗</div><h3>Um próximo passo por vez</h3><p>Selecione uma tarefa para consultar o contexto, registrar uma tentativa ou combinar o próximo retorno com o paciente.</p><p className="fu-help">As tarefas são humanas. Nenhuma mensagem é enviada pelo vencimento, e a Val segue o ciclo atual do atendimento.</p></div>}
          </main>
        </div>
      </>}
    </div>
  </div>;
}
