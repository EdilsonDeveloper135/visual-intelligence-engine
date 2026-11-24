import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import ConfirmDialog from "../../components/ConfirmDialog";
import { ApiError, api } from "../../lib/api";
import { formatBytes, formatDateTime } from "../../lib/format";
import { DOC_TYPES } from "../../lib/labels";

const SECTIONS = [
  ["modelos", "Modelos"],
  ["camara", "Cámara"],
  ["esquemas", "Esquemas de extracción"],
  ["almacenamiento", "Almacenamiento"],
  ["auditoria", "Auditoría"],
  ["api", "API"],
] as const;

export default function SettingsPage() {
  const [section, setSection] = useState<string>("modelos");
  return (
    <div className="flex h-full min-h-0 flex-col md:flex-row">
      <nav className="flex flex-none gap-1 overflow-x-auto border-b hairline bg-paper px-3 py-3 md:w-56 md:flex-col md:border-b-0 md:border-r" aria-label="Ajustes">
        <h1 className="t-head mb-2 hidden px-2 md:block">Ajustes</h1>
        {SECTIONS.map(([id, label]) => (
          <button key={id} className={`rounded-md px-3 py-2 text-left t-small font-semibold ${section === id ? "bg-paper-2 text-ink" : "text-ink-2 hover:bg-paper-2"}`} onClick={() => setSection(id)} aria-current={section === id}>
            {label}
          </button>
        ))}
      </nav>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-[860px]">
          {section === "modelos" && <Models />}
          {section === "camara" && <CameraSettings />}
          {section === "esquemas" && <Schemas />}
          {section === "almacenamiento" && <Storage />}
          {section === "auditoria" && <Audit />}
          {section === "api" && <ApiInfo />}
        </div>
      </div>
    </div>
  );
}

function Section({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="t-title mb-1">{title}</h2>
      {intro && <p className="mb-4 max-w-[70ch] text-ink-2">{intro}</p>}
      {children}
    </section>
  );
}

interface ModelsInfo {
  active: string;
  ollama_version: string | null;
  installed: { name: string; size_bytes: number; digest: string; details?: { parameter_size?: string; quantization_level?: string } }[];
  loaded: string[];
  recommended: { name: string; profile: string; size_gb: number; license: string; note: string }[];
  install_note: string;
}

function Models() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["models"], queryFn: () => api<ModelsInfo>("/models") });
  const activate = useMutation({
    mutationFn: (model: string) => api("/models/active", { method: "PUT", json: { model } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["models"] });
      qc.invalidateQueries({ queryKey: ["system-status"] });
    },
  });
  const d = q.data;
  return (
    <Section title="Modelos" intro="El modelo multimodal se ejecuta localmente con Ollama, sin conexión. Elija cuál usar; solo se pueden activar modelos ya instalados.">
      {q.isError && <p className="text-red">No se pudo consultar el servidor de modelos.</p>}
      {d && (
        <>
          <p className="mb-3 t-small text-ink-2">Ollama {d.ollama_version ?? "—"} · en memoria: {d.loaded.join(", ") || "ninguno"}</p>
          <table className="mb-6 w-full bg-paper t-small">
            <thead><tr className="border-b hairline text-left text-ink-2"><th className="px-3 py-2">Instalado</th><th>Tamaño</th><th>Detalles</th><th className="pr-3" /></tr></thead>
            <tbody>
              {d.installed.map((m) => (
                <tr key={m.name} className="border-b hairline">
                  <td className="px-3 py-2 font-semibold">{m.name}</td>
                  <td className="num">{formatBytes(m.size_bytes)}</td>
                  <td className="text-ink-2">{[m.details?.parameter_size, m.details?.quantization_level].filter(Boolean).join(" · ")}</td>
                  <td className="pr-3 text-right">
                    {d.active === m.name ? (
                      <span className="font-semibold text-green">Activo</span>
                    ) : (
                      <button className="btn" onClick={() => activate.mutate(m.name)} disabled={activate.isPending}>Usar este modelo</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {activate.error && <p className="mb-3 text-red">{(activate.error as Error).message}</p>}
          <h3 className="t-sub mb-2">Modelos recomendados</h3>
          <ul className="mb-3">
            {d.recommended.map((m) => (
              <li key={m.name} className="border-b hairline py-2 t-small">
                <span className="font-semibold">{m.name}</span> <span className="text-ink-3">· {m.size_gb} GB · {m.license} · perfil {m.profile}</span>
                <div className="text-ink-2">{m.note}</div>
              </li>
            ))}
          </ul>
          <p className="t-small text-ink-2">{d.install_note}</p>
        </>
      )}
    </Section>
  );
}

interface CameraCfg {
  interval_ms: number;
  min_ocr_interval_s: number;
  min_vlm_interval_s: number;
  auto_vlm: boolean;
  repeat_threshold: number;
  new_threshold: number;
}

function CameraSettings() {
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api<{ camera: CameraCfg }>("/settings") });
  const [form, setForm] = useState<CameraCfg | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const cfg = form ?? q.data?.camera ?? null;
  const set = (k: keyof CameraCfg, v: number | boolean) => setForm({ ...(cfg as CameraCfg), [k]: v });
  const save = async () => {
    try {
      await api("/settings/camera", { method: "PUT", json: cfg });
      setMsg("Ajustes de cámara guardados. Se aplican a la próxima sesión.");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "No se pudo guardar.");
    }
  };
  if (!cfg) return <Section title="Cámara"><p className="text-ink-3">Cargando…</p></Section>;
  const num = (k: keyof CameraCfg, label: string, hint: string, step = 1) => (
    <label className="grid grid-cols-[16rem_8rem_1fr] items-center gap-3 border-b hairline py-2 t-small">
      <span>{label}</span>
      <input type="number" step={step} className="field-input num" value={cfg[k] as number} onChange={(e) => set(k, Number(e.target.value))} />
      <span className="t-tiny text-ink-3">{hint}</span>
    </label>
  );
  return (
    <Section title="Cámara" intro="Controlan cuándo una escena se considera nueva, actualizada o repetida, y con qué frecuencia se usa el modelo.">
      {num("min_ocr_interval_s", "Intervalo mínimo entre lecturas (s)", "Evita leer escenas a cada instante.", 0.5)}
      {num("min_vlm_interval_s", "Intervalo mínimo del modelo (s)", "El modelo tarda ~30–60 s por imagen en CPU.")}
      {num("repeat_threshold", "Umbral de escena repetida", "Bits distintos (de 64) por debajo de los cuales es la misma escena.")}
      {num("new_threshold", "Umbral de escena nueva", "Bits distintos a partir de los cuales es una escena nueva.")}
      <label className="flex items-center gap-2 border-b hairline py-2 t-small">
        <input type="checkbox" checked={cfg.auto_vlm} onChange={(e) => set("auto_vlm", e.target.checked)} />
        Interpretar automáticamente con el modelo las escenas nuevas (respetando el intervalo mínimo)
      </label>
      <button className="btn btn-ink mt-4" onClick={save}>Guardar ajustes de cámara</button>
      {msg && <p className="mt-2 t-small text-ink-2" role="status">{msg}</p>}
    </Section>
  );
}

interface SchemaInfo {
  id: string;
  title: string;
  description: string;
  builtin: boolean;
  dynamic: boolean;
  document_types: string[];
  fields: { name: string; label: string; type: string; required: boolean }[];
}

const FIELD_TYPES = ["string", "text", "money", "decimal", "integer", "date", "ruc", "dni", "doc_id", "serie_numero", "currency", "percent"];

function Schemas() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["schemas"], queryFn: () => api<SchemaInfo[]>("/schemas") });
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ id: "custom_", title: "", description: "", document_types: ["otro_documento"], has_items: false, fields: [{ name: "", label: "", type: "string", required: false }] });
  const [err, setErr] = useState<string | null>(null);
  const create = async () => {
    setErr(null);
    try {
      await api("/schemas", { method: "POST", json: draft });
      setCreating(false);
      qc.invalidateQueries({ queryKey: ["schemas"] });
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message} ${JSON.stringify(e.details ?? "")}` : "No se pudo crear el esquema.");
    }
  };
  const remove = async (id: string) => {
    await api(`/schemas/${id}`, { method: "DELETE" });
    qc.invalidateQueries({ queryKey: ["schemas"] });
  };
  return (
    <Section title="Esquemas de extracción" intro="Los esquemas indican qué campos buscar en cada tipo de documento. Si un documento no encaja en ninguno, se usa el modo universal con campos dinámicos.">
      <ul className="mb-4">
        {(q.data ?? []).map((s) => (
          <li key={s.id} className="border-b hairline py-2">
            <div className="flex items-center gap-2">
              <button className="text-left font-semibold hover:text-blue" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
                {s.title}
              </button>
              <span className="t-tiny text-ink-3">{s.builtin ? "integrado" : "personalizado"} · {s.dynamic ? "campos dinámicos" : `${s.fields.length} campos`}</span>
              {!s.builtin && (
                <button className="btn btn-quiet btn-icon ml-auto" onClick={() => remove(s.id)} aria-label={`Eliminar esquema ${s.title}`}>
                  <Trash2 size={14} />
                </button>
              )}
            </div>
            <p className="t-small text-ink-2">{s.description}</p>
            {open === s.id && s.fields.length > 0 && (
              <table className="mt-2 t-small">
                <tbody>
                  {s.fields.map((f) => (
                    <tr key={f.name}>
                      <td className="raw pr-4 text-ink-3">{f.name}</td>
                      <td className="pr-4">{f.label}</td>
                      <td className="pr-4 text-ink-2">{f.type}</td>
                      <td className="text-ink-3">{f.required ? "requerido" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </li>
        ))}
      </ul>
      {!creating ? (
        <button className="btn" onClick={() => setCreating(true)}>
          <Plus size={14} /> Crear esquema personalizado
        </button>
      ) : (
        <div className="rounded-lg border hairline bg-paper p-4">
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            <label className="t-small">Identificador<input className="field-input mt-1 w-full" value={draft.id} onChange={(e) => setDraft({ ...draft, id: e.target.value })} /></label>
            <label className="t-small">Nombre<input className="field-input mt-1 w-full" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
            <label className="t-small sm:col-span-2">Descripción<input className="field-input mt-1 w-full" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <label className="t-small">Tipo de documento
              <select className="field-input mt-1 w-full" value={draft.document_types[0]} onChange={(e) => setDraft({ ...draft, document_types: [e.target.value] })}>
                {Object.entries(DOC_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="mt-6 flex items-center gap-2 t-small"><input type="checkbox" checked={draft.has_items} onChange={(e) => setDraft({ ...draft, has_items: e.target.checked })} /> Tiene tabla de ítems</label>
          </div>
          <h3 className="t-sub mb-1">Campos</h3>
          {draft.fields.map((f, i) => (
            <div key={i} className="mb-1 grid grid-cols-[1fr_1fr_8rem_auto_auto] items-center gap-2">
              <input className="field-input" placeholder="nombre_campo" value={f.name} onChange={(e) => { const fields = [...draft.fields]; fields[i] = { ...f, name: e.target.value }; setDraft({ ...draft, fields }); }} aria-label="Nombre del campo" />
              <input className="field-input" placeholder="Etiqueta visible" value={f.label} onChange={(e) => { const fields = [...draft.fields]; fields[i] = { ...f, label: e.target.value }; setDraft({ ...draft, fields }); }} aria-label="Etiqueta" />
              <select className="field-input" value={f.type} onChange={(e) => { const fields = [...draft.fields]; fields[i] = { ...f, type: e.target.value }; setDraft({ ...draft, fields }); }} aria-label="Tipo">
                {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <label className="flex items-center gap-1 t-tiny"><input type="checkbox" checked={f.required} onChange={(e) => { const fields = [...draft.fields]; fields[i] = { ...f, required: e.target.checked }; setDraft({ ...draft, fields }); }} />requerido</label>
              <button className="btn btn-quiet btn-icon" onClick={() => setDraft({ ...draft, fields: draft.fields.filter((_, j) => j !== i) })} aria-label="Quitar campo"><Trash2 size={13} /></button>
            </div>
          ))}
          <button className="btn btn-quiet mt-1" onClick={() => setDraft({ ...draft, fields: [...draft.fields, { name: "", label: "", type: "string", required: false }] })}><Plus size={13} /> Añadir campo</button>
          {err && <p className="mt-2 t-small text-red">{err}</p>}
          <div className="mt-3 flex gap-2">
            <button className="btn btn-ink" onClick={create}>Guardar esquema</button>
            <button className="btn" onClick={() => setCreating(false)}>Cancelar</button>
          </div>
        </div>
      )}
    </Section>
  );
}

interface StorageInfo {
  usage_bytes: Record<string, number>;
  quota_bytes: number;
  retention_days: number;
  observations_by_status: Record<string, number>;
  trash: number;
}

function Storage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["storage"], queryFn: () => api<StorageInfo>("/storage") });
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const d = q.data;
  const purge = async () => {
    const { confirm_token } = await api<{ confirm_token: string }>("/trash/purge-request", { method: "POST" });
    const r = await api<{ purged: number }>(`/trash?confirm_token=${encodeURIComponent(confirm_token)}`, { method: "DELETE" });
    setMsg(`${r.purged} observación(es) eliminadas de forma permanente.`);
    qc.invalidateQueries({ queryKey: ["storage"] });
  };
  return (
    <Section title="Almacenamiento" intro="Los originales se guardan sin modificar e identificados por su huella SHA-256; las copias procesadas se guardan aparte. Todo permanece en los volúmenes locales de Docker.">
      {d && (
        <>
          <div className="mb-2 h-3 w-full overflow-hidden rounded-full bg-desk">
            <div className="h-full bg-blue" style={{ width: `${Math.min(100, (d.usage_bytes.total / d.quota_bytes) * 100)}%` }} />
          </div>
          <p className="mb-4 t-small text-ink-2 num">{formatBytes(d.usage_bytes.total)} de {formatBytes(d.quota_bytes)} · originales {formatBytes(d.usage_bytes.originals)} · copias procesadas {formatBytes(d.usage_bytes.derived)}</p>
          <p className="mb-1 t-small">Conservación: {d.retention_days > 0 ? `los elementos de la papelera se eliminan tras ${d.retention_days} días` : "se conserva todo indefinidamente"} (variable VIE_RETENTION_DAYS).</p>
          <p className="mb-4 t-small">Observaciones por estado: {Object.entries(d.observations_by_status).map(([k, v]) => `${k} ${v}`).join(" · ") || "ninguna"}</p>
          <button className="btn btn-danger" disabled={!d.trash} onClick={() => setConfirm(true)}>Vaciar papelera ({d.trash})</button>
          {msg && <p className="mt-2 t-small text-ink-2">{msg}</p>}
          <p className="mt-4 t-small text-ink-2">Para respaldos completos use <span className="raw">make backup</span> y <span className="raw">make restore</span> (ver docs/backup-restore.md).</p>
        </>
      )}
      <ConfirmDialog open={confirm} title="Vaciar la papelera" body="Se eliminarán de forma permanente las observaciones de la papelera, con sus imágenes y datos. No se puede deshacer." action="Eliminar permanentemente" onConfirm={purge} onClose={() => setConfirm(false)} />
    </Section>
  );
}

function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api<{ id: number; ts: string; actor: string; action: string; target_id: string | null; outcome: string; details: Record<string, unknown> }[]>("/audit?limit=200") });
  return (
    <Section title="Auditoría" intro="Registro de operaciones: inicios de sesión, cargas, ediciones, eliminaciones, exportaciones y cambios de configuración.">
      <table className="w-full bg-paper t-small">
        <thead><tr className="border-b hairline text-left text-ink-2"><th className="px-3 py-2">Fecha</th><th>Operación</th><th>Objetivo</th><th className="pr-3">Resultado</th></tr></thead>
        <tbody>
          {(q.data ?? []).map((r) => (
            <tr key={r.id} className="border-b hairline">
              <td className="num px-3 py-1.5 text-ink-2">{formatDateTime(r.ts)}</td>
              <td>{r.action}</td>
              <td className="raw text-ink-3">{r.target_id?.slice(0, 18) ?? "—"}</td>
              <td className={`pr-3 ${r.outcome === "ok" ? "text-green" : "text-red"}`}>{r.outcome === "ok" ? "correcto" : "denegado"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function ApiInfo() {
  return (
    <Section title="API" intro="La API interna está documentada con OpenAPI. La documentación interactiva se sirve localmente, sin recursos externos.">
      <a className="btn btn-ink" href="/docs/" target="_blank" rel="noopener">Abrir la documentación de la API</a>
      <p className="mt-3 t-small text-ink-2">Especificación: <span className="raw">/api/v1/openapi.json</span>. Eventos en tiempo real: <span className="raw">/api/v1/events/stream</span> (SSE) y <span className="raw">/api/v1/camera/ws</span> (WebSocket).</p>
    </Section>
  );
}
