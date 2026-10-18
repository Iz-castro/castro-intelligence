import { useRef } from "react";
import { ApiError } from "../../api";

function newOperationId(): string {
  return crypto.randomUUID();
}

export function useOperationId() {
  const operation = useRef<{ fingerprint: string; id: string } | null>(null);
  return (payload: unknown) => {
    const fingerprint = JSON.stringify(payload);
    if (operation.current?.fingerprint !== fingerprint) operation.current = { fingerprint, id: newOperationId() };
    return operation.current.id;
  };
}

export function requestError(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return "Outra pessoa alterou este registro. Atualize os dados e revise a ação antes de salvar novamente.";
  if (error instanceof ApiError && error.status === 403) return "Seu acesso a este contato ou a esta tarefa não permite esta ação. Atualize a lista.";
  return error instanceof Error ? error.message : "Não foi possível concluir. Tente novamente.";
}

export function isAccessDenied(error: unknown): boolean {
  return error instanceof ApiError && [401, 403, 404].includes(error.status);
}
