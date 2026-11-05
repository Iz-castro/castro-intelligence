import { useCallback, useRef, useState } from "react";

export type BusyLock = {
  // Estado para desabilitar botoes enquanto a acao roda.
  busy: boolean;
  // Leitura sincrona (clique duplo no mesmo tick, antes do render).
  isBusy: () => boolean;
  // Roda a acao com a trava; outra chamada durante o envio e ignorada
  // (devolve undefined).
  run: <T>(action: () => Promise<T>) => Promise<T | undefined>;
  // Envolve um fechamento MANUAL (fundo, "Fechar", "Cancelar", Esc): ignorado
  // enquanto a acao roda. O fechamento de sucesso, dentro da acao, usa o
  // onClose cru.
  guard: (close: () => void) => () => void;
};

// Trava de envio de um modal (mesmo padrao do busyRef do MoveStageDialog):
// fechar no meio do envio desmontava o modal e o erro do servidor
// (409/422/403 do encerramento) ficava sem ninguem para ver. Ref + estado: o
// ref responde no mesmo tick, o estado redesenha os botoes.
export function useBusyLock(): BusyLock {
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const isBusy = useCallback(() => busyRef.current, []);
  const run = useCallback(async <T>(action: () => Promise<T>): Promise<T | undefined> => {
    if (busyRef.current) return undefined;
    busyRef.current = true;
    setBusy(true);
    try {
      return await action();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);
  const guard = useCallback((close: () => void) => () => { if (!busyRef.current) close(); }, []);
  return { busy, isBusy, run, guard };
}
