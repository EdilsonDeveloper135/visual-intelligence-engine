import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router";
import { ApiError, api, assetUrl, qs } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { STATUS, VALIDATION, docTypeLabel } from "../../lib/labels";
import type { ObservationSummary } from "../../lib/types";

const ACCEPT = ".png,.jpg,.jpeg,.webp,.pdf,image/png,image/jpeg,image/webp,application/pdf";

export async function uploadFiles(files: File[], opts: { mode?: string; sequence?: boolean } = {}) {
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  fd.append("mode", opts.mode ?? "full");
  if (opts.sequence) fd.append("sequence", "true");
  return api<{ observations: { id: string; filename: string }[] }>("/observations", { method: "POST", body: fd });
}

export default function UploadPane() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ocrOnly, setOcrOnly] = useState(false);
  const recent = useQuery({
    queryKey: ["observations", "desk"],
    queryFn: () => api<{ items: ObservationSummary[] }>(`/observations${qs({ page_size: 8 })}`),
  });

  const send = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const res = await uploadFiles(files, { mode: ocrOnly ? "ocr_only" : "full", sequence: files.length > 1 });
      qc.invalidateQueries({ queryKey: ["observations"] });
      navigate(`/o/${res.observations[0].id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo cargar el archivo.");
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    send(Array.from(e.dataTransfer.files));
  };

  return (
    <div className="scroll-thin flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-6 py-10">
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={`relative flex aspect-[1/1.35] h-[min(570px,calc(100vh-15rem))] min-h-[420px] max-w-full flex-none flex-col items-center justify-center rounded-sm bg-paper px-8 text-center shadow-[0_1px_0_var(--rule),0_14px_40px_rgb(0_0_0/0.10)] transition-transform ${
          over ? "scale-[1.02] outline outline-2 outline-offset-4 outline-blue" : ""
        }`}
      >
        <div className="absolute inset-x-10 top-12 space-y-3 opacity-60" aria-hidden>
          <div className="h-2.5 w-2/3 rounded bg-blue-wash" />
          <div className="h-2.5 w-1/2 rounded bg-blue-wash" />
          <div className="h-2.5 w-3/5 rounded bg-blue-wash" />
        </div>
        <FileUp size={30} className="mb-3 text-blue" />
        <h1 className="t-title mb-2">Ponga un documento sobre la mesa</h1>
        <p className="mb-5 max-w-[30ch] text-ink-2">Arrastre aquí una foto, un escaneo o un PDF. Se lee el texto, se interpreta con el modelo local y se verifica.</p>
        <button className="btn btn-ink" onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Cargando…" : "Elegir archivos"}
        </button>
        <label className="mt-3 flex items-center gap-2 t-small text-ink-2">
          <input type="checkbox" checked={ocrOnly} onChange={(e) => setOcrOnly(e.target.checked)} />
          Solo lectura (sin el modelo, más rápido)
        </label>
        <p className="t-tiny absolute bottom-5 px-6 text-ink-3">PNG, JPEG, WEBP o PDF, hasta 20 MB por imagen y 30 MB por PDF. Nada sale de este equipo.</p>
        <input ref={input} type="file" accept={ACCEPT} multiple hidden onChange={(e) => send(Array.from(e.target.files ?? []))} data-testid="file-input" />
      </div>
      {error && (
        <p role="alert" className="mt-4 max-w-[420px] text-center t-small text-red">
          {error}
        </p>
      )}

      {(recent.data?.items.length ?? 0) > 0 && (
        <div className="mt-10 w-full max-w-[880px]">
          <h2 className="t-sub mb-2 text-ink-2">Recientes</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {recent.data!.items.map((o) => (
              <Link key={o.id} to={`/o/${o.id}`} className="group rounded-md bg-paper p-2 hover:outline hover:outline-1 hover:outline-rule">
                <div className="mb-2 h-28 overflow-hidden rounded-sm bg-desk">
                  {o.thumbnail_asset_id && <img src={assetUrl(o.thumbnail_asset_id)} alt="" className="h-full w-full object-cover object-top" />}
                </div>
                <div className="truncate t-small font-semibold">{o.title ?? docTypeLabel(o.document_type)}</div>
                <div className="t-tiny text-ink-3">
                  {o.validation_status ? VALIDATION[o.validation_status] : STATUS[o.status]} · {formatDateTime(o.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
