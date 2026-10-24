import { test, expect } from "@playwright/test";

test("recent monitor submits configuration, inspects discovered topics and stops", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let starts = 0;
  let state: any = {
    active: false,
    phase: "idle",
    message: "Name an event to start monitoring.",
    topics: [],
    edges: [],
    timeline: [],
    log: [],
  };
  const fulfill = (route: any) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(state),
    });
  await page.route("**/api/monitor", fulfill);
  await page.route("**/api/monitor/start", async (route) => {
    starts++;
    const config = route.request().postDataJSON();
    expect(config.name).toBe("Recent research demo");
    expect(config.exclude_terms).toEqual(["headline"]);
    const series = [10, 12, 11, 100, 300].map((views, i) => ({
      hour: `20261024-0${i}0000`,
      views,
      baseline: i < 3,
    }));
    state = {
      ...state,
      active: true,
      phase: "monitoring",
      message: "2 candidate spikes found.",
      config,
      baselineReady: 3,
      baselineHours: 3,
      sourceRecords: 30000000,
      processedHours: 5,
      scannedArticles: 1200000,
      candidateCount: 2,
      latestHour: new Date(Date.now() - 3 * 3600000).toISOString(),
      topics: [
        {
          id: "Unexpected_topic",
          title: "Unexpected topic",
          views: 300,
          baseline: 11,
          lift: 27.27,
          z: 87.1,
          excess: 289,
          baselineSamples: 3,
          series,
        },
        {
          id: "Another_topic",
          title: "Another topic",
          views: 600,
          baseline: 22,
          lift: 27.27,
          z: 100,
          excess: 578,
          baselineSamples: 3,
          series: series.map((p) => ({ ...p, views: p.views * 2 })),
        },
      ],
      edges: [
        {
          source: "Unexpected_topic",
          target: "Another_topic",
          correlation: 0.99,
          samples: 5,
        },
      ],
    };
    return fulfill(route);
  });
  await page.route("**/api/monitor/stop", (route) => {
    state = {
      ...state,
      active: false,
      phase: "stopped",
      message: "Monitoring stopped. Last observations are retained.",
    };
    return fulfill(route);
  });
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Workspace views" })
    .getByRole("button", { name: "Live monitor" })
    .click();
  await expect(
    page.getByRole("heading", { name: "The unexpected, as it emerges." }),
  ).toBeVisible();
  expect(starts).toBe(0);
  await page
    .getByLabel("Event name", { exact: true })
    .fill("Recent research demo");
  await page
    .getByLabel("Headline terms to exclude", { exact: false })
    .fill("headline");
  await page.getByRole("button", { name: "Start monitoring" }).click();
  await expect(
    page.getByRole("button", { name: "Stop monitoring" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Discovery constellation" }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Inspect live topic Another topic",
      exact: true,
    })
    .click();
  await expect(page.locator(".live-inspector h3")).toHaveText("Another topic");
  await expect(
    page.getByText("MONITOR RUNNING", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop monitoring" }).click();
  await expect(
    page.getByText("LAST OBSERVATIONS", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Start monitoring" }),
  ).toBeVisible();
  expect(starts).toBe(1);
  expect(errors).toEqual([]);
});

test("live monitor is available without historical artifacts and fits mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/events", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "No historical studies" }),
    }),
  );
  await page.route("**/api/monitor", (r) =>
    r.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        active: false,
        phase: "idle",
        message: "Ready to observe.",
        topics: [],
        edges: [],
        timeline: [],
        log: [],
      }),
    }),
  );
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Workspace views" })
    .getByRole("button", { name: "Live monitor" })
    .click();
  await expect(
    page.getByRole("button", { name: "Start monitoring" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
