import { useEffect } from "react";

export function useClickOutside(ref: { current: HTMLElement | null }, active: boolean, onClose: () => void) {
  useEffect(() => {
    if (!active) return undefined;
    const handlePointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [active, onClose, ref]);
}
