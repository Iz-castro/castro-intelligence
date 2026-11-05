import { ApiError } from "../../api";

// Textos por `code` estavel das rotas /api/funnel (contrato, secao 3). A UI
// prefere o mapa local ao texto do servidor: mesmo vocabulario em toda tela.
export const FUNNEL_ERROR_MESSAGES: Record<string, string> = {
  funnel_disabled: "O funil comercial não está disponível para esta empresa.",
  tenant_mismatch: "A sessão não corresponde à empresa atual. Entre novamente.",
  read_only_session: "Sessões somente leitura não acessam o funil comercial.",
  user_inactive: "Seu usuário está inativo ou foi alterado. Entre novamente.",
  permission_denied: "Seu perfil não permite esta ação no funil.",
  owner_filter_forbidden: "Somente a gestão pode filtrar o quadro por dono do lead.",
  out_of_scope_write: "Você pode consultar a etapa deste contato, mas só move contatos seus ou sem dono.",
  rate_limited: "Muitas consultas seguidas. Aguarde alguns segundos e tente de novo.",
  filter_invalid: "Filtro inválido. Revise a ordenação e o dono escolhidos.",
  owner_invalid: "Este usuário não pode ser usado no filtro: ele ainda não entrou no CRM.",
  invalid_conversation: "Conversa inválida para este contato.",
  invalid_payload: "Dados inválidos. Revise e tente de novo.",
  // 422 de validacao do FastAPI nas rotas /api/funnel (query/path fora do
  // formato): a UI nunca monta esses valores, entao o caminho e recarregar.
  invalid_request: "Parâmetros inválidos. Atualize a tela e tente de novo.",
  cursor_invalid: "A lista expirou. Atualize o quadro para continuar.",
  out_of_scope: "Este contato não está disponível no seu acesso.",
  unknown_stage: "Etapa inexistente no funil desta empresa.",
  stage_not_allowed: "Esta etapa não pode ser escolhida.",
  reason_required: "Informe o motivo.",
  reason_not_allowed: "Motivo inválido para esta etapa.",
  note_not_allowed: "Texto livre só no motivo Outro.",
  note_invalid: "Use até 120 caracteres, sem quebra de linha.",
  appointment_kind_invalid: "Tipo de compromisso inválido.",
  same_stage: "O contato já está nesta etapa.",
  contact_unavailable: "Contato em backup ou arquivado não muda de etapa.",
  operation_reused: "Esta confirmação já foi usada com outros dados. Revise e confirme de novo.",
  context_changed: "O dono ou o acesso deste contato mudou. Revise antes de mover.",
  stale_version: "Outra pessoa mudou a etapa deste contato.",
  try_again: "Muitas alterações ao mesmo tempo neste contato. Tente de novo.",
  month_invalid: "Mês inválido.",
  // Aba "Etapas" (validate_overrides): nomes ate 40, textos ate 200.
  overrides_invalid: "Revise os textos: nomes com até 40 caracteres e textos explicativos com até 200, sem quebra de linha.",
};

const STATUS_MESSAGES: Record<number, string> = {
  400: "Pedido inválido. Atualize e tente de novo.",
  401: "Sua sessão expirou. Entre novamente.",
  403: "Seu acesso não permite esta ação.",
  404: "Não encontrado ou fora do seu acesso.",
  409: "Os dados mudaram. Atualize e tente de novo.",
  422: "Dados inválidos. Revise e tente de novo.",
  429: FUNNEL_ERROR_MESSAGES.rate_limited,
};

// "Encerrar atendimento" com o desfecho pelo funil (set-attendance com
// `funnel`): mesmos codes, com o texto do contexto do encerramento.
export const FUNNEL_CLOSE_ERROR_MESSAGES: Record<string, string> = {
  // 409 do encerramento: o funil saiu do ar depois que a tela carregou.
  funnel_disabled: "O funil comercial ficou indisponível. Escolha o desfecho de novo para encerrar.",
  permission_denied: "Trocar um desfecho já registrado exige a permissão de mover etapas do funil.",
  stage_not_allowed: "Este desfecho não pode ser usado no encerramento. Escolha outro.",
  context_changed: "O dono ou o acesso deste contato mudou. Atualize a conversa e encerre de novo.",
  contact_unavailable: "Contato em backup ou arquivado: atualize a conversa e encerre de novo.",
  out_of_scope: "Este contato não está mais disponível no seu acesso. Atualize a conversa.",
};

export function funnelErrorCode(error: unknown): string {
  return error instanceof ApiError ? error.code || "" : "";
}

export function funnelCloseErrorMessage(error: unknown): string {
  const code = funnelErrorCode(error);
  return (code && FUNNEL_CLOSE_ERROR_MESSAGES[code]) || funnelErrorMessage(error);
}

export function funnelErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code && FUNNEL_ERROR_MESSAGES[error.code]) return FUNNEL_ERROR_MESSAGES[error.code];
    if (STATUS_MESSAGES[error.status]) return STATUS_MESSAGES[error.status];
    if (error.status >= 500) return "O servidor não respondeu. Tente de novo em instantes.";
    return error.message || "Não foi possível concluir. Tente de novo.";
  }
  if (error instanceof DOMException && error.name === "AbortError") return "Consulta cancelada.";
  if (error instanceof TypeError) return "Sem conexão com o servidor. Verifique a rede e tente de novo.";
  return error instanceof Error && error.message ? error.message : "Não foi possível concluir. Tente de novo.";
}

// 401/403/404 nas leituras do drawer = acesso perdido (o drawer fecha). Erro
// de regra (422/409) ou de rede nao fecha nada.
export function isAccessLost(error: unknown): boolean {
  return error instanceof ApiError && [401, 403, 404].includes(error.status);
}
