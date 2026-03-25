import type { ChatMessage } from "../types";

export type LightboxMedia = {
  src: string;
  kind: "image" | "video";
  alt: string;
  gifLike?: boolean;
};

export type ResolvedMessageMedia =
  | { kind: "image"; alt: string; gifLike: boolean; sticker: boolean }
  | { kind: "video"; alt: string; gifLike: boolean }
  | { kind: "audio" }
  | { kind: "document" };

export function resolveMessageMedia(message: ChatMessage): ResolvedMessageMedia | null {
  if (!message.media_path) return null;

  const msgType = String(message.msg_type || "").toLowerCase();
  const mime = String(message.media_mime || "").toLowerCase();
  const alt = message.filename || (msgType === "sticker" ? "figurinha" : "midia");

  if (msgType === "audio" || mime.startsWith("audio/")) return { kind: "audio" };
  if (msgType === "gif") {
    if (mime.startsWith("image/")) return { kind: "image", alt, gifLike: true, sticker: false };
    return { kind: "video", alt, gifLike: true };
  }
  if (msgType === "sticker") return { kind: "image", alt, gifLike: false, sticker: true };
  if (msgType === "image" || mime.startsWith("image/")) return { kind: "image", alt, gifLike: mime === "image/gif", sticker: false };
  if (msgType === "video" || mime.startsWith("video/")) return { kind: "video", alt, gifLike: false };
  return { kind: "document" };
}
