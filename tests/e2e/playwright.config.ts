import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 240_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "/results/e2e-results.json" }]],
  outputDir: "/results/artifacts",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8080",
    trace: "off",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        `--use-file-for-fake-video-capture=${process.env.FAKE_CAMERA ?? "/samples/camera_sequence.y4m"}`,
      ],
    },
  },
});
