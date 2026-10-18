import type { FollowupSettings } from "./types";

export const FOLLOWUP_TIMEZONE = "America/Sao_Paulo";

export function localInput(iso: string | Date, timezone = FOLLOWUP_TIMEZONE): string {
  const moment = new Date(iso);
  if (!Number.isFinite(moment.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(moment);
  const part = (key: string) => parts.find((entry) => entry.type === key)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function localToIso(value: string, timezone = FOLLOWUP_TIMEZONE): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) throw new Error("Escolha uma data e um horário válidos.");
  const target = Date.parse(`${value}:00Z`);
  let guess = target;
  for (let pass = 0; pass < 4; pass++) {
    const represented = Date.parse(`${localInput(new Date(guess), timezone)}:00Z`);
    const adjustment = target - represented;
    if (!adjustment) break;
    guess += adjustment;
  }
  if (!Number.isFinite(guess) || localInput(new Date(guess), timezone) !== value) throw new Error("Esse horário não existe no fuso da clínica.");
  return new Date(guess).toISOString();
}

export function formatMoment(iso?: string | null, timezone = FOLLOWUP_TIMEZONE): string {
  if (!iso) return "Não informado";
  const moment = new Date(iso);
  if (!Number.isFinite(moment.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: timezone, dateStyle: "short", timeStyle: "short",
  }).format(moment);
}

export function scheduleProblem(value: string, settings: FollowupSettings | null): string {
  if (!value) return "Escolha a data e o horário do próximo contato.";
  if (!settings?.configured) return "A gestão precisa configurar os dias e horários de contato antes do uso.";
  const [date, time] = value.split("T");
  const parsed = new Date(`${date}T12:00:00Z`);
  if (!Number.isFinite(parsed.getTime()) || !time) return "Escolha uma data e um horário válidos.";
  const day = (parsed.getUTCDay() + 6) % 7;
  if (day >= 5) return "Não há contatos aos sábados e domingos. Escolha um dia permitido.";
  if (settings.holidays.includes(date)) return "Esta data está cadastrada como feriado ou recesso. Escolha outra data.";
  const ranges = settings.contact_hours[String(day)] || [];
  if (!ranges.some(([start, end]) => start <= time && time < end)) return "O horário está fora das faixas de contato. Escolha um horário permitido.";
  return "";
}

export function shortcutDate(days: number, settings: FollowupSettings | null, base = new Date()): string {
  const current = localInput(base, settings?.timezone || FOLLOWUP_TIMEZONE);
  const date = new Date(`${current.slice(0, 10)}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return `${date.toISOString().slice(0, 10)}T${settings?.preferred_time || current.slice(11, 16)}`;
}

export function previousContactDate(nominal: string, settings: FollowupSettings): string | null {
  const [day, originalTime] = nominal.split("T");
  const date = new Date(`${day}T12:00:00Z`);
  for (let index = 1; index <= 370; index++) {
    date.setUTCDate(date.getUTCDate() - 1);
    const dateKey = date.toISOString().slice(0, 10);
    const weekday = (date.getUTCDay() + 6) % 7;
    const ranges = settings.contact_hours[String(weekday)] || [];
    if (weekday >= 5 || settings.holidays.includes(dateKey) || !ranges.length) continue;
    const preferred = [originalTime, settings.preferred_time || ""].find((time) => ranges.some(([start, end]) => start <= time && time < end));
    return `${dateKey}T${preferred || ranges[0][0]}`;
  }
  return null;
}

export function nextContactDate(after: Date, before: Date, settings: FollowupSettings): string | null {
  const current = localInput(after, settings.timezone);
  const date = new Date(`${current.slice(0, 10)}T12:00:00Z`);
  for (let index = 0; index <= 370; index++) {
    const dateKey = date.toISOString().slice(0, 10);
    const weekday = (date.getUTCDay() + 6) % 7;
    for (const [start] of settings.contact_hours[String(weekday)] || []) {
      const candidate = `${dateKey}T${dateKey === current.slice(0, 10) && current.slice(11) > start ? current.slice(11) : start}`;
      if (scheduleProblem(candidate, settings)) continue;
      const instant = new Date(localToIso(candidate, settings.timezone));
      if (instant >= after && instant < before) return candidate;
    }
    date.setUTCDate(date.getUTCDate() + 1);
    if (new Date(`${date.toISOString().slice(0, 10)}T00:00:00Z`) > before) break;
  }
  return null;
}
