// Formatacao do funil no fuso da clinica. Intl e caro de construir: cache de
// modulo por combinacao de opcoes (o quadro formata centenas de datas).

export const FUNNEL_TIMEZONE = "America/Sao_Paulo";
const DAY_MS = 86_400_000;

const dateFormats = new Map<string, Intl.DateTimeFormat>();
let countFormat: Intl.NumberFormat | null = null;

function dateFormat(key: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  let format = dateFormats.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat("pt-BR", { timeZone: FUNNEL_TIMEZONE, ...options });
    dateFormats.set(key, format);
  }
  return format;
}

// Instante (ms) a partir de ISO; sem fuso = UTC (padrao dos campos do CRM,
// igual ao funnel_catalog.as_utc). Invalido/vazio = null.
export function parseInstant(value?: string | null): number | null {
  if (!value || typeof value !== "string") return null;
  const text = value.trim();
  const zoned = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(text) || !text.includes("T") ? text : `${text}Z`;
  const parsed = Date.parse(zoned);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatClock(value?: string | null): string {
  const instant = parseInstant(value);
  return instant == null ? "--:--" : dateFormat("clock", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(instant);
}

export function formatDateTime(value?: string | null): string {
  const instant = parseInstant(value);
  return instant == null ? "Data não informada" : dateFormat("datetime", { dateStyle: "short", timeStyle: "short" }).format(instant);
}

export function formatDate(value?: string | null): string {
  const instant = parseInstant(value);
  return instant == null ? "Data não informada" : dateFormat("date", { dateStyle: "short" }).format(instant);
}

export function formatCount(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (!countFormat) countFormat = new Intl.NumberFormat("pt-BR");
  return countFormat.format(value);
}

// Percentual inteiro de `part` sobre `total`; sem base = travessao.
export function formatPercent(part: number | null | undefined, total: number | null | undefined): string {
  if (typeof part !== "number" || typeof total !== "number" || !total || total < 0) return "—";
  return `${Math.round((part / total) * 100)}%`;
}

export function plural(count: number, singular: string, pluralForm: string): string {
  return count === 1 ? singular : pluralForm;
}

// Rotulo literal do card: "há N dias na etapa".
export function daysInStageText(days: number | null | undefined): string {
  if (typeof days !== "number" || !Number.isFinite(days)) return "tempo na etapa não informado";
  if (days < 1) return "há menos de 1 dia na etapa";
  return `há ${formatCount(days)} ${plural(days, "dia", "dias")} na etapa`;
}

export function daysAgoText(days: number | null | undefined): string {
  if (typeof days !== "number" || !Number.isFinite(days)) return "não informado";
  if (days < 1) return "há menos de 1 dia";
  return `há ${formatCount(days)} ${plural(days, "dia", "dias")}`;
}

// Dias inteiros decorridos (piso), como o derived_signals do backend.
export function elapsedDays(value: string | null | undefined, now = Date.now()): number | null {
  const instant = parseInstant(value);
  return instant == null ? null : Math.floor((now - instant) / DAY_MS);
}

// Mes corrente 'AAAA-MM' no fuso da clinica (mesma regra do cohort_month).
export function currentMonth(now: Date | number = Date.now()): string {
  const parts = dateFormat("month-key", { year: "numeric", month: "2-digit" }).formatToParts(now);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value || "";
  return `${part("year")}-${part("month")}`;
}

export function isMonthKey(value: string): boolean {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test(value);
}

export function shiftMonth(month: string, delta: number): string {
  if (!isMonthKey(month)) return month;
  const [year, mon] = month.split("-").map(Number);
  const index = year * 12 + (mon - 1) + delta;
  return `${String(Math.floor(index / 12)).padStart(4, "0")}-${String((index % 12) + 1).padStart(2, "0")}`;
}

// "outubro de 2026" (meio do mes em UTC: nenhum fuso muda o mes).
export function formatMonth(month: string): string {
  if (!isMonthKey(month)) return month;
  const [year, mon] = month.split("-").map(Number);
  return dateFormat("month-label", { month: "long", year: "numeric" }).format(Date.UTC(year, mon - 1, 15, 12));
}
