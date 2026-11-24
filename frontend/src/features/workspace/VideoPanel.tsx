import { useQuery } from "@tanstack/react-query";
import { Film } from "lucide-react";
import { Link } from "react-router";
import { api, assetUrl, qs } from "../../lib/api";
import { STATUS, VALIDATION, docTypeLabel } from "../../lib/labels";
import type { ObservationDetail, ObservationSummary } from "../../lib/types";

interface VideoInfo {
  duration_s: number;
  fps: number;
  frames_total: number;
  sampled: number;
  scenes_detected: number;
  keyframes: { observation_id: string; scene: number; t_s: number; blur_variance: number; scene_frames: number }[];
}

/** A video is shown as its distinct scenes; each scene is an observation of its own. */
export default function VideoPanel({ detail }: { detail: ObservationDetail }) {
  const video = (detail.result as unknown as { video?: VideoInfo }).video;
  const children = useQuery({
    queryKey: ["observations", "children", detail.id],
    queryFn: () => api<{ items: ObservationSummary[] }>(`/observations${qs({ parent_id: detail.id, page_size: 50 })}`),
    refetchInterval: (q) => ((q.state.data?.items ?? []).some((o) => ["queued", "processing", "interpreting"].includes(o.status)) ? 3000 : false),
  });
  const byId = new Map((children.data?.items ?? []).map((o) => [o.id, o]));

  if (!video) {
    return <div className="grid flex-1 place-items-center text-ink-3">{STATUS[detail.status] ?? detail.status}: extrayendo escenas del video…</div>;
  }
  return (
    <div className="scroll-thin flex-1 overflow-y-auto px-6 py-6">
      <div className="mb-4 flex items-center gap-3">
        <Film size={22} className="text-blue" />
        <div>
          <h1 className="t-head">{detail.original_filename ?? "Video"}</h1>
          <p className="t-small text-ink-2 num">
            {video.duration_s.toFixed(1)} s · {video.fps} fps · {video.sampled} fotogramas muestreados · {video.scenes_detected} cambios de escena · {video.keyframes.length} escena(s) analizadas
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {video.keyframes.map((k) => {
          const o = byId.get(k.observation_id);
          return (
            <Link key={k.observation_id} to={`/o/${k.observation_id}`} className="rounded-md bg-paper p-2 hover:outline hover:outline-1 hover:outline-rule">
              <div className="mb-2 h-40 overflow-hidden rounded-sm bg-desk">
                {o?.thumbnail_asset_id && <img src={assetUrl(o.thumbnail_asset_id)} alt="" className="h-full w-full object-cover object-top" />}
              </div>
              <div className="t-small font-semibold">
                Escena {k.scene} · <span className="num">{k.t_s.toFixed(1)} s</span>
              </div>
              <div className="t-tiny text-ink-3">
                {o ? `${o.title ?? docTypeLabel(o.document_type)} · ${o.validation_status ? VALIDATION[o.validation_status] : STATUS[o.status]}` : "En cola"}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
