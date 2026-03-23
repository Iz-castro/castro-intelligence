import type { TransportMode } from "../types";

const TRANSPORT_KEY = "crm_transport_mode";
const THEME_KEY = "crm_theme";

export function transportPref() {
  try {
    const mode = window.localStorage.getItem(TRANSPORT_KEY);
    return mode === "snapshot" || mode === "polling" ? mode : null;
  } catch {
    return null;
  }
}

export function setTransportPref(mode: TransportMode) {
  try {
    window.localStorage.setItem(TRANSPORT_KEY, mode);
  } catch {
    return;
  }
}

export function themePref(): "dark" | "light" {
  try {
    const saved = window.localStorage.getItem(THEME_KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    // ignore
  }
  return "dark";
}

export function applyTheme(theme: "dark" | "light") {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* ignore */ }
}
