// Web Audio com "unlock" no primeiro gesto do usuario.
//
// O Chrome bloqueia um AudioContext criado/iniciado antes de qualquer
// interacao do usuario, gerando no console:
//   "The AudioContext was not allowed to start. It must be resumed (or
//    created) after a user gesture on the page."
//
// Em vez de criar um `new AudioContext()` a cada beep (cada um nasce
// suspenso e dispara o warning), mantemos UM AudioContext compartilhado e o
// destravamos (resume) no primeiro gesto. Beeps disparados antes do primeiro
// gesto sao silenciosos — o navegador nao permitiria toca-los de qualquer
// forma, e assim evitamos o warning.

let _ctx: AudioContext | null = null;
let _installed = false;

function getCtx(): AudioContext | null {
  const Ctor =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!_ctx) {
    try {
      _ctx = new Ctor();
    } catch {
      return null;
    }
  }
  return _ctx;
}

/** Destrava o audio no primeiro gesto do usuario. Chamar uma vez no boot. */
export function installAudioUnlock(): void {
  if (_installed) return;
  _installed = true;
  const unlock = () => {
    const ctx = getCtx();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    window.removeEventListener("pointerdown", unlock);
    window.removeEventListener("keydown", unlock);
    window.removeEventListener("touchstart", unlock);
  };
  window.addEventListener("pointerdown", unlock);
  window.addEventListener("keydown", unlock);
  window.addEventListener("touchstart", unlock);
}

export interface BeepOptions {
  freq?: number;
  type?: OscillatorType;
  gain?: number;
  duration?: number;
  /** Tons adicionais agendados em t+at (segundos) a partir do inicio. */
  steps?: { freq: number; at: number }[];
}

/**
 * Toca um beep usando o AudioContext compartilhado. Faz nada (silencioso) se
 * o audio ainda nao foi destravado por um gesto do usuario — isso evita o
 * warning do Chrome sem precisar de try/catch em cada chamador.
 */
export function playBeep(opts: BeepOptions = {}): void {
  const ctx = getCtx();
  if (!ctx) return;
  if (ctx.state === "suspended") {
    ctx.resume().catch(() => {});
    if (ctx.state === "suspended") return; // sem gesto ainda — nao toca
  }
  try {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = opts.type ?? "sine";
    osc.frequency.value = opts.freq ?? 880;
    gain.gain.value = opts.gain ?? 0.3;
    const dur = opts.duration ?? 0.3;
    for (const s of opts.steps ?? []) {
      osc.frequency.setValueAtTime(s.freq, ctx.currentTime + s.at);
    }
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);
    osc.stop(ctx.currentTime + dur);
  } catch {
    /* noop */
  }
}
