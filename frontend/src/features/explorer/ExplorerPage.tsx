import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Download, GitCompareArrows, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import ConfirmDialog from "../../components/ConfirmDialog";
import { ApiError, api, assetUrl, download, qs } from "../../lib/api";
import { formatDate, formatDateTime, formatMoney } from "../../lib/format";
import { DOC_TYPES, STATUS, VALIDATION, docTypeLabel, fieldLabel } from "../../lib/labels";
import type { ObservationSummary } from "../../lib/types";

interface Page {
  items: ObservationSummary[];
  total: number;
  page: number;
  page_size: number;
}

interface CompareResult {
  fields: { field: string; a: unknown; b: unknown; equal: boolean }[];
  findings: string[];
  same_document_type: boolean;
}

export default function ExplorerPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [docType, setDocType] = useState("");
  const [validation, setValidation] = useState("");
  const [source, setSource] = useState("");
  const [review, setReview] = useState(false);
  const [trash, setTrash] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [confirm, setConfirm] = useState<null | "delete" | "purge">(null);

  const params = { q: term, document_type: docType, validation_status: validation, source, needs_review: review || undefined, only_deleted: trash || undefined, page, page_size: 30 };
  const list = useQuery({ queryKey: ["observations", "explorer", params], queryFn: () => api<Page>(`/observations${qs(params)}`) });
  const items = list.data?.items ?? [];
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg(ok);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "No se pudo completar la acción.");
    }
  };

  const exportAs = (format: string) =>
    run(() => download("/exports", selected.length ? { format, observation_ids: selected } : { format, filters: { q: term || null, document_type: docType || null } }, `vie.${format}`));

  const deleteSelected = async () => {
    for (const id of selected) {
      const { confirm_token } = await api<{ confirm_token: string }>(`/observations/${id}/delete-request`, { method: "POST" });
      await api(`/observations/${id}${qs({ confirm_token })}`, { method: "DELETE" });
    }
    setMsg(`${selected.length} observación(es) movidas a la papelera.`);
    setSelected([]);
    qc.invalidateQueries({ queryKey: ["observations"] });
  };
  const restoreSelected = () =>
    run(async () => {
      for (const id of selected) await api(`/observations/${id}/restore`, { method: "POST" });
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["observations"] });
    }, "Restauradas.");
  const purge = async () => {
    const { confirm_token } = await api<{ confirm_token: string }>("/trash/purge-request", { method: "POST" });
    const r = await api<{ purged: number }>(`/trash${qs({ confirm_token })}`, { method: "DELETE" });
    setMsg(`${r.purged} observación(es) eliminadas de forma permanente.`);
    qc.invalidateQueries({ queryKey: ["observations"] });
  };

  return (
    <div className="scroll-thin flex h-full flex-col overflow-y-auto">
      <header className="border-b hairline bg-paper px-6 py-4">
        <h1 className="t-title mb-3">{trash ? "Papelera" : "Explorar observaciones"}</h1>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setTerm(q);
            setPage(1);
          }}
        >
          <div className="relative min-w-[240px] flex-1">
            <Search size={15} className="absolute left-2.5 top-2.5 text-ink-3" />
            <input className="field-input w-full pl-8" placeholder="Buscar texto, RUC, serie o emisor" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Buscar" />
          </div>
          <select className="field-input" value={docType} onChange={(e) => { setDocType(e.target.value); setPage(1); }} aria-label="Tipo de documento">
            <option value="">Todos los tipos</option>
            {Object.entries(DOC_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="field-input" value={validation} onChange={(e) => { setValidation(e.target.value); setPage(1); }} aria-label="Validación">
            <option value="">Cualquier validación</option>
            {Object.entries(VALIDATION).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="field-input" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} aria-label="Origen">
            <option value="">Todo origen</option>
            <option value="upload">Archivo</option>
            <option value="camera">Cámara</option>
            <option value="sequence">Secuencia</option>
          </select>
          <label className="flex items-center gap-1.5 t-small text-ink-2">
            <input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} /> Con revisión pendiente
          </label>
          <button className="btn btn-ink">Buscar</button>
          <button type="button" className={`btn ${trash ? "bg-paper-2" : ""}`} onClick={() => { setTrash(!trash); setSelected([]); setPage(1); }}>
            <Trash2 size={14} /> {trash ? "Salir de la papelera" : "Papelera"}
          </button>
        </form>
      </header>

      <div className="flex flex-wrap items-center gap-2 px-6 py-2 t-small">
        <span className="text-ink-2">{list.data ? `${list.data.total} resultado(s)` : "Cargando…"}{selected.length ? ` · ${selected.length} seleccionado(s)` : ""}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {!trash && (
            <>
              <span className="self-center text-ink-3">Exportar {selected.length ? "selección" : "resultados"}:</span>
              {[["csv", "CSV"], ["csv_items", "CSV de ítems"], ["xlsx", "Excel"], ["json", "JSON"], ["html", "Informe"]].map(([f, label]) => (
                <button key={f} className="btn" onClick={() => exportAs(f)}>
                  <Download size={14} /> {label}
                </button>
              ))}
              <button className="btn" disabled={selected.length !== 2} onClick={() => run(async () => setCompare(await api<CompareResult>("/compare", { method: "POST", json: { a: selected[0], b: selected[1] } })))}>
                <GitCompareArrows size={14} /> Comparar 2
              </button>
              <button className="btn btn-danger" disabled={!selected.length} onClick={() => setConfirm("delete")}>
                <Trash2 size={14} /> Mover a la papelera
              </button>
            </>
          )}
          {trash && (
            <>
              <button className="btn" disabled={!selected.length} onClick={restoreSelected}>
                <ArchiveRestore size={14} /> Restaurar
              </button>
              <button className="btn btn-danger" disabled={!list.data?.total} onClick={() => setConfirm("purge")}>
                Vaciar papelera
              </button>
            </>
          )}
        </div>
        {msg && <p role="status" className="w-full text-ink-2">{msg}</p>}
      </div>

      {compare && (
        <div className="mx-6 mb-3 rounded-lg border hairline bg-paper p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="t-sub">Comparación de documentos</h2>
            <button className="btn btn-quiet" onClick={() => setCompare(null)}>Cerrar</button>
          </div>
          {compare.findings.map((f, i) => <p key={i} className="t-small text-amber">{f}</p>)}
          <table className="mt-2 w-full t-small">
            <thead><tr className="text-left text-ink-2"><th className="py-1">Campo</th><th>A</th><th>B</th></tr></thead>
            <tbody>
              {compare.fields.map((r) => (
                <tr key={r.field} className={`border-t hairline ${r.equal ? "" : "bg-amber-wash"}`}>
                  <td className="py-1 pr-3 text-ink-2">{fieldLabel(r.field)}</td>
                  <td className="num pr-3">{String(r.a ?? "—")}</td>
                  <td className="num">{String(r.b ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="px-6 pb-8">
        {items.length === 0 && list.data && (
          <p className="py-12 text-center text-ink-3">{trash ? "La papelera está vacía." : "No hay observaciones con esos filtros. Cargue un documento desde la Mesa."}</p>
        )}
        {items.length > 0 && (
          <table className="w-full bg-paper t-small">
            <thead>
              <tr className="border-b hairline text-left text-ink-2">
                <th className="w-8 px-2 py-2"><span className="sr-only">Seleccionar</span></th>
                <th className="py-2 font-semibold">Documento</th>
                <th className="py-2 font-semibold">RUC emisor</th>
                <th className="py-2 font-semibold">Fecha</th>
                <th className="py-2 text-right font-semibold">Total</th>
                <th className="px-3 py-2 font-semibold">Verificación</th>
                <th className="py-2 pr-3 font-semibold">Registrado</th>
              </tr>
            </thead>
            <tbody>
              {items.map((o) => (
                <tr key={o.id} className="border-b hairline hover:bg-paper-2">
                  <td className="px-2"><input type="checkbox" checked={selected.includes(o.id)} onChange={() => toggle(o.id)} aria-label={`Seleccionar ${o.title ?? o.id}`} /></td>
                  <td className="py-1.5">
                    <Link to={trash ? "#" : `/o/${o.id}`} className="flex items-center gap-2.5">
                      <span className="h-10 w-8 flex-none overflow-hidden rounded-sm bg-desk">
                        {o.thumbnail_asset_id && <img src={assetUrl(o.thumbnail_asset_id)} alt="" className="h-full w-full object-cover object-top" />}
                      </span>
                      <span>
                        <span className="block font-semibold">{o.title ?? docTypeLabel(o.document_type)}</span>
                        <span className="t-tiny text-ink-3">{o.original_filename ?? (o.source === "camera" ? "Cámara" : "")}{o.kind === "updated" ? " · actualización" : ""}</span>
                      </span>
                    </Link>
                  </td>
                  <td className="num">{o.issuer_ruc ?? "—"}</td>
                  <td className="num">{formatDate(o.issue_date)}</td>
                  <td className="num text-right">{o.total ? formatMoney(o.total, o.currency) : "—"}</td>
                  <td className="px-3">
                    <span className={o.validation_status === "valid" ? "text-green" : o.validation_status === "invalid" ? "text-red" : o.validation_status === "valid_with_warnings" ? "text-amber" : "text-ink-3"}>
                      {o.validation_status ? VALIDATION[o.validation_status] : STATUS[o.status]}
                    </span>
                    {o.needs_review_count > 0 && <span className="ml-1 text-red">· {o.needs_review_count} por revisar</span>}
                  </td>
                  <td className="t-tiny pr-3 text-ink-3">{formatDateTime(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {list.data && list.data.total > list.data.page_size && (
          <div className="mt-3 flex items-center justify-center gap-2 t-small">
            <button className="btn" disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</button>
            <span className="text-ink-2">Página {page} de {Math.ceil(list.data.total / list.data.page_size)}</span>
            <button className="btn" disabled={page * list.data.page_size >= list.data.total} onClick={() => setPage(page + 1)}>Siguiente</button>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirm === "delete"}
        title="Mover a la papelera"
        body={`Se moverán ${selected.length} observación(es) a la papelera. Podrá restaurarlas hasta que vacíe la papelera.`}
        action="Mover a la papelera"
        onConfirm={() => run(deleteSelected)}
        onClose={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "purge"}
        title="Vaciar la papelera"
        body="Las observaciones de la papelera, sus imágenes y sus datos se eliminarán de forma permanente. Esta acción no se puede deshacer."
        action="Eliminar permanentemente"
        onConfirm={() => run(purge)}
        onClose={() => setConfirm(null)}
      />
    </div>
  );
}
