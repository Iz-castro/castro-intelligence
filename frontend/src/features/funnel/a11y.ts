import { useLayoutEffect, useRef, type RefObject } from "react";

// Pilha de camadas do funil (painel -> drawer -> dialogo). Esc fecha SO a do
// topo; Tab circula dentro da do topo; ao fechar, o foco volta ao elemento de
// origem (card, botao "Mover para…") ou, se ele saiu da tela, a camada de
// baixo. Nucleo puro (testavel sem DOM) + um listener de documento so
// enquanto houver camada aberta.

export type Layer = { id: number; onEscape: () => void; element: () => HTMLElement | null };

export function createLayerStack() {
  const layers: Layer[] = [];
  let sequence = 0;
  return {
    push(onEscape: () => void, element: () => HTMLElement | null = () => null): { id: number; release: () => void } {
      sequence += 1;
      const layer: Layer = { id: sequence, onEscape, element };
      layers.push(layer);
      return {
        id: layer.id,
        release: () => {
          const index = layers.findIndex((entry) => entry.id === layer.id);
          if (index >= 0) layers.splice(index, 1);
        },
      };
    },
    top(): Layer | null {
      return layers.length ? layers[layers.length - 1] : null;
    },
    size(): number {
      return layers.length;
    },
    // Esc: so o topo reage. Devolve se alguma camada tratou.
    escape(): boolean {
      const top = layers.length ? layers[layers.length - 1] : null;
      if (!top) return false;
      top.onEscape();
      return true;
    },
  };
}

const stack = createLayerStack();

const FOCUSABLE = [
  "button:not(:disabled)", "input:not(:disabled):not([type='hidden'])", "select:not(:disabled)", "textarea:not(:disabled)",
  "a[href]", "summary", "[tabindex]:not([tabindex='-1'])",
].join(", ");

export function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((element) => element.getClientRects().length > 0 && !element.closest("[hidden], [inert]"));
}

function handleKeydown(event: KeyboardEvent) {
  const top = stack.top();
  if (!top) return;
  if (event.key === "Escape") {
    // Componente que ja consumiu o Esc (ex.: limpar a busca) chama preventDefault.
    if (event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    stack.escape();
    return;
  }
  if (event.key !== "Tab") return;
  const root = top.element();
  if (!root) return;
  const items = focusableIn(root);
  if (!items.length) { event.preventDefault(); root.focus(); return; }
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || !root.contains(active))) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && (active === last || !root.contains(active))) { event.preventDefault(); first.focus(); }
}

function focusQuietly(element: HTMLElement | null | undefined): boolean {
  if (!element || !element.isConnected) return false;
  element.focus({ preventScroll: true });
  return document.activeElement === element;
}

export function useLayer(ref: RefObject<HTMLElement>, onEscape: () => void, options: {
  initialFocus?: RefObject<HTMLElement | null>; returnFocus?: () => HTMLElement | null;
} = {}) {
  const escapeRef = useRef(onEscape);
  escapeRef.current = onEscape;
  const returnRef = useRef(options.returnFocus);
  returnRef.current = options.returnFocus;
  const initialRef = options.initialFocus;
  // StrictMode (dev) desmonta e remonta: a origem do foco e capturada uma vez
  // e a restauracao adiada so roda se a camada nao voltou.
  const previousRef = useRef<HTMLElement | null>(null);
  const mountedRef = useRef(false);

  useLayoutEffect(() => {
    mountedRef.current = true;
    if (!previousRef.current && document.activeElement instanceof HTMLElement) previousRef.current = document.activeElement;
    const layer = stack.push(() => escapeRef.current(), () => ref.current);
    if (stack.size() === 1) document.addEventListener("keydown", handleKeydown);
    const container = ref.current;
    if (container && !container.contains(document.activeElement)) {
      // Alvo inicial desabilitado/oculto nao recebe foco: cai no container.
      if (!focusQuietly(initialRef?.current)) container.focus({ preventScroll: true });
    }
    return () => {
      mountedRef.current = false;
      layer.release();
      if (stack.size() === 0) document.removeEventListener("keydown", handleKeydown);
      // Adiado: quando varias camadas fecham juntas, o DOM ja saiu e so a
      // origem que ainda existe recebe o foco (nunca um no removido).
      window.setTimeout(() => {
        if (mountedRef.current) return;
        // Outra camada ja assumiu o foco (ex.: o painel real substituiu o
        // "Carregando…" do lazy): restaurar aqui roubaria o foco dela.
        const top = stack.top()?.element();
        if (top && document.activeElement instanceof Node && top.contains(document.activeElement)) return;
        if (focusQuietly(returnRef.current?.()) || focusQuietly(previousRef.current)) return;
        focusQuietly(stack.top()?.element());
      }, 0);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
