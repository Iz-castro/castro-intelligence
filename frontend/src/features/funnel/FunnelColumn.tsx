import { memo, useState } from "react";
import { columnHasHidden, type BoardColumn } from "./boardReducer";
import { FunnelCard } from "./FunnelCard";
import { formatCount, plural } from "./format";
import { InfoButton } from "./InfoButton";
import type { FunnelCard as FunnelCardData } from "./types";

type Props = {
  column: BoardColumn;
  // Rotulo do catalogo (textos da clinica recem-salvos valem sem recarregar
  // o quadro); sem catalogo, o do /board.
  label?: string;
  description?: string;
  current: boolean;
  canMove: boolean;
  onOpen: (contactId: number, trigger: HTMLElement) => void;
  onMove: (card: FunnelCardData, trigger: HTMLElement) => void;
  onMore: (stage: string) => void;
};

export function columnDomId(stage: string): string {
  return `fn-column-${stage}`;
}

export const FunnelColumn = memo(function FunnelColumn({ column, label, description, current, canMove, onOpen, onMove, onMore }: Props) {
  const headingId = `${columnDomId(column.stage)}-title`;
  const infoId = `${columnDomId(column.stage)}-info`;
  const [infoOpen, setInfoOpen] = useState(false);
  const title = label || column.label;
  const remaining = Math.max(0, column.count - column.cards.length);
  return <section className={`fn-column fn-kind-top--${column.kind}${current ? " is-current" : ""}${column.active ? "" : " is-inactive"}`} id={columnDomId(column.stage)} aria-labelledby={headingId}>
    <header className="fn-column-header">
      <div className="fn-column-title">
        <h3 id={headingId} tabIndex={-1}>{title}</h3>
        {description && <InfoButton expanded={infoOpen} controls={infoId} subject={title} onToggle={() => setInfoOpen((open) => !open)} />}
      </div>
      <p className="fn-column-count"><strong>{formatCount(column.count)}</strong> {plural(column.count, "contato", "contatos")}{column.staleCount ? <span className="fn-column-stale"> · {formatCount(column.staleCount)} {plural(column.staleCount, "parado", "parados")}</span> : null}</p>
      {description && <p id={infoId} className="fn-column-info" hidden={!infoOpen}>{description}</p>}
      {!column.active && <p className="fn-column-note">Etapa inativa: ainda tem contatos; não recebe novos.</p>}
    </header>
    <div className="fn-column-body">
      {column.cards.length ? <ul className="fn-card-list">{column.cards.map((card) => <li key={card.contact_id}><FunnelCard card={card} canMove={canMove} onOpen={onOpen} onMove={onMove} /></li>)}</ul>
        : <p className="fn-empty-column">{column.count ? "Nenhum contato carregado nesta etapa." : "Nenhum contato nesta etapa."}</p>}
      {columnHasHidden(column) && <p className="fn-column-hidden">Alguns contatos desta etapa estão fora do seu acesso.</p>}
      {column.error && <p className="fn-notice fn-notice--danger" role="alert">{column.error}</p>}
      {column.nextCursor &&<button type="button" className="fn-button fn-load-more" disabled={column.loadingMore} onClick={() => onMore(column.stage)}>{column.loadingMore ? "Carregando…" : remaining ? `Carregar mais (${formatCount(remaining)} restantes)` : "Carregar mais"}</button>}
    </div>
  </section>;
});
