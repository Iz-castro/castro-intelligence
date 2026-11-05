import { useCrm } from "../../context/CrmContext";
import { funnelAvailable } from "./useFunnelConfig";

// Gate unico das telas do funil + chave do cache de /config (muda quando a
// identidade ou um toggle que altera capacidades muda, ao vivo pelo perfil).
export function useFunnelAccess() {
  const { bundle, config, readOnly, funnelEnabled, followupEnabled, can, canSeeAll, sessionUser } = useCrm();
  const available = funnelAvailable({ readOnly, featureFunnel: config?.feature_funnel, funnelEnabled, canView: can("ver_funil") });
  const accessKey = JSON.stringify([
    sessionUser?.firebase_uid || "", sessionUser?.id ?? null, sessionUser?.role || "", canSeeAll,
    can("mover_etapa_funil"), can("ver_contatos_agente_funil"), can("ver_dashboard_funil"), can("gerenciar_config_sistema"),
    can("gerenciar_followup"), followupEnabled,
  ]);
  return { auth: bundle?.auth ?? null, available, accessKey };
}
