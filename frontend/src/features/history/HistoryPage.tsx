import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, assetUrl, qs } from "../../lib/api";
import { formatMoney } from "../../lib/format";
import { STATUS, VALIDATION, docTypeLabel } from "../../lib/labels";
import type { ObservationSummary } from "../../lib/types";

interface CameraSession {
  id: string;
  started_at: string;
  ended_at: string | null;
  stats: Record<string, number>;
}

export default function HistoryPage() {
  const obs = useQuery({
    queryKey: ["observations", "history"],
    queryFn: () => api<{ items: ObservationSummary[] }>(`/observations${qs({ page_size: 120 })}`),
  });
  const sessions = useQuery({ queryKey: ["camera-sessions"], queryFn: () => api<CameraSession[]>("/camera/sessions") });

  const groups = new Map<string, ObservationSummary[]>();
  for (const o of obs.data?.items ?? []) {
    const day = new Date(o.created_at).toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    groups.set(day, [...(groups.get(day) ?? []), o]);
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto px-6 py-6">
      <h1 className="t-title mb-1">Historial visual</h1>
      <p className="mb-6 text-ink-2">Todo lo que la mesa ha observado, por día. Las observaciones de cámara marcadas como «actualización» reemplazan a una anterior de la misma escena.</p>
      {obs.data && obs.data.items.length === 0 && <p className="text-ink-3">Aún no hay observaciones.</p>}
      {[...groups.entries()].map(([day, list]) => (
        <section key={day} className="mb-8">
          <h2 className="t-sub mb-3 first-letter:uppercase">{day}</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {list.map((o) => (
              <Link key={o.id} to={`/o/${o.id}`} className="rounded-md bg-paper p-2 hover:outline hover:outline-1 hover:outline-rule">
                <div className="relative mb-2 h-32 overflow-hidden rounded-sm bg-desk">
                  {o.thumbnail_asset_id && <img src={assetUrl(o.thumbnail_asset_id)} alt="" className="h-full w-full object-cover object-top" />}
                  {o.source === "camera" && <span className="absolute left-1 top-1 rounded bg-ink/80 px-1.5 t-tiny text-paper">{o.kind === "updated" ? "Cámara · actualizada" : "Cámara"}</span>}
                  {o.repeat_count > 0 && <span className="absolute bottom-1 right-1 rounded bg-paper/90 px-1.5 t-tiny num">vista {o.repeat_count + 1} veces</span>}
                </div>
                <div className="truncate t-small font-semibold">{o.title ?? docTypeLabel(o.document_type)}</div>
                <div className="t-tiny text-ink-3">
                  {new Date(o.created_at).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })} ·{" "}
                  {o.validation_status ? VALIDATION[o.validation_status] : STATUS[o.status]}
                  {o.total ? ` · ${formatMoney(o.total, o.currency)}` : ""}
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
      {(sessions.data?.length ?? 0) > 0 && (
        <section className="mt-10">
          <h2 className="t-sub mb-2">Sesiones de cámara</h2>
          <table className="bg-paper t-small">
            <thead>
              <tr className="text-left text-ink-2">
                <th className="px-3 py-1.5">Inicio</th>
                <th className="px-3">Duración</th>
                <th className="px-3">Fotogramas</th>
                <th className="px-3">Nuevas</th>
                <th className="px-3">Actualizadas</th>
                <th className="px-3">Repetidas</th>
              </tr>
            </thead>
            <tbody>
              {sessions.data!.map((s) => (
                <tr key={s.id} className="border-t hairline num">
                  <td className="px-3 py-1.5">{new Date(s.started_at).toLocaleString("es-PE")}</td>
                  <td className="px-3">{s.ended_at ? `${Math.round((+new Date(s.ended_at) - +new Date(s.started_at)) / 1000)} s` : "en curso"}</td>
                  <td className="px-3">{s.stats.frames ?? 0}</td>
                  <td className="px-3">{s.stats.new ?? 0}</td>
                  <td className="px-3">{s.stats.updated ?? 0}</td>
                  <td className="px-3">{s.stats.repeated ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
