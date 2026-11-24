import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Layers,
  MessageSquareText,
  Maximize,
  RotateCw,
  SquareDashedMousePointer,
  Type,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent, type WheelEvent } from "react";
import { assetUrl } from "../../lib/api";
import { boxesIntersect, normalizeRect } from "../../lib/format";
import { QUALITY_FLAGS, STEPS, fieldLabel } from "../../lib/labels";
import type { ObservationDetail, TextLine } from "../../lib/types";
import { useUi, type Layer } from "../../store/ui";

const LAYER_LABEL: Record<Layer, string> = { text: "Texto leído", fields: "Campos", codes: "Códigos QR", review: "Por revisar" };

export default function DocumentViewer({ detail }: { detail: ObservationDetail }) {
  const result = detail.result;
  const pages = result.pages ?? [];
  const [page, setPage] = useState(0);
  const [showOriginal, setShowOriginal] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [rot, setRot] = useState(0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selectMode, setSelectMode] = useState(false);
  const [sel, setSel] = useState<[number, number, number, number] | null>(null);
  const [tip, setTip] = useState<{ line: TextLine; x: number; y: number } | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ kind: "pan" | "select"; x: number; y: number; px: number; py: number; ix?: number; iy?: number } | null>(null);
  const [fit, setFit] = useState(1);

  const { layers, toggleLayer, hot, hotBox, overlayText, setOverlayText, setRegion, setLedgerTab, setHot } = useUi();

  const info = pages[page] ?? pages[0];
  const workAsset = detail.assets.find((a) => a.kind === "work" && a.page_index === page);
  const imgId = showOriginal ? workAsset?.id : (info?.display_asset_id ?? workAsset?.id);
  const width = (showOriginal ? workAsset?.width : info?.width) ?? info?.width ?? 1000;
  const height = (showOriginal ? workAsset?.height : info?.height) ?? info?.height ?? 1400;
  const overlaysMatch = !showOriginal || !info || info.display_asset_id === workAsset?.id;

  const lines = useMemo(() => (result.text?.lines ?? []).filter((l) => l.page === page), [result, page]);
  const fieldBoxes = useMemo(
    () =>
      Object.entries(result.fields ?? {})
        .filter(([, f]) => f && f.bounding_box && (f.page ?? 0) === page)
        .map(([name, f]) => ({ name, box: f!.bounding_box!, review: f!.needs_review })),
    [result, page],
  );
  const codes = (result.codes ?? []).filter((c) => c.page === page && c.bbox);

  // fit to available width on load / resize
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const compute = () => {
      const w = el.clientWidth - 48;
      const h = el.clientHeight - 48;
      const rotated = rot % 180 !== 0;
      const iw = rotated ? height : width;
      const ih = rotated ? width : height;
      setFit(Math.max(0.05, Math.min(w / iw, h / ih)));
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, [width, height, rot]);

  useEffect(() => {
    setPan({ x: 0, y: 0 });
    setZoom(1);
    setSel(null);
  }, [detail.id, page]);

  const scale = fit * zoom;

  const toImage = (clientX: number, clientY: number): [number, number] => {
    const svg = svgRef.current;
    if (!svg) return [0, 0];
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const m = svg.getScreenCTM();
    if (!m) return [0, 0];
    const p = pt.matrixTransform(m.inverse());
    return [Math.max(0, Math.min(width, p.x)), Math.max(0, Math.min(height, p.y))];
  };

  const onPointerDown = (e: RPointerEvent) => {
    if (e.button !== 0) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setDragging(true);
    if (selectMode) {
      const [ix, iy] = toImage(e.clientX, e.clientY);
      drag.current = { kind: "select", x: e.clientX, y: e.clientY, px: 0, py: 0, ix, iy };
      setSel([ix, iy, ix, iy]);
    } else {
      drag.current = { kind: "pan", x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    }
  };
  const onPointerMove = (e: RPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (d.kind === "pan") setPan({ x: d.px + e.clientX - d.x, y: d.py + e.clientY - d.y });
    else {
      const [ix, iy] = toImage(e.clientX, e.clientY);
      setSel(normalizeRect(d.ix!, d.iy!, ix, iy));
    }
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    if (d?.kind === "select" && sel && (sel[2] - sel[0] < 6 || sel[3] - sel[1] < 6)) setSel(null);
  };
  const onWheel = (e: WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    setZoom((z) => Math.min(8, Math.max(0.2, z * (e.deltaY < 0 ? 1.12 : 0.89))));
  };

  const selectedText = sel ? lines.filter((l) => boxesIntersect(l.bbox, sel)).map((l) => l.text).join("\n") : "";

  const askRegion = () => {
    if (!sel) return;
    setRegion({ page, bbox: sel.map(Math.round) });
    setLedgerTab("preguntar");
    setSelectMode(false);
  };

  const quality = info?.quality;
  const applied = (info?.preprocessing ?? []).filter((s) => s.applied);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-1 border-b hairline bg-paper px-3 py-1.5">
        <button className="btn btn-quiet btn-icon" title="Reducir" aria-label="Reducir" onClick={() => setZoom((z) => Math.max(0.2, z / 1.25))}>
          <ZoomOut size={16} />
        </button>
        <span className="t-tiny num w-11 text-center text-ink-2">{Math.round(scale * 100)}%</span>
        <button className="btn btn-quiet btn-icon" title="Ampliar" aria-label="Ampliar" onClick={() => setZoom((z) => Math.min(8, z * 1.25))}>
          <ZoomIn size={16} />
        </button>
        <button className="btn btn-quiet btn-icon" title="Ajustar a la vista" aria-label="Ajustar a la vista" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>
          <Maximize size={16} />
        </button>
        <button className="btn btn-quiet btn-icon" title="Rotar 90°" aria-label="Rotar 90 grados" onClick={() => setRot((r) => (r + 90) % 360)}>
          <RotateCw size={16} />
        </button>
        <span className="mx-1 h-5 w-px bg-rule" />
        <button
          className={`btn btn-quiet ${selectMode ? "bg-blue-wash text-blue" : ""}`}
          aria-pressed={selectMode}
          onClick={() => { setSelectMode((v) => !v); setSel(null); }}
          title="Seleccionar una región para preguntar o copiar su texto"
        >
          <SquareDashedMousePointer size={16} /> Región
        </button>
        <button className={`btn btn-quiet ${overlayText ? "bg-blue-wash text-blue" : ""}`} aria-pressed={overlayText} onClick={() => setOverlayText(!overlayText)} title="Mostrar el texto leído encima de la imagen">
          <Type size={16} /> Texto
        </button>
        <div className="relative">
          <button className="btn btn-quiet" aria-expanded={layersOpen} onClick={() => setLayersOpen((v) => !v)}>
            <Layers size={16} /> Capas
          </button>
          {layersOpen && (
            <div className="absolute left-0 top-9 z-20 w-48 rounded-lg border hairline bg-paper p-2 shadow-lg">
              {(Object.keys(LAYER_LABEL) as Layer[]).map((l) => (
                <label key={l} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 t-small hover:bg-paper-2">
                  <input type="checkbox" checked={layers[l]} onChange={() => toggleLayer(l)} />
                  <span className={`h-2.5 w-2.5 rounded-sm ${l === "text" ? "bg-blue" : l === "fields" ? "bg-green" : l === "codes" ? "bg-pink" : "bg-red"}`} />
                  {LAYER_LABEL[l]}
                </label>
              ))}
            </div>
          )}
        </div>
        {info && workAsset && info.display_asset_id !== workAsset.id && (
          <label className="ml-1 flex items-center gap-1.5 t-small text-ink-2">
            <input type="checkbox" checked={showOriginal} onChange={(e) => setShowOriginal(e.target.checked)} />
            Ver sin corregir
          </label>
        )}
        <div className="ml-auto flex items-center gap-1">
          {pages.length > 1 && (
            <>
              <button className="btn btn-quiet btn-icon" aria-label="Página anterior" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={16} />
              </button>
              <span className="t-small num text-ink-2">
                Página {page + 1} de {pages.length}
              </span>
              <button className="btn btn-quiet btn-icon" aria-label="Página siguiente" disabled={page >= pages.length - 1} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* desk */}
      <div
        ref={wrapRef}
        className={`relative min-h-0 flex-1 overflow-hidden ${selectMode ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"}`}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setTip(null)}
        data-testid="viewer"
      >
        {imgId ? (
          <div
            className="absolute left-1/2 top-1/2"
            style={{
              width,
              height,
              transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rot}deg)`,
              transformOrigin: "center center",
            }}
          >
            <img src={assetUrl(imgId)} width={width} height={height} alt="Imagen analizada" draggable={false} className="block select-none shadow-[0_1px_0_var(--rule),0_8px_30px_rgb(0_0_0/0.12)]" />
            {overlaysMatch && (
              <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="absolute inset-0" style={{ strokeWidth: 2 / scale }}>
                {layers.text &&
                  lines.map((l) => (
                    <g key={l.id}>
                      <rect
                        x={l.bbox[0]}
                        y={l.bbox[1]}
                        width={l.bbox[2] - l.bbox[0]}
                        height={l.bbox[3] - l.bbox[1]}
                        rx={3}
                        className={`ov-line ${hot.includes(l.id) ? "is-hot" : ""}`}
                        onPointerEnter={(e) => setTip({ line: l, x: e.clientX, y: e.clientY })}
                        onPointerLeave={() => setTip(null)}
                        onClick={() => { setHot([l.id]); setLedgerTab("texto"); }}
                      />
                      {overlayText && (
                        <text
                          x={l.bbox[0]}
                          y={l.bbox[3] - (l.bbox[3] - l.bbox[1]) * 0.2}
                          fontSize={(l.bbox[3] - l.bbox[1]) * 0.8}
                          fill="var(--overlay-text)"
                          style={{ paintOrder: "stroke", stroke: "rgb(255 255 255 / 0.85)", strokeWidth: (l.bbox[3] - l.bbox[1]) * 0.15, pointerEvents: "none" }}
                          className="raw"
                        >
                          {l.text}
                        </text>
                      )}
                    </g>
                  ))}
                {layers.fields &&
                  fieldBoxes
                    .filter((f) => !f.review)
                    .map((f) => (
                      <rect key={f.name} x={f.box[0] - 4} y={f.box[1] - 4} width={f.box[2] - f.box[0] + 8} height={f.box[3] - f.box[1] + 8} rx={5} className="ov-field" pointerEvents="none">
                        <title>{fieldLabel(f.name)}</title>
                      </rect>
                    ))}
                {layers.review &&
                  fieldBoxes
                    .filter((f) => f.review)
                    .map((f) => (
                      <rect key={f.name} x={f.box[0] - 5} y={f.box[1] - 5} width={f.box[2] - f.box[0] + 10} height={f.box[3] - f.box[1] + 10} rx={5} className="ov-review" pointerEvents="none" />
                    ))}
                {layers.codes &&
                  codes.map((c, i) => (
                    <rect key={i} x={c.bbox![0]} y={c.bbox![1]} width={c.bbox![2] - c.bbox![0]} height={c.bbox![3] - c.bbox![1]} rx={4} className="ov-code" pointerEvents="none" />
                  ))}
                {hotBox && hotBox.length === 4 && (
                  <rect x={hotBox[0] - 6} y={hotBox[1] - 6} width={hotBox[2] - hotBox[0] + 12} height={hotBox[3] - hotBox[1] + 12} rx={6} className="ov-hot" pointerEvents="none" />
                )}
                {sel && <rect x={sel[0]} y={sel[1]} width={sel[2] - sel[0]} height={sel[3] - sel[1]} className="ov-select" pointerEvents="none" />}
              </svg>
            )}
          </div>
        ) : (
          <div className="grid h-full place-items-center t-small text-ink-3">La imagen aparecerá cuando termine la lectura.</div>
        )}

        {tip && (
          <div className="pointer-events-none fixed z-30 max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-paper shadow-lg" style={{ left: tip.x + 14, top: tip.y + 14 }}>
            <div className="raw text-[0.8rem]">{tip.line.text}</div>
            <div className="t-tiny opacity-75">
              {tip.line.id}
              {tip.line.score ? ` · confianza del reconocedor ${tip.line.score.value.toFixed(2)} (no es probabilidad)` : " · texto del PDF"}
            </div>
          </div>
        )}

        {sel && !dragging && (
          <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-lg border hairline bg-paper p-1.5 shadow-lg">
            <button className="btn btn-ink" onClick={askRegion}>
              <MessageSquareText size={15} /> Preguntar sobre esta región
            </button>
            <button className="btn" disabled={!selectedText} onClick={() => navigator.clipboard?.writeText(selectedText)}>
              <Copy size={15} /> Copiar texto
            </button>
            <button className="btn btn-quiet" onClick={() => setSel(null)}>
              Cancelar
            </button>
          </div>
        )}

        {/* quality chips */}
        {quality?.metrics && (
          <div className="absolute left-3 top-3 flex max-w-[70%] flex-wrap gap-1.5">
            <QualityChip label="Nitidez" value={quality.metrics.blur_variance} bad={quality.flags?.includes("blurry")} />
            <QualityChip label="Brillo" value={quality.metrics.brightness} bad={quality.flags?.includes("too_dark") || quality.flags?.includes("overexposed")} />
            <QualityChip label="Contraste" value={quality.metrics.contrast} bad={quality.flags?.includes("low_contrast")} />
            <QualityChip label="Resolución" text={`${quality.metrics.width}×${quality.metrics.height}`} bad={quality.flags?.includes("low_resolution")} />
            {applied.map((s) => (
              <span key={s.name} className="rounded-full bg-paper/90 px-2 py-0.5 t-tiny text-blue" title="Corrección aplicada a una copia; el original se conserva">
                {STEPS[s.name] ?? s.name}
              </span>
            ))}
            {(quality.flags ?? []).length > 0 && (
              <span className="rounded-full bg-paper/90 px-2 py-0.5 t-tiny text-amber">{quality.flags!.map((f) => QUALITY_FLAGS[f] ?? f).join(", ")}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function QualityChip({ label, value, text, bad }: { label: string; value?: number; text?: string; bad?: boolean }) {
  return (
    <span className={`rounded-full bg-paper/90 px-2 py-0.5 t-tiny num ${bad ? "text-amber" : "text-ink-2"}`} title="Medición heurística (OpenCV), no es una probabilidad">
      {label} {text ?? (value !== undefined ? Math.round(value) : "—")}
    </span>
  );
}
