import type { FunnelUi } from "./catalog";
import { useFunnelAccess } from "./useFunnelAccess";
import { useFunnelConfig } from "./useFunnelConfig";
import type { FunnelCapabilities } from "./types";

export type FunnelCatalogState = FunnelUi & { capabilities: FunnelCapabilities | null };

const OFF: FunnelCatalogState = { status: "off", catalog: null, capabilities: null };
const LOADING: FunnelCatalogState = { status: "loading", catalog: null, capabilities: null };

// Catalogo do funil para as telas do CRM fora do painel (chips do chat e da
// barra lateral, filtro, painel do contato, encerramento). "off" = sem
// catalogo para este usuario (Ver como, flag, tenant, sem ver_funil e sem
// fechar_atendimento_manual) ou /config com erro: a tela segue o fluxo
// legado. Disponivel tambem para quem so fecha atendimento (decisao do PO);
// o cartao da etapa e o quadro seguem exigindo ver_funil (access.available).
// Mesmo cache do /config (1 GET).
export function useFunnelCatalog(): FunnelCatalogState {
  const access = useFunnelAccess();
  const { config, loading } = useFunnelConfig(access.auth, access.catalogAvailable, access.accessKey);
  if (!access.catalogAvailable) return OFF;
  if (config?.catalog && Array.isArray(config.catalog.stages)) return { status: "ready", catalog: config.catalog, capabilities: config.capabilities || null };
  return loading ? LOADING : OFF;
}
