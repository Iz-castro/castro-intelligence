import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Auth } from "firebase/auth";
import { LeadTemperatureDot, leadTemperatureText } from "../../components/LeadTemperatureDot";
import { useCrm } from "../../context/CrmContext";
import { ReadOnlyContext } from "../followup/ReadOnlyContext";
import { useAccessSignal } from "../followup/useAccessSignal";
import { useLayer } from "./a11y";
import { FUNNEL_BASE, loadContactContext, loadContactFunnel, loadContactHistory, loadContactStage } from "./api";
import { buildBadges } from "./badges";
import { closeOutcomeStages } from "./catalog";
import { funnelErrorMessage, isAccessLost } from "./errors";
import { daysInStageText, formatCount, formatDate, formatDateTime } from "./format";
import { MoveStageDialog } from "./MoveStageDialog";
import { StageHistory } from "./StageHistory";
import type { BotOutcome, ContactFunnel, ContactStageCheck, ContextThread, FunnelCatalog, HistoryItem, MoveStageResponse, StaleCurrent, StageState, StageSuggestion, SuggestionSource } from "./types";

type Props = {
  auth: Auth;
  contactId: number;
  catalog: FunnelCatalog;
  returnFocus: () => HTMLElement | null;
  onClose: () => void;
  onMoved: (contactId: number, response: MoveStageResponse) => void;
  onConflict: (contactId: number, current: StaleCurrent) => void;
  // Etapa vista no servidor (carga/revalidacao): o quadro corrige o card.
  onStageSeen: (contactId: number, stage: StageState | null) => void;
  onAccessLost: (contactId: number) => void;
  onOpenConversation: (thread: ContextThread) => void;
};

type HistoryState = { items: HistoryItem[]; cursor: string | null; busy: boolean; error: string };
const EMPTY_HISTORY: HistoryState = { items: [], cursor: null, busy: false, error: "" };

const SOURCE_LABELS: Record<string, string> = {
  user: "Mudança manual", intake: "Entrada automática", graduation: "Backup graduado", migration: "Classificação inicial", system: "Regra do sistema",
  // Automacoes por evento (funnel_catalog.SOURCE_RULE_PREFIX + evento).
  "rule:handoff": "Automática: o agente de IA passou para a recepção",
  "rule:human_reply": "Automática: primeira resposta da equipe",
};

function unreadOf(thread: ContextThread): number {
  const value = Number(thread.unread_count ?? thread.unread ?? 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

// O `label` da sugestao e o rotulo da etapa de destino (ja dito no botao):
// o texto descreve o registro do bot que motivou a sugestao.
function suggestionText(entry: StageSuggestion, outcome: BotOutcome | null | undefined): string {
  if (entry.source === "bot_outcome" && outcome === "agendado") return "O bot registrou um agendamento neste ciclo.";
  if (entry.source === "bot_outcome" && outcome === "link_enviado") return "O bot enviou o link de agendamento neste ciclo.";
  return `Sugestão: ${entry.label}`;
}

function historyFrom(value: ContactFunnel): HistoryState {
  return { items: Array.isArray(value.history?.items) ? value.history.items : [], cursor: value.history?.next_cursor || null, busy: false, error: "" };
}

// Tudo o que o drawer exibe da etapa (mesmo shape no GET completo e no leve).
function stageSignature(stage: StageState | null | undefined): string {
  if (!stage) return "";
  return JSON.stringify([
    stage.key, stage.version ?? 0, stage.kind ?? null, stage.label ?? null, stage.changed_at ?? null, stage.source ?? null, stage.entered_at ?? null,
    stage.reason?.key ?? null, stage.reason?.label ?? null, stage.reason_note ?? null, stage.appointment_kind ?? null,
  ]);
}

// Revalidacao leve (GET /contacts/{id}/stage): o drawer completo (historico,
// tarefas, sinais) so volta quando a versao ou a etapa exibida mudou, ou o
// escopo de escrita (historico e nota dependem dele). Resposta sem `stage` =
// recarga completa (nunca "nada mudou" por falta de dado).
export function stageCheckChanged(current: ContactFunnel | null | undefined, check: ContactStageCheck | null | undefined): boolean {
  if (!current || !check || typeof check !== "object" || !("stage" in check)) return true;
  const shown = current.stage || null;
  const fresh = check.stage || null;
  const version = Number.isInteger(check.version) ? Number(check.version) : fresh?.version ?? 0;
  if (version !== (shown?.version ?? 0) || stageSignature(fresh) !== stageSignature(shown)) return true;
  return typeof check.write_scope === "boolean" && check.write_scope !== (current.capabilities?.write_scope !== false);
}

// Sem mudanca de etapa/escopo, o "mover" ainda pode mudar (toggle do perfil,
// contato arquivado visto pela gestao): aplicado no lugar, sem o GET completo.
export function applyStageCheck(current: ContactFunnel, check: ContactStageCheck): ContactFunnel {
  if (typeof check.can_move !== "boolean" || check.can_move === Boolean(current.capabilities?.can_move)) return current;
  return { ...current, capabilities: { ...current.capabilities, can_move: check.can_move } };
}

// Drawer SO-LEITURA: abrir nao assume, nao pega tarefa, nao muda etapa e nao
// chama /api/wa/conversation/open. Revalida o acesso a cada 30 s com a aba
// visivel (e na hora, quando o dono muda no CRM ao vivo) pelo GET leve da
// etapa; 401/403/404 fecha.
export function ContactDrawer({ auth, contactId, catalog, returnFocus, onClose, onMoved, onConflict, onStageSeen, onAccessLost, onOpenConversation }: Props) {
  const { channels, canPeek, peekMode, can } = useCrm();
  const id = useId();
  const drawerRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [data, setData] = useState<ContactFunnel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<HistoryState>(EMPTY_HISTORY);
  const [threads, setThreads] = useState<ContextThread[] | null>(null);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsError, setThreadsError] = useState("");
  const [readingThread, setReadingThread] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{ target: string | null; suggestedBy: SuggestionSource | null; trigger: HTMLElement | null } | null>(null);
  const [reload, setReload] = useState(0);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const sequence = useRef(0);
  const dataRef = useRef<ContactFunnel | null>(null);
  dataRef.current = data;
  const ownChange = useRef(false);
  const callbacks = useRef({ onAccessLost, onStageSeen });
  callbacks.current = { onAccessLost, onStageSeen };
  const accessSignal = useAccessSignal(contactId);
  const observedSignal = useRef<string | null>(null);
  const observedNonce = useRef(0);
  const stages = useMemo(() => new Map(catalog.stages.map((stage) => [stage.key, stage])), [catalog]);
  useLayer(drawerRef, onClose, { initialFocus: titleRef, returnFocus });

  const lose = useCallback(() => {
    sequence.current++;
    setData(null); setThreads(null); setReadingThread(null); setDialog(null);
    callbacks.current.onAccessLost(contactId);
  }, [contactId]);

  useEffect(() => {
    const request = ++sequence.current;
    let cancelled = false;
    const current = () => !cancelled && request === sequence.current;
    setLoading(true); setError(""); setData(null); setHistory(EMPTY_HISTORY); setThreads(null); setThreadsError(""); setReadingThread(null);
    void (async () => {
      let value: ContactFunnel;
      try { value = await loadContactFunnel(auth, contactId); }
      catch (reason) {
        if (!current()) return;
        if (isAccessLost(reason)) { lose(); return; }
        setError(funnelErrorMessage(reason)); setLoading(false);
        return;
      }
      if (!current()) return;
      setData(value); setLoading(false); setHistory(historyFrom(value));
      callbacks.current.onStageSeen(contactId, value.stage);
      // Conversas so depois de o acesso ao contato estar confirmado.
      setThreadsLoading(true);
      try {
        const context = await loadContactContext(auth, contactId);
        if (current()) setThreads(Array.isArray(context.conversations) ? context.conversations.filter((thread) => thread && typeof thread.id === "string" && thread.id) : []);
      } catch (reason) {
        if (!current()) return;
        if (isAccessLost(reason)) { lose(); return; }
        setThreadsError(funnelErrorMessage(reason));
      } finally { if (current()) setThreadsLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [auth, contactId, reload, lose]);

  // Revalidacao silenciosa: mantem o conteudo (e o foco) no lugar. Ciclo de
  // 30 s = GET leve da etapa; o completo so quando ele mostra mudanca. Eventos
  // raros vao direto ao completo: mudanca feita aqui (a versao ja mudou) e
  // dono mudado no CRM ao vivo (o dono aparece no cabecalho; o leve nao o traz).
  const hasData = Boolean(data);
  useEffect(() => {
    if (!hasData) return;
    let cancelled = false;
    let checking = false;
    const ownerChanged = observedSignal.current !== null && observedSignal.current !== accessSignal;
    observedSignal.current = accessSignal;
    const forced = observedNonce.current !== refreshNonce;
    observedNonce.current = refreshNonce;
    async function revalidate(full: boolean) {
      if (checking || document.visibilityState !== "visible") return;
      checking = true;
      const request = sequence.current;
      try {
        if (!full) {
          const check = await loadContactStage(auth, contactId);
          if (cancelled || request !== sequence.current) return;
          const shown = dataRef.current;
          if (shown && !stageCheckChanged(shown, check)) {
            const next = applyStageCheck(shown, check);
            if (next !== shown) setData(next);
            return;
          }
        }
        const fresh = await loadContactFunnel(auth, contactId);
        if (cancelled || request !== sequence.current) return;
        const previous = dataRef.current;
        setData(fresh);
        callbacks.current.onStageSeen(contactId, fresh.stage);
        const versionChanged = (previous?.stage?.version ?? 0) !== (fresh.stage?.version ?? 0);
        // Historico e nota dependem do escopo de escrita: mudou, recomeca.
        const scopeChanged = (previous?.capabilities?.write_scope !== false) !== (fresh.capabilities?.write_scope !== false);
        if (versionChanged || scopeChanged) setHistory(historyFrom(fresh));
        if (versionChanged && !ownChange.current) setNotice("A etapa deste contato foi alterada. Os dados foram atualizados.");
        ownChange.current = false;
      } catch (reason) {
        if (cancelled || request !== sequence.current) return;
        if (isAccessLost(reason)) lose();
        // Falha transitoria: mantem os dados e tenta no proximo ciclo.
      } finally { checking = false; }
    }
    if (ownerChanged || forced) void revalidate(true);
    const timer = window.setInterval(() => void revalidate(false), 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [auth, contactId, hasData, accessSignal, refreshNonce, lose]);

  async function moreHistory() {
    if (!history.cursor || history.busy) return;
    const request = sequence.current;
    const cursor = history.cursor;
    setHistory((state) => ({ ...state, busy: true, error: "" }));
    try {
      const page = await loadContactHistory(auth, contactId, cursor);
      if (request !== sequence.current) return;
      setHistory((state) => ({
        items: [...state.items, ...(page.items || []).filter((item) => !state.items.some((existing) => existing.id === item.id && existing.event_type === item.event_type))],
        cursor: page.next_cursor || null, busy: false, error: "",
      }));
    } catch (reason) {
      if (request !== sequence.current) return;
      if (isAccessLost(reason)) { lose(); return; }
      setHistory((state) => ({ ...state, busy: false, error: funnelErrorMessage(reason) }));
    }
  }

  function moved(response: MoveStageResponse) {
    onMoved(contactId, response);
    ownChange.current = true;
    setNotice(`Etapa alterada para ${response.stage?.label || stages.get(response.stage?.key)?.label || "a nova etapa"}. Nenhuma mensagem foi enviada.`);
    setRefreshNonce((value) => value + 1);
  }

  const contact = data?.contact;
  const stage = data?.stage || null;
  const stageDef = stage ? stages.get(stage.key) : undefined;
  const archived = Boolean(contact?.is_archived);
  // O can_move do drawer ja vem do backend com escopo de escrita e
  // arquivo/backup aplicados; o toggle cru so explica por que nao move.
  const canWrite = Boolean(data?.capabilities?.can_move && data.capabilities.write_scope && !archived);
  const writeScope = data?.capabilities?.write_scope !== false;
  const badges = data ? buildBadges({ signals: data.signals, badges: data.badges, tasksVisible: data.tasks !== null }) : [];
  const suggestions = canWrite ? (data?.suggestions || []).filter((entry) => entry.to_stage !== stage?.key && stages.get(entry.to_stage)?.active) : [];
  const channelLabel = (thread: ContextThread) => String(thread.channel_label || channels.find((channel) => channel.id === Number(thread.channel_id))?.label || (thread.channel_id ? `Canal ${thread.channel_id}` : "Conversa"));
  const peeking = canPeek && peekMode;
  const closeWithFunnel = closeOutcomeStages(catalog).length > 0;

  function openDialog(target: string | null, suggestedBy: SuggestionSource | null, trigger: HTMLElement) {
    setNotice(""); setDialog({ target, suggestedBy, trigger });
  }

  return createPortal(<div className="fn-layer fn-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <aside className="fn-drawer" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} ref={drawerRef} tabIndex={-1}>
      <header className="fn-drawer-header">
        <div>
          <p className="fn-eyebrow">Contato no funil</p>
          <h2 id={`${id}-title`} ref={titleRef} tabIndex={-1}>{contact?.display_name || (loading ? "Carregando contato…" : `Contato #${contactId}`)}</h2>
          {contact && <p className="fn-drawer-sub"><span className="fn-inline-icon"><LeadTemperatureDot temperature={contact.lead_temperature || undefined} decorative />{leadTemperatureText(contact.lead_temperature)}</span><span>Dono do lead: {contact.owner?.name || "sem dono"}</span></p>}
        </div>
        <button type="button" className="fn-icon-button" onClick={onClose} aria-label="Fechar detalhes do contato">✕</button>
      </header>
      <div className="fn-drawer-body">
        <p className="fn-help">Consulta: abrir não assume o atendimento, não pega tarefa, não muda a etapa e não marca mensagens como lidas.</p>
        {notice && <p className="fn-notice fn-notice--success" role="status">{notice}</p>}
        {loading ? <p className="fn-help" role="status">Carregando contato…</p> : error ? <div className="fn-notice fn-notice--danger" role="alert"><span>{error}</span><button type="button" className="fn-button" onClick={() => setReload((value) => value + 1)}>Tentar novamente</button></div> : data && <>
          <section className="fn-drawer-section" aria-labelledby={`${id}-stage`}>
            <h3 id={`${id}-stage`}>Etapa do funil</h3>
            {stage ? <>
              <p className="fn-stage-line"><span className={`fn-stage-pill fn-kind-bg--${stage.kind || stageDef?.kind || "open"}`}>{stage.label || stageDef?.label || stage.key}</span><span>{daysInStageText(data.signals?.days_in_stage)}</span></p>
              <dl className="fn-meta">
                <div><dt>Na etapa desde</dt><dd>{formatDateTime(stage.changed_at)}</dd></div>
                <div><dt>Origem</dt><dd>{SOURCE_LABELS[stage.source || ""] || "Registro do funil"}</dd></div>
                {stage.entered_at && <div><dt>No funil desde</dt><dd>{formatDate(stage.entered_at)}</dd></div>}
                {stage.reason && <div><dt>Motivo</dt><dd>{stage.reason.label}{stage.reason_note ? ` — ${stage.reason_note}` : ""}</dd></div>}
                {stage.appointment_kind && <div><dt>Compromisso</dt><dd>{stage.appointment_kind === "procedure" ? "Procedimento" : "Consulta"}</dd></div>}
              </dl>
              {stageDef?.description && <p className="fn-help">{stageDef.description}</p>}
            </> : <p>Fora do funil.</p>}
            {canWrite ? <button type="button" className="fn-button fn-button--primary" onClick={(event) => openDialog(null, null, event.currentTarget)}>{stage ? "Mover para…" : "Incluir no funil"}</button>
              : archived ? <p className="fn-help">Contato arquivado: a etapa não pode ser alterada.</p>
                : can("mover_etapa_funil") && !writeScope ? <p className="fn-help">Você pode consultar a etapa, mas só move contatos seus ou sem dono.</p> : null}
            {closeWithFunnel && <p className="fn-help">O desfecho escolhido no encerramento do atendimento também define a etapa.</p>}
          </section>
          {badges.length > 0 && <section className="fn-drawer-section" aria-labelledby={`${id}-signals`}>
            <h3 id={`${id}-signals`}>Sinais</h3>
            <ul className="fn-badges">{badges.map((badge) => <li key={badge.key} className={`fn-badge fn-badge--${badge.tone}`} title={badge.title}>{badge.text}</li>)}</ul>
          </section>}
          {suggestions.length > 0 && <section className="fn-drawer-section" aria-labelledby={`${id}-suggestions`}>
            <h3 id={`${id}-suggestions`}>Sugestões</h3>
            <ul className="fn-suggestions">{suggestions.map((entry) => <li key={`${entry.source}-${entry.to_stage}`}><span>{suggestionText(entry, data.badges?.bot_outcome)}</span><button type="button" className="fn-button" onClick={(event) => openDialog(entry.to_stage, entry.source, event.currentTarget)}>Mover para {stages.get(entry.to_stage)?.label || entry.to_stage}…</button></li>)}</ul>
            <p className="fn-help">Registro do bot neste ciclo. A etapa só muda se você confirmar.</p>
          </section>}
          {data.tasks !== null && <section className="fn-drawer-section" aria-labelledby={`${id}-tasks`}>
            <h3 id={`${id}-tasks`}>Próximas tarefas</h3>
            {data.tasks.length ? <ul className="fn-task-list">{data.tasks.map((task) => <li key={task.id}><strong>{task.title}</strong><span className={task.overdue ? "fn-overdue" : undefined}>{formatDateTime(task.due_at)}{task.overdue ? " · atrasada" : ""}</span><span>{task.assignee_name ? `Responsável: ${task.assignee_name}` : "Na fila"}</span></li>)}</ul> : <p className="fn-help">Nenhuma tarefa pendente acessível.</p>}
          </section>}
          <section className="fn-drawer-section" aria-labelledby={`${id}-threads`}>
            <h3 id={`${id}-threads`}>Conversas</h3>
            {threadsLoading ? <p className="fn-help" role="status">Consultando conversas acessíveis…</p>
              : threadsError ? <p className="fn-notice fn-notice--danger" role="alert">{threadsError}</p>
                : !threads?.length ? <p className="fn-help">Nenhuma conversa acessível. Nenhum atendimento foi criado.</p>
                  : <ul className="fn-thread-list">{threads.map((thread) => {
                    const unread = unreadOf(thread);
                    const warningId = `${id}-unread-${thread.id}`;
                    return <li key={thread.id}>
                      <p className="fn-thread-title"><strong>{channelLabel(thread)}</strong>{unread > 0 && <span className="fn-badge fn-badge--info">{formatCount(unread)} não {unread === 1 ? "lida" : "lidas"}</span>}</p>
                      <div className="fn-inline">
                        <button type="button" className="fn-button fn-button--primary" onClick={() => onOpenConversation(thread)} aria-describedby={unread > 0 ? warningId : undefined}>Abrir conversa no chat</button>
                        <button type="button" className="fn-button" aria-expanded={readingThread === thread.id} onClick={() => setReadingThread((value) => value === thread.id ? null : thread.id)}>{readingThread === thread.id ? "Recolher mensagens" : "Ler aqui, sem abrir"}</button>
                      </div>
                      {unread > 0 && <p id={warningId} className="fn-warning-text">{peeking ? "Modo só espiar ativo: abrir não marca as mensagens como lidas." : "Abrir marca as mensagens como lidas."}</p>}
                    </li>;
                  })}</ul>}
            {readingThread && <ReadOnlyContext auth={auth} contactId={contactId} conversationId={readingThread} basePath={FUNNEL_BASE} />}
          </section>
          <section className="fn-drawer-section" aria-labelledby={`${id}-history`}>
            <h3 id={`${id}-history`}>Histórico da etapa</h3>
            {/* Acesso so por thread propria (coex): o backend entrega a etapa
                atual sem historico nem nota (mesma regra do escopo de escrita). */}
            <StageHistory items={history.items} nextCursor={history.cursor} busy={history.busy} error={history.error} onMore={() => void moreHistory()}
              emptyText={writeScope ? undefined : "O histórico da etapa fica com o dono do lead e com a gestão."} />
          </section>
        </>}
      </div>
    </aside>
    {dialog && data && <MoveStageDialog
      auth={auth} catalog={catalog} contactId={contactId} contactName={contact?.display_name || `Contato #${contactId}`}
      currentStage={stage?.key || null} currentReason={stage?.reason?.key || null} expectedVersion={stage?.version ?? 0}
      initialTarget={dialog.target} suggestedBy={dialog.suggestedBy}
      returnFocus={() => (dialog.trigger?.isConnected ? dialog.trigger : null)}
      onClose={() => setDialog(null)} onMoved={moved}
      onConflict={(current) => { onConflict(contactId, current); ownChange.current = true; setRefreshNonce((value) => value + 1); }}
      onAccessLost={() => lose()} />}
  </div>, document.body);
}
