import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useUi } from "../store/ui";
import type { VieEvent } from "./types";

const REFRESH_TYPES = new Set([
  "observation.queued",
  "observation.processing",
  "observation.ocr_ready",
  "observation.interpreting",
  "observation.completed",
  "observation.partial",
  "observation.failed",
  "observation.edited",
  "observation.deleted",
  "camera.observation",
]);

/** One SSE connection for the whole app; same-origin cookie authentication. */
export function useEventStream(enabled: boolean) {
  const qc = useQueryClient();
  const pushEvent = useUi((s) => s.pushEvent);
  const appendDelta = useUi((s) => s.appendDelta);

  useEffect(() => {
    if (!enabled) return;
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      es = new EventSource("/api/v1/events/stream");
      es.onmessage = (msg) => {
        let ev: VieEvent;
        try {
          ev = JSON.parse(msg.data);
        } catch {
          return;
        }
        if (ev.type === "chat.delta") {
          const d = ev.data as { message_id: string; delta: string };
          appendDelta(d.message_id, d.delta);
          return;
        }
        pushEvent(ev);
        if (ev.backlog) return;
        if (ev.observation_id && REFRESH_TYPES.has(ev.type)) {
          qc.invalidateQueries({ queryKey: ["observation", ev.observation_id] });
          qc.invalidateQueries({ queryKey: ["observations"] });
        }
        if ((ev.type === "chat.done" || ev.type === "chat.error") && ev.observation_id) {
          qc.invalidateQueries({ queryKey: ["chat", ev.observation_id] });
        }
      };
      es.onerror = () => {
        es?.close();
        if (!closed) retry = setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      es?.close();
    };
  }, [enabled, qc, pushEvent, appendDelta]);
}
