import { useEffect, useRef, useState } from "react";

type VideoMediaProps = {
  src: string;
  alt: string;
  filename?: string;
  expanded?: boolean;
  startTime?: number;
  onExpand?: (currentTime: number) => void;
};

type Failure = "format" | "network" | "missing" | null;

// Um player com som por vez (video ou audio do chat), como no WhatsApp. GIFs
// tocam mudos em loop e ficam fora: nem pausam os outros nem sao pausados.
// Instalado no carregamento do modulo (o App importa este arquivo), para valer
// tambem em conversa so com audios.
let exclusivePlaybackInstalled = false;
function ensureExclusivePlayback() {
  if (exclusivePlaybackInstalled || typeof document === "undefined") return;
  exclusivePlaybackInstalled = true;
  document.addEventListener("play", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLMediaElement) || target.muted) return;
    document.querySelectorAll<HTMLMediaElement>("audio, video").forEach((el) => {
      if (el !== target && !el.paused && !el.muted) el.pause();
    });
  }, true);
}
ensureExclusivePlayback();

export function VideoMedia({ src, alt, filename, expanded = false, startTime = 0, onExpand }: VideoMediaProps) {
  const playerRef = useRef<HTMLVideoElement | null>(null);
  const mountedRef = useRef(true);
  const [failed, setFailed] = useState<Failure>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);

  function expand() {
    const player = playerRef.current;
    player?.pause();
    onExpand?.(player?.currentTime || 0);
  }

  async function handleError() {
    const player = playerRef.current;
    const code = player?.error?.code;
    // 3 = decodificacao (formato/codec). 4 ANTES dos metadados (readyState 0)
    // tambem e o que o navegador reporta para 404, 503 e queda de rede: sonda
    // o servidor (a rota aceita HEAD sem baixar o corpo) para nao culpar o formato.
    let next: Failure = code === 3 || code === 4 ? "format" : "network";
    if (code === 4 && (player?.readyState ?? 0) === 0) {
      try {
        const res = await fetch(src, { method: "HEAD", cache: "no-store", credentials: "same-origin" });
        next = res.status === 404 ? "missing" : res.ok ? "format" : "network";
      } catch {
        next = "network";
      }
    }
    if (mountedRef.current) setFailed(next);
  }

  const failureText = failed === "format"
    ? "Este navegador não reproduz o formato deste vídeo. Baixe o arquivo para abri-lo no computador."
    : failed === "network"
      ? "Não foi possível carregar o vídeo agora. Tente novamente ou baixe o arquivo."
      : failed === "missing"
        ? "Este vídeo não está mais disponível."
        : "";
  const downloadLabel = filename ? `Baixar vídeo — ${filename}` : "Baixar vídeo";

  return (
    <div className={expanded ? "expanded-video" : "message-video"}>
      {failed ? null : (
        <video
          key={attempt}
          ref={playerRef}
          className={expanded ? "lightbox-media" : "media video-media"}
          src={src}
          aria-label={`Vídeo: ${alt}`}
          controls
          playsInline
          preload={expanded ? "metadata" : "none"}
          autoPlay={expanded}
          onLoadedMetadata={(e) => {
            if (expanded && startTime > 0 && startTime < (e.currentTarget.duration || Infinity)) e.currentTarget.currentTime = startTime;
          }}
          onError={() => { void handleError(); }}
        />
      )}
      {/* Regiao viva sempre montada: so o texto muda, para o aviso ser anunciado. */}
      <p className="video-error" role="status">{failureText}</p>
      <div className="video-actions">
        {failed === "network" ? <button type="button" onClick={() => { setFailed(null); setAttempt((n) => n + 1); }}>Tentar novamente</button> : null}
        {onExpand && !failed ? <button type="button" onClick={expand}>Ampliar vídeo</button> : null}
        {failed === "missing" ? null : <a href={src} download={filename || "video"} target="_blank" rel="noreferrer">{downloadLabel}</a>}
      </div>
    </div>
  );
}
