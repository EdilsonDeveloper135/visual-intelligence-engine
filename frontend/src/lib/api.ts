/** Same-origin API client. Authentication uses an HttpOnly session cookie. */

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const BASE = "/api/v1";

async function handle<T>(res: Response): Promise<T> {
  if (res.ok) {
    const ct = res.headers.get("content-type") ?? "";
    return (ct.includes("application/json") ? res.json() : (res.blob() as unknown)) as Promise<T>;
  }
  let body: { code?: string; message?: string; details?: unknown } = {};
  try {
    body = await res.json();
  } catch {
    /* non-JSON error */
  }
  if (res.status === 401) window.dispatchEvent(new CustomEvent("vie:unauthorized"));
  throw new ApiError(res.status, body.code ?? "http_error", body.message ?? `Error ${res.status}`, body.details);
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(BASE + path, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  return handle<T>(res);
}

export async function download(path: string, payload: unknown, fallbackName: string): Promise<void> {
  const res = await fetch(BASE + path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await handle(res);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export const assetUrl = (id: string | null | undefined, download = false) =>
  id ? `${BASE}/assets/${id}${download ? "?download=true" : ""}` : undefined;

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}
