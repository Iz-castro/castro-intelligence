import { useRef, useState } from "react";

type VideoMediaProps = {
  src: string;
  alt: string;
  filename?: string;
  expanded?: boolean;
  onExpand?: () => void;
};

export function VideoMedia({ src, alt, filename, expanded = false, onExpand }: VideoMediaProps) {
  const playerRef = useRef<HTMLVideoElement | null>(null);
  const [failed, setFailed] = useState(false);

  function expand() {
    playerRef.current?.pause();
    onExpand?.();
  }

  return (
    <div className={expanded ? "expanded-video" : "message-video"}>
      {failed ? (
        <p className="video-error" role="status">Não foi possível reproduzir este vídeo. Baixe o arquivo para abri-lo no computador.</p>
      ) : (
        <video
          ref={playerRef}
          className={expanded ? "lightbox-media" : "media video-media"}
          src={src}
          aria-label={`Vídeo: ${alt}`}
          controls
          playsInline
          preload={expanded ? "metadata" : "none"}
          autoPlay={expanded}
          onError={() => setFailed(true)}
        />
      )}
      <div className="video-actions">
        {onExpand && !failed ? <button type="button" onClick={expand}>Ampliar vídeo</button> : null}
        <a href={src} download={filename || "video"} target="_blank" rel="noreferrer">Baixar vídeo</a>
      </div>
    </div>
  );
}
