import { useCrm } from "../../context/CrmContext";
import { funnelAvailable, funnelCatalogAvailable } from "./useFunnelConfig";

// Gates das telas do funil + chave do cache de /config (muda quando a
// identidade ou um toggle que altera capacidades muda, ao vivo pelo perfil).
// - available: quadro (FunnelEntry), cartao da etapa, drawer e tudo que chama
//   rotas que exigem ver_funil;
// - catalogAvailable: o catalogo do /config (encerramento, gate do menu,
//   chip, filtro), com ver_funil OU fechar_atendimento_manual (decisao do PO).
// Os dois usam o MESMO cache (1 GET): todo consumidor do /config passa
// catalogAvailable ao useFunnelConfig e cada tela decide o que mostra.
export function useFunnelAccess() {
  const { bundle, config, readOnly, funnelEnabled, followupEnabled, can, canSeeAll, sessionUser } = useCrm();
  const canView = can("ver_funil");
  const canClose = can("fechar_atendimento_manual");
  const gate = { readOnly, featureFunnel: config?.feature_funnel, funnelEnabled, canView };
  const available = funnelAvailable(gate);
  const catalogAvailable = funnelCatalogAvailable({ ...gate, canClose });
  const accessKey = JSON.stringify([
    sessionUser?.firebase_uid || "", sessionUser?.id ?? null, sessionUser?.role || "", canSeeAll,
    canView, canClose,
    can("mover_etapa_funil"), can("ver_contatos_agente_funil"), can("ver_dashboard_funil"), can("gerenciar_config_sistema"),
    can("gerenciar_followup"), followupEnabled,
  ]);
  return { auth: bundle?.auth ?? null, available, catalogAvailable, accessKey };
}
