import { useCallback, useEffect, useId, useMemo, useRef, useState, type Dispatch, type KeyboardEvent } from "react";
import { useCrm } from "../../context/CrmContext";
import { useLayer } from "./a11y";
import { loadBoard, loadStageCards } from "./api";
import { findCard, nextBoardRequestId, sameFilters, type BoardAction, type BoardState } from "./boardReducer";
import { stageLegacyQualification } from "./catalog";
import { ContactDrawer } from "./ContactDrawer";
import { funnelErrorCode, funnelErrorMessage, isAccessLost } from "./errors";
import { FunnelBoard } from "./FunnelBoard";
import { columnDomId } from "./FunnelColumn";
import { FunnelDashboard } from "./FunnelDashboard";
import { FunnelSearch } from "./FunnelSearch";
import { FunnelSettingsPanel } from "./FunnelSettingsPanel";
import { formatClock } from "./format";
import { MoveStageDialog } from "./MoveStageDialog";
import { useFunnelAccess } from "./useFunnelAccess";
import { useFunnelConfig } from "./useFunnelConfig";
import type { BoardFilters, ContextThread, FunnelCard, MoveStageResponse, StaleCurrent, StageState } from "./types";

export type FunnelPanelTab = "board" | "dashboard" | "settings";

const TAB_LABELS: Record<FunnelPanelTab, string> = { board: "Quadro", dashboard: "Painel gerencial", settings: "Etapas" };

// Abas visiveis na ordem; teclado: setas circulam, Home/End vao as pontas.
export function panelTabs(input: { canDashboard: boolean; canConfigure: boolean }): FunnelPanelTab[] {
  return ["board", ...(input.canDashboard ? ["dashboard" as const] : []), ...(input.canConfigure ? ["settings" as const] : [])];
}

export function nextPanelTab(tabs: FunnelPanelTab[], active: FunnelPanelTab, key: string): FunnelPanelTab | null {
  if (tabs.length < 2) return null;
  const index = Math.max(0, tabs.indexOf(active));
  if (key === "Home") return tabs[0];
  if (key === "End") return tabs[tabs.length - 1];
  if (key === "ArrowRight") return tabs[(index + 1) % tabs.length];
  if (key === "ArrowLeft") return tabs[(index + tabs.length - 1) % tabs.length];
  return null;
}

export type FunnelPanelProps = {
  board: BoardState;
  dispatch: Dispatch<BoardAction>;
  filters: BoardFilters;
  onFiltersChange: (filters: BoardFilters) => void;
  tab: FunnelPanelTab;
  onTabChange: (tab: FunnelPanelTab) => void;
  onClose: (options?: { toChat?: boolean }) => void;
  // Origem do foco ao fechar (botao da barra superior). Sem isto, o painel
  // montado depois do "Carregando…" do lazy devolveria o foco ao body.
  returnFocus?: () => HTMLElement | null;
};

// Quadro reaberto reusa o estado em memoria (com "dados de HH:MM"); passa
// disso ou troca de filtro = nova carga. Sem polling e sem recarregar no
// visibilitychange: o resto e o botao Atualizar (com trava).
const BOARD_MAX_AGE_MS = 5 * 60_000;
const REFRESH_LOCK_MS = 10_000;

export function FunnelPanel({ board, dispatch, filters, onFiltersChange, tab, onTabChange, onClose, returnFocus }: FunnelPanelProps) {
  const { operators, systemSettings, settingsLoaded, focusExistingConversation, patchContactStage } = useCrm();
  const access = useFunnelAccess();
  const { config, error: configError, accessLost: configLost, reload: reloadConfig } = useFunnelConfig(access.auth, access.catalogAvailable, access.accessKey);
  const auth = access.auth;
  const id = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const boardRef = useRef(board);
  boardRef.current = board;
  const [drawer, setDrawer] = useState<{ contactId: number; trigger: HTMLElement | null } | null>(null);
  const [move, setMove] = useState<{ card: FunnelCard; trigger: HTMLElement | null } | null>(null);
  // Tom do aviso: sucesso (etapa mudou) x alerta (acesso perdido, falha).
  const [notice, setNotice] = useState<{ text: string; tone: "success" | "warning" } | null>(null);
  const [locked, setLocked] = useState(false);
  const movedTo = useRef<string | null>(null);
  useLayer(panelRef, () => onClose(), { initialFocus: closeRef, returnFocus });

  const catalog = config?.catalog || null;
  const capabilities = config?.capabilities || null;
  const stages = useMemo(() => new Map((catalog?.stages || []).map((stage) => [stage.key, stage])), [catalog]);
  const canMove = Boolean(capabilities?.can_move);
  const privileged = Boolean(capabilities?.privileged);
  const canDashboard = Boolean(capabilities?.can_dashboard);
  const canConfigure = capabilities?.can_configure === true;
  const tabs = panelTabs({ canDashboard, canConfigure });
  const activeTab: FunnelPanelTab = tabs.includes(tab) ? tab : "board";
  // Aba "Etapas" monta na 1a visita e fica montada (rascunho sobrevive a
  // troca de aba enquanto o painel esta aberto).
  const settingsVisited = useRef(false);
  if (activeTab === "settings") settingsVisited.current = true;
  const ownerOptions = useMemo(() => [...operators].filter((operator) => operator.is_active !== 0).sort((left, right) => left.display_name.localeCompare(right.display_name, "pt-BR")), [operators]);

  const loadNow = useCallback(async (next: BoardFilters) => {
    if (!auth) return;
    const requestId = nextBoardRequestId();
    dispatch({ type: "load_started", requestId, filters: next });
    try {
      const response = await loadBoard(auth, next);
      dispatch({ type: "load_succeeded", requestId, response, loadedAt: Date.now() });
    } catch (reason) {
      dispatch({ type: "load_failed", requestId, error: funnelErrorMessage(reason), code: funnelErrorCode(reason), clear: isAccessLost(reason) });
    }
  }, [auth, dispatch]);

  useEffect(() => {
    if (!auth || !catalog || activeTab !== "board") return;
    const current = boardRef.current;
    const sameScope = sameFilters(current.filters, filters);
    if (current.status === "loading" && sameScope) return;
    if (current.status === "idle" || !sameScope || Date.now() - current.loadedAt > BOARD_MAX_AGE_MS) void loadNow(filters);
  }, [auth, catalog, filters, activeTab, loadNow]);

  useEffect(() => {
    if (!locked) return;
    const timer = window.setTimeout(() => setLocked(false), REFRESH_LOCK_MS);
    return () => window.clearTimeout(timer);
  }, [locked]);

  function refresh() {
    if (locked || board.status === "loading") return;
    setLocked(true); setNotice(null);
    void loadNow(filters);
  }

  const loadMore = useCallback(async (stage: string) => {
    if (!auth) return;
    const state = boardRef.current;
    const column = state.columns.find((entry) => entry.stage === stage);
    if (!column?.nextCursor || column.loadingMore) return;
    const requestId = state.requestId;
    dispatch({ type: "more_started", stage });
    try {
      const page = await loadStageCards(auth, stage, state.filters, column.nextCursor, 20);
      dispatch({ type: "more_succeeded", requestId, stage, cards: Array.isArray(page.cards) ? page.cards : [], nextCursor: page.next_cursor || null });
    } catch (reason) {
      dispatch({ type: "more_failed", requestId, stage, error: funnelErrorMessage(reason), expired: funnelErrorCode(reason) === "cursor_invalid" });
    }
  }, [auth, dispatch]);

  const openContact = useCallback((contactId: number, trigger: HTMLElement) => { setNotice(null); setDrawer({ contactId, trigger }); }, []);
  const openMove = useCallback((card: FunnelCard, trigger: HTMLElement) => { setNotice(null); movedTo.current = null; setMove({ card, trigger }); }, []);

  // Foco volta ao card (mesmo que ele tenha mudado de coluna); sem card, a
  // coluna de destino; sem coluna, a camada de baixo (useLayer).
  const cardElement = useCallback((contactId: number, selector: string) => panelRef.current?.querySelector<HTMLElement>(`[data-fn-card="${contactId}"] ${selector}`) || null, []);
  const columnHeading = (stage?: string | null) => (stage ? document.getElementById(`${columnDomId(stage)}-title`) : null);

  // A etapa nova (POST ou 409) tambem vai para a copia do contato no
  // CrmContext: sem isso o chip do chat e o "Encerrar atendimento" seguiam
  // na versao velha (409 enganoso) para contato sem listener (picker/Equipe).
  const applyMoved = useCallback((contactId: number, response: MoveStageResponse, name?: string) => {
    movedTo.current = response.stage?.key || null;
    dispatch({ type: "card_moved", contactId, result: response.stage, target: stages.get(response.stage?.key), now: Date.now() });
    // Mudanca MANUAL: o backend gravou junto o legado equivalente.
    patchContactStage(contactId, response.stage, stageLegacyQualification(catalog, response.stage?.key));
    setNotice({ tone: "success", text: `${name || "O contato"} agora está em ${response.stage?.label || stages.get(response.stage?.key)?.label || "outra etapa"}. Nenhuma mensagem foi enviada.` });
  }, [dispatch, stages, catalog, patchContactStage]);

  const applyConflict = useCallback((contactId: number, current: StaleCurrent) => {
    if (!current.stage) { dispatch({ type: "card_removed", contactId }); return; }
    const target = stages.get(current.stage);
    const stage: StageState = {
      key: current.stage, label: target?.label || current.stage, kind: target?.kind || "open", version: current.version,
      changed_at: current.changed_at || "", source: "user", entered_at: null, reason: null, reason_note: null, appointment_kind: null,
    };
    dispatch({ type: "card_moved", contactId, result: stage, target, now: Date.now() });
    patchContactStage(contactId, stage);
  }, [dispatch, stages, patchContactStage]);

  const stageSeen = useCallback((contactId: number, stage: StageState | null) => {
    const card = findCard(boardRef.current, contactId);
    if (!card) return;
    if (!stage) { dispatch({ type: "card_removed", contactId }); return; }
    if (stage.version > card.stage_version) dispatch({ type: "card_moved", contactId, result: stage, target: stages.get(stage.key), now: Date.now() });
  }, [dispatch, stages]);

  const drawerLost = useCallback((contactId: number) => {
    setDrawer(null); setMove(null);
    dispatch({ type: "card_removed", contactId });
    setNotice({ tone: "warning", text: "Este contato não está mais disponível no seu acesso. Use Atualizar para conferir o quadro." });
  }, [dispatch]);

  function openConversation(thread: ContextThread) {
    const conversationId = focusExistingConversation(thread);
    if (!conversationId) { setNotice({ tone: "warning", text: "Não foi possível abrir esta conversa no chat." }); return; }
    onClose({ toChat: true });
  }

  function onTabKeys(event: KeyboardEvent<HTMLButtonElement>) {
    const next = nextPanelTab(tabs, activeTab, event.key);
    if (!next) return;
    event.preventDefault();
    onTabChange(next);
    window.requestAnimationFrame(() => document.getElementById(`${id}-tab-${next}`)?.focus());
  }

  function setOrder(order: BoardFilters["order"]) { onFiltersChange({ ...filters, order }); }
  function setOwner(value: string) { onFiltersChange({ ...filters, ownerId: value ? Number(value) : null, mine: false }); }
  function setMine(mine: boolean) { onFiltersChange({ ...filters, mine, ownerId: null }); }

  const loading = board.status === "loading";
  const searchEnabled = settingsLoaded && systemSettings.picker_v2_enabled;

  return <div className="fn-layer fn-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="fn-panel" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} aria-describedby={`${id}-subtitle`} ref={panelRef} tabIndex={-1}>
      <header className="fn-header">
        <div><p className="fn-eyebrow">Castro Intelligence CRM</p><h2 id={`${id}-title`}>Funil comercial</h2><p id={`${id}-subtitle`}>Onde cada contato está na jornada. As primeiras etapas mudam sozinhas; o desfecho vem do encerramento do atendimento ou de “Mover para…”.</p></div>
        <button type="button" className="fn-icon-button" ref={closeRef} onClick={() => onClose()} aria-label="Fechar funil comercial">✕</button>
      </header>
      {configError ? <div className="fn-panel-message"><p className="fn-notice fn-notice--danger" role="alert">{configError}</p>{!configLost && <button type="button" className="fn-button" onClick={reloadConfig}>Tentar novamente</button>}</div>
        : !catalog || !auth ? <p className="fn-panel-message fn-help" role="status">Carregando o funil…</p> : <>
          <div className="fn-tabs" role="tablist" aria-label="Seções do funil">
            {tabs.map((entry) => <button key={entry} type="button" role="tab" id={`${id}-tab-${entry}`} aria-selected={activeTab === entry} aria-controls={`${id}-panel-${entry}`} tabIndex={activeTab === entry ? 0 : -1} onClick={() => onTabChange(entry)} onKeyDown={onTabKeys}>{TAB_LABELS[entry]}</button>)}
          </div>
          {/* Quadro fica montado (e com a rolagem) enquanto o painel gerencial esta aberto. */}
          <div className="fn-tabpanel" role="tabpanel" id={`${id}-panel-board`} aria-labelledby={`${id}-tab-board`} hidden={activeTab !== "board"}>
            <div className="fn-toolbar">
              <label className="fn-field fn-field--inline" htmlFor={`${id}-order`}><span>Ordem</span>
                <select id={`${id}-order`} value={filters.order} onChange={(event) => setOrder(event.target.value === "asc" ? "asc" : "desc")}>
                  <option value="desc">Mais recentes na etapa</option>
                  <option value="asc">Mais antigos na etapa</option>
                </select>
              </label>
              {privileged && <label className="fn-field fn-field--inline" htmlFor={`${id}-owner`}><span>Dono do lead</span>
                <select id={`${id}-owner`} value={filters.ownerId == null ? "" : String(filters.ownerId)} onChange={(event) => setOwner(event.target.value)}>
                  <option value="">Todos</option>
                  {ownerOptions.map((operator) => <option key={operator.id} value={operator.id}>{operator.display_name}</option>)}
                </select>
              </label>}
              <label className="fn-check" htmlFor={`${id}-mine`}><input id={`${id}-mine`} type="checkbox" checked={filters.mine} onChange={(event) => setMine(event.target.checked)} /><span>Só os meus</span></label>
              {searchEnabled && <FunnelSearch auth={auth} onOpen={openContact} />}
              <div className="fn-toolbar-end">
                {board.generatedAt && <span className="fn-freshness">Dados de {formatClock(board.generatedAt)}</span>}
                <button type="button" className="fn-button" onClick={refresh} disabled={locked || loading} title={locked ? "Aguarde alguns segundos para atualizar de novo." : undefined}>{loading ? "Atualizando…" : "Atualizar"}</button>
              </div>
            </div>
            {!privileged && <p className="fn-scope-hint fn-help">Você vê os contatos que são seus e os sem dono.</p>}
            {notice && <p className={`fn-notice fn-notice--${notice.tone} fn-panel-notice`} role="status">{notice.text}</p>}
            {board.status === "error" && <p className="fn-notice fn-notice--danger fn-panel-notice" role="alert">{board.error}{board.columns.length ? " Exibindo os dados anteriores." : ""}</p>}
            {board.outdated && board.status !== "error" && <p className="fn-notice fn-notice--warning fn-panel-notice" role="status">Os totais podem não refletir as últimas mudanças. Use Atualizar para conferir.</p>}
            {board.columns.length ? <FunnelBoard columns={board.columns} stages={stages} canMove={canMove} busy={loading} onOpen={openContact} onMove={openMove} onMore={(stage) => void loadMore(stage)} />
              : loading ? <p className="fn-panel-message fn-help" role="status">Carregando o quadro…</p>
                : board.status === "ready" ? <p className="fn-panel-message fn-help">Nenhuma etapa para exibir.</p> : null}
          </div>
          {canDashboard && <div className="fn-tabpanel fn-tabpanel--scroll" role="tabpanel" id={`${id}-panel-dashboard`} aria-labelledby={`${id}-tab-dashboard`} hidden={activeTab !== "dashboard"}>
            {activeTab === "dashboard" && <FunnelDashboard auth={auth} catalog={catalog} onAccessLost={(reason) => { onTabChange("board"); setNotice({ tone: "warning", text: funnelErrorMessage(reason) }); }} />}
          </div>}
          {canConfigure && <div className="fn-tabpanel fn-tabpanel--scroll" role="tabpanel" id={`${id}-panel-settings`} aria-labelledby={`${id}-tab-settings`} hidden={activeTab !== "settings"}>
            {settingsVisited.current && <FunnelSettingsPanel auth={auth} catalog={catalog} onAccessLost={(reason) => { onTabChange("board"); setNotice({ tone: "warning", text: funnelErrorMessage(reason) }); }} />}
          </div>}
        </>}
    </div>
    {drawer && catalog && auth && <ContactDrawer
      key={drawer.contactId} auth={auth} contactId={drawer.contactId} catalog={catalog}
      returnFocus={() => cardElement(drawer.contactId, ".fn-card-open") || (drawer.trigger?.isConnected ? drawer.trigger : null)}
      onClose={() => setDrawer(null)} onMoved={(contactId, response) => applyMoved(contactId, response)} onConflict={applyConflict}
      onStageSeen={stageSeen} onAccessLost={drawerLost} onOpenConversation={openConversation} />}
    {move && catalog && auth && <MoveStageDialog
      auth={auth} catalog={catalog} contactId={move.card.contact_id} contactName={move.card.display_name || `Contato #${move.card.contact_id}`}
      currentStage={move.card.stage} currentReason={move.card.reason?.key || null} expectedVersion={move.card.stage_version}
      returnFocus={() => cardElement(move.card.contact_id, ".fn-card-move") || cardElement(move.card.contact_id, ".fn-card-open") || columnHeading(movedTo.current) || columnHeading(move.card.stage)}
      onClose={() => setMove(null)}
      onMoved={(response) => applyMoved(move.card.contact_id, response, move.card.display_name)}
      onConflict={(current) => applyConflict(move.card.contact_id, current)}
      onAccessLost={() => drawerLost(move.card.contact_id)} />}
  </div>;
}
