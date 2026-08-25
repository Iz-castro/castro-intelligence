/*
 * Parser da formatacao do WhatsApp — puro (sem React, sem HTML, sem
 * dependencia). Produz uma arvore (blocos > inline) que WaText.tsx renderiza
 * como elementos React e waPlainText() achata pra previas (citacao de
 * resposta), igual ao proprio WhatsApp faz na caixa de resposta.
 *
 * Sintaxe suportada (a do WhatsApp, nao Markdown):
 *   *negrito*  _italico_  ~riscado~  `mono`  ```bloco mono```
 *   > citacao      - item / * item      1. item
 * Regras de pareamento (aproximam o app): marcador de abertura precedido por
 * inicio/nao-letra e colado no texto; fechamento colado no texto e seguido
 * por fim/nao-letra; nunca atravessa linha; mesmo marcador nao aninha.
 *
 * Links: http(s)://, www., dominio "pelado" com TLD conhecido
 * (doc.gov.br/x, wa.me/55...) e e-mail. Href so sai daqui com prefixo
 * https:// ou mailto: — nunca um esquema vindo do texto do cliente.
 * Marcadores dentro de um link (a_b_c na URL) nao viram formatacao.
 */

export type WaInline =
  | { type: "text"; value: string }
  | { type: "link"; href: string; label: string }
  | { type: "bold" | "italic" | "strike"; children: WaInline[] }
  | { type: "mono"; value: string };

export type WaBlock =
  | { type: "line"; children: WaInline[] }
  | { type: "quote"; children: WaInline[] }
  | { type: "bullet"; children: WaInline[] }
  | { type: "number"; marker: string; children: WaInline[] }
  | { type: "pre"; value: string };

type LinkSpan = { start: number; end: number; href: string; label: string };

// TLDs aceitos pra dominio sem esquema/www. `br` cobre gov.br, com.br, jus.br...
const TLDS = "br|com|org|net|gov|edu|io|app|me|co|info|us|dev|online|site|digital|link|page|shop|store|cloud|ai|tv|blog|biz|eu|pt|es|ar|uk|de|fr|it|ca|mx|cl|uy|py|bo|pe|ve";

const LINK_RE = new RegExp(
  [
    "[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)+",
    "https?:\\/\\/[^\\s<>\"']+",
    "www\\.[^\\s<>\"']+",
    `(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\\.)+(?:${TLDS})(?:\\/[^\\s<>"']*)?`,
  ].join("|"),
  "gi",
);
const FENCE_RE = /```([\s\S]*?)```/g;
const QUOTE_RE = /^>\s?(.*)$/;
const BULLET_RE = /^[-*]\s+(.*)$/;
const NUMBER_RE = /^(\d{1,3})\.\s+(.*)$/;
const WORD_RE = /[\p{L}\p{N}]/u;
const MARKERS = "*_~`";
const TRAILING_PUNCT = ".,;:!?'\"*_~`";

function isWord(ch: string | undefined): boolean {
  return ch !== undefined && WORD_RE.test(ch);
}
function isSpace(ch: string | undefined): boolean {
  return ch !== undefined && /\s/.test(ch);
}

function countChar(s: string, ch: string): number {
  let n = 0;
  for (const c of s) if (c === ch) n += 1;
  return n;
}

// Tira pontuacao/marcador colado no fim do link ("veja x.com." / "*x.com*")
// e parentese/colchete de fechamento sem par dentro do proprio link.
function trimTrailing(text: string, start: number, end: number): number {
  while (end > start) {
    const ch = text[end - 1];
    if (TRAILING_PUNCT.includes(ch)) { end -= 1; continue; }
    if (ch === ")" || ch === "]") {
      const open = ch === ")" ? "(" : "[";
      const slice = text.slice(start, end);
      if (countChar(slice, ch) > countChar(slice, open)) { end -= 1; continue; }
    }
    break;
  }
  return end;
}

function findLinks(line: string): LinkSpan[] {
  const spans: LinkSpan[] = [];
  LINK_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = LINK_RE.exec(line)) !== null) {
    const start = m.index;
    const rawEnd = start + m[0].length;
    const prev = start > 0 ? line[start - 1] : undefined;
    const next = rawEnd < line.length ? line[rawEnd] : undefined;
    // Fronteira de palavra dos dois lados: "site.compras" nao e link
    // (TLD colado em letra), nem um dominio grudado num @ ou / anterior.
    if (isWord(prev) || prev === "@" || prev === "/" || isWord(next)) continue;
    const end = trimTrailing(line, start, rawEnd);
    if (end <= start) continue;
    const label = line.slice(start, end);
    const lower = label.toLowerCase();
    let href: string;
    if (label.includes("@") && !lower.startsWith("http")) href = `mailto:${label}`;
    else if (lower.startsWith("http://") || lower.startsWith("https://")) href = label;
    else href = `https://${label}`;
    spans.push({ start, end, href, label });
  }
  return spans;
}

function linkStartingAt(links: LinkSpan[], i: number): LinkSpan | null {
  for (const l of links) if (l.start === i) return l;
  return null;
}
function insideLink(links: LinkSpan[], i: number): boolean {
  for (const l of links) if (i >= l.start && i < l.end) return true;
  return false;
}

function canOpen(s: string, i: number, to: number): boolean {
  if (i + 1 >= to) return false;
  const prev = i > 0 ? s[i - 1] : undefined;
  const next = s[i + 1];
  if (isWord(prev)) return false;
  if (isSpace(next) || next === s[i]) return false;
  return true;
}

function findClose(s: string, marker: string, from: number, to: number, links: LinkSpan[]): number {
  for (let j = from; j < to; j += 1) {
    if (s[j] !== marker || insideLink(links, j)) continue;
    if (isSpace(s[j - 1])) continue;
    const next = j + 1 < to ? s[j + 1] : undefined;
    if (isWord(next)) continue;
    return j;
  }
  return -1;
}

function kindOf(marker: string): "bold" | "italic" | "strike" {
  if (marker === "*") return "bold";
  if (marker === "_") return "italic";
  return "strike";
}

function parseInline(s: string, from: number, to: number, links: LinkSpan[], banned: string): WaInline[] {
  const out: WaInline[] = [];
  let buf = "";
  const flush = () => { if (buf) { out.push({ type: "text", value: buf }); buf = ""; } };
  let i = from;
  while (i < to) {
    const link = linkStartingAt(links, i);
    if (link && link.end <= to) {
      flush();
      out.push({ type: "link", href: link.href, label: link.label });
      i = link.end;
      continue;
    }
    const ch = s[i];
    if (MARKERS.includes(ch) && !banned.includes(ch) && canOpen(s, i, to)) {
      const j = findClose(s, ch, i + 1, to, links);
      if (j !== -1) {
        flush();
        if (ch === "`") out.push({ type: "mono", value: s.slice(i + 1, j) });
        else out.push({ type: kindOf(ch), children: parseInline(s, i + 1, j, links, banned + ch) });
        i = j + 1;
        continue;
      }
    }
    buf += ch;
    i += 1;
  }
  flush();
  return out;
}

function parseLine(line: string): WaBlock {
  const inline = (text: string) => parseInline(text, 0, text.length, findLinks(text), "");
  const q = QUOTE_RE.exec(line);
  if (q) return { type: "quote", children: inline(q[1]) };
  const b = BULLET_RE.exec(line);
  if (b) return { type: "bullet", children: inline(b[1]) };
  const n = NUMBER_RE.exec(line);
  if (n) return { type: "number", marker: n[1], children: inline(n[2]) };
  return { type: "line", children: inline(line) };
}

function pushLines(segment: string, blocks: WaBlock[], afterFence: boolean, beforeFence: boolean) {
  let s = segment;
  if (afterFence) s = s.replace(/^\n/, "");
  if (beforeFence) s = s.replace(/\n$/, "");
  if (!s) return;
  for (const line of s.split("\n")) blocks.push(parseLine(line));
}

export function parseWaText(text: string): WaBlock[] {
  const src = String(text ?? "").replace(/\r\n?/g, "\n");
  const blocks: WaBlock[] = [];
  let last = 0;
  FENCE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = FENCE_RE.exec(src)) !== null) {
    if (!m[1].trim()) continue;
    pushLines(src.slice(last, m.index), blocks, last > 0, true);
    blocks.push({ type: "pre", value: m[1].replace(/^\n/, "").replace(/\n$/, "") });
    last = m.index + m[0].length;
  }
  pushLines(src.slice(last), blocks, last > 0, false);
  return blocks;
}

function inlineText(nodes: WaInline[]): string {
  return nodes.map((n) => {
    if (n.type === "text" || n.type === "mono") return n.value;
    if (n.type === "link") return n.label;
    return inlineText(n.children);
  }).join("");
}

function blockText(block: WaBlock): string {
  switch (block.type) {
    case "pre": return block.value;
    case "bullet": return `• ${inlineText(block.children)}`;
    case "number": return `${block.marker}. ${inlineText(block.children)}`;
    default: return inlineText(block.children);
  }
}

// Texto sem marcadores (links viram o proprio rotulo). Pra previas.
export function waPlainText(text: string): string {
  return parseWaText(text).map(blockText).join("\n");
}
