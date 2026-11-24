import { useQuery } from "@tanstack/react-query";
import { FilePlus2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError, api } from "../../lib/api";
import type { ObservationDetail } from "../../lib/types";
import CameraPane from "./CameraPane";
import Console from "./Console";
import DocumentViewer from "./DocumentViewer";
import Ledger from "./Ledger";
import UploadPane from "./UploadPane";

export function useObservation(id: string | undefined) {
  return useQuery({
    queryKey: ["observation", id],
    queryFn: () => api<ObservationDetail>(`/observations/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ["queued", "processing", "interpreting"].includes(q.state.data.status) ? 4000 : false),
  });
}

export default function WorkspacePage({ cameraMode = false }: { cameraMode?: boolean }) {
  const { id } = useParams();
  const [cameraObs, setCameraObs] = useState<string | undefined>();
  const obsId = cameraMode ? cameraObs : id;
  const q = useObservation(obsId);
  const detail = q.data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <section className="flex min-h-[55vh] min-w-0 flex-1 flex-col lg:min-h-0" aria-label="Imagen">
          {cameraMode ? (
            <CameraPane onObservation={setCameraObs} />
          ) : !id ? (
            <UploadPane />
          ) : q.isError ? (
            <div className="grid flex-1 place-items-center px-6 text-center">
              <div>
                <p className="mb-3 text-ink-2">{q.error instanceof ApiError && q.error.status === 404 ? "Esta observación no existe o está en la papelera." : "No se pudo cargar la observación."}</p>
                <Link to="/" className="btn">
                  Volver a la mesa
                </Link>
              </div>
            </div>
          ) : detail ? (
            <>
              <DocumentViewer detail={detail} />
              <div className="flex items-center justify-end border-t hairline bg-paper px-3 py-1">
                <Link to="/" className="btn btn-quiet">
                  <FilePlus2 size={15} /> Nuevo documento
                </Link>
              </div>
            </>
          ) : (
            <div className="grid flex-1 place-items-center text-ink-3">Cargando…</div>
          )}
        </section>
        <aside className="panel flex min-h-[50vh] w-full flex-none flex-col border-t hairline lg:min-h-0 lg:w-[460px] lg:border-l lg:border-t-0" aria-label="Interpretación">
          {detail ? (
            <Ledger detail={detail} />
          ) : (
            <div className="px-6 py-10 text-ink-2">
              <h2 className="t-head mb-2 text-ink">Interpretación</h2>
              <p className="max-w-[40ch]">
                {cameraMode
                  ? "Cuando la cámara registre una escena nueva, aquí verá el texto leído, los datos extraídos y su verificación."
                  : "Cargue un documento para ver el tipo, los campos extraídos con su evidencia y las verificaciones independientes."}
              </p>
            </div>
          )}
        </aside>
      </div>
      <Console detail={detail} />
    </div>
  );
}
