import { useEffect, useId, useRef, useState } from "react";
import type { Auth } from "firebase/auth";
import type { PickerRow } from "../../types";
import { searchContacts } from "./api";
import { funnelErrorMessage } from "./errors";
import { formatCount, plural } from "./format";

const DEBOUNCE_MS = 300;

// Mesma regra do picker v2.1 (2+ letras ou 4+ digitos) para nao gastar busca.
export function searchProblem(term: string): string {
  const text = term.trim();
  if (!text) return "";
  const hasLetter = /\p{L}/u.test(text);
  const digits = (text.match(/\d/g) || []).length;
  const ready = hasLetter ? text.replace(/[^\p{L}\p{N}]+/gu, "").length >= 2 : digits >= 4;
  return ready ? "" : "Digite ao menos 2 letras ou 4 números.";
}

// Resultado mostra so o final do telefone (o card do funil nem isso mostra).
function phoneEnd(phone: string): string {
  const digits = (phone || "").replace(/\D/g, "");
  return digits.length >= 4 ? `final ${digits.slice(-4)}` : "";
}

// Busca do quadro pelo endpoint do picker (escopo do backend), sem
// qualification no resultado; abrir = drawer por id (nada e assumido).
export function FunnelSearch({ auth, onOpen }: { auth: Auth; onOpen: (contactId: number, trigger: HTMLElement) => void }) {
  const id = useId();
  const [term, setTerm] = useState("");
  const [rows, setRows] = useState<PickerRow[] | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);
  const immediate = useRef(false);
  const sequence = useRef(0);

  useEffect(() => {
    const text = term.trim();
    const request = ++sequence.current;
    if (!text) { setRows(null); setHint(""); setTruncated(false); setBusy(false); return; }
    const problem = searchProblem(text);
    if (problem) { setRows(null); setHint(problem); setBusy(false); return; }
    setHint("");
    const delay = immediate.current ? 0 : DEBOUNCE_MS;
    immediate.current = false;
    const timer = window.setTimeout(() => {
      if (request !== sequence.current) return;
      setBusy(true);
      void searchContacts(auth, text, 20).then((result) => {
        if (request !== sequence.current) return;
        setRows(Array.isArray(result.contacts) ? result.contacts.filter((row) => row && Number.isInteger(row.id)) : []);
        setTruncated(Boolean(result.truncated));
      }).catch((reason) => { if (request === sequence.current) setHint(funnelErrorMessage(reason)); })
        .finally(() => { if (request === sequence.current) setBusy(false); });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [auth, term, nonce]);

  const status = busy ? "Buscando…" : hint || (!rows ? "" : rows.length
    ? `${formatCount(rows.length)}${truncated ? "+" : ""} ${plural(rows.length, "resultado", "resultados")}${truncated ? ": refine a busca para ver os demais." : ""}`
    : "Nenhum contato encontrado no seu acesso.");
  return <div className="fn-search" role="search">
    <label htmlFor={`${id}-input`} className="fn-sr">Buscar contato no funil</label>
    <input id={`${id}-input`} type="search" value={term} maxLength={120} autoComplete="off" placeholder="Buscar contato (nome ou telefone)"
      aria-describedby={`${id}-status`} aria-controls={rows?.length ? `${id}-results` : undefined}
      onChange={(event) => setTerm(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") { event.preventDefault(); immediate.current = true; setNonce((value) => value + 1); }
        // Esc com texto so limpa a busca (preventDefault: a camada nao fecha).
        if (event.key === "Escape" && term) { event.preventDefault(); setTerm(""); }
      }} />
    <p id={`${id}-status`} className="fn-search-status" role="status" aria-live="polite">{status}</p>
    {rows && rows.length > 0 && <ul id={`${id}-results`} className="fn-search-results" aria-label="Resultados da busca">{rows.map((row) => <li key={row.id}>
      <button type="button" onClick={(event) => onOpen(row.id, event.currentTarget)}><strong>{row.display_name || `Contato #${row.id}`}</strong><span>{[phoneEnd(row.phone_formatted), `Dono do lead: ${row.assigned_name || "sem dono"}`].filter(Boolean).join(" · ")}</span></button>
    </li>)}</ul>}
  </div>;
}
