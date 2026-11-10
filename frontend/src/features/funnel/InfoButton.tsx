// Botao ⓘ do texto explicativo da etapa (cabecalho da coluna, cartao do
// contato). Controlado pelo pai: o texto fica num elemento irmao com
// `hidden`, apontado por aria-controls.
export function InfoButton({ expanded, controls, subject, onToggle }: { expanded: boolean; controls: string; subject: string; onToggle: () => void }) {
  return <button type="button" className="fn-info-button" aria-expanded={expanded} aria-controls={controls} onClick={onToggle} title={expanded ? "Ocultar o que significa esta etapa" : "O que significa esta etapa"}>
    <span aria-hidden="true">ⓘ</span><span className="fn-sr">{expanded ? "Ocultar explicação da etapa" : "Explicação da etapa"} {subject}</span>
  </button>;
}
