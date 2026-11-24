export function formatMoney(value: string | number | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  const symbol = currency === "USD" ? "US$" : currency === "EUR" ? "€" : "S/";
  return `${symbol} ${n.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-PE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-PE", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function formatBytes(b: number | null | undefined): string {
  if (!b && b !== 0) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = b;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function formatValue(type: string, value: unknown, currency?: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  if (type === "money") return formatMoney(value as string, currency);
  if (type === "date") return formatDate(String(value));
  if (type === "percent") return `${value}%`;
  return String(value);
}

/** Map a box in image coordinates to a rotated frame (used for rotation of the viewer). */
export function boxCenter(b: number[]): [number, number] {
  return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];
}

export function boxesIntersect(a: number[], b: number[]): boolean {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
}

export function normalizeRect(x0: number, y0: number, x1: number, y1: number): [number, number, number, number] {
  return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
}

/** Very small, safe renderer for model answers: no HTML, only paragraphs, bullets, **bold** and [r_0001] citations. */
export type Segment = { kind: "text" | "bold" | "cite"; value: string };
export function parseInline(text: string): Segment[] {
  const out: Segment[] = [];
  const re = /\*\*([^*]+)\*\*|\[(r_\d{4})\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ kind: "text", value: text.slice(last, m.index) });
    if (m[1]) out.push({ kind: "bold", value: m[1] });
    else if (m[2]) out.push({ kind: "cite", value: m[2] });
    last = re.lastIndex;
  }
  if (last < text.length) out.push({ kind: "text", value: text.slice(last) });
  return out;
}
