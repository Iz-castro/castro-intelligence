import { useEffect, useRef } from "react";
import type { Auth } from "firebase/auth";
import { isFirebaseSessionActive } from "../firebase";

export type PollCycle = { signal: AbortSignal; current: () => boolean };

export function useImpersonationPolling(auth: Auth | null, enabled: boolean, intervalMs: number, poll: (cycle: PollCycle) => Promise<void>, refreshNonce = 0) {
  const latest = useRef({ auth, enabled, intervalMs, poll, refreshNonce });
  latest.current = { auth, enabled, intervalMs, poll, refreshNonce };
  useEffect(() => {
    if (!enabled || !auth) return;
    let disposed = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    // Descarta a geracao anterior ja no render da nova selecao, antes do cleanup.
    const current = () => !disposed && latest.current.auth === auth && latest.current.enabled
      && latest.current.poll === poll && latest.current.intervalMs === intervalMs
      && latest.current.refreshNonce === refreshNonce && isFirebaseSessionActive(auth);
    const tick = async () => {
      if (!current()) return;
      controller = new AbortController();
      try { await poll({ signal: controller.signal, current }); }
      catch { /* O painel apresenta o erro; o proximo ciclo nao e acelerado. */ }
      finally {
        if (current()) timer = window.setTimeout(() => void tick(), intervalMs);
      }
    };
    void tick();
    return () => {
      disposed = true;
      controller?.abort();
      window.clearTimeout(timer);
    };
  }, [auth, enabled, intervalMs, poll, refreshNonce]);
}
