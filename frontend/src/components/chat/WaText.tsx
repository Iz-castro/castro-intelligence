import { Fragment, useMemo, type ReactNode } from "react";
import { parseWaText, type WaInline } from "../../utils/waFormat";

/*
 * Renderiza texto com a formatacao do WhatsApp (parser em utils/waFormat.ts).
 * So elementos React — nunca innerHTML: o texto vem do cliente. Links abrem
 * em aba nova com noopener; o href ja vem saneado do parser (https/mailto).
 */
function renderInline(nodes: WaInline[]): ReactNode[] {
  return nodes.map((node, i) => {
    switch (node.type) {
      case "text": return <Fragment key={i}>{node.value}</Fragment>;
      case "link": return <a key={i} className="wa-link" href={node.href} target="_blank" rel="noopener noreferrer">{node.label}</a>;
      case "bold": return <strong key={i}>{renderInline(node.children)}</strong>;
      case "italic": return <em key={i}>{renderInline(node.children)}</em>;
      case "strike": return <s key={i}>{renderInline(node.children)}</s>;
      case "mono": return <code key={i} className="wa-code">{node.value}</code>;
      default: return null;
    }
  });
}

export function WaText({ text }: { text: string }) {
  const blocks = useMemo(() => parseWaText(text), [text]);
  const out: ReactNode[] = [];
  let prevWasLine = false;
  blocks.forEach((block, i) => {
    if (block.type === "line") {
      // Linhas simples: <br/> so entre linhas consecutivas. Citacao, lista e
      // bloco mono sao display:block e quebram sozinhos.
      if (prevWasLine) out.push(<br key={`br-${i}`} />);
      out.push(<Fragment key={i}>{renderInline(block.children)}</Fragment>);
      prevWasLine = true;
      return;
    }
    prevWasLine = false;
    if (block.type === "pre") { out.push(<code key={i} className="wa-pre">{block.value}</code>); return; }
    if (block.type === "quote") { out.push(<span key={i} className="wa-quote">{renderInline(block.children)}</span>); return; }
    const marker = block.type === "bullet" ? "•" : `${block.marker}.`;
    out.push(<span key={i} className="wa-li"><span className="wa-li-marker">{marker}</span><span className="wa-li-body">{renderInline(block.children)}</span></span>);
  });
  return <>{out}</>;
}
