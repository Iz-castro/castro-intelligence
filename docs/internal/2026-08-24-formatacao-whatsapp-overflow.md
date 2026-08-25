# 2026-08-24 — Formatação WhatsApp na bolha, overflow de URL e cartão de contato

Pedido do PO: (1) texto "truncado" na janela de mensagens quando o cliente manda link ou
cartão de contato; (2) renderizar a formatação do WhatsApp (negrito, itálico, links clicáveis).
Decisões do PO: sintaxe do WhatsApp (asterisco simples, não Markdown); links clicáveis
**inclusive domínio sem `https://`** (ex.: `doc.gov.br/consulta` — as atendentes não copiam URL
pro navegador); cartão de contato como texto legível; `preview_url` no envio; atalhos no compositor.

## Diagnóstico

- **Não era truncamento, era overflow.** `.bubble p` tinha `white-space: pre-wrap` sem
  `overflow-wrap`; uma URL longa não quebra, vaza do `max-width` da bolha e `.messages` ganha
  scroll horizontal (o que aparecia no print).
- **Cartão de contato era `str(lista)`** em `webhook.py` (inbound e smb echo): repr Python de
  uma lista de dicts, numa linha só — ilegível na bolha, na prévia de resposta, no "Copiar" e na busca.
- Saída já mandava o `body` cru pra Meta (`main.py`), então `*negrito*` digitado pelo operador já
  chegava formatado no celular do cliente; só a **renderização** no CRM faltava.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `frontend/src/styles.css` | `.bubble` `min-width:0` + `overflow-wrap:anywhere`; `.bubble p/.bubble-text` idem + `word-break`; `.messages overflow-x:hidden`; `.reply-quote p` e `.transcription-text` `overflow-wrap`; classes `.wa-link/.wa-code/.wa-pre/.wa-quote/.wa-li` |
| `frontend/src/utils/waFormat.ts` (novo) | Parser puro (sem React/HTML/dependência) → AST de blocos/inline. `*` `_` `~` `` ` `` ``` ``` `>` `-`/`*` `1.`; regras de pareamento do app (marcador colado na palavra, fronteira de palavra, não atravessa linha, mesmo marcador não aninha). Links: `https?://`, `www.`, domínio pelado com TLD whitelist (`br` cobre gov.br/com.br), e-mail. Pontuação/marcador colado no fim é aparado; parêntese sem par também. **Href só sai com `https://` ou `mailto:`** — esquema do texto do cliente nunca vira href. Marcadores dentro de URL (`a_b_c`) não formatam. `waPlainText()` pra prévias. |
| `frontend/src/components/chat/WaText.tsx` (novo) | Renderiza o AST como elementos React (nunca `innerHTML`); `<a target=_blank rel="noopener noreferrer">`. |
| `frontend/src/App.tsx` | Bolha: `<p>` → `<div class="bubble-text"><WaText/>`; `ReplyQuote` mostra `waPlainText(preview)`; view Equipe com `overflowWrap`; `title` no textarea com os atalhos. |
| `frontend/src/utils/formatting.ts` | `buildMessageReplyReference` grava prévia sem marcadores; `messageTypeLabel`: `contacts`→"contato", `location`→"localizacao". |
| `frontend/src/context/CrmContext.tsx` | `handleDraftKeyDown`: Ctrl+B `*`, Ctrl+I `_`, Ctrl+Shift+X `~`, Ctrl+Shift+M `` ` `` (envolve seleção; sem seleção insere par com cursor no meio; toggle se já envolvido). |
| `webhook.py` | `_format_contacts_text()` → "👤 Nome / 📞 fone / ✉️ e-mail / 🏢 org / 📍 endereço / 🔗 url", um bloco por contato; `try/except` cai no repr antigo (caminho do webhook nunca levanta). Usado no inbound e no smb echo. |
| `main.py` | Envio de texto com `"preview_url": True` (cliente vê prévia do link). |
| `frontend/tools/check_wa_format.mjs` (novo) | Gate do parser: compila com o esbuild do Vite e roda 32 asserts. |
| `CLAUDE.md` | Gate novo documentado em "Rodar e validar". |

Comportamento intencional: "Copiar" e busca continuam com o texto **cru** (marcadores), igual ao
WhatsApp; a citação de resposta fica **sem** marcadores, igual ao WhatsApp.

## Validação (2026-08-24)

- `node tools\check_wa_format.mjs` → 32 ok, 0 falhas (casos: multiplicação `2*3*4` não é negrito,
  URL com `_` não vira itálico, `*veja https://x.com*` = negrito com link, `doc.gov.br/consulta`,
  `www.site.com.br.` apara o ponto, e-mail → mailto, `arquivo.pdf`/`R$ 10.50`/`site.compras` não
  linkam, `javascript:`/`data:` não linkam, parêntese externo/interno, `wa.me`, link do print,
  mono não linkifica, blocos, linha vazia preservada, fence, CRLF, texto vazio, texto plano).
- `npm run build` (tsc estrito + vite) OK.
- `py_compile` dos módulos do gate OK; `tools\sim_bot_flow.py` 56/56.
- `_format_contacts_text` exercitado com payload real da Meta (2 contatos, telefones/e-mail/org/
  endereço/url) e com lixo (`[]`, `None`, dict sem name, string) → nunca levanta.

## Pendências / follow-ups

- **Sem commit e sem deploy** — decisão do PO. Deploy exige rebuild da imagem (frontend embutido).
- Mensagens de cartão de contato **antigas** continuam como repr; backfill só se o PO pedir.
- Card estruturado de contato (botão "criar contato") = frente separada.
- Teste manual do PO: link longo do print, cartão de contato real, `*negrito*` vindo do cliente,
  Ctrl+B no compositor, prévia de link no celular do cliente.
