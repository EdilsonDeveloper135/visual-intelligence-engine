import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Download, Pencil, RefreshCw, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { ApiError, api } from "../../lib/api";
import { formatMs, formatValue } from "../../lib/format";
import { CHECK_STATUS, DOC_TYPES, SOURCES, STATUS, VALIDATION, docTypeLabel, fieldLabel } from "../../lib/labels";
import type { CheckResult, FieldValue, ObservationDetail } from "../../lib/types";
import { useUi } from "../../store/ui";
import ChatPanel from "./ChatPanel";

const TABS = [
  ["resumen", "Resumen"],
  ["campos", "Campos"],
  ["items", "Ítems"],
  ["texto", "Texto"],
  ["contexto", "Objetos y relaciones"],
  ["validacion", "Validación"],
  ["revision", "Revisión"],
  ["preguntar", "Preguntar"],
  ["json", "JSON"],
] as const;

/** Pencil mark: how a value is backed. */
export function ProvenanceMark({ f }: { f: FieldValue }) {
  if (f.edited_by_human) return <span className="mark text-ink" title="Corregido por una persona">✎</span>;
  if (f.needs_review) return <span className="mark text-red" title={f.review_reasons.join(" ") || "Requiere revisión"}>?</span>;
  if (f.sources.length > 1 || f.source === "qr") return <span className="mark text-green" title="Confirmado por más de una fuente o por el QR">✓</span>;
  return <span className="mark text-blue" title="Leído por la máquina con evidencia visual">·</span>;
}

function StatusLine({ d }: { d: ObservationDetail }) {
  const v = d.result.validation?.status ?? "pending";
  const color = v === "valid" ? "text-green" : v === "invalid" ? "text-red" : v === "valid_with_warnings" ? "text-amber" : "text-ink-3";
  const busy = ["queued", "processing", "interpreting"].includes(d.status);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 t-small">
      <span className={`font-semibold ${color}`}>{VALIDATION[v] ?? v}</span>
      <span className="text-ink-2">
        {busy && <RefreshCw size={12} className="mr-1 inline animate-spin" />}
        {STATUS[d.status] ?? d.status}
      </span>
      {d.needs_review_count > 0 && <span className="text-red">{d.needs_review_count} por revisar</span>}
    </div>
  );
}

export default function Ledger({ detail }: { detail: ObservationDetail }) {
  const tab = useUi((s) => s.ledgerTab);
  const setTab = useUi((s) => s.setLedgerTab);
  const r = detail.result;
  const reviewCount = r.validation?.needs_review?.length ?? 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b hairline px-4 pb-3 pt-4">
        <h2 className="t-head">{detail.title ?? docTypeLabel(r.document_type)}</h2>
        <StatusLine d={detail} />
      </header>
      <div role="tablist" aria-label="Interpretación" className="scroll-thin flex gap-1 overflow-x-auto border-b hairline px-2">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className="tab" onClick={() => setTab(id)}>
            {label}
            {id === "revision" && reviewCount > 0 && <span className="ml-1 rounded-full bg-red px-1.5 text-[0.7rem] text-paper">{reviewCount}</span>}
          </button>
        ))}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {tab === "resumen" && <Summary d={detail} />}
        {tab === "campos" && <Fields d={detail} />}
        {tab === "items" && <Items d={detail} />}
        {tab === "texto" && <TextTab d={detail} />}
        {tab === "contexto" && <ContextTab d={detail} />}
        {tab === "validacion" && <Checks checks={r.validation?.checks ?? []} />}
        {tab === "revision" && <Review d={detail} />}
        {tab === "preguntar" && <ChatPanel detail={detail} />}
        {tab === "json" && <JsonTab d={detail} />}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9.5rem_1fr] gap-3 border-b hairline px-4 py-2 t-small">
      <div className="text-ink-2">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function Summary({ d }: { d: ObservationDetail }) {
  const r = d.result;
  const m = r.metadata ?? ({} as ObservationDetail["result"]["metadata"]);
  const counts = useMemo(() => {
    const c = { pass: 0, fail: 0, warn: 0, skipped: 0 };
    for (const ch of r.validation?.checks ?? []) c[ch.status] += 1;
    return c;
  }, [r]);
  const t = m.timings ?? {};
  return (
    <div>
      {r.description && (
        <div className="border-b hairline px-4 py-3">
          <p className="leading-relaxed">{r.description}</p>
          <p className="t-tiny mt-1 text-ink-3">Descripción redactada por el modelo; los datos de abajo se verifican por separado.</p>
        </div>
      )}
      <Row label="Tipo de documento">
        {docTypeLabel(r.document_type)}
        {r.document_type_info?.rules && r.document_type_info?.vlm && r.document_type_info.rules !== r.document_type_info.vlm && (
          <span className="t-tiny ml-2 text-amber">reglas: {docTypeLabel(r.document_type_info.rules)} · modelo: {docTypeLabel(r.document_type_info.vlm)}</span>
        )}
      </Row>
      <Row label="Verificaciones">
        <span className="text-green">{counts.pass} correctas</span>
        {counts.warn > 0 && <span className="ml-3 text-amber">{counts.warn} advertencias</span>}
        {counts.fail > 0 && <span className="ml-3 text-red">{counts.fail} fallas</span>}
        <span className="ml-3 text-ink-3">{counts.skipped} sin datos</span>
      </Row>
      <Row label="Texto reconocido">
        {r.text?.lines?.length ?? 0} líneas · {r.codes?.length ?? 0} código(s)
      </Row>
      <Row label="Origen">
        {d.source === "camera" ? "Cámara" : d.source === "sequence" ? "Secuencia" : d.source === "video" ? "Video" : d.source === "video_frame" ? "Escena de un video" : "Archivo"}
        {d.parent_id && <a href={`/o/${d.parent_id}`} className="ml-2 text-blue">ver video</a>}
        {d.original_filename ? <span className="ml-1 text-ink-2">· {d.original_filename}</span> : null}
        {d.kind === "updated" && <span className="ml-2 text-blue">actualización de una observación previa</span>}
      </Row>
      <Row label="Modelo">
        {m.model ?? "—"}
        {m.vlm_status && m.vlm_status !== "done" && (
          <span className={`ml-2 ${m.vlm_status === "pending" ? "text-ink-3" : "text-amber"}`}>
            {m.vlm_status === "pending" ? "pendiente" : m.vlm_status === "not_requested" ? "no solicitado" : `sin interpretación (${m.vlm_error ?? m.vlm_status})`}
          </span>
        )}
      </Row>
      <Row label="Tiempos">
        <span className="num">
          lectura {formatMs(t.stage1_ms)} · modelo {formatMs(t.vlm_ms)} · total {formatMs(m.processing_time_ms)}
        </span>
      </Row>
      <Row label="Motor OCR">
        <span className="t-tiny text-ink-2">{m.ocr_engine ?? "—"}</span>
      </Row>
      {(r.unreadable ?? []).length > 0 && (
        <Row label="Ilegible según el modelo">{r.unreadable.map((u) => u.element).join(", ")}</Row>
      )}
      {d.error && <Row label="Error"><span className="text-red">{d.error.message}</span></Row>}
      <Actions d={d} />
    </div>
  );
}

function Actions({ d }: { d: ObservationDetail }) {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      setMsg(ok);
      qc.invalidateQueries({ queryKey: ["observation", d.id] });
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "No se pudo completar la acción.");
    }
  };
  const busy = ["queued", "processing", "interpreting"].includes(d.status);
  return (
    <div className="flex flex-wrap gap-2 px-4 py-3">
      <button className="btn" disabled={busy} onClick={() => run(() => api(`/observations/${d.id}/analyze`, { method: "POST", json: { stages: "interpret" } }), "Interpretación en cola.")}>
        <RefreshCw size={14} /> Interpretar de nuevo
      </button>
      <button className="btn" disabled={busy} onClick={() => run(() => api(`/observations/${d.id}/validate`, { method: "POST" }), "Validación actualizada.")}>
        <Check size={14} /> Revalidar
      </button>
      <button className="btn" onClick={() => run(() => api("/actions/save_record", { method: "POST", json: { params: { observation_id: d.id } } }), "Registro confirmado.")}>
        Confirmar registro
      </button>
      {msg && <p className="w-full t-small text-ink-2" role="status">{msg}</p>}
    </div>
  );
}

function useEdit(d: ObservationDetail) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: object) => api(`/observations/${d.id}/fields`, { method: "PATCH", json: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["observation", d.id] }),
  });
}

function FieldRow({ name, f, d, label }: { name: string; f: FieldValue | null; d: ObservationDetail; label?: string }) {
  const setHot = useUi((s) => s.setHot);
  const setHotBox = useUi((s) => s.setHotBox);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const edit = useEdit(d);
  const start = () => {
    setValue(f?.value === null || f?.value === undefined ? "" : String(f.value));
    setEditing(true);
  };
  const save = () =>
    edit.mutate({ changes: [{ field: name, value: value || null }], reason: "Corrección manual" }, { onSuccess: () => setEditing(false) });
  return (
    <div
      className={`group grid grid-cols-[1.5rem_8.5rem_1fr_auto] items-start gap-2 border-b hairline px-3 py-2 t-small ${f?.needs_review ? "bg-red-wash" : ""}`}
      onMouseEnter={() => {
        setHot(f?.evidence_ids ?? []);
        setHotBox(f?.bounding_box ?? null);
      }}
      onMouseLeave={() => {
        setHot([]);
        setHotBox(null);
      }}
    >
      <div className="pt-0.5">{f ? <ProvenanceMark f={f} /> : <span className="mark text-ink-3 opacity-50">–</span>}</div>
      <div className="pt-0.5 text-ink-2">{label ?? fieldLabel(name)}</div>
      <div className="min-w-0">
        {editing ? (
          <div className="flex gap-1">
            <input className="field-input w-full" value={value} onChange={(e) => setValue(e.target.value)} autoFocus onKeyDown={(e) => e.key === "Enter" && save()} aria-label={`Nuevo valor de ${fieldLabel(name)}`} />
            <button className="btn btn-ink btn-icon" onClick={save} aria-label="Guardar cambio" disabled={edit.isPending}>
              <Check size={14} />
            </button>
            <button className="btn btn-icon" onClick={() => setEditing(false)} aria-label="Cancelar">
              <X size={14} />
            </button>
          </div>
        ) : (
          <>
            <div className={`num break-words ${f?.value == null ? "text-ink-3" : "font-semibold"}`}>
              {f ? formatValue(f.type, f.value, f.currency) : "No encontrado"}
            </div>
            {f && f.value !== null && (
              <div className="t-tiny text-ink-3">
                {f.sources.map((s) => SOURCES[s.source] ?? s.source).join(" + ")}
                {f.evidence_ids.length > 0 && <span className="raw ml-1">{f.evidence_ids.slice(0, 3).join(" ")}</span>}
              </div>
            )}
            {f?.review_reasons?.map((reason, i) => (
              <div key={i} className="t-tiny text-red">
                {reason}
              </div>
            ))}
            {edit.error && <div className="t-tiny text-red">{(edit.error as Error).message}</div>}
          </>
        )}
      </div>
      {!editing && (
        <button className="btn btn-quiet btn-icon opacity-60 group-hover:opacity-100" onClick={start} aria-label={`Editar ${fieldLabel(name)}`}>
          <Pencil size={13} />
        </button>
      )}
    </div>
  );
}

function Fields({ d }: { d: ObservationDetail }) {
  const fields = d.result.fields ?? {};
  const names = Object.keys(fields);
  const ordered = [...names.filter((n) => fields[n] !== null), ...names.filter((n) => fields[n] === null)];
  const dyn = d.result.dynamic_fields ?? [];
  if (!names.length && !dyn.length) return <Empty text="Aún no hay campos. Aparecerán al terminar la lectura." />;
  return (
    <div>
      <p className="t-tiny px-4 py-2 text-ink-3">
        <span className="text-green">✓</span> confirmado · <span className="text-blue">·</span> leído con evidencia · <span className="text-red">?</span> requiere revisión · ✎ corregido. Pase el cursor para ver la evidencia en la imagen.
      </p>
      {ordered.map((n) => (
        <FieldRow key={n} name={n} f={fields[n]} d={d} />
      ))}
      {dyn.length > 0 && <h3 className="t-sub px-4 pb-1 pt-4">Campos detectados (modo universal)</h3>}
      {dyn.map((f) => (
        <FieldRow key={f.key} name={f.key} f={f} d={d} label={f.label} />
      ))}
    </div>
  );
}

function Items({ d }: { d: ObservationDetail }) {
  const items = d.result.items ?? [];
  const setHotBox = useUi((s) => s.setHotBox);
  const currency = d.result.fields?.currency?.value as string | undefined;
  if (!items.length) return <Empty text="No se identificaron ítems en este documento." />;
  return (
    <table className="w-full t-small">
      <thead>
        <tr className="border-b hairline text-left text-ink-2">
          <th className="px-3 py-2 font-semibold">Descripción</th>
          <th className="px-2 py-2 text-right font-semibold">Cant.</th>
          <th className="px-2 py-2 text-right font-semibold">P. unit.</th>
          <th className="px-3 py-2 text-right font-semibold">Importe</th>
        </tr>
      </thead>
      <tbody>
        {items.map((it, i) => (
          <tr key={i} className={`border-b hairline ${it.needs_review ? "bg-red-wash" : ""}`} onMouseEnter={() => setHotBox(it.bounding_box)} onMouseLeave={() => setHotBox(null)}>
            <td className="px-3 py-2">
              {it.description}
              <div className="t-tiny text-ink-3">{SOURCES[it.source ?? ""] ?? it.source}</div>
            </td>
            <td className="num px-2 py-2 text-right">{it.quantity ?? "—"}</td>
            <td className="num px-2 py-2 text-right">{formatValue("money", it.unit_price, currency)}</td>
            <td className="num px-3 py-2 text-right font-semibold">{formatValue("money", it.amount, currency)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TextTab({ d }: { d: ObservationDetail }) {
  const lines = d.result.text?.lines ?? [];
  const hot = useUi((s) => s.hot);
  const setHot = useUi((s) => s.setHot);
  const setHotBox = useUi((s) => s.setHotBox);
  if (!lines.length) return <Empty text="No se reconoció texto en la imagen." />;
  return (
    <div>
      <div className="flex items-center justify-between px-4 py-2">
        <span className="t-tiny text-ink-3">{lines[0].source === "pdf_text" ? "Texto incrustado en el PDF (sin OCR)" : "Texto reconocido por OCR, en orden de lectura"}</span>
        <button className="btn btn-quiet" onClick={() => navigator.clipboard?.writeText(d.result.text.full_text)}>
          <Copy size={14} /> Copiar
        </button>
      </div>
      <ol>
        {lines.map((l) => (
          <li
            key={l.id}
            className={`grid cursor-default grid-cols-[4rem_1fr_3rem] gap-2 border-b hairline px-4 py-1.5 ${hot.includes(l.id) ? "bg-blue-wash" : ""}`}
            onMouseEnter={() => { setHot([l.id]); setHotBox(l.bbox); }}
            onMouseLeave={() => { setHot([]); setHotBox(null); }}
          >
            <span className="raw text-ink-3">{l.id}</span>
            <span className="raw break-words">{l.text}</span>
            <span className="t-tiny num text-right text-ink-3" title={l.score ? `Confianza del reconocedor (${l.score.source}); no es una probabilidad` : "Texto del PDF"}>
              {l.score ? l.score.value.toFixed(2) : "PDF"}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function ContextTab({ d }: { d: ObservationDetail }) {
  const r = d.result;
  return (
    <div className="px-4 py-3">
      <h3 className="t-sub mb-1">Entidades</h3>
      {(r.entities ?? []).length === 0 ? (
        <p className="t-small text-ink-3">Sin entidades.</p>
      ) : (
        <ul className="mb-4">
          {r.entities.map((e, i) => (
            <li key={i} className="flex gap-2 border-b hairline py-1.5 t-small">
              <span className="w-28 flex-none text-ink-2">{ENTITY[e.type] ?? e.type}{e.role ? ` (${ROLE[e.role] ?? e.role})` : ""}</span>
              <span className="break-words">{e.normalized ?? e.value}</span>
            </li>
          ))}
        </ul>
      )}
      <h3 className="t-sub mb-1 mt-4">Objetos vistos</h3>
      {(r.objects ?? []).length === 0 ? (
        <p className="t-small text-ink-3">El modelo no reportó objetos.</p>
      ) : (
        <ul className="mb-4">
          {r.objects.map((o, i) => (
            <li key={i} className="flex items-center gap-2 border-b hairline py-1.5 t-small">
              <span className={`mark ${o.verified === true ? "text-green" : o.verified === false ? "text-red" : "text-ink-3"}`}>
                {o.verified === true ? "✓" : o.verified === false ? "✗" : "·"}
              </span>
              {o.label}
              <span className="t-tiny ml-auto text-ink-3">
                {o.verified === true ? `confirmado por ${o.verified_by}` : o.verified === false ? "no confirmado por el detector" : "según el modelo, sin verificar"}
              </span>
            </li>
          ))}
        </ul>
      )}
      <h3 className="t-sub mb-1 mt-4">Relaciones</h3>
      {(r.relationships ?? []).length === 0 ? (
        <p className="t-small text-ink-3">Sin relaciones detectadas.</p>
      ) : (
        <ul>
          {r.relationships.map((rel, i) => (
            <li key={i} className="border-b hairline py-1.5 t-small">
              <span className="font-semibold">{fieldLabel(rel.source)}</span> <span className="text-ink-2">{REL[rel.type] ?? rel.type}</span>{" "}
              <span className="font-semibold">{rel.target.split(" ").map((t) => (t.match(/^[a-z_]+$/) ? fieldLabel(t) : t)).join(" ")}</span>
              {rel.description && <div className="t-tiny text-ink-3">{rel.description}</div>}
            </li>
          ))}
        </ul>
      )}
      {(r.inferences ?? []).length > 0 && (
        <>
          <h3 className="t-sub mb-1 mt-4">Inferencias del modelo</h3>
          <p className="t-tiny mb-1 text-ink-3">No están escritas literalmente en el documento.</p>
          <ul>
            {r.inferences.map((inf, i) => (
              <li key={i} className="border-b hairline py-1.5 t-small">
                {inf.statement}
                {inf.basis && <div className="t-tiny text-ink-3">Base: {inf.basis}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

const ENTITY: Record<string, string> = { organization: "Organización", person: "Persona", tax_id: "RUC", national_id: "DNI", address: "Dirección", date: "Fecha", amount: "Monto", document_id: "Comprobante" };
const ROLE: Record<string, string> = { issuer: "emisor", customer: "cliente", issue: "emisión", due: "vencimiento", total: "total", document: "documento" };
const REL: Record<string, string> = { identified_by: "se identifica con", issued_to: "emitido a", tax_of: "es impuesto de", sum_of: "es la suma de", modifies: "modifica" };

export function Checks({ checks }: { checks: CheckResult[] }) {
  if (!checks.length) return <Empty text="La validación se ejecuta al terminar la lectura." />;
  const order = { fail: 0, warn: 1, pass: 2, skipped: 3 };
  const sorted = [...checks].sort((a, b) => order[a.status] - order[b.status]);
  return (
    <div>
      <p className="t-tiny px-4 py-2 text-ink-3">Verificaciones deterministas, independientes del modelo. «Sin datos» nunca se cuenta como correcto.</p>
      <ul>
        {sorted.map((c) => (
          <li key={c.id} className="grid grid-cols-[1.5rem_1fr] gap-2 border-b hairline px-3 py-2 t-small">
            <span className={`mark ${c.status === "pass" ? "text-green" : c.status === "fail" ? "text-red" : c.status === "warn" ? "text-amber" : "text-ink-3"}`}>
              {c.status === "pass" ? "✓" : c.status === "fail" ? "✗" : c.status === "warn" ? "!" : "–"}
            </span>
            <div>
              <div>{c.message}</div>
              <div className="t-tiny text-ink-3">
                {CHECK_STATUS[c.status]} · {c.rule}
                {c.tolerance ? ` · tolerancia ${c.tolerance}` : ""}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Review({ d }: { d: ObservationDetail }) {
  const list = d.result.validation?.needs_review ?? [];
  const edit = useEdit(d);
  const fields = d.result.fields ?? {};
  if (!list.length) return <Empty text="Nada pendiente de revisión humana." />;
  const confirm = (name: string) => {
    const f = fields[name];
    edit.mutate({ changes: [{ field: name, value: f?.value == null ? null : String(f.value) }], reason: "Confirmado en revisión" });
  };
  return (
    <div>
      <p className="t-tiny px-4 py-2 text-ink-3">Confirme el valor si coincide con la imagen o corríjalo en la pestaña Campos.</p>
      {list.map((name) => {
        const f = fields[name];
        return (
          <div key={name} className="border-b hairline px-4 py-2.5 t-small">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{name.startsWith("items[") ? `Ítem ${Number(name.slice(6, -1)) + 1}` : fieldLabel(name)}</span>
              {f && !name.startsWith("items[") && (
                <button className="btn" onClick={() => confirm(name)} disabled={edit.isPending}>
                  <Check size={14} /> Confirmar {f.value != null ? formatValue(f.type, f.value, f.currency) : "vacío"}
                </button>
              )}
            </div>
            {f?.review_reasons?.map((r, i) => (
              <div key={i} className="t-tiny text-red">
                {r}
              </div>
            ))}
            {!f && !name.startsWith("items[") && <div className="t-tiny text-red">Campo requerido no encontrado.</div>}
          </div>
        );
      })}
      {edit.error && <p className="px-4 py-2 t-small text-red">{(edit.error as Error).message}</p>}
    </div>
  );
}

function JsonTab({ d }: { d: ObservationDetail }) {
  const json = JSON.stringify(d.result, null, 2);
  const save = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `observacion-${d.id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };
  return (
    <div>
      <div className="flex gap-2 px-4 py-2">
        <button className="btn" onClick={() => navigator.clipboard?.writeText(json)}>
          <Copy size={14} /> Copiar
        </button>
        <button className="btn" onClick={save}>
          <Download size={14} /> Descargar
        </button>
      </div>
      <pre className="raw scroll-thin overflow-x-auto whitespace-pre px-4 pb-6 text-[0.75rem] leading-relaxed text-ink-2">{json}</pre>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="px-4 py-8 text-center t-small text-ink-3">{text}</p>;
}

export const DOC_TYPE_OPTIONS = Object.entries(DOC_TYPES);
