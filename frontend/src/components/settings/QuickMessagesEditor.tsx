import type { QuickMessage } from "../../types";
import { duplicateQuickShortcuts, isQuickMessageComplete, normalizeShortcut } from "../../utils/quickMessages";

type Props = {
  items: QuickMessage[];
  onChange: (items: QuickMessage[]) => void;
  addLabel: string;
  /** Limite de itens (lista pessoal). Sem valor = sem limite (globais). */
  max?: number;
};

// Editor das mensagens rapidas (globais do tenant e pessoais do operador):
// um card por mensagem com titulo (pra identificar na lista), atalho e o
// texto num textarea. Trava: card incompleto ou com atalho repetido fica
// marcado e bloqueia o "+ Adicionar" ate ser corrigido (ou removido); o
// salvar valida de novo (quickMessagesProblem) e o backend rejeita
// atalho/mensagem vazios e atalho repetido.
export function QuickMessagesEditor({ items, onChange, addLabel, max }: Props) {
  const duplicates = new Set(duplicateQuickShortcuts(items));
  const hasProblem = items.some((qm) => !isQuickMessageComplete(qm) || duplicates.has(normalizeShortcut(qm.shortcut)));
  const atLimit = max != null && items.length >= max;

  function update(idx: number, patch: Partial<QuickMessage>) {
    onChange(items.map((qm, i) => (i === idx ? { ...qm, ...patch } : qm)));
  }

  return (
    <div className="qm-editor">
      {items.length === 0 ? <div className="sub qm-hint">Nenhuma mensagem rapida cadastrada.</div> : null}
      {items.map((qm, idx) => {
        const complete = isQuickMessageComplete(qm);
        const duplicate = duplicates.has(normalizeShortcut(qm.shortcut));
        const cardClass = `qm-card${complete ? "" : " is-incomplete"}${duplicate ? " is-duplicate" : ""}`;
        return (
          <div key={idx} className={cardClass}>
            <div className="qm-card-head">
              <span className="qm-index">{idx + 1}</span>
              <input className="qm-title" value={qm.title ?? ""} onChange={(e) => update(idx, { title: e.target.value })} placeholder="Titulo (ex.: Saudacao Tanusa)" aria-label="Titulo" />
              <input className="qm-shortcut" value={qm.shortcut} onChange={(e) => update(idx, { shortcut: e.target.value })} placeholder="/atalho" aria-label="Atalho" />
              <button type="button" className="ghost qm-remove" onClick={() => onChange(items.filter((_, i) => i !== idx))} aria-label="Remover mensagem" title="Remover">X</button>
            </div>
            <textarea className="qm-text" value={qm.message} onChange={(e) => update(idx, { message: e.target.value })} placeholder="Mensagem completa (como vai pro cliente)" rows={2} aria-label="Mensagem" />
            {complete ? null : <div className="qm-warn">Preencha titulo, atalho e mensagem — ou remova este item.</div>}
            {duplicate ? <div className="qm-warn">Atalho repetido: outra mensagem desta lista usa {normalizeShortcut(qm.shortcut)}.</div> : null}
          </div>
        );
      })}
      {atLimit ? (
        <div className="sub qm-hint">Limite de {max} mensagens rapidas atingido.</div>
      ) : (
        <button
          type="button"
          className="ghost qm-add"
          disabled={hasProblem}
          title={hasProblem ? "Corrija a mensagem marcada antes de adicionar outra" : undefined}
          onClick={() => onChange([...items, { title: "", shortcut: "", message: "" }])}
        >{addLabel}</button>
      )}
    </div>
  );
}
