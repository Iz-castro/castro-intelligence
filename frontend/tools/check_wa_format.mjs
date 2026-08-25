// Gate do parser de formatacao do WhatsApp (src/utils/waFormat.ts).
// Uso, a partir de frontend/:  node tools/check_wa_format.mjs
// Compila o .ts com o esbuild que ja vem com o Vite, importa e roda os casos
// abaixo. Sai 0/1, no espirito de tools/sim_bot_flow.py.
import { build } from "esbuild";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const dir = mkdtempSync(join(tmpdir(), "waformat-"));
const outfile = join(dir, "waFormat.mjs");
await build({ entryPoints: ["src/utils/waFormat.ts"], bundle: true, format: "esm", outfile, logLevel: "silent" });
const { parseWaText, waPlainText } = await import(pathToFileURL(outfile).href);

let failed = 0;
let passed = 0;
function check(name, cond, detail) {
  if (cond) { passed += 1; return; }
  failed += 1;
  console.log(`FAIL ${name}${detail !== undefined ? ` -> ${JSON.stringify(detail)}` : ""}`);
}
const first = (text) => parseWaText(text)[0];
const inl = (text) => first(text).children;
const links = (nodes) => {
  const out = [];
  const walk = (list) => list.forEach((x) => { if (x.type === "link") out.push(x); else if (x.children) walk(x.children); });
  walk(nodes);
  return out;
};
const types = (nodes) => nodes.map((x) => x.type).join(",");

// --- negrito / italico / riscado / mono ---------------------------------
{ const n = inl("*negrito*"); check("bold", n.length === 1 && n[0].type === "bold" && n[0].children[0].value === "negrito", n); }
{ const n = inl("2*3*4"); check("multiplicacao nao e negrito", n.length === 1 && n[0].type === "text" && n[0].value === "2*3*4", n); }
{ const n = inl("_it_ ~ri~ `mono`"); check("italic/strike/mono", types(n) === "italic,text,strike,text,mono", n); }
{ const n = inl("*_ambos_*"); check("aninhado", n[0].type === "bold" && n[0].children[0].type === "italic", n); }
{ const n = inl("*olá*!"); check("unicode", n[0].type === "bold" && n[1].value === "!", n); }
{ const n = inl("a * b * c"); check("marcador solto", n.length === 1 && n[0].type === "text", n); }
{ const n = inl("*sem fechar"); check("sem fechamento", n.length === 1 && n[0].type === "text", n); }
{ const n = inl("**"); check("par vazio", n.length === 1 && n[0].type === "text", n); }
{ const n = inl("R$ 10 *à vista* ou 2x"); check("frase real", types(n) === "text,bold,text", n); }
check("bullet com asterisco", first("* item").type === "bullet");

// --- links ----------------------------------------------------------------
{ const n = inl("veja https://x.com/a_b_c ok"); const l = links(n); check("url com underscore", l.length === 1 && l[0].href === "https://x.com/a_b_c", l); check("sem italico na url", n.every((x) => x.type !== "italic"), n); }
{ const n = inl("*veja https://x.com*"); const l = links(n); check("negrito com link dentro", n[0].type === "bold" && l.length === 1 && l[0].href === "https://x.com", n); }
{ const l = links(inl("acesse doc.gov.br/consulta agora")); check("dominio pelado gov.br", l.length === 1 && l[0].href === "https://doc.gov.br/consulta" && l[0].label === "doc.gov.br/consulta", l); }
{ const n = inl("www.site.com.br."); check("www + ponto final", n[0].type === "link" && n[0].href === "https://www.site.com.br" && n[1].value === ".", n); }
{ const l = links(inl("email: joao@empresa.com.br")); check("email", l.length === 1 && l[0].href === "mailto:joao@empresa.com.br", l); }
{ const l = links(inl("arquivo.pdf e R$ 10.50 e site.compras e fim.")); check("falsos positivos", l.length === 0, l); }
{ const l = links(inl("javascript:alert(1) e data:text/html,x")); check("esquema perigoso", l.length === 0, l); }
{ const l = links(inl("(https://x.com/a)")); check("parentese externo", l.length === 1 && l[0].label === "https://x.com/a", l); }
{ const l = links(inl("https://pt.wikipedia.org/wiki/A_(b)")); check("parentese interno", l.length === 1 && l[0].label === "https://pt.wikipedia.org/wiki/A_(b)", l); }
{ const l = links(inl("wa.me/5531983440484")); check("wa.me", l.length === 1 && l[0].href === "https://wa.me/5531983440484", l); }
{ const l = links(inl("https://secret.autentique.com.br/documentos/2a51c95e10620b8f8a2be008af7aca280cd7407a")); check("link do print", l.length === 1, l); }
{ const n = inl("`https://x.com`"); check("mono nao linkifica", n.length === 1 && n[0].type === "mono", n); }
{ const l = links(inl("Maiusculo: HTTPS://X.COM/A")); check("maiusculo", l.length === 1 && l[0].href === "HTTPS://X.COM/A", l); }

// --- blocos ---------------------------------------------------------------
{ const b = parseWaText("> citação\n- item\n1. um\nfim"); check("blocos", types(b) === "quote,bullet,number,line" && b[2].marker === "1", b); }
{ const b = parseWaText("a\n\nb"); check("linha vazia preservada", b.length === 3 && b[1].children.length === 0, b); }
{ const b = parseWaText("x\n```\ncode *x*\n```\ny"); check("fence", types(b) === "line,pre,line" && b[1].value === "code *x*", b); }
{ const b = parseWaText("a\r\nb"); check("crlf", b.length === 2, b); }
{ const b = parseWaText(""); check("texto vazio", b.length === 0, b); }
{ const b = parseWaText("👤 Fulano\n📞 +55 31 98765-4321"); check("cartao de contato", b.length === 2 && links(b[1].children).length === 0, b); }

// --- texto plano (previas) ------------------------------------------------
check("plain", waPlainText("*a* _b_ https://x.com") === "a b https://x.com", waPlainText("*a* _b_ https://x.com"));
check("plain lista", waPlainText("- x\n1. y") === "• x\n1. y", waPlainText("- x\n1. y"));

rmSync(dir, { recursive: true, force: true });
console.log(`${passed} ok, ${failed} falha(s)`);
process.exit(failed ? 1 : 0);
