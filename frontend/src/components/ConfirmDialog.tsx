import { useEffect, useRef, useState } from "react";

/** Irreversible-operation confirmation: the user must type the confirmation word. */
export default function ConfirmDialog({
  open,
  title,
  body,
  word = "ELIMINAR",
  action,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: string;
  word?: string;
  action: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      setTyped("");
      d.showModal();
    } else if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog ref={ref} onClose={onClose} className="m-auto w-[min(440px,92vw)] rounded-xl border hairline bg-paper p-6 text-ink backdrop:bg-black/40">
      <h2 className="t-head mb-2">{title}</h2>
      <p className="mb-4 t-small text-ink-2">{body}</p>
      <label className="t-small mb-1 block">
        Escriba <span className="font-bold">{word}</span> para confirmar
      </label>
      <input className="field-input w-full" value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus aria-label="Palabra de confirmación" />
      <div className="mt-5 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn-danger"
          disabled={typed !== word || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } finally {
              setBusy(false);
            }
          }}
        >
          {action}
        </button>
      </div>
    </dialog>
  );
}
