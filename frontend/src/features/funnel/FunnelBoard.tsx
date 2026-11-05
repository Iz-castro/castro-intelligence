import { useEffect, useState } from "react";
import type { BoardColumn } from "./boardReducer";
import { FunnelColumn, columnDomId } from "./FunnelColumn";
import { formatCount } from "./format";
import type { FunnelCard, FunnelStage } from "./types";

type Props = {
  columns: BoardColumn[];
  stages: Map<string, FunnelStage>;
  canMove: boolean;
  busy: boolean;
  onOpen: (contactId: number, trigger: HTMLElement) => void;
  onMove: (card: FunnelCard, trigger: HTMLElement) => void;
  onMore: (stage: string) => void;
};

function prefersReducedMotion(): boolean {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
}

// Colunas na ordem do catalogo, SO as que o backend devolve (etapa
// invisivel ao usuario, como Novo contato sem ver_contatos_agente_funil, nem
// chega). Navegador de etapas: no desktop rola ate a coluna; ate 650px so a
// coluna escolhida fica visivel (CSS). Rotulo e texto explicativo vem do
// catalogo (textos da clinica recem-salvos valem sem recarregar o quadro).
export function FunnelBoard({ columns, stages, canMove, busy, onOpen, onMove, onMore }: Props) {
  const [current, setCurrent] = useState(columns[0]?.stage || "");
  useEffect(() => {
    if (columns.length && !columns.some((column) => column.stage === current)) setCurrent(columns[0].stage);
  }, [columns, current]);

  function select(stage: string) {
    setCurrent(stage);
    window.requestAnimationFrame(() => document.getElementById(columnDomId(stage))?.scrollIntoView({ block: "nearest", inline: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" }));
  }

  const labelOf = (column: BoardColumn) => stages.get(column.stage)?.label || column.label;
  return <div className="fn-board-wrap">
    <nav className="fn-stage-nav" aria-label="Etapas do funil">
      {columns.map((column) => <button key={column.stage} type="button" className={`fn-stage-chip fn-kind-edge--${column.kind}`} aria-current={current === column.stage ? "true" : undefined} onClick={() => select(column.stage)}>
        <span>{labelOf(column)}</span><strong>{formatCount(column.count)}</strong>
      </button>)}
    </nav>
    <div className="fn-board" aria-busy={busy}>
      {columns.map((column) => <FunnelColumn key={column.stage} column={column} label={labelOf(column)} description={stages.get(column.stage)?.description} current={current === column.stage} canMove={canMove} onOpen={onOpen} onMove={onMove} onMore={onMore} />)}
    </div>
  </div>;
}
