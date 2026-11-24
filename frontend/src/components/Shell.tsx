import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, FileSearch, GalleryHorizontalEnd, LogOut, Moon, ScanText, Settings, Sun, SunMoon } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router";
import { api } from "../lib/api";
import { useUi, type Theme } from "../store/ui";

interface SystemStatus {
  status: string;
  llm: { active_model: string; model_installed: boolean; status: string };
  vision: { status: string };
  worker: { status: string };
  database: { status: string };
  queue: Record<string, Record<string, number>>;
}

const NAV = [
  { to: "/", label: "Mesa", icon: ScanText, end: true },
  { to: "/camara", label: "Cámara", icon: Camera },
  { to: "/explorador", label: "Explorar", icon: FileSearch },
  { to: "/historial", label: "Historial", icon: GalleryHorizontalEnd },
  { to: "/ajustes", label: "Ajustes", icon: Settings },
];

const NEXT_THEME: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<Theme, string> = { system: "Tema del sistema", light: "Tema claro", dark: "Tema oscuro" };

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: () => api<SystemStatus>("/system/status"),
    refetchInterval: 15_000,
  });
}

export default function Shell({ children }: { children: ReactNode }) {
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const qc = useQueryClient();
  const status = useSystemStatus();
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : SunMoon;

  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.setQueryData(["session"], { authenticated: false });
  };

  const ok = status.data?.status === "ok";
  return (
    <div className="flex h-full min-h-0">
      <nav aria-label="Secciones" className="flex w-[76px] flex-none flex-col items-center gap-1 bg-desk-2 py-3">
        <div className="mb-3 grid h-9 w-9 place-items-center rounded-lg bg-ink text-paper" title="Visual Intelligence Engine">
          <ScanText size={18} strokeWidth={2.2} />
        </div>
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex w-[64px] flex-col items-center gap-1 rounded-lg px-1 py-2 t-tiny font-semibold ${
                isActive ? "bg-paper text-ink" : "text-ink-2 hover:bg-paper/60"
              }`
            }
          >
            <Icon size={19} />
            {label}
          </NavLink>
        ))}
        <div className="mt-auto flex flex-col items-center gap-1">
          <span
            className="mb-1 flex items-center gap-1 t-tiny text-ink-3"
            title={
              status.data
                ? `Base de datos: ${status.data.database.status} · Visión: ${status.data.vision.status} · Modelo: ${status.data.llm.active_model}`
                : "Comprobando servicios"
            }
          >
            <span className={`h-2 w-2 rounded-full ${ok ? "bg-green" : status.data ? "bg-amber" : "bg-ink-3"}`} />
            {ok ? "Listo" : status.data ? "Parcial" : "…"}
          </span>
          <button className="btn btn-quiet btn-icon" onClick={() => setTheme(NEXT_THEME[theme])} title={THEME_LABEL[theme]} aria-label={THEME_LABEL[theme]}>
            <ThemeIcon size={17} />
          </button>
          <button className="btn btn-quiet btn-icon" onClick={logout} title="Cerrar sesión" aria-label="Cerrar sesión">
            <LogOut size={17} />
          </button>
        </div>
      </nav>
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}
