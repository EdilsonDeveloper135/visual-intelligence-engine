import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, api } from "../../lib/api";
import { formatMs, parseInline } from "../../lib/format";
import type { ChatMessage, ObservationDetail } from "../../lib/types";
import { useUi } from "../../store/ui";

const SUGGESTIONS = ["¿Qué tipo de documento es y quién lo emite?", "¿Cuál es el total y cómo se compone?", "¿Hay algo ilegible o sospechoso?"];

function Answer({ text, detail }: { text: string; detail: ObservationDetail }) {
  const setHot = useUi((s) => s.setHot);
  const setHotBox = useUi((s) => s.setHotBox);
  const byId = new Map((detail.result.text?.lines ?? []).map((l) => [l.id, l]));
  return (
    <>
      {text.split(/\n+/).map((para, i) => (
        <p key={i} className={para.trim().startsWith("- ") || para.trim().startsWith("* ") ? "pl-3" : ""}>
          {parseInline(para.replace(/^\s*[-*]\s+/, "• ")).map((seg, j) =>
            seg.kind === "bold" ? (
              <strong key={j}>{seg.value}</strong>
            ) : seg.kind === "cite" ? (
              <button
                key={j}
                className="raw mx-0.5 rounded bg-blue-wash px-1 text-blue"
                onMouseEnter={() => {
                  setHot([seg.value]);
                  setHotBox(byId.get(seg.value)?.bbox ?? null);
                }}
                onMouseLeave={() => {
                  setHot([]);
                  setHotBox(null);
                }}
                title={byId.get(seg.value)?.text ?? "Región no encontrada"}
              >
                {seg.value}
              </button>
            ) : (
              <span key={j}>{seg.value}</span>
            ),
          )}
        </p>
      ))}
    </>
  );
}

export default function ChatPanel({ detail }: { detail: ObservationDetail }) {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const region = useUi((s) => s.region);
  const setRegion = useUi((s) => s.setRegion);
  const deltas = useUi((s) => s.chatDeltas);
  const endRef = useRef<HTMLDivElement>(null);

  const history = useQuery({
    queryKey: ["chat", detail.id],
    queryFn: () => api<ChatMessage[]>(`/observations/${detail.id}/chat`),
    refetchInterval: (query) => ((query.state.data ?? []).some((m) => m.status === "queued" || m.status === "streaming") ? 3000 : false),
  });

  const ask = useMutation({
    mutationFn: (question: string) =>
      api<{ message_id: string }>(`/observations/${detail.id}/chat`, { method: "POST", json: { question, region } }),
    onSuccess: () => {
      setQ("");
      setRegion(null);
      qc.invalidateQueries({ queryKey: ["chat", detail.id] });
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [history.data, deltas]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (q.trim()) ask.mutate(q.trim());
  };
  const busy = ["queued", "processing"].includes(detail.status);
  const messages = history.data ?? [];

  return (
    <div className="flex h-full min-h-[420px] flex-col">
      <div className="flex-1 space-y-3 px-4 py-3">
        {messages.length === 0 && (
          <div className="t-small text-ink-2">
            <p className="mb-2">Pregunte sobre esta imagen. Las respuestas citan las regiones del texto, por ejemplo <span className="raw text-blue">r_0012</span>; pase el cursor sobre la cita para verla en la imagen.</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn" onClick={() => setQ(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => {
          const streaming = deltas[m.id];
          const content = m.status === "done" || m.status === "error" ? m.content : (streaming ?? "");
          return (
            <div key={m.id} className={m.role === "user" ? "ml-8 rounded-lg bg-paper-2 px-3 py-2" : "mr-2"}>
              {m.role === "user" ? (
                <>
                  <p>{m.content}</p>
                  {m.region && <p className="t-tiny text-ink-3">Sobre una región seleccionada</p>}
                </>
              ) : (
                <div className="space-y-1.5 t-small leading-relaxed">
                  {content ? <Answer text={content} detail={detail} /> : <p className="text-ink-3">{m.status === "queued" ? "En cola; el modelo atiende una pregunta a la vez…" : "Escribiendo…"}</p>}
                  {m.status === "error" && <p className="text-red">No se obtuvo respuesta.</p>}
                  {m.status === "done" && <p className="t-tiny text-ink-3">{m.model} · {formatMs(m.duration_ms)}</p>}
                </div>
              )}
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      <form onSubmit={submit} className="sticky bottom-0 border-t hairline bg-paper px-3 py-2">
        {region && (
          <div className="mb-1.5 flex items-center gap-2 t-tiny text-blue">
            Pregunta limitada a la región seleccionada
            <button type="button" className="btn btn-quiet btn-icon h-6 w-6" onClick={() => setRegion(null)} aria-label="Quitar región">
              <X size={12} />
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <input
            className="field-input flex-1"
            placeholder={busy ? "Espere a que termine la lectura…" : "Escriba una pregunta sobre la imagen"}
            value={q}
            maxLength={1000}
            disabled={busy}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Pregunta"
          />
          <button className="btn btn-ink" disabled={!q.trim() || ask.isPending || busy}>
            <Send size={14} /> Preguntar
          </button>
        </div>
        {ask.error && <p className="mt-1 t-tiny text-red">{ask.error instanceof ApiError ? ask.error.message : "No se pudo enviar la pregunta."}</p>}
      </form>
    </div>
  );
}
