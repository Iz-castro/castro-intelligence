import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";

import { useCrm } from "../../context/CrmContext";
import { chatTabRealName } from "../../hooks/useChatTabs";

// Regiao do chat controlada pelas guias (role=tabpanel no ChatPanel).
export const CHAT_TABPANEL_ID = "chat-tabpanel";
export const chatTabDomId = (id: string) => `chat-tab-${id}`;
const SHORTCUT_HINT = "Ctrl+Alt+↑/↓ alterna as guias";

// any: a faixa transborda. Com transbordo as DUAS setas ficam na tela (a do
// lado sem nada escondido desabilitada): a largura da faixa nao muda ao rolar,
// e a guia ativa revelada nao e cortada pela seta que apareceria depois.
type Overflow = { any: boolean; left: number; right: number; leftUnread: number; rightUnread: number };
const NO_OVERFLOW: Overflow = { any: false, left: 0, right: 0, leftUnread: 0, rightUnread: 0 };
const sameOverflow = (a: Overflow, b: Overflow) => a.any === b.any && a.left === b.left && a.right === b.right && a.leftUnread === b.leftUnread && a.rightUnread === b.rightUnread;

// Guias de conversa (PO 2026-10-28): faixa no topo do painel do chat com as
// conversas abertas, como as guias do navegador. Clique (ou Enter) abre, X /
// botao do meio / Delete fecha, setas esquerda/direita andam entre as guias,
// Ctrl+Alt+Seta cima/baixo alterna de qualquer lugar (useChatTabs). Guia nao
// ativa com mensagem nao lida pisca (so visual, sem som). As guias encolhem
// ate um minimo; o que nao cabe rola, com indicador nas pontas (e quantas das
// escondidas tem nao lidas). Aparece mesmo sem conversa selecionada; nunca na
// aba de Ver como (readOnly).
export function ChatTabs() {
  const { readOnly, tabInfo, activateTab, closeTab, closeAllTabs } = useCrm();
  const stripRef = useRef<HTMLDivElement | null>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const tabsRef = useRef(tabInfo);
  tabsRef.current = tabInfo;
  const [overflow, setOverflow] = useState<Overflow>(NO_OVERFLOW);
  const [focusAfterClose, setFocusAfterClose] = useState<string | null>(null);
  const visible = !readOnly && tabInfo.length > 0;
  const activeId = tabInfo.find((tab) => tab.isActive)?.id ?? null;
  const activeIdRef = useRef(activeId);
  activeIdRef.current = activeId;
  const tabKey = tabInfo.map((tab) => tab.id).join("|");

  // Guia ativa (inclusive a recem-aberta, que entra no fim) sempre a vista:
  // rola so a faixa, na horizontal (nao mexe na rolagem da pagina).
  const reveal = useCallback(() => {
    const strip = stripRef.current;
    const id = activeIdRef.current;
    const element = id ? tabRefs.current.get(id)?.parentElement : null;
    if (!strip || !element) return;
    const box = strip.getBoundingClientRect();
    const rect = element.getBoundingClientRect();
    if (rect.left < box.left) strip.scrollLeft -= box.left - rect.left + 8;
    else if (rect.right > box.right) strip.scrollLeft += rect.right - box.right + 8;
  }, []);

  // Quais guias estao (mesmo que em parte) fora da area visivel, de cada lado,
  // e quantas delas tem nao lidas — o piscar escondido aparece no indicador.
  const measure = useCallback(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const box = strip.getBoundingClientRect();
    const next: Overflow = { any: strip.scrollWidth > strip.clientWidth + 1, left: 0, right: 0, leftUnread: 0, rightUnread: 0 };
    for (const tab of tabsRef.current) {
      const element = tabRefs.current.get(tab.id)?.parentElement;
      if (!element) continue;
      const rect = element.getBoundingClientRect();
      const unread = tab.unread > 0 && !tab.isActive;
      if (rect.left < box.left - 1) { next.left += 1; if (unread) next.leftUnread += 1; }
      else if (rect.right > box.right + 1) { next.right += 1; if (unread) next.rightUnread += 1; }
    }
    setOverflow((prev) => (sameOverflow(prev, next) ? prev : next));
  }, []);

  useEffect(() => { measure(); }, [tabInfo, measure]);

  // Rolar so mede (nao puxa de volta pra ativa). A FAIXA mudar de tamanho
  // (setas aparecendo, fonte carregando, janela) revela a ativa de novo.
  useEffect(() => {
    const strip = stripRef.current;
    if (!visible || !strip) return undefined;
    const resized = () => { reveal(); measure(); };
    strip.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", resized);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resized);
    observer?.observe(strip);
    return () => {
      strip.removeEventListener("scroll", measure);
      window.removeEventListener("resize", resized);
      observer?.disconnect();
    };
  }, [visible, measure, reveal]);

  useEffect(() => { reveal(); }, [activeId, tabKey, overflow.any, reveal]);

  // Fechar pelo teclado/X leva o foco pra guia vizinha (nao se perde no body).
  useEffect(() => {
    if (!focusAfterClose) return;
    tabRefs.current.get(focusAfterClose)?.focus();
    setFocusAfterClose(null);
  }, [focusAfterClose, tabKey]);

  if (!visible) return null;

  const closeWithFocus = (id: string) => {
    const ids = tabInfo.map((tab) => tab.id);
    const index = ids.indexOf(id);
    setFocusAfterClose(ids[index + 1] ?? ids[index - 1] ?? null);
    closeTab(id);
  };
  const closeAll = () => {
    if (tabInfo.some((tab) => tab.hasDraft) && !window.confirm("Fechar todas as guias? Os rascunhos não enviados serão descartados.")) return;
    closeAllTabs();
  };
  const scrollStrip = (direction: -1 | 1) => {
    const strip = stripRef.current;
    if (strip) strip.scrollBy({ left: direction * Math.max(strip.clientWidth * 0.8, 120), behavior: "smooth" });
  };
  // Setas esquerda/direita, Home/End: movem o foco entre as guias (Enter abre
  // — abrir marca como lida, entao nao abre so de passar). Delete fecha.
  const onTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, id: string) => {
    const ids = tabInfo.map((tab) => tab.id);
    const index = ids.indexOf(id);
    let target = -1;
    if (event.key === "ArrowRight") target = (index + 1) % ids.length;
    else if (event.key === "ArrowLeft") target = (index - 1 + ids.length) % ids.length;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = ids.length - 1;
    else if (event.key === "Delete") { event.preventDefault(); closeWithFocus(id); return; }
    else return;
    event.preventDefault();
    tabRefs.current.get(ids[target])?.focus();
  };
  const moreLabel = (count: number, unread: number, side: string) => (count
    ? `${count} ${count === 1 ? "guia" : "guias"} à ${side}${unread ? ` (${unread} com não lidas)` : ""}`
    : `Nenhuma guia escondida à ${side}`);
  // Tab do teclado entra na faixa pela guia ativa (ou pela 1a, sem ativa).
  const focusableId = activeId ?? tabInfo[0].id;

  return (
    <div className="chat-tabs-bar">
      {overflow.any ? (
        <button type="button" className={`chat-tabs__more${overflow.leftUnread ? " unread" : ""}`} onClick={() => scrollStrip(-1)} disabled={!overflow.left}
          aria-label={moreLabel(overflow.left, overflow.leftUnread, "esquerda")} title={moreLabel(overflow.left, overflow.leftUnread, "esquerda")}>
          <span aria-hidden="true">‹</span>{overflow.leftUnread ? <b aria-hidden="true">+{overflow.leftUnread}</b> : null}
        </button>
      ) : null}
      <div ref={stripRef} className="chat-tabs" role="tablist" aria-label="Conversas abertas">
        {tabInfo.map((tab) => {
          const unreadText = tab.unread > 0 ? `${tab.unread} ${tab.unread === 1 ? "não lida" : "não lidas"}` : "";
          const label = [tab.name, tab.channel, unreadText].filter(Boolean).join(", ");
          const realName = chatTabRealName(tab.name);
          const closeLabel = realName ? `Fechar guia de ${realName}` : "Fechar guia";
          const blink = tab.unread > 0 && !tab.isActive;
          const closeOnMiddle = (event: MouseEvent) => {
            if (event.button !== 1) return;
            event.preventDefault();
            closeWithFocus(tab.id);
          };
          return (
            <div
              key={tab.id}
              className={`chat-tab${tab.isActive ? " active" : ""}${blink ? " unread" : ""}`}
              onAuxClick={closeOnMiddle}
              onMouseDown={(event) => { if (event.button === 1) event.preventDefault(); }}
            >
              <button
                type="button"
                role="tab"
                id={chatTabDomId(tab.id)}
                ref={(element) => { if (element) tabRefs.current.set(tab.id, element); else tabRefs.current.delete(tab.id); }}
                className="chat-tab__main"
                aria-selected={tab.isActive}
                aria-controls={CHAT_TABPANEL_ID}
                aria-label={label}
                tabIndex={tab.id === focusableId ? 0 : -1}
                title={`${label} (${SHORTCUT_HINT})`}
                onClick={() => activateTab(tab.id)}
                onKeyDown={(event) => onTabKeyDown(event, tab.id)}
              >
                <span className="chat-tab__name">{tab.name}</span>
                {/* Chip curto: guia minima precisa de espaco pro nome (nome completo no title/aria-label). */}
                {tab.channel ? <span className={`chat-tab__channel ${tab.channel === "Coex" ? "is-coex" : "is-standard"}`} title={tab.channel === "Coex" ? "Coexistence" : "Standard (Cloud API)"}>{tab.channel === "Coex" ? "Coex" : "Std"}</span> : null}
                {tab.unread > 0 ? <b className="badge chat-tab__badge" aria-hidden="true">{tab.unread > 99 ? "99+" : tab.unread}</b> : null}
              </button>
              <button type="button" className="chat-tab__close" tabIndex={-1} aria-label={closeLabel} title={closeLabel} onClick={() => closeWithFocus(tab.id)}>×</button>
            </div>
          );
        })}
      </div>
      {overflow.any ? (
        <button type="button" className={`chat-tabs__more${overflow.rightUnread ? " unread" : ""}`} onClick={() => scrollStrip(1)} disabled={!overflow.right}
          aria-label={moreLabel(overflow.right, overflow.rightUnread, "direita")} title={moreLabel(overflow.right, overflow.rightUnread, "direita")}>
          {overflow.rightUnread ? <b aria-hidden="true">+{overflow.rightUnread}</b> : null}<span aria-hidden="true">›</span>
        </button>
      ) : null}
      {tabInfo.length >= 2 ? (
        <button type="button" className="chat-tabs__close-all" onClick={closeAll} title="Fechar todas as guias">Fechar todas</button>
      ) : null}
    </div>
  );
}
