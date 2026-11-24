import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { useSystemStatus } from "../../components/Shell";
import { api, assetUrl, qs } from "../../lib/api";
import { formatBytes, formatDateTime, formatMs } from "../../lib/format";
import { STATUS, docTypeLabel } from "../../lib/labels";
import type { ObservationDetail, ObservationSummary } from "../../lib/types";
import { useUi } from "../../store/ui";

const TABS = [
  ["eventos", "Eventos"],
  ["estado", "Procesamiento"],
  ["recursos", "Recursos"],
  ["historial", "Observaciones recientes"],
] as const;

const PIPELINE = [
  ["queued", "En cola"],
  ["processing", "Lectura y OCR"],
  ["ocr_ready", "Texto listo"],
  ["interpreting", "Modelo"],
  ["completed", "Completado"],
] as const;

export default function Console({ detail }: { detail?: ObservationDetail }) {
  const open = useUi((s) => s.consoleOpen);
  const setOpen = useUi((s) => s.setConsoleOpen);
  const [tab, setTab] = useState<string>("eventos");
  return (
    <section aria-label="Consola" className="flex-none border-t hairline bg-paper">
      <div className="flex items-center gap-1 px-2">
        <div role="tablist" className="flex gap-1 overflow-x-auto">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={open && tab === id} className="tab" onClick={() => { setTab(id); setOpen(true); }}>
              {label}
            </button>
          ))}
        </div>
        <button className="btn btn-quiet btn-icon ml-auto" onClick={() => setOpen(!open)} aria-label={open ? "Ocultar consola" : "Mostrar consola"}>
          {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      </div>
      {open && (
        <div className="scroll-thin h-44 overflow-y-auto border-t hairline">
          {tab === "eventos" && <Events observationId={detail?.id} />}
          {tab === "estado" && <Pipeline detail={detail} />}
          {tab === "recursos" && <Resources />}
          {tab === "historial" && <Recent />}
        </div>
      )}
    </section>
  );
}

function Events({ observationId }: { observationId?: string }) {
  const events = useUi((s) => s.events);
  const [onlyThis, setOnlyThis] = useState(false);
  const list = onlyThis && observationId ? events.filter((e) => e.observation_id === observationId) : events;
  return (
    <div>
      {observationId && (
        <label className="flex items-center gap-2 px-3 py-1.5 t-tiny text-ink-2">
          <input type="checkbox" checked={onlyThis} onChange={(e) => setOnlyThis(e.target.checked)} /> Solo esta observación
        </label>
      )}
      {list.length === 0 && <p className="px-3 py-2 t-small text-ink-3">Sin eventos todavía.</p>}
      <ol>
        {list.map((e, i) => (
          <li key={e.id ?? `${e.ts}-${i}`} className="grid grid-cols-[5.5rem_1fr] gap-2 px-3 py-1 t-small">
            <span className="num t-tiny pt-0.5 text-ink-3">{new Date(e.ts).toLocaleTimeString("es-PE")}</span>
            <span className={e.level === "error" ? "text-red" : e.level === "warning" ? "text-amber" : ""}>
              {e.message || e.type}
              {e.observation_id && (
                <Link to={`/o/${e.observation_id}`} className="raw ml-2 text-ink-3 hover:text-blue">
                  {e.observation_id.slice(0, 8)}
                </Link>
              )}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Pipeline({ detail }: { detail?: ObservationDetail }) {
  if (!detail) return <p className="px-3 py-2 t-small text-ink-3">Seleccione una observación.</p>;
  const order = PIPELINE.map((p) => p[0]) as string[];
  const current = detail.status === "partial" ? 4 : detail.status === "failed" ? -1 : order.indexOf(detail.status);
  const t = detail.result.metadata?.timings ?? {};
  const tok = detail.result.metadata?.vlm_tokens;
  return (
    <div className="px-3 py-2">
      <ol className="flex flex-wrap items-center gap-2 t-small">
        {PIPELINE.map(([id, label], i) => (
          <li key={id} className="flex items-center gap-2">
            <span className={`mark ${i < current || detail.status === "completed" ? "text-green" : i === current ? "text-blue" : "text-ink-3"}`}>{i + 1}</span>
            <span className={i === current ? "font-semibold" : "text-ink-2"}>{label}</span>
            {i < PIPELINE.length - 1 && <span className="text-ink-3">—</span>}
          </li>
        ))}
        {detail.status === "partial" && <li className="text-amber">Sin interpretación del modelo (resultado parcial)</li>}
        {detail.status === "failed" && <li className="text-red">Error: {detail.error?.message}</li>}
      </ol>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 t-small md:grid-cols-4">
        <div><dt className="text-ink-3">Decodificación</dt><dd className="num">{formatMs(t.vision_decode_ms)}</dd></div>
        <div><dt className="text-ink-3">Preprocesamiento</dt><dd className="num">{formatMs(t.vision_preprocess_ms)}</dd></div>
        <div><dt className="text-ink-3">OCR</dt><dd className="num">{formatMs(t.vision_ocr_ms)}</dd></div>
        <div><dt className="text-ink-3">Inferencia del modelo</dt><dd className="num">{formatMs(t.vlm_ms)}</dd></div>
        <div><dt className="text-ink-3">Modelo activo</dt><dd>{detail.result.metadata?.model ?? detail.model_name ?? "—"}</dd></div>
        <div><dt className="text-ink-3">Tokens (entrada / salida)</dt><dd className="num">{tok ? `${tok.prompt ?? "—"} / ${tok.output ?? "—"}` : "—"}</dd></div>
        <div><dt className="text-ink-3">Versión del pipeline</dt><dd>{detail.pipeline_version ?? "—"}</dd></div>
        <div><dt className="text-ink-3">Esquema</dt><dd>{detail.schema_id ?? detail.result.metadata?.schema_id ?? "—"}</dd></div>
      </dl>
    </div>
  );
}

function Resources() {
  const { data } = useSystemStatus();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const s = data as Record<string, any> | undefined;
  if (!s) return <p className="px-3 py-2 t-small text-ink-3">Consultando servicios…</p>;
  const res = s.resources ?? {};
  const rows: [string, string, any][] = [
    ["Base de datos", s.database?.status, null],
    ["Motor de visión y OCR", s.vision?.status, res.vision],
    ["API", "ok", res.api],
    ["Procesador (worker)", s.worker?.status, res.worker],
    ["Modelo multimodal", s.llm?.model_installed ? "ok" : "falta el modelo", null],
  ];
  return (
    <div className="grid gap-x-8 px-3 py-2 md:grid-cols-2">
      <table className="t-small">
        <tbody>
          {rows.map(([name, st, r]) => (
            <tr key={name}>
              <td className="py-0.5 pr-4 text-ink-2">{name}</td>
              <td className={`py-0.5 pr-4 ${st === "ok" ? "text-green" : "text-amber"}`}>{st === "ok" ? "operativo" : st ?? "—"}</td>
              <td className="num py-0.5 text-ink-3">{r?.memory_bytes ? `${formatBytes(r.memory_bytes)} de ${formatBytes(r.memory_limit_bytes)}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="t-small">
        <p className="text-ink-2">Modelo activo: <span className="text-ink">{s.llm?.active_model}</span> (Ollama {s.llm?.version ?? "—"})</p>
        {(s.llm?.loaded ?? []).map((m: any) => (
          <p key={m.name} className="text-ink-3">En memoria: {m.name} · {formatBytes(m.size_bytes)}</p>
        ))}
        <p className="mt-1 text-ink-2">
          Cola: lectura {s.queue?.fast?.queued ?? 0} en espera / {s.queue?.fast?.running ?? 0} en curso · modelo {s.queue?.vlm?.queued ?? 0} / {s.queue?.vlm?.running ?? 0}
        </p>
      </div>
    </div>
  );
}

function Recent() {
  const { data } = useQuery({
    queryKey: ["observations", "recent"],
    queryFn: () => api<{ items: ObservationSummary[] }>(`/observations${qs({ page_size: 20 })}`),
  });
  const items = data?.items ?? [];
  if (!items.length) return <p className="px-3 py-2 t-small text-ink-3">Aún no hay observaciones.</p>;
  return (
    <div className="flex gap-2 overflow-x-auto px-3 py-2">
      {items.map((o) => (
        <Link key={o.id} to={`/o/${o.id}`} className="w-36 flex-none rounded-md border hairline p-1.5 hover:bg-paper-2">
          <div className="mb-1 h-20 overflow-hidden rounded bg-desk">
            {o.thumbnail_asset_id && <img src={assetUrl(o.thumbnail_asset_id)} alt="" className="h-full w-full object-cover object-top" />}
          </div>
          <div className="truncate t-tiny font-semibold">{o.title ?? docTypeLabel(o.document_type)}</div>
          <div className="t-tiny text-ink-3">
            {o.kind === "updated" ? "actualizada · " : ""}
            {STATUS[o.status]} · {formatDateTime(o.created_at)}
          </div>
        </Link>
      ))}
    </div>
  );
}
