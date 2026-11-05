import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { Auth } from "firebase/auth";
import { loadDashboard } from "./api";
import { funnelErrorMessage, isAccessLost } from "./errors";
import { currentMonth, formatClock, formatCount, formatMonth, formatPercent, shiftMonth } from "./format";
import type { Cohort, DashboardData, FunnelCatalog, ReasonCount } from "./types";

// Painel gerencial: count() e coortes no backend (sem varrer mensagens),
// cache de 2 min la. Aqui: barras CSS (1 matiz, 2 tons: mes x mes anterior)
// e tabelas com os numeros sempre visiveis (a barra nunca e o unico canal).

const REFRESH_LOCK_MS = 10_000;
const MONTH_OPTIONS = 18;

type Props = { auth: Auth; catalog: FunnelCatalog; onAccessLost: (error: unknown) => void };

function Bar({ value, max, tone, title }: { value: number; max: number; tone: "current" | "previous"; title: string }) {
  const width = max > 0 && value > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return <span className={`fn-bar fn-bar--${tone}`} title={title} aria-hidden="true"><span style={{ width: `${width}%` }} /></span>;
}

function PairBars({ month, previous, max, monthLabel, previousLabel }: { month: number; previous: number; max: number; monthLabel: string; previousLabel: string }) {
  return <span className="fn-bars">
    <Bar value={month} max={max} tone="current" title={`${monthLabel}: ${formatCount(month)}`} />
    <Bar value={previous} max={max} tone="previous" title={`${previousLabel}: ${formatCount(previous)}`} />
  </span>;
}

function delta(current: number, previous: number): { text: string; direction: "up" | "down" | "flat" } {
  const diff = (current || 0) - (previous || 0);
  if (!diff) return { text: "= igual", direction: "flat" };
  return diff > 0 ? { text: `▲ +${formatCount(diff)}`, direction: "up" } : { text: `▼ −${formatCount(Math.abs(diff))}`, direction: "down" };
}

function StatTile({ label, value, previous, previousLabel, upIsGood }: { label: string; value: number; previous: number; previousLabel: string; upIsGood?: boolean }) {
  const change = delta(value, previous);
  const tone = upIsGood === undefined || change.direction === "flat" ? "neutral" : (change.direction === "up") === upIsGood ? "good" : "bad";
  return <div className="fn-stat">
    <span className="fn-stat-label">{label}</span>
    <strong className="fn-stat-value">{formatCount(value)}</strong>
    <span className={`fn-stat-delta fn-stat-delta--${tone}`}>{change.text} <span className="fn-stat-ref">vs {previousLabel} ({formatCount(previous)})</span></span>
  </div>;
}

function Section({ id, title, subtitle, children }: { id: string; title: string; subtitle?: string; children: ReactNode }) {
  return <section className="fn-dash-card" aria-labelledby={id}>
    <h3 id={id}>{title}</h3>
    {subtitle && <p className="fn-help">{subtitle}</p>}
    {children}
  </section>;
}

function countOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

// Base das taxas da coorte: quem entrou SEM os descartados (etapa de
// exclusao fica fora das metricas de conversao). Payload antigo, sem
// excluded/entered_net, = base igual a entered (sem linha de descartados).
export function cohortBase(cohort: Cohort | null | undefined): { entered: number; excluded: number | null; net: number } {
  const entered = countOrNull(cohort?.entered) ?? 0;
  const excluded = countOrNull(cohort?.excluded);
  const net = countOrNull(cohort?.entered_net) ?? Math.max(0, entered - (excluded ?? 0));
  return { entered, excluded, net };
}

export type CohortRow = { key: string; label: string; value: number | null; base: number | null };

// Linhas da coorte com o denominador de cada taxa (null = sem taxa). Degraus
// (reached ja liquido) e "Encerraram sem agendar" sobre a base sem
// descartados; o aceite LGPD conta a coorte inteira, entao a taxa dele e
// sobre todos que entraram (nunca passa de 100%). `excludedLabel` = rotulo
// da etapa de exclusao do catalogo (Não qualificado na clinica).
export function cohortRows(cohort: Cohort, excludedLabel = "Descartados"): CohortRow[] {
  const { entered, excluded, net } = cohortBase(cohort);
  return [
    { key: "entered", label: "Entraram no funil", value: entered, base: null },
    ...(excluded === null ? [] : [{ key: "excluded", label: excludedLabel, value: excluded, base: null }]),
    { key: "lgpd", label: "Aceitaram o aviso LGPD", value: cohort.lgpd_accepted, base: entered },
    ...(cohort.levels || []).map((level) => ({ key: `level-${level.stage}`, label: `Alcançaram ${level.label}`, value: countOrNull(level.reached), base: net })),
    { key: "closed", label: "Encerraram sem agendar", value: countOrNull(cohort.closed_without_booking) ?? 0, base: net },
  ];
}

export type ReasonRow = { key: string; label: string; month: number; previous: number };

// Une mes e mes anterior por motivo (ordem: mes, anterior, rotulo).
export function reasonRows(month: ReasonCount[] | null | undefined, previous: ReasonCount[] | null | undefined): ReasonRow[] {
  const keys = new Map<string, { label: string; month: number; previous: number }>();
  for (const entry of Array.isArray(month) ? month : []) keys.set(entry.reason, { label: entry.label, month: entry.count, previous: 0 });
  for (const entry of Array.isArray(previous) ? previous : []) {
    const current = keys.get(entry.reason);
    if (current) current.previous = entry.count; else keys.set(entry.reason, { label: entry.label, month: 0, previous: entry.count });
  }
  return [...keys.entries()].map(([key, value]) => ({ key, ...value })).sort((left, right) => right.month - left.month || right.previous - left.previous || left.label.localeCompare(right.label));
}

export function FunnelDashboard({ auth, catalog, onAccessLost }: Props) {
  const id = useId();
  const thisMonth = useMemo(() => currentMonth(), []);
  const [month, setMonth] = useState(thisMonth);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const [locked, setLocked] = useState(false);
  const sequence = useRef(0);
  const forceRef = useRef(false);
  const lostRef = useRef(onAccessLost);
  lostRef.current = onAccessLost;
  const months = useMemo(() => Array.from({ length: MONTH_OPTIONS }, (_, index) => shiftMonth(thisMonth, -index)), [thisMonth]);

  useEffect(() => {
    const request = ++sequence.current;
    let cancelled = false;
    const force = forceRef.current;
    forceRef.current = false;
    setLoading(true); setError("");
    void loadDashboard(auth, month, force).then((value) => {
      if (!cancelled && request === sequence.current) setData(value);
    }).catch((reason) => {
      if (cancelled || request !== sequence.current) return;
      if (isAccessLost(reason)) { lostRef.current(reason); return; }
      setError(funnelErrorMessage(reason));
    }).finally(() => { if (!cancelled && request === sequence.current) setLoading(false); });
    return () => { cancelled = true; };
  }, [auth, month, nonce]);

  useEffect(() => {
    if (!locked) return;
    const timer = window.setTimeout(() => setLocked(false), REFRESH_LOCK_MS);
    return () => window.clearTimeout(timer);
  }, [locked]);

  function refresh() {
    if (locked || loading) return;
    forceRef.current = true; setLocked(true); setNonce((value) => value + 1);
  }

  const shownMonth = data?.month || month;
  const monthLabel = formatMonth(shownMonth);
  const previousLabel = formatMonth(data?.previous_month || shiftMonth(shownMonth, -1));
  const kpis = catalog.kpis || {};
  const levelOf = (cohort: Cohort | undefined, stage?: string) => (stage ? cohort?.levels?.find((level) => level.stage === stage)?.reached ?? 0 : 0);
  const stageName = (key?: string) => catalog.stages.find((stage) => stage.key === key)?.label || key || "";
  // Rotulos do catalogo (a clinica renomeia): etapa de exclusao e as de
  // perda/exclusao que definem reativacao.
  const excludedLabel = catalog.stages.find((stage) => stage.kind === "excluded")?.label || "Descartados";
  const closedLabels = catalog.stages.filter((stage) => stage.kind === "lost" || stage.kind === "excluded").map((stage) => stage.label);
  // Na clinica a conversao E o agendamento (booked = won): um quadro so.
  const wonTile = Boolean(kpis.won_stage && kpis.won_stage !== kpis.booked_stage);
  const inProgress = shownMonth === thisMonth;
  // Payload antigo nao separa a classificacao de antigos: a tabela some (em
  // vez de afirmar "nenhum").
  const triageReasons = Array.isArray(data?.reasons?.month_triage) || Array.isArray(data?.reasons?.previous_triage);

  return <div className={`fn-dashboard${loading && data ? " is-refreshing" : ""}`} aria-busy={loading}>
    <div className="fn-dash-toolbar">
      <label className="fn-field fn-field--inline" htmlFor={`${id}-month`}><span>Mês</span>
        <select id={`${id}-month`} value={month} onChange={(event) => setMonth(event.target.value)}>{months.map((entry) => <option key={entry} value={entry}>{formatMonth(entry)}</option>)}</select>
      </label>
      <button type="button" className="fn-button" onClick={refresh} disabled={locked || loading} title={locked ? "Aguarde alguns segundos para atualizar de novo." : undefined}>{loading && data ? "Atualizando…" : "Atualizar"}</button>
      {data && <span className="fn-freshness" role="status">Dados de {formatClock(data.generated_at)}{data.cached ? " (em cache por até 2 minutos)" : ""}</span>}
    </div>
    {error && <p className="fn-notice fn-notice--danger" role="alert">{error}{data ? " Exibindo a última consulta." : ""}</p>}
    {!data ? (loading ? <p className="fn-help" role="status">Carregando o painel…</p> : null) : <>
      <p className="fn-legend" aria-label="Legenda das barras"><span className="fn-legend-item"><span className="fn-swatch fn-swatch--current" aria-hidden="true" />{monthLabel}</span><span className="fn-legend-item"><span className="fn-swatch fn-swatch--previous" aria-hidden="true" />{previousLabel}</span><span className="fn-help">Fuso da clínica.{inProgress ? " Mês em andamento: os números ainda crescem." : ""}</span></p>

      <div className="fn-stats" role="group" aria-label={`Resumo de ${monthLabel}`}>
        <StatTile label="Entraram no funil" value={data.cohort.month.entered} previous={data.cohort.previous.entered} previousLabel={previousLabel} upIsGood />
        {kpis.booked_stage && <StatTile label={`Alcançaram ${stageName(kpis.booked_stage)}`} value={levelOf(data.cohort.month, kpis.booked_stage)} previous={levelOf(data.cohort.previous, kpis.booked_stage)} previousLabel={previousLabel} upIsGood />}
        {wonTile && <StatTile label={`Alcançaram ${stageName(kpis.won_stage)}`} value={levelOf(data.cohort.month, kpis.won_stage)} previous={levelOf(data.cohort.previous, kpis.won_stage)} previousLabel={previousLabel} upIsGood />}
        <StatTile label="Encerraram sem agendar" value={data.cohort.month.closed_without_booking} previous={data.cohort.previous.closed_without_booking} previousLabel={previousLabel} upIsGood={false} />
      </div>

      <div className="fn-dash-grid">
        <Section id={`${id}-cohort`} title="Coorte do mês" subtitle="Contatos que entraram no funil no mês e até onde chegaram (maior etapa alcançada).">
          <CohortTable data={data} monthLabel={monthLabel} previousLabel={previousLabel} excludedLabel={excludedLabel} />
          <p className="fn-help">Contatos antigos e backups graduados contam no mês do primeiro contato; meses fechados podem crescer.</p>
        </Section>

        <Section id={`${id}-now`} title="Agora no funil" subtitle="Situação atual por etapa, sem arquivados e backups.">
          <CurrentTable data={data} />
        </Section>

        <Section id={`${id}-moves`} title="Movimentos do mês" subtitle="Entradas em cada etapa no mês (manuais, no encerramento do atendimento e automáticas), inclusive reativações. A classificação de antigos fica à parte.">
          <PairTable caption={`Movimentos por etapa de destino: ${monthLabel} e ${previousLabel}`} firstHeader="Etapa de destino" rows={(data.movements || []).map((entry) => ({ key: entry.stage, label: entry.label, month: entry.month, previous: entry.previous }))} monthLabel={monthLabel} previousLabel={previousLabel} empty="Nenhum movimento nos dois meses." />
        </Section>

        <Section id={`${id}-other`} title="Classificação de antigos e reativações">
          <div className="fn-stats fn-stats--compact">
            <StatTile label="Contatos antigos classificados" value={data.triage.month} previous={data.triage.previous} previousLabel={previousLabel} />
            <StatTile label="Reativações" value={data.reactivations.month} previous={data.reactivations.previous} previousLabel={previousLabel} upIsGood />
          </div>
          <p className="fn-help">Reativação = saiu de {closedLabels.length ? closedLabels.join(" ou ") : "uma etapa de perda ou exclusão"} para uma etapa aberta ou ganha.</p>
        </Section>

        <Section id={`${id}-reasons`} title="Não convertidos por motivo" subtitle="Motivo vigente de quem entrou em etapa de perda nos movimentos do mês, com as correções já aplicadas; a classificação de antigos aparece à parte.">
          <ReasonsTable month={data.reasons?.month} previous={data.reasons?.previous} truncated={Boolean(data.reasons?.truncated)}
            caption={`Não convertidos por motivo: ${monthLabel} e ${previousLabel}`} monthLabel={monthLabel} previousLabel={previousLabel}
            empty="Nenhum não convertido nos movimentos do mês e do anterior; a classificação de antigos aparece à parte." />
        </Section>

        {triageReasons && <Section id={`${id}-triage-reasons`} title="Motivos — classificação de contatos antigos" subtitle="Motivo vigente dos contatos antigos ou sem etapa classificados em etapa de perda no mês, com as correções já aplicadas.">
          <ReasonsTable month={data.reasons?.month_triage} previous={data.reasons?.previous_triage} truncated={Boolean(data.reasons?.truncated)}
            caption={`Motivos da classificação de contatos antigos: ${monthLabel} e ${previousLabel}`} monthLabel={monthLabel} previousLabel={previousLabel}
            empty="Nenhum contato antigo classificado em etapa de perda nos dois meses." />
        </Section>}
      </div>
      {(data.notes || []).length > 0 && <ul className="fn-dash-notes" aria-label="Observações">{data.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>}
    </>}
  </div>;
}

function CohortTable({ data, monthLabel, previousLabel, excludedLabel }: { data: DashboardData; monthLabel: string; previousLabel: string; excludedLabel: string }) {
  const month = cohortRows(data.cohort.month, excludedLabel);
  const previous = cohortRows(data.cohort.previous, excludedLabel);
  const monthBase = cohortBase(data.cohort.month);
  const previousBase = cohortBase(data.cohort.previous);
  const max = Math.max(monthBase.entered, previousBase.entered, 1);
  const lgpdMeasured = data.cohort.month.lgpd_accepted != null || data.cohort.previous.lgpd_accepted != null;
  // Payload antigo nao separa os descartados: a legenda nao promete a exclusao.
  const excludedKnown = monthBase.excluded !== null || previousBase.excluded !== null;
  const percent = (row: CohortRow | undefined) => (row && row.base !== null && row.value !== null ? <small> {formatPercent(row.value, row.base)}</small> : null);
  return <>
    <table className="fn-table">
      <caption className="fn-sr">Coorte de {monthLabel} comparada a {previousLabel}</caption>
      <thead><tr><th scope="col">Degrau</th><th scope="col" className="num">{monthLabel}</th><th scope="col" className="num">{previousLabel}</th></tr></thead>
      <tbody>
        {month.map((row) => {
          const earlier = previous.find((entry) => entry.key === row.key);
          const before = earlier?.value ?? null;
          if (row.key === "lgpd" && row.value === null && before === null) {
            return <tr key={row.key}><th scope="row">{row.label}</th><td colSpan={2} className="fn-muted">Não medido: o aviso é tratado pelo agente de IA.</td></tr>;
          }
          return <tr key={row.key} className={row.key === "closed" ? "fn-table-separator" : undefined}>
            <th scope="row"><span className="fn-row-label">{row.label}</span>{row.key === "excluded" && <small className="fn-row-hint">Fora das taxas de conversão</small>}<PairBars month={row.value || 0} previous={before || 0} max={max} monthLabel={monthLabel} previousLabel={previousLabel} /></th>
            <td className="num">{row.value === null ? "—" : formatCount(row.value)}{percent(row)}</td>
            <td className="num">{before === null ? "—" : formatCount(before)}{percent(earlier)}</td>
          </tr>;
        })}
      </tbody>
    </table>
    <p className="fn-help">{excludedKnown ? `Taxas sobre quem entrou, sem os contatos em ${excludedLabel}` : "Taxas sobre quem entrou"} ({formatCount(monthBase.net)} em {monthLabel}; {formatCount(previousBase.net)} em {previousLabel}){lgpdMeasured ? "; o aceite LGPD, sobre todos que entraram" : ""}.</p>
  </>;
}

function CurrentTable({ data }: { data: DashboardData }) {
  const stages = data.current?.stages || [];
  const max = Math.max(1, ...stages.map((entry) => entry.count || 0));
  return <>
    <table className="fn-table">
      <caption className="fn-sr">Contatos por etapa agora</caption>
      <thead><tr><th scope="col">Etapa</th><th scope="col" className="num">Contatos</th><th scope="col" className="num">Parados</th></tr></thead>
      <tbody>{stages.map((entry) => <tr key={entry.stage}>
        <th scope="row"><span className="fn-row-label">{entry.label}</span><span className="fn-bars"><Bar value={entry.count || 0} max={max} tone="current" title={`${entry.label}: ${formatCount(entry.count)}`} /></span></th>
        <td className="num">{formatCount(entry.count)}</td>
        <td className="num">{entry.stale_count == null ? <span className="fn-muted" title="O sinal desta etapa vem das tarefas">—</span> : formatCount(entry.stale_count)}</td>
      </tr>)}</tbody>
    </table>
    <p className="fn-help">{formatCount(data.current?.with_stage)} contatos com etapa.{data.current?.unknown_stage ? ` ${formatCount(data.current.unknown_stage)} com etapa fora do catálogo atual.` : ""}</p>
  </>;
}

function PairTable({ caption, firstHeader, rows, monthLabel, previousLabel, empty }: {
  caption: string; firstHeader: string; rows: { key: string; label: string; month: number; previous: number }[]; monthLabel: string; previousLabel: string; empty: string;
}) {
  if (!rows.length || rows.every((row) => !row.month && !row.previous)) return <p className="fn-help">{empty}</p>;
  const max = Math.max(1, ...rows.map((row) => Math.max(row.month || 0, row.previous || 0)));
  return <table className="fn-table">
    <caption className="fn-sr">{caption}</caption>
    <thead><tr><th scope="col">{firstHeader}</th><th scope="col" className="num">{monthLabel}</th><th scope="col" className="num">{previousLabel}</th></tr></thead>
    <tbody>{rows.map((row) => <tr key={row.key}>
      <th scope="row"><span className="fn-row-label">{row.label}</span><PairBars month={row.month || 0} previous={row.previous || 0} max={max} monthLabel={monthLabel} previousLabel={previousLabel} /></th>
      <td className="num">{formatCount(row.month)}</td>
      <td className="num">{formatCount(row.previous)}</td>
    </tr>)}</tbody>
  </table>;
}

function ReasonsTable({ month, previous, truncated, caption, empty, monthLabel, previousLabel }: {
  month: ReasonCount[] | undefined; previous: ReasonCount[] | undefined; truncated: boolean; caption: string; empty: string; monthLabel: string; previousLabel: string;
}) {
  return <>
    <PairTable caption={caption} firstHeader="Motivo" rows={reasonRows(month, previous)} monthLabel={monthLabel} previousLabel={previousLabel} empty={empty} />
    {truncated && <p className="fn-notice fn-notice--warning">A consulta de motivos atingiu o limite de registros: os números podem estar incompletos.</p>}
  </>;
}
