// Screenshots of the REAL interface for the explainer (run in the Playwright e2e image).
import { chromium } from "@playwright/test";

const BASE = "http://127.0.0.1:8080";
const OUT = "/out";
const OBS = process.env.OBS_ID;
const CHAT_OBS = process.env.CHAT_OBS_ID;
const VIDEO_OBS = process.env.VIDEO_OBS_ID;

const browser = await chromium.launch({
  args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--use-file-for-fake-video-capture=/samples/camera_sequence.y4m"],
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
const page = await ctx.newPage();
const shot = async (name) => { await page.waitForTimeout(900); await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 88 }); console.log("saved", name); };

await page.goto(BASE + "/");
await page.getByLabel("Clave de acceso").fill(process.env.VIE_ACCESS_KEY);
await page.getByRole("button", { name: "Entrar" }).click();
await page.getByRole("navigation", { name: "Secciones" }).waitFor();
await page.getByRole("button", { name: "Ocultar consola" }).click().catch(() => {});
await shot("ui-mesa");

await page.goto(`${BASE}/o/${OBS}`);
await page.locator("rect.ov-line").first().waitFor();
await page.getByRole("tab", { name: "Campos" }).click();
await page.getByText("RUC del emisor").first().hover();
await shot("ui-campos");
await page.getByRole("tab", { name: "Validación" }).click();
await page.mouse.move(10, 10);
await shot("ui-validacion");

await page.goto(`${BASE}/o/${CHAT_OBS}`);
await page.getByRole("tab", { name: "Preguntar" }).click();
await page.getByText("Observado").first().waitFor({ timeout: 15000 }).catch(() => {});
await shot("ui-chat");

await page.goto(`${BASE}/o/${VIDEO_OBS}`);
await page.getByText("Escena 1").first().waitFor();
await shot("ui-video");

await page.goto(`${BASE}/explorador`);
await page.getByText(/resultado\(s\)/).waitFor();
await shot("ui-explorar");

await page.goto(`${BASE}/camara`);
await page.getByTestId("camera-start").click();
await page.getByTestId("camera-stats").waitFor({ timeout: 30000 });
await page.waitForTimeout(9000);
await shot("ui-camara");
await page.getByRole("button", { name: "Detener" }).click();
await browser.close();
