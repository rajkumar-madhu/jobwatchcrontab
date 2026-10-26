import { test, expect } from "@playwright/test";

// R74: the first-run path is a pasted crontab line — schedule and name come from it, and the person
// gets the same line back with the ping appended.
test("onboarding: a pasted crontab line becomes a scheduled job and a one-line change", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("How do your jobs run?");
  await expect(page.getByRole("radio", { name: /A crontab line/ })).toHaveAttribute("aria-checked", "true");   // the default
  await page.getByRole("button", { name: "Continue" }).click();

  const box = page.getByLabel("Crontab line");
  await box.fill("not a crontab line");
  await expect(page.getByTestId("cron-parse")).toContainText("Not a crontab entry");
  await box.fill("15 2 * * *  /opt/jobs/pg-backup.sh --full >> /var/log/pg.log 2>&1");
  await expect(page.getByTestId("cron-parse")).toContainText("pg-backup");
  await expect(page.getByTestId("cron-parse")).toContainText("15 2 * * *");
  await page.getByRole("button", { name: "Create the job" }).click();

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Waiting for the first signal");
  const pre = page.locator("pre");
  await expect(pre).toContainText("15 2 * * *  /opt/jobs/pg-backup.sh --full >> /var/log/pg.log 2>&1 && curl -fsS -m 10 --retry 5 ");
  await expect(pre).toContainText("/ping/tok_");
  await expect(page.getByText(/means a failing command never pings/)).toBeVisible();
});

test("onboarding: an empty line still gives a plain ping URL", async ({ page }) => {
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("cron-parse")).toContainText("leave it empty");
  await page.getByRole("button", { name: "Create a ping URL" }).click();
  await expect(page.locator("pre")).toContainText("curl -fsS ");
  await expect(page.locator("pre")).toContainText("/ping/tok_");
});

test("jobs page: Add job accepts a crontab line and shows the ping URL once", async ({ page }) => {
  await page.goto("/jobs");
  await page.getByRole("button", { name: "Add job" }).first().click();
  await page.getByLabel(/From a crontab line/).fill("@daily /usr/local/bin/certbot renew --quiet");
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue("certbot");
  await expect(page.getByLabel(/Schedule/)).toHaveValue("0 0 * * *");
  await page.getByRole("button", { name: "Create job" }).click();
  const box = page.getByTestId("job-created");
  await expect(box).toContainText("certbot created");
  await expect(box.locator("pre")).toContainText("0 0 * * *  /usr/local/bin/certbot renew --quiet && curl -fsS -m 10 --retry 5 ");
  await expect(box.locator("pre")).toContainText("/ping/tok_");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(box).toHaveCount(0);
});

// R75: pricing by jobs, USD or INR, monthly or yearly; Enterprise shows a floor instead of "contact sales"
test("pricing section: currency and interval toggles, enterprise floor", async ({ page }) => {
  await page.goto("/welcome#pricing");
  const sec = page.locator("#pricing");
  await expect(sec).toContainText("100 jobs");
  await expect(sec).toContainText("1,000 jobs");
  await expect(sec).toContainText("Unlimited jobs");
  await expect(sec).toContainText("from $6,000 /year");
  await expect(sec).toContainText("$190");                               // yearly is the default
  await sec.getByRole("radio", { name: "Monthly" }).click();
  await expect(sec).toContainText("$19");
  await sec.getByRole("radio", { name: "INR" }).click();
  await expect(sec).toContainText("₹799");
  await expect(sec).toContainText("18% GST");
  await sec.getByRole("radio", { name: /Yearly/ }).click();
  await expect(sec).toContainText("₹7,999");
});

test("billing page: INR toggle explains what is missing when Razorpay is not configured", async ({ page }) => {
  await page.goto("/billing");
  const t = page.getByTestId("billing-toggles");
  await t.getByRole("radio", { name: /INR/ }).click();
  await expect(page.getByText(/INR billing is not configured/)).toBeVisible();
  await expect(page.getByText("₹7,999/yr")).toBeVisible();
  await t.getByRole("radio", { name: /USD/ }).click();
  await expect(page.getByText("$190/yr")).toBeVisible();
  await expect(page.getByText("from $6,000/yr")).toBeVisible();
});
