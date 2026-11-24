import { create } from "zustand";
import type { VieEvent } from "../lib/types";

export type Layer = "text" | "fields" | "codes" | "review";
export type Theme = "light" | "dark" | "system";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem("vie.theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

interface UiState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  layers: Record<Layer, boolean>;
  toggleLayer: (l: Layer) => void;
  overlayText: boolean;
  setOverlayText: (v: boolean) => void;
  /** evidence ids currently highlighted on the document (hover/selection in the ledger) */
  hot: string[];
  setHot: (ids: string[]) => void;
  hotBox: number[] | null;
  setHotBox: (b: number[] | null) => void;
  events: VieEvent[];
  pushEvent: (e: VieEvent) => void;
  chatDeltas: Record<string, string>;
  appendDelta: (messageId: string, delta: string) => void;
  clearDelta: (messageId: string) => void;
  consoleOpen: boolean;
  setConsoleOpen: (v: boolean) => void;
  ledgerTab: string;
  setLedgerTab: (t: string) => void;
  region: { page: number; bbox: number[] } | null;
  setRegion: (r: { page: number; bbox: number[] } | null) => void;
}

export const useUi = create<UiState>((set) => ({
  theme: readTheme(),
  setTheme: (theme) => {
    try {
      if (theme === "system") localStorage.removeItem("vie.theme");
      else localStorage.setItem("vie.theme", theme);
    } catch {
      /* storage unavailable */
    }
    applyTheme(theme);
    set({ theme });
  },
  layers: { text: true, fields: true, codes: true, review: true },
  toggleLayer: (l) => set((s) => ({ layers: { ...s.layers, [l]: !s.layers[l] } })),
  overlayText: false,
  setOverlayText: (overlayText) => set({ overlayText }),
  hot: [],
  setHot: (hot) => set({ hot }),
  hotBox: null,
  setHotBox: (hotBox) => set({ hotBox }),
  events: [],
  pushEvent: (e) =>
    set((s) => {
      if (e.id && s.events.some((x) => x.id === e.id)) return s;
      return { events: [e, ...s.events].slice(0, 300) };
    }),
  chatDeltas: {},
  appendDelta: (id, delta) => set((s) => ({ chatDeltas: { ...s.chatDeltas, [id]: (s.chatDeltas[id] ?? "") + delta } })),
  clearDelta: (id) =>
    set((s) => {
      const next = { ...s.chatDeltas };
      delete next[id];
      return { chatDeltas: next };
    }),
  consoleOpen: true,
  setConsoleOpen: (consoleOpen) => set({ consoleOpen }),
  ledgerTab: "resumen",
  setLedgerTab: (ledgerTab) => set({ ledgerTab }),
  region: null,
  setRegion: (region) => set({ region }),
}));
