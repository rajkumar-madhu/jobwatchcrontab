import { test, expect } from "@playwright/test";

// R67: Sentry Crons import on the Import page.
test("Sentry needs an organization and a token before preview", async ({ page }) => {
  await page.goto("/import");
  await page.getByRole("tab", { name: "Sentry Crons" }).click();
  await expect(page.getByLabel(/Sentry Crons URL/)).toHaveValue("https://sentry.io");
  const preview = page.getByRole("button", { name: "Preview" });
  await page.getByLabel(/Auth token/).fill("sntrys_example_token");
  await expect(preview).toBeDisabled();                                       // organization still empty
  await page.getByLabel(/^Organization/).fill("acme");
  await expect(preview).toBeEnabled();
});

test("preview lists results, warnings and the DSN change", async ({ page }) => {
  const sent: any[] = [];
  page.on("request", (r) => { if (r.url().includes("/api/v1/import/")) sent.push({ url: r.url(), body: r.postDataJSON() }); });
  await page.goto("/import");
  await page.getByRole("tab", { name: "Sentry Crons" }).click();
  await page.getByLabel(/^Organization/).fill("acme");
  await page.getByLabel(/Auth token/).fill("sntrys_example_token");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText("Needs a schedule")).toBeVisible();
  await expect(page.getByLabel("Import warnings")).toContainText("2 active client keys");
  await expect(page.getByText("Same DSN key, host under /sentry/").first()).toBeVisible();
  expect(sent[0].url).toContain("/api/v1/import/sentry");
  expect(sent[0].body).toMatchObject({ auth_token: "sntrys_example_token", organization: "acme", base_url: "https://sentry.io", dry_run: true });
  expect(sent[0].body.api_key).toBeUndefined();                                // the token is sent as auth_token only
  await page.getByRole("button", { name: /^Import \d+ jobs?$/ }).click();
  await expect(page.getByRole("status")).toContainText("/sentry/<project id>");
});
