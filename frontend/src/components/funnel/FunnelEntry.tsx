import { Component, Suspense, useCallback, useEffect, useId, useReducer, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { boardReducer, createBoardState, DEFAULT_FILTERS, FunnelPanel, useFunnelAccess, useLayer, type BoardFilters, type FunnelPanelTab } from "../../features/funnel";

// Mesmo corte do styles.css: ate 860px o chat fica empilhado abaixo da lista.
const STACKED_LAYOUT = "(max-width: 860px)";

function matches(query: string): boolean {
  try { return window.matchMedia(query).matches; } catch { return false; }
}

// Camada do painel preguicoso enquanto o chunk carrega (ou se falhar): mesma
// pilha do funil (Esc fecha, foco preso e devolvido ao botao de origem).
function FunnelShell({ failed, onClose, returnFocus }: { failed: boolean; onClose: () => void; returnFocus: () => HTMLElement | null }) {
  const id = useId();
  const shellRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useLayer(shellRef, onClose, { initialFocus: closeRef, returnFocus });
  return <div className="fn-layer fn-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="fn-shell" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} ref={shellRef} tabIndex={-1}>
      <p className="fn-eyebrow">Castro Intelligence CRM</p>
      <h2 id={`${id}-title`}>Funil comercial</h2>
      {failed
        ? <p className="fn-notice fn-notice--danger" role="alert">Não foi possível abrir o funil. Recarregue a página para tentar de novo.</p>
        : <p className="fn-help" role="status">Carregando o funil…</p>}
      <div className="fn-inline">
        {failed && <button type="button" className="fn-button fn-button--primary" onClick={() => window.location.reload()}>Recarregar a página</button>}
        <button type="button" className="fn-button" ref={closeRef} onClick={onClose}>Fechar</button>
      </div>
    </div>
  </div>;
}

// Falha do chunk (deploy novo trocou os hashes) ou erro de render do painel:
// mostra a camada de falha em vez de derrubar a TopBar inteira. O lazy guarda
// a rejeicao, entao a saida e recarregar a pagina.
class PanelBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    // Sem a mensagem/stack: erro de render pode carregar dado do contato.
    console.warn("Painel do funil indisponivel:", error instanceof Error ? error.name : "erro");
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

// Botao "Funil" da barra superior. Renderiza (e consulta) NADA quando o funil
// esta indisponivel: Ver como, flag global, tenant sem funil ou perfil sem
// ver_funil. O quadro fica em memoria enquanto a sessao/perfil nao muda:
// reabrir mostra os mesmos dados (com "dados de HH:MM"), sem polling.
export function FunnelEntry() {
  const access = useFunnelAccess();
  const [open, setOpen] = useState(false);
  const [board, dispatch] = useReducer(boardReducer, undefined, () => createBoardState());
  const [filters, setFilters] = useState<BoardFilters>(DEFAULT_FILTERS);
  const [tab, setTab] = useState<FunnelPanelTab>("board");
  const trigger = useRef<HTMLButtonElement>(null);
  const scope = useRef<string | null>(null);
  const scrollTimer = useRef<number | null>(null);
  const returnFocus = useCallback(() => trigger.current, []);

  // O quadro pertence a UMA identidade/perfil (escopo LGPD): trocou de
  // usuario, de toggle ou o funil saiu do ar -> descarta o estado; se ficou
  // indisponivel, fecha tambem (nada do funil fica montado).
  const scopeKey = access.available ? access.accessKey : null;
  useEffect(() => {
    if (scope.current === scopeKey) return;
    const hadScope = scope.current !== null;
    scope.current = scopeKey;
    if (hadScope) {
      dispatch({ type: "reset" });
      setFilters(DEFAULT_FILTERS);
      setTab("board");
    }
    if (!scopeKey) setOpen(false);
  }, [scopeKey]);

  useEffect(() => () => { if (scrollTimer.current != null) window.clearTimeout(scrollTimer.current); }, []);

  const close = useCallback((options?: { toChat?: boolean }) => {
    setOpen(false);
    if (!options?.toChat || !matches(STACKED_LAYOUT)) return;
    // Layout empilhado: leva a conversa recem-focada para a vista (o foco
    // volta ao botao com preventScroll, entao a rolagem nao e desfeita).
    if (scrollTimer.current != null) window.clearTimeout(scrollTimer.current);
    scrollTimer.current = window.setTimeout(() => {
      scrollTimer.current = null;
      const behavior: ScrollBehavior = matches("(prefers-reduced-motion: reduce)") ? "auto" : "smooth";
      document.querySelector<HTMLElement>(".chat-panel")?.scrollIntoView({ block: "start", behavior });
    }, 60);
  }, []);

  if (!access.available) return null;

  const panel = open ? createPortal(
    <PanelBoundary fallback={<FunnelShell failed onClose={() => close()} returnFocus={returnFocus} />}>
      <Suspense fallback={<FunnelShell failed={false} onClose={() => close()} returnFocus={returnFocus} />}>
        <FunnelPanel board={board} dispatch={dispatch} filters={filters} onFiltersChange={setFilters} tab={tab} onTabChange={setTab} onClose={close} returnFocus={returnFocus} />
      </Suspense>
    </PanelBoundary>,
    document.body,
  ) : null;

  return <>
    <button type="button" className="composer-icon" ref={trigger} onClick={() => setOpen(true)} title="Funil comercial" aria-label="Abrir funil comercial" aria-haspopup="dialog">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 4.5h18l-7 8.2v5.6l-4 2.2v-7.8z" /></svg>
    </button>
    {panel}
  </>;
}
