// Temperatura do lead (tenants com motor CX): bolinha vermelha/amarela/branca.
// Data-driven: sem campo no doc (tenants sem IA) -> null, nenhum plumbing de
// plano/modulo necessario. Gravada pelo backend UMA vez, no handoff do bot.
// Extraido do App.tsx para o funil reusar no card e no drawer.
export const LEAD_TEMPERATURE_META: Record<string, { bg: string; border: string; label: string }> = {
  quente: { bg: "#dc2626", border: "#dc2626", label: "Lead quente — alta intencao (priorize este atendimento)" },
  morno: { bg: "#f59e0b", border: "#f59e0b", label: "Lead morno — exploratorio" },
  frio: { bg: "#ffffff", border: "#94a3b8", label: "Lead frio — suporte generico / curiosidade" },
};

// Texto curto do selo (o funil nunca mostra so a cor).
export function leadTemperatureText(temperature?: string | null): string {
  if (!temperature) return "Temperatura não informada";
  return ({ quente: "Quente", morno: "Morno", frio: "Frio" } as Record<string, string>)[temperature] || temperature;
}

// decorative: o funil exibe o texto ao lado, entao a bolinha fica fora da
// arvore de acessibilidade (sem leitura em dobro). Padrao = comportamento antigo.
export function LeadTemperatureDot({ temperature, decorative = false }: { temperature?: string; decorative?: boolean }) {
  if (!temperature) return null;
  // Valor fora do vocabulario (override futuro de tenant): bolinha NEUTRA
  // cinza — o dot nunca some enquanto o chip do header mostra o texto.
  const meta = LEAD_TEMPERATURE_META[temperature] || { bg: "#e2e8f0", border: "#94a3b8", label: `Temperatura do lead: ${temperature}` };
  return (
    <span
      title={decorative ? undefined : meta.label}
      aria-label={decorative ? undefined : meta.label}
      aria-hidden={decorative ? true : undefined}
      style={{ width: 10, height: 10, borderRadius: "50%", display: "inline-block", flexShrink: 0, background: meta.bg, border: `1.5px solid ${meta.border}` }}
    />
  );
}
