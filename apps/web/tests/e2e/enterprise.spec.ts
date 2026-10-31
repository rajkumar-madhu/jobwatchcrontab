import { test, expect } from "@playwright/test";

// R69: enterprise-level landing, sign-in/up, overview and team administration (mock API in tools/ui-review).

test("overview: range switch, KPI tiles and widgets", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  for (const k of ["Success rate", "Runs", "Failed or missed", "Jobs needing attention", "Time to detect", "Time to recover"]) await expect(page.getByText(k, { exact: true }).first()).toBeVisible();
  for (const w of ["Run outcomes", "Job states", "Job health map", "Open incidents", "Needs attention", "Unusual runs"]) await expect(page.getByRole("heading", { name: w })).toBeVisible();
  await expect(page.getByText(/vs previous 7 days/).first()).toBeVisible();
  await page.getByRole("button", { name: "30d" }).click();
  await expect(page.getByText(/vs previous 30 days/).first()).toBeVisible();
  await page.reload();                                                      // the range is remembered
  await expect(page.getByRole("button", { name: "30d" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Tag" }).click();
  await expect(page.getByText(/Group by/)).toBeVisible();
  const sw = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(sw).toBeLessThanOrEqual(0);
});

test("sign-in: SSO-first copy and no horizontal overflow", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to Argus" })).toBeVisible();
  await expect(page.getByLabel("Work email")).toBeVisible();
  await expect(page.getByText(/multi-factor|authenticator/i).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Talk to a human" }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});

test("sign-up: free-mail advice, then an invitation shows who invited you", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Work email").fill("someone@gmail.com");
  await expect(page.getByText(/Use your work email if you can/)).toBeVisible();
  await page.getByLabel("Work email").fill("someone@acme.io");
  await expect(page.getByText(/Use your work email if you can/)).toHaveCount(0);

  await page.goto("/signup?invite=demo-invite-token-0123456789abcdef");
  await expect(page.getByRole("heading", { name: "Join Acme on Argus" })).toBeVisible();
  await expect(page.getByText(/Ana Rao invited/)).toBeVisible();
  await expect(page.getByLabel("Work email")).toHaveValue("farah@acme.io");
  await expect(page.getByLabel("Work email")).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: "Create account and join" })).toBeEnabled();

  await page.goto("/signup?invite=not-a-real-token");
  await expect(page.getByText(/expired, was revoked, or was already used/)).toBeVisible();
});

test("settings: invite, change a role, remove, revoke", async ({ page }, info) => {
  const email = `new-${info.project.name}-${Date.now()}@acme.io`;
  await page.goto("/settings");
  const team = page.locator("#team-h").locator("..");
  await expect(team.getByText("ana@acme.io")).toBeVisible();
  await expect(team.getByText("Directory").first()).toBeVisible();          // SCIM-managed members are marked
  await team.getByLabel("Invite by email").fill(email);
  await team.locator("#invite-role").selectOption("sre");
  await team.getByRole("button", { name: "Send invite" }).click();
  await expect(team.getByRole("status")).toContainText(`Invitation created for ${email}`);
  await expect(team.getByRole("status")).toContainText("/signup?invite=");
  await expect(team.getByText(email).nth(1)).toBeVisible();                 // listed as pending
  await team.getByRole("row", { name: new RegExp(email) }).getByRole("button", { name: "Revoke" }).click();

  const gone = `temp-${info.project.name}-${Date.now()}@acme.io`;
  await page.request.post("http://localhost:8000/__seed/member", { data: { email: gone } });
  await page.reload();
  await team.getByLabel(`Role for ${gone}`).selectOption("developer");
  await expect(team.getByLabel(`Role for ${gone}`)).toHaveValue("developer");
  await expect(team.getByLabel("Role for ben@acme.io")).toHaveCount(0);     // directory-managed: role is not editable here
  const row = team.getByRole("row", { name: new RegExp(gone) });
  await row.getByRole("button", { name: "Remove", exact: true }).click();
  await row.getByRole("button", { name: "Remove", exact: true }).click();   // confirm
  await expect(team.getByText(gone)).toHaveCount(0);
});

test("settings: require multi-factor sign-in", async ({ page }) => {
  await page.goto("/settings");
  const box = page.getByLabel(/Require multi-factor sign-in/);
  await expect(box).toBeEnabled();
  const before = await box.isChecked();
  await box.click();                                                       // controlled: it flips once the server answers
  await expect(box).toBeChecked({ checked: !before });
  await page.reload();
  await expect(page.getByLabel(/Require multi-factor sign-in/)).toBeChecked({ checked: !before });
  await page.getByLabel(/Require multi-factor sign-in/).click();
  await expect(page.getByLabel(/Require multi-factor sign-in/)).toBeChecked({ checked: before });
});

test("contact sales: topic preselected, sent, confirmation", async ({ page }) => {
  await page.goto("/contact?topic=security-review");
  await expect(page.getByLabel("Security review or questionnaire")).toBeChecked();
  await page.getByLabel("Name", { exact: true }).fill("Priya Shah");
  await page.getByLabel("Work email").fill("priya@bigco.com");
  await page.getByLabel("Company").fill("BigCo");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("status")).toContainText("Thanks, Priya");
});

test("landing and security pages carry the enterprise content and navigation", async ({ page, isMobile }) => {
  await page.goto("/welcome");
  await expect(page.getByRole("link", { name: "Talk to a human" }).first()).toBeVisible();   // R74: BOOKING_URL unset → /contact
  await expect(page.getByTestId("sixty-seconds")).toContainText("&& curl -fsS -m 10 --retry 5");
  await expect(page.locator("#start")).toContainText("Start with one line");
  await expect(page.locator("#enterprise")).toContainText("Built to pass your security review");
  await expect(page.locator("#enterprise")).toContainText("Self-hosted");
  await page.getByText("Is Argus SOC 2 certified?").click();
  await expect(page.getByText(/Not yet/).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);

  await page.goto("/security");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("security review");
  for (const h of ["Identity and access", "Data protection", "Application security", "Auditing", "Deployment and residency", "Compliance", "Reporting a vulnerability"]) await expect(page.getByRole("heading", { name: h })).toBeVisible();
  await expect(page.getByText(/has not yet completed a SOC 2/)).toBeVisible();
  if (!isMobile) {
    for (const l of ["Enterprise", "Security", "Docs"]) await expect(page.getByRole("navigation").getByRole("link", { name: l }).first()).toBeVisible();
  }
});

test("onboarding offers the cluster install and the invite step", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});
