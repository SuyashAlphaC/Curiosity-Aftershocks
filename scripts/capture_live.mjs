import { chromium } from "../frontend/node_modules/playwright/index.mjs";
const base = process.env.AFTERSHOCKS_URL || "http://127.0.0.1:8000";
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || "/usr/bin/google-chrome",
  args: ["--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.goto(base);
await page
  .getByRole("navigation", { name: "Workspace views" })
  .getByRole("button", { name: "Live monitor" })
  .click();
await page
  .getByRole("heading", { name: "Discovery constellation" })
  .waitFor({ timeout: 180000 });
if (process.env.AFTERSHOCKS_EXPECT_HOUR) {
  await page.waitForFunction(
    (hour) =>
      document
        .querySelector(".live-metrics .watermark")
        ?.textContent?.includes(hour),
    process.env.AFTERSHOCKS_EXPECT_HOUR,
    { timeout: 180000 },
  );
}
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: "docs/live-monitor.png", fullPage: true });
await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: "docs/live-monitor-mobile.png", fullPage: true });
const dimensions = await page.evaluate(() => ({
  viewport: innerWidth,
  page: document.documentElement.scrollWidth,
}));
console.log(JSON.stringify({ errors, dimensions }, null, 2));
await browser.close();
if (errors.length || dimensions.page > dimensions.viewport) process.exit(1);
