import { useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError, api } from "../../lib/api";

export default function LoginPage() {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", json: { access_key: key } });
      await qc.invalidateQueries({ queryKey: ["session"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo conectar con el servicio local.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid h-full place-items-center px-4">
      <form onSubmit={submit} className="panel w-full max-w-[380px] rounded-xl border hairline p-7">
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-ink text-paper">
            <KeyRound size={18} />
          </div>
          <div>
            <h1 className="t-head">Mesa de verificación</h1>
            <p className="t-small text-ink-2">Visual Intelligence Engine · uso local</p>
          </div>
        </div>
        <label htmlFor="key" className="t-small mb-1 block font-semibold">
          Clave de acceso
        </label>
        <input
          id="key"
          type="password"
          autoComplete="current-password"
          className="field-input w-full"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          autoFocus
        />
        <p className="t-tiny mt-2 text-ink-3">
          La clave está en el archivo <span className="raw">.env</span> del proyecto (VIE_ACCESS_KEY). La instalación la muestra al terminar.
        </p>
        {error && (
          <p role="alert" className="t-small mt-3 text-red">
            {error}
          </p>
        )}
        <button className="btn btn-ink mt-5 w-full justify-center" disabled={!key || busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
