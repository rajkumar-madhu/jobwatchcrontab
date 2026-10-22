import { test, expect } from "@playwright/test";

// R70: the job page explains a failure with the host's state and the run's output; the agent page
// shows the server's facts, 24 h of samples and its jobs.
test("failed run: why it failed, host panel and log viewer", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("link", { name: "customer-report-generator" }).first().click();
  const why = page.getByTestId("failure-summary");
  await expect(why).toContainText("Exit code 2");
  await expect(why).toContainText("prod-db-01");
  await expect(why).toContainText(/disk 9\d%/);
  await expect(page.getByTestId("evidence")).toContainText("No space left on device");

  const host = page.getByTestId("host-panel");
  await expect(host).toContainText("prod-db-01");
  await expect(host.getByTestId("agent-state")).toHaveText(/Agent online/);
  await expect(host.getByTestId("gauge-disk_pct")).toContainText("94%");
  await expect(host.getByTestId("host-facts")).toContainText("Ubuntu 24.04");
  await expect(host).toContainText("Also on this host (2)");
  await expect(host.getByRole("link", { name: "mongodb-backup" })).toBeVisible();

  const logs = page.getByTestId("log-viewer");
  await expect(logs.getByRole("tab", { name: "stderr" })).toHaveAttribute("aria-selected", "true");
  await expect(logs).toContainText("11 lines");
  await logs.getByLabel("Errors only").check();
  await expect(logs).toContainText("6 of 11 lines");
  await logs.getByLabel("Errors only").uncheck();
  await logs.getByLabel("Find in output").fill("backup.py");
  await expect(logs).toContainText("2 of 11 lines");
  await expect(logs.locator("mark").first()).toHaveText("backup.py");
  await logs.getByLabel("Find in output").fill("");
  await logs.getByRole("tab", { name: "stdout" }).click();
  await expect(page.getByTestId("log-lines")).toContainText("starting customer-report-generator");
  await page.getByTestId("host-during").locator("summary").click();
  await expect(page.getByTestId("host-during")).toContainText("I/O wait");

  // R72: picking another run resets the viewer (a failed run's stderr tab must not carry over)
  await page.getByTestId("run-table").getByRole("button", { name: /Success/ }).first().click();
  await expect(page.getByTestId("log-viewer").getByRole("tab", { name: "stdout" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("log-viewer")).not.toContainText("No lines match");
  await page.getByTestId("run-table").getByRole("button", { name: /Failed/ }).first().click();
  await expect(logs.getByRole("tab", { name: "stderr" })).toHaveAttribute("aria-selected", "true");
  await logs.getByRole("tab", { name: "stdout" }).click();

  const dl = page.waitForEvent("download");
  await logs.getByRole("button", { name: "Download" }).click();
  expect((await dl).suggestedFilename()).toMatch(/^run-.*-stdout\.log$/);
});

test("ping-only job explains how to get host context; agent page shows facts, charts and jobs", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("link", { name: "payments/settle-eod" }).first().click();
  const host = page.getByTestId("host-panel");
  await expect(host).toContainText("Reported by ping URL");
  await expect(host).toContainText("prod-web-01");
  await expect(host.getByRole("link", { name: "Install an agent" })).toBeVisible();

  await page.goto("/agents");
  await expect(page.getByRole("link", { name: "prod-db-01" })).toHaveAttribute("href", "/agents/a1");
  await page.goto("/agents/a1");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("prod-db-01");
  await expect(page.getByTestId("host-facts")).toContainText("6.8.0-45-generic");
  await expect(page.getByTestId("chart-disk_pct")).toContainText(/now 94%/);
  await expect(page.getByTestId("chart-disk_pct").getByRole("img").first()).toBeVisible();
  await expect(page.getByTestId("agent-jobs").getByRole("link", { name: /customer-report-generator/ })).toBeVisible();
});

test("the job page's host panel links to the agent page", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("link", { name: "nightly-database-backup" }).first().click();
  await page.getByTestId("host-panel").getByRole("link", { name: "Details" }).click();
  await expect(page).toHaveURL(/\/agents\/a1$/);
});
