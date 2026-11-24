import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router";
import Shell from "./components/Shell";
import LoginPage from "./features/auth/LoginPage";
import ExplorerPage from "./features/explorer/ExplorerPage";
import HistoryPage from "./features/history/HistoryPage";
import SettingsPage from "./features/settings/SettingsPage";
import WorkspacePage from "./features/workspace/WorkspacePage";
import { api } from "./lib/api";
import { useEventStream } from "./lib/events";

export default function App() {
  const qc = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<{ authenticated: boolean }>("/auth/session"),
    staleTime: 60_000,
  });
  const authed = session.data?.authenticated === true;
  useEventStream(authed);

  useEffect(() => {
    const onUnauthorized = () => qc.setQueryData(["session"], { authenticated: false });
    window.addEventListener("vie:unauthorized", onUnauthorized);
    return () => window.removeEventListener("vie:unauthorized", onUnauthorized);
  }, [qc]);

  if (session.isLoading) {
    return <div className="grid h-full place-items-center text-ink-3">Cargando…</div>;
  }
  if (!authed) return <LoginPage />;

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<WorkspacePage />} />
        <Route path="/o/:id" element={<WorkspacePage />} />
        <Route path="/camara" element={<WorkspacePage cameraMode />} />
        <Route path="/explorador" element={<ExplorerPage />} />
        <Route path="/historial" element={<HistoryPage />} />
        <Route path="/ajustes" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
