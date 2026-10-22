import { test, expect } from "@playwright/test";

// R68: unusual runs on the job page and as an alert condition.
test("job page shows settings, the flagged run and why", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("link", { name: "log-cleanup" }).first().click();
  const section = page.getByRole("region", { name: "Unusual runs" });
  await expect(section.getByLabel("Sensitivity")).toHaveValue("normal");
  await expect(section.getByLabel("When a run is unusual")).toHaveValue("warn");
  await expect(section.getByText(/condition Unusual run/)).toBeVisible();
  const chip = page.getByText("Unusual", { exact: true }).first();
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(page.getByText("Unusual for this job")).toBeVisible();
  await expect(page.getByText(/finished in 1\.8 s; usually 2 min 00 s — it may have done nothing/)).toBeVisible();
});

test("changing sensitivity saves it", async ({ page }) => {
  await page.route("**/api/v1/jobs/*", async (r) => {
    if (r.request().method() !== "PATCH") return r.fallback();
    const body = r.request().postDataJSON();
    const job = await (await page.request.get(r.request().url())).json();
    await r.fulfill({ json: { ...job, ...body } });
  });
  await page.goto("/jobs");
  await page.getByRole("link", { name: "log-cleanup" }).first().click();
  const section = page.getByRole("region", { name: "Unusual runs" });
  const req = page.waitForRequest((r) => r.method() === "PATCH");
  await section.getByLabel("Sensitivity").selectOption("off");
  expect((await req).postDataJSON()).toEqual({ anomaly_sensitivity: "off" });
});

test("alert rules offer the Unusual run condition", async ({ page }) => {
  await page.goto("/alerting");
  await page.getByRole("button", { name: "Add rule" }).click();
  await expect(page.locator("option", { hasText: "Unusual run (learned from history)" }).first()).toBeAttached();
});
