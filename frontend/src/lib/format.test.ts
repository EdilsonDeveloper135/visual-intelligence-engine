import { describe, expect, it } from "vitest";
import { meanDiff } from "../features/workspace/CameraPane";
import { boxesIntersect, formatMoney, formatValue, normalizeRect, parseInline } from "./format";

describe("format", () => {
  it("formats Peruvian money with the right symbol", () => {
    expect(formatMoney("128.62", "PEN")).toBe("S/ 128.62");
    expect(formatMoney("1234.5", "USD")).toMatch(/^US\$ 1.?234\.50$/);
    expect(formatMoney(null)).toBe("—");
  });
  it("formats typed values", () => {
    expect(formatValue("percent", "18")).toBe("18%");
    expect(formatValue("string", null)).toBe("—");
  });
  it("normalizes selection rectangles and intersects boxes", () => {
    expect(normalizeRect(10, 20, 5, 2)).toEqual([5, 2, 10, 20]);
    expect(boxesIntersect([0, 0, 10, 10], [5, 5, 20, 20])).toBe(true);
    expect(boxesIntersect([0, 0, 10, 10], [11, 11, 20, 20])).toBe(false);
  });
  it("renders citations and bold safely (no HTML)", () => {
    const segs = parseInline("El total es **S/ 128.62** [r_0040] <script>x</script>");
    expect(segs.map((s) => s.kind)).toEqual(["text", "bold", "text", "cite", "text"]);
    expect(segs[3].value).toBe("r_0040");
    expect(segs[4].value).toContain("<script>"); // rendered as text by React, never as HTML
  });
});

describe("camera prefilter", () => {
  it("measures the mean luminance difference of two thumbnails", () => {
    const a = new Uint8ClampedArray(1024).fill(100);
    const b = new Uint8ClampedArray(1024).fill(110);
    expect(meanDiff(a, a)).toBe(0);
    expect(meanDiff(a, b)).toBe(10);
  });
});
