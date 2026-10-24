import { defineConfig } from "@playwright/test";
const port = process.env.AFTERSHOCKS_TEST_PORT || "8000";
export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    launchOptions: {
      executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
      args: ["--no-sandbox"],
    },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `cd .. && uv run uvicorn aftershocks.api:app --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: !process.env.CI,
  },
  reporter: "list",
});
