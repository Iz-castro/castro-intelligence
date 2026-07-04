import { useCrm } from "../context/CrmContext";
import type { PermissionKey } from "../types";

// RBAC dinamico (M-B2, PLANO_RBAC §3.7): checagem de toggle efetivo da
// sessao. Deny-by-default — retorna false enquanto o perfil nao carregou.
// Para escopo de DADOS amplo (listeners/filtros de visibilidade) use
// `canSeeAll` do contexto, que combina o toggle com o teto das rules.
export function useCan(perm: PermissionKey): boolean {
  const { can } = useCrm();
  return can(perm);
}
