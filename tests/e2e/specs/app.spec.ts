import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const KEY = process.env.VIE_ACCESS_KEY ?? "";
const truth = JSON.parse(readFileSync("/samples/factura_ok.json", "utf-8"));

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Clave de acceso").fill(KEY);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("navigation", { name: "Secciones" })).toBeVisible();
}

test("rechaza una clave incorrecta", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Clave de acceso").fill("clave-equivocada");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toContainText("incorrecta");
});

test("carga una factura, muestra regiones, campos verificados y permite editar", async ({ page }) => {
  await login(page);
  await page.getByTestId("file-input").setInputFiles("/samples/factura_ok.png");
  await page.waitForURL(/\/o\/[0-9a-f-]{36}/);
  // OCR stage finishes in seconds; the model stage continues in the background
  await expect(page.getByText(/Texto listo|Interpretando|Completado|Con advertencias|Verificado/).first()).toBeVisible({ timeout: 60_000 });
  await expect.poll(async () => page.locator("rect.ov-line").count(), { timeout: 60_000 }).toBeGreaterThan(20);
  await expect(page.locator("rect.ov-code")).toHaveCount(1);

  await page.getByRole("tab", { name: "Campos" }).click();
  await expect(page.getByText(truth.issuer_ruc).first()).toBeVisible();
  await expect(page.getByText(truth.serie_numero).first()).toBeVisible();

  // human correction of a field
  await page.getByRole("button", { name: "Editar Forma de pago" }).click();
  await page.getByLabel("Nuevo valor de Forma de pago").fill("CONTADO");
  await page.getByRole("button", { name: "Guardar cambio" }).click();
  await expect(page.getByText("CONTADO").first()).toBeVisible();

  await page.getByRole("tab", { name: "Validación" }).click();
  await expect(page.getByText(/Total verificado/)).toBeVisible();
});

test("explora el historial y exporta CSV", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Explorar" }).click();
  await expect(page.getByText(/resultado\(s\)/)).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "CSV", exact: true }).click()]);
  const path = await download.path();
  const csv = readFileSync(path!, "utf-8");
  expect(csv).toContain("issuer_ruc");
  expect(csv).toContain(truth.issuer_ruc);
});

test("cámara autorizada: registra escenas nuevas y no repite las idénticas", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "Cámara" }).click();
  await page.getByTestId("camera-start").click();
  await expect(page.getByTestId("camera-video")).toBeVisible();
  const stats = page.getByTestId("camera-stats");
  await expect(stats).toBeVisible({ timeout: 30_000 });
  // the synthetic stream shows an empty desk, a factura, the same factura moved and a boleta (12 s loop)
  await expect.poll(async () => Number(/(\d+) nuevas/.exec((await stats.textContent()) ?? "")?.[1] ?? 0), { timeout: 120_000 }).toBeGreaterThanOrEqual(1);
  await expect.poll(async () => Number(/(\d+) repetidas/.exec((await stats.textContent()) ?? "")?.[1] ?? 0), { timeout: 120_000 }).toBeGreaterThanOrEqual(1);
  // a different document with the same layout (the boleta) must become its own NEW observation
  const started = Date.now() - 5_000;
  await expect
    .poll(
      async () => {
        const r = await page.request.get("/api/v1/observations?source=camera&page_size=30");
        const items = ((await r.json()).items ?? []) as { document_type: string | null; kind: string; created_at: string }[];
        const recent = items.filter((o) => Date.parse(o.created_at) >= started);
        return recent.some((o) => o.document_type === "boleta" && o.kind === "new") && recent.some((o) => o.document_type === "factura");
      },
      { timeout: 180_000, intervals: [3_000] },
    )
    .toBe(true);
  // the ledger shows the camera observation
  await expect(page.getByRole("tab", { name: "Campos" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Detener" }).click();
});
