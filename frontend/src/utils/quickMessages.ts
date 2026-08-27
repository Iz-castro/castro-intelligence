import type { QuickMessage } from "../types";

// Regras das mensagens rapidas (globais do tenant e pessoais do operador).
// A UI usa isto pra marcar cards incompletos e travar o salvar; o backend
// (_clean_quick_messages em database_firestore.py) repete a validacao de
// atalho/mensagem vazios e atalho repetido — a trava de verdade e la.

/** Atalho normalizado pra comparar: minusculo, sempre com "/" na frente. */
export function normalizeShortcut(shortcut: string): string {
  const t = (shortcut || "").trim().toLowerCase();
  if (!t) return "";
  return t.startsWith("/") ? t : `/${t}`;
}

/** Completa = titulo, atalho e mensagem preenchidos (o titulo identifica a mensagem na UI). */
export function isQuickMessageComplete(qm: QuickMessage): boolean {
  return Boolean((qm.title || "").trim() && (qm.shortcut || "").trim() && (qm.message || "").trim());
}

/** Atalhos (normalizados) que aparecem mais de uma vez na lista. */
export function duplicateQuickShortcuts(items: QuickMessage[]): string[] {
  const seen = new Map<string, number>();
  for (const qm of items) {
    const k = normalizeShortcut(qm.shortcut);
    if (k) seen.set(k, (seen.get(k) ?? 0) + 1);
  }
  return [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k);
}

/** Mensagem de erro pra travar o salvar; null = lista ok. `label` ex.: "Mensagens globais". */
export function quickMessagesProblem(items: QuickMessage[], label: string): string | null {
  const incomplete = items.map((qm, i) => (isQuickMessageComplete(qm) ? 0 : i + 1)).filter((n) => n > 0);
  if (incomplete.length) {
    return `${label}: preencha titulo, atalho e mensagem (item${incomplete.length > 1 ? "s" : ""} ${incomplete.join(", ")}) ou remova.`;
  }
  const dup = duplicateQuickShortcuts(items);
  if (dup.length) return `${label}: atalho repetido (${dup.join(", ")}).`;
  return null;
}
