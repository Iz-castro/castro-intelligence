import { lazy } from "react";
import "./funnel.css";

// Painel (quadro, drawer, busca, painel gerencial e aba "Etapas") carregado
// so quando o usuario abre o funil: fora do bundle principal. O que vive no
// chat (cartao da etapa, dialogo de mudanca, historico, desfecho do
// encerramento, chips e filtro da barra lateral) e estatico.
export const FunnelPanel = lazy(() => import("./FunnelPanel").then((module) => ({ default: module.FunnelPanel })));
export type { FunnelPanelProps, FunnelPanelTab } from "./FunnelPanel";

export { useLayer } from "./a11y";
export { loadContactHistory, loadContactStage } from "./api";
export { boardReducer, createBoardState, DEFAULT_FILTERS } from "./boardReducer";
export type { BoardAction, BoardState } from "./boardReducer";
export {
  buildCloseFunnel, CLOSE_NOTE_MAX, closeChoiceProblem, closeExcluded, closeFormMode, closeGateApplies, closeKeepsStage, closeNoteAllowed, closeOpensModal, closeOutcomeStages,
  contactMatchesFilter, contactStageLabel, contactStagePatch, effectiveCloseChoice, EMPTY_CLOSE_DRAFT, filterValueValid, findStage, freezeCloseDraft, initialCloseTarget,
  LEGACY_OPEN_QUALIFICATIONS, moveTargets, patchCloseDraft, selectableReasons, STAGE_FILTER_PREFIX, stageFilterOptions, stageFromFilter, stageLegacyQualification, stageVisible,
} from "./catalog";
export type { CloseBase, CloseChoice, CloseDraft, CloseFormMode, FunnelUi, FunnelUiStatus, StageFilterOption } from "./catalog";
export { FUNNEL_CLOSE_ERROR_MESSAGES, FUNNEL_ERROR_MESSAGES, funnelCloseErrorMessage, funnelErrorCode, funnelErrorMessage, isAccessLost } from "./errors";
export { daysInStageText, elapsedDays, formatDateTime } from "./format";
export { InfoButton } from "./InfoButton";
export { MoveStageDialog, staleCurrent } from "./MoveStageDialog";
export { StageHistory } from "./StageHistory";
export { useFunnelAccess } from "./useFunnelAccess";
export { useFunnelCatalog } from "./useFunnelCatalog";
export type { FunnelCatalogState } from "./useFunnelCatalog";
export { funnelAvailable, invalidateFunnelConfig, useFunnelConfig } from "./useFunnelConfig";
export type { BoardFilters, CloseFunnelBody, FunnelCapabilities, FunnelCatalog, FunnelConfig, FunnelStage, HistoryItem, MoveStageResponse, StageState, StaleCurrent } from "./types";
