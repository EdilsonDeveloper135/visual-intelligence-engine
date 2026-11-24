import { Camera, CameraOff, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

type FrameMsg = {
  type: "frame";
  action: string;
  reason: string;
  distance: number | null;
  has_document: boolean;
  stats: Record<string, number>;
  assessment: { blur_variance: number; brightness: number; document_area_ratio: number };
};
type Msg =
  | FrameMsg
  | { type: "session"; id: string; settings: { interval_ms: number; min_vlm_interval_s: number; auto_vlm: boolean } }
  | { type: "observation"; id: string; kind: string; mode: string }
  | { type: "document_detected" }
  | { type: "analyze_queued"; id: string }
  | { type: "event"; event: { type: string; message: string; observation_id: string } }
  | { type: "stats"; stats: Record<string, number> }
  | { type: "error"; message: string };

const ACTION_LABEL: Record<string, string> = {
  new: "Escena nueva: analizando",
  updated: "Escena actualizada: analizando",
  repeated: "Sin cambios: no se repite el análisis",
  stabilizing: "Esperando que la imagen se estabilice",
  ignored: "Imagen demasiado oscura o movida",
  throttled: "Esperando el intervalo mínimo",
  busy: "Análisis anterior en curso",
  skipped_local: "Sin cambios (filtrado en el navegador)",
};

/** Small luminance thumbnail used to skip near-identical frames before sending them. */
function signature(video: HTMLVideoElement, canvas: HTMLCanvasElement): Uint8ClampedArray | null {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  canvas.width = 32;
  canvas.height = 32;
  ctx.drawImage(video, 0, 0, 32, 32);
  const data = ctx.getImageData(0, 0, 32, 32).data;
  const out = new Uint8ClampedArray(32 * 32);
  for (let i = 0; i < out.length; i++) out[i] = (data[i * 4] * 0.299 + data[i * 4 + 1] * 0.587 + data[i * 4 + 2] * 0.114) | 0;
  return out;
}

export function meanDiff(a: Uint8ClampedArray, b: Uint8ClampedArray): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
  return s / a.length;
}

export default function CameraPane({ onObservation }: { onObservation: (id: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(document.createElement("canvas"));
  const sigRef = useRef<HTMLCanvasElement>(document.createElement("canvas"));
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inFlight = useRef(false);
  const lastSig = useRef<Uint8ClampedArray | null>(null);
  const lastAction = useRef<string>("stabilizing");
  const lastSentAt = useRef(0);
  const [skipped, setSkipped] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [resolution, setResolution] = useState("1280x720");
  const [intervalMs, setIntervalMs] = useState(1500);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string>("La cámara está apagada.");
  const [last, setLast] = useState<FrameMsg | null>(null);
  const [log, setLog] = useState<{ t: string; text: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const addLog = (text: string) => setLog((l) => [{ t: new Date().toLocaleTimeString("es-PE"), text }, ...l].slice(0, 40));

  const stop = useCallback(() => {
    clearInterval(timer.current);
    wsRef.current?.close();
    wsRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    inFlight.current = false;
    lastSig.current = null;
    lastAction.current = "stabilizing";
    setRunning(false);
    setStatus("La cámara está apagada.");
  }, []);

  useEffect(() => stop, [stop]);

  const tick = () => {
    const video = videoRef.current;
    const ws = wsRef.current;
    if (!video || !ws || ws.readyState !== WebSocket.OPEN || video.readyState < 2) return;
    if (inFlight.current) return; // one frame in flight (backpressure)
    const sig = signature(video, sigRef.current);
    // Skip near-identical frames locally ONLY when the server already holds this scene;
    // while it is stabilising / throttled / busy it needs follow-up frames. Send one every 10 s anyway.
    const serverSettled = ["repeated", "ignored"].includes(lastAction.current);
    if (sig && lastSig.current && serverSettled && meanDiff(sig, lastSig.current) < 0.6 && Date.now() - lastSentAt.current < 10_000) {
      setSkipped((n) => n + 1);
      setStatus(ACTION_LABEL.skipped_local);
      return;
    }
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    inFlight.current = true;
    canvas.toBlob(
      (blob) => {
        if (!blob || ws.readyState !== WebSocket.OPEN) {
          inFlight.current = false;
          return;
        }
        blob.arrayBuffer().then((buf) => {
          ws.send(buf);
          lastSentAt.current = Date.now();
          if (sig) lastSig.current = sig;
        });
      },
      "image/jpeg",
      0.85,
    );
  };

  const start = async () => {
    setError(null);
    const [w, h] = resolution.split("x").map(Number);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: deviceId ? { exact: deviceId } : undefined, width: { ideal: w }, height: { ideal: h } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      const list = await navigator.mediaDevices.enumerateDevices();
      setDevices(list.filter((d) => d.kind === "videoinput"));
    } catch (e) {
      const name = (e as DOMException)?.name;
      setError(
        name === "NotAllowedError"
          ? "Permiso de cámara denegado. Permita la cámara para este sitio en el navegador (y en macOS: Ajustes del Sistema → Privacidad → Cámara)."
          : name === "NotFoundError"
            ? "No se encontró ninguna cámara."
            : "No se pudo abrir la cámara.",
      );
      return;
    }
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/v1/camera/ws`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    ws.onopen = () => {
      setRunning(true);
      setStatus("Observando…");
      addLog("Sesión de cámara iniciada");
      timer.current = setInterval(tick, intervalMs);
    };
    ws.onclose = (ev) => {
      if (ev.code === 4401) setError("La sesión expiró; vuelva a iniciar sesión.");
      if (streamRef.current) stop();
    };
    ws.onmessage = (ev) => {
      let msg: Msg;
      try {
        msg = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      if (msg.type === "frame") {
        inFlight.current = false;
        lastAction.current = msg.action;
        setLast(msg);
        setStatus(ACTION_LABEL[msg.action] ?? msg.reason);
      } else if (msg.type === "stats") {
        const stats = msg.stats;
        setLast((l) => (l ? { ...l, stats } : l));
      } else if (msg.type === "session") {
        setSessionId(msg.id);
      } else if (msg.type === "observation") {
        addLog(msg.kind === "new" ? "Observación nueva registrada" : "Observación actualizada registrada");
        onObservation(msg.id);
      } else if (msg.type === "document_detected") {
        addLog("Documento detectado en la escena");
      } else if (msg.type === "analyze_queued") {
        addLog("Interpretación con el modelo en cola");
      } else if (msg.type === "event") {
        if (msg.event.message) addLog(msg.event.message);
      } else if (msg.type === "error") {
        inFlight.current = false;
        addLog(msg.message);
      }
    };
  };

  useEffect(() => {
    if (!running) return;
    clearInterval(timer.current);
    timer.current = setInterval(tick, intervalMs);
    return () => clearInterval(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, running]);

  const stats = last?.stats;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b hairline bg-paper px-3 py-1.5">
        {!running ? (
          <button className="btn btn-ink" onClick={start} data-testid="camera-start">
            <Camera size={15} /> Activar cámara
          </button>
        ) : (
          <button className="btn" onClick={stop}>
            <CameraOff size={15} /> Detener
          </button>
        )}
        <select className="field-input" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} disabled={running} aria-label="Cámara">
          <option value="">Cámara predeterminada</option>
          {devices.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Cámara ${i + 1}`}
            </option>
          ))}
        </select>
        <select className="field-input" value={resolution} onChange={(e) => setResolution(e.target.value)} disabled={running} aria-label="Resolución">
          <option value="1280x720">1280 × 720</option>
          <option value="1920x1080">1920 × 1080</option>
          <option value="640x480">640 × 480</option>
        </select>
        <label className="flex items-center gap-1.5 t-small text-ink-2">
          Cada
          <select className="field-input" value={intervalMs} onChange={(e) => setIntervalMs(Number(e.target.value))} aria-label="Intervalo de captura">
            {[500, 1000, 1500, 3000, 5000].map((v) => (
              <option key={v} value={v}>
                {v / 1000} s
              </option>
            ))}
          </select>
        </label>
        <button className="btn ml-auto" disabled={!running} onClick={() => wsRef.current?.send(JSON.stringify({ type: "analyze_now" }))} title="Envía la última observación al modelo multimodal">
          <Sparkles size={15} /> Interpretar con el modelo
        </button>
      </div>
      <div className="relative grid min-h-0 flex-1 place-items-center overflow-hidden bg-desk p-4">
        <video ref={videoRef} muted playsInline className={`max-h-full max-w-full rounded-sm bg-black ${running ? "" : "hidden"}`} data-testid="camera-video" />
        {!running && (
          <div className="max-w-[46ch] text-center">
            <Camera size={30} className="mx-auto mb-3 text-blue" />
            <h1 className="t-title mb-2">Observación continua</h1>
            <p className="text-ink-2">
              La cámara solo se enciende cuando usted lo autoriza. Se analizan las escenas nuevas o con cambios; las repetidas no se vuelven a procesar. El modelo multimodal se usa a demanda para no saturar el equipo.
            </p>
            {error && <p role="alert" className="mt-3 t-small text-red">{error}</p>}
          </div>
        )}
        {running && (
          <div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-center gap-3 rounded-lg bg-paper/95 px-3 py-2 t-small shadow">
            <span className={`h-2.5 w-2.5 rounded-full ${last?.has_document ? "bg-green" : "bg-ink-3"}`} />
            <span className="font-semibold">{status}</span>
            {last && (
              <span className="num t-tiny text-ink-3">
                nitidez {Math.round(last.assessment.blur_variance)} · brillo {Math.round(last.assessment.brightness)}
                {last.distance !== null ? ` · cambio ${last.distance}/64` : ""}
              </span>
            )}
            {stats && (
              <span className="num t-tiny ml-auto text-ink-2" data-testid="camera-stats">
                {stats.frames} analizados · {stats.new ?? 0} nuevas · {stats.updated ?? 0} actualizadas · {stats.repeated ?? 0} repetidas · {skipped} filtrados en el navegador
              </span>
            )}
          </div>
        )}
      </div>
      {log.length > 0 && (
        <ol className="scroll-thin max-h-24 overflow-y-auto border-t hairline bg-paper px-3 py-1 t-tiny text-ink-2" aria-label="Actividad de la cámara">
          {sessionId && <li className="text-ink-3">Sesión {sessionId.slice(0, 8)}</li>}
          {log.map((l, i) => (
            <li key={i}>
              <span className="num mr-2 text-ink-3">{l.t}</span>
              {l.text}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
