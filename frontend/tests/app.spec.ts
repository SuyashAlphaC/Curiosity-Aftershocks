import { test, expect } from "@playwright/test";

test("real studies, inspection, replay, filtering, export and research views", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "When the sun disappeared" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect Solar eclipse", exact: true })
    .click();
  await expect(page.locator(".inspector h3")).toHaveText("Solar eclipse");
  await page.getByLabel("Replay day").fill("5");
  await expect(page.locator(".replay-date")).toContainText("Day +5");
  await page.getByRole("button", { name: "Play replay", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Pause replay", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause replay", exact: true }).click();
  await page.getByRole("button", { name: "Reset to event day" }).click();
  await expect(page.locator(".replay-date")).toContainText("Event day");
  await page.getByLabel("Find a topic").fill("zzzznoresults");
  await expect(
    page.getByText("No topics match", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Clear search", exact: true })
    .first()
    .click();
  await page.getByLabel("Show controls").check();
  await expect(page.locator("tbody tr")).toHaveCount(19);
  await page.getByLabel("Sort topics").selectOption("peakLift");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export data" }).click();
  expect((await download).suggestedFilename()).toBe("aftershocks-eclipse.csv");
  await page.getByRole("button", { name: /02 \/ SPACE EXPLORATION/ }).click();
  await expect(
    page.getByRole("heading", { name: "A landing. A billion questions." }),
  ).toBeVisible();
  await page.getByRole("button", { name: /03 \/ GLOBAL NEWS/ }).click();
  await expect(
    page.getByRole("heading", { name: "The ocean became a question" }),
  ).toBeVisible();
  await expect(page.locator(".inspector h3")).toHaveText(
    "Wreck of the Titanic",
  );
  await page.getByLabel("Minimum correlation").fill("0.99");
  await expect(page.locator(".correlation-control output")).toHaveText("0.99");
  await page
    .getByRole("navigation", { name: "Workspace views" })
    .getByRole("button", { name: "Methodology" })
    .click();
  await expect(page.getByText("Curiosity, with receipts.")).toBeVisible();
  await page
    .getByRole("navigation", { name: "Workspace views" })
    .getByRole("button", { name: "Data pipeline" })
    .click();
  await expect(
    page.getByRole("heading", { name: "A real engine underneath." }),
  ).toBeVisible();
  await expect(page.getByText("2,850", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile layout and keyboard navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "When the sun disappeared" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.keyboard.press("Tab");
  await expect(page.getByText("Skip to content")).toBeFocused();
  await page.evaluate(() => (document.activeElement as HTMLElement)?.blur());
  await page.screenshot({ path: "../docs/mobile.png", fullPage: true });
});

test("readable service failure and retry", async ({ page }) => {
  await page.route("**/api/events/eclipse", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Analytics unavailable for test" }),
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Analytics unavailable for test",
  );
  await page.unroute("**/api/events/eclipse");
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(
    page.getByRole("heading", { name: "When the sun disappeared" }),
  ).toBeVisible();
});
