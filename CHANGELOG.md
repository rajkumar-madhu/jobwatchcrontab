# R53 — systemd timers get real schedules, so a timer that stops is a missed run

Closes the gap found while writing the R52 landing page: the agent discovered systemd timers, but
their schedules were not cron, so they had no expected runs and silence went unnoticed.

## What ships
- **`cronsentinel/oncalendar.py`** translates systemd schedules to cron:
  - the agent's `TimersCalendar` property (`{ OnCalendar=Mon..Fri *-*-* 09:00:00 ; next_elapse=… }`,
    already normalized by systemd), raw expressions (`daily`, `Mon..Fri 09:00`, `*:0/15`,
    `*-*-01 03:00 UTC`) and shorthands (minutely … annually, quarterly, semiannually);
  - weekday lists and ranges, `*`, lists, `a..b` ranges, `a/n` and `*/n` steps, a trailing time zone;
  - interval timers (`OnUnitActiveSec=15min`) become an every-period cron with the period added to grace.
- **Refused, with a reason, never guessed:** a specific year, non-zero seconds, `~` (from month end),
  weekday and day-of-month both set (systemd needs both, cron fires on either), several differing
  OnCalendar entries, weekday ranges that wrap (systemd rejects those too), one-shot boot timers.
- **Random delays:** the agent now reports each timer's `RandomizedDelaySec + AccuracySec`
  (`timer_slack_s`); the server adds it to grace. certbot's 12-hour delay no longer looks late.
  **Agents older than R53 do not report it, so their timers stay unscheduled as before** — upgrade the
  agent to get timer schedules.
- **Discovery rules:** new timer jobs get schedule, time zone and grace. An existing unscheduled timer
  gets its schedule filled in with slot generation starting now (no backlog of "missed" runs from
  before the schedule was known). A schedule set by a person is never overwritten by a translated one.
  Native crontab lines still refresh as before.
- **Discovery time-zone fix:** discovered jobs were inserted without a time zone and their next run
  computed in UTC; both now use the schedule's zone.
- **Healthchecks import:** OnCalendar checks are converted instead of skipped (live import updated).
- Landing page: the certificate-renewal use case now states what the product does.

## Verification
- **Against systemd itself:** for 22 expressions, `systemd-analyze calendar` and the translated cron
  give the same next 15 run times from the same base time, including Asia/Kolkata and
  America/New_York zones and certbot's `*-*-* 00,12:00:00`. These tests skip where systemd-analyze is
  not installed (GitHub's Ubuntu runners have it).
- 8 discovery integration tests; mutation-checked: removing "slots start now" or "never overwrite a
  person's schedule" each makes a test fail.
- Agent: `go vet` and tests including the new timespan parser.
- Backend 699 passed / 0 failed; Healthchecks live tests; Playwright 68/0.
- **Flaky test fixed:** `test_overdue_slots_become_missed_and_job_failing` asserted a "failing" change
  even when the job was legitimately "late", so it failed in the ~90 s after every 5-minute boundary.
  Verified passing across a whole cycle.
- **Full stack:** one run had `test_6_a_missed_run_is_detected_and_alerted_with_no_heartbeat_at_all`
  time out (reconciler did not flag the job within 150 s). The next three runs passed 6/6; run times
  on this single shared CPU varied from 86 s to 208 s, and R53 does not touch the reconciler,
  scheduler or rule engine. Treated as CPU starvation in the sandbox; watch it in CI.

---

# R52 — more incident.io-style sections on the landing page

Added the incident.io homepage sections JobWatch can fill honestly; skipped the ones it cannot
(customer logos, testimonials, G2 badges, event promos), because JobWatch has none of those yet.

- **"Where you work" layer** at the top of the platform diagram (web app, Slack and Teams, email,
  webhooks and API, status pages), after incident.io's interfaces row.
- **Lead-in above the product tour** ("From 'did it run?' to 'it's handled'").
- **AI copilot section** (incident.io's "built on Nexus" slot): what the copilot reads, that secrets
  are redacted first, that it never runs commands, and that it can use a self-hosted model, next to
  a real screenshot of a copilot answer, labelled as demo data.
- **"Built for the jobs that fail quietly"** — six use-case cards (backups, ETL, billing, Kubernetes
  CronJobs, certificate renewals, nightly CI) in place of a customer-story grid: what goes wrong, and
  what JobWatch does about it.
- **Closing band:** full-width dark call to action replacing the plain closing section.

## Claim corrected before shipping
The certificate-renewal card first said a skipped systemd timer "is a missed run". It is not, yet:
the agent discovers timers, but their `OnCalendar` schedules are not cron, so discovered timers have
no expected schedule until one is set. The card now says so. **Product gap worth a round:**
translate common `OnCalendar` forms (daily, weekly, `*-*-* HH:MM`) to cron at discovery.

## Verification
Production build; Playwright 68 passed / 0 failed; all 22 pages at 390 px in light and dark, no
overflow or page errors; landing reviewed in light, dark and phone captures. No backend changes.

---

# R51 — landing page, sign-up and sign-in rebuilt (layout inspired by incident.io)

## Landing page (`/welcome`)
Structure borrowed from incident.io's homepage; words, visuals and claims are JobWatch's own.
- Announcement bar for the migration path (Healthchecks.io and Cronitor import).
- Centered hero with a **real product screenshot** (the overview page rendered from the demo data in
  `tools/ui-review`) and the schedule tape overlapping it.
- "Works with" strip (names only, no third-party logos).
- **Without / With JobWatch** toggle: the same nine-day silent backup failure, caught in 15 minutes.
- **Platform layers:** where jobs run → detection → response → foundation.
- **Product tour** with tabbed real screenshots: Overview / Jobs / Run detail; Alerting / Incidents;
  Status page. Images are WebP, ~310 KB in total, statically imported (no `public/` dir needed in
  the standalone image) and lazily loaded below the fold.
- Kept: three ways to connect, security controls, comparison summary, pricing, FAQ (now mentions
  Cronitor), final call to action. Removed the older "how a run becomes an alert" section, which the
  before/after block replaces. Every "Start" button now goes to `/signup`.
- No customer logos, testimonials or ratings: JobWatch has none yet, so none are shown.

## Sign-up (`/signup`) and sign-in (`/login`)
- Split layout: form on the left; on wide screens a panel showing the product (schedule tape and
  three concrete points) instead of testimonials. Light, dark and gold themes; phone layout checked.
- **Sign-in:** configured social providers, then a work email. The email is checked with
  `/auth/discover`: a company with verified SSO goes straight to its identity provider; anyone else
  goes to Keycloak's password page with the email filled in (where password reset also lives).
- **Sign-up:** configured social providers (`/auth/signup?idp=…`, the provider creates the account
  on first use), or a work email: SSO domains join their company's workspace, everyone else gets
  Keycloak's registration form with the email filled in. New accounts land on `/onboarding`.
- **API:** `GET /auth/providers` lists the buttons to show, from the new `AUTH_SOCIAL_PROVIDERS`
  setting (empty by default; the dev compose file enables google, github, microsoft, which exist in
  its realm). `/auth/login` and `/auth/signup` accept only configured provider aliases or an
  organization's own IdP as hints.
- Credentials are never handled by these pages; all of that stays on Keycloak.

## Verification
- Backend 640 passed / 0 failed (new tests: provider list and hint allow-list, sign-up goes to
  Keycloak's registration endpoint and lands on onboarding). Ruff clean.
- Playwright **68 passed / 0 failed**, including 4 new auth-routing tests on desktop and phone
  (provider links, SSO discovery route, password-step route with `next`, sign-up route).
- All 22 pages checked at 390 px in light and dark: no horizontal overflow, no page errors.

## Not done
- Keycloak's own login and registration screens still use Keycloak's default theme; a matching
  Keycloak theme is the natural follow-up so the hand-off looks seamless.
- A sales contact address is not invented: set `NEXT_PUBLIC_SALES_EMAIL` to enable "Talk to us".

---

# R50 — import from Cronitor, with cronitor.link URLs that keep working

First item of the next-round research report (Cronitor migration path).

## What ships
- **Jobs → Import** now offers Healthchecks.io and Cronitor. Cronitor needs an API key with the
  `monitor:read` scope; optionally the **telemetry key** used in your `cronitor.link` URLs. Neither is
  stored: the API key is used for the request, the telemetry key survives only inside each job's
  hashed ping token.
- **Cronitor API client** (`cronsentinel/importers/cronitor.py`): HTTP Basic with the key as username,
  `page`/`pageSize` paging until a short page, `Cronitor-Version: 2025-11-28` pinned (lists every
  schedule; the older single `schedule` field is accepted too), and any of three response envelopes
  (bare list, `monitors`, `data`), because Cronitor's docs do not show the list envelope.
- **Mapping:** `job` and `heartbeat` monitors import (`check`/`site` are HTTP uptime and are
  reported); cron kept with timezone; `every N minutes|hours|days` converted when the period fits the
  clock, otherwise imported without a schedule and flagged; `at HH:MM` → daily cron; multiple
  schedules → first imported, the rest reported; `grace_seconds` with Cronitor's defaults (60 for jobs,
  0 for heartbeats); `metric.duration < X` → expected runtime; other assertions reported (enforcing
  them is the run-metrics item planned next); note, tags, paused carried over.
- **Cronitor-compatible telemetry on ingest:** `/cronitor/p/<key>/<monitor>` and the legacy
  `/cronitor/ping/<key>/<monitor>`, GET/POST/HEAD, with `state=run|complete|fail|tick|ok`,
  `series` pairing start and end into one run, `metric=duration:<s>` → run duration,
  other `metric=` values kept on the run, `message`, `status_code`, `host`, `env`.
  Migrating a script is `cronitor.link/` → `<ingest>/cronitor/`. Unknown monitors get 404
  (Cronitor would auto-create one; JobWatch does not, on purpose).
- The import router was refactored so both importers share one code path (limits, de-duplication,
  token reuse, cache invalidation); the Healthchecks live tests passed unchanged afterwards.
- Ping tokens may now be up to 200 characters (telemetry key + monitor key).

## How it was tested — read this
Cronitor is closed source, so unlike Healthchecks it could not be run locally. Tests run against
`tests/fakes/cronitor.py`, a stand-in written to Cronitor's public Monitor and Telemetry API docs
(Basic auth, scopes, paging, version header behaviour, 101 monitors to force a second page, every
envelope shape). **Before announcing the importer, run one import against a real Cronitor account**
— the list envelope and any undocumented fields are the most likely surprises; if they differ,
update the fake first so the tests describe reality.

## Verification
- 9 new tests (mapping, schedule translation, paging across all envelopes, key/scope errors, full
  import → ping with Cronitor paths → runs recorded with duration and exit code, re-run creates
  nothing, no-telemetry-key path, SSRF guard). Mutation-checked: without the start/end sequence
  rule the run's end is dropped and the test fails.
- Backend 637 passed / 0 failed; ruff clean. Web: typecheck, production build, Playwright 60/0.
- Not built: the Sentry check-in shim from the report (Sentry's REST response schema could not be
  verified); next on the list is run metrics and assertions.

---

# R49 — deploy pipeline, and three deployment bugs that only real domains expose

## Deploy pipeline (`.github/workflows/deploy.yml`, `docs/DEPLOY.md`)
- A version tag (or a manual run per environment) builds the API, web and K8s-agent images to GHCR,
  deploys with `helm upgrade --install --atomic` (migrations first, as the chart's pre-upgrade hook),
  runs `deploy/smoke.sh` against the live URLs, and rolls the application back if the smoke test fails.
- GitHub Environments carry the per-environment URLs and secrets; production can require a reviewer.
  Secrets reach Helm through a values file on the runner, never the command line.
- Tags also publish the Linux agent binaries and `SHA256SUMS` to the GitHub release (what `install.sh` downloads).
- `deploy/environments/{staging,production}.yaml`: non-secret per-environment settings.
- `deploy/smoke.sh`: API reachable, API talks to the database, SCIM routed to the API, web app up,
  ingest healthy, ingest serves pings and Healthchecks paths, and (with `SMOKE_PING_TOKEN`) a real ping
  accepted end to end.
- Linted with actionlint 1.7.7 and shellcheck (clean); every shell script in `deploy/` and `tools/`
  is shellcheck-clean at warning level.

## Bugs fixed (all invisible with local ports)
- **Every ping URL shown in the UI pointed at the wrong host.** The web app derived the ingest URL
  by replacing port 8000 with 8010 in the API URL. With real domains that is a no-op, so the job page
  and onboarding showed ping URLs on the app domain, which does not serve pings: every copied URL
  would 404. New `NEXT_PUBLIC_INGEST_URL` (build arg, set by the deploy workflow); the port swap
  remains only as the local fallback. API side: `INGEST_PUBLIC_URL` set by Helm.
- **SCIM was unreachable in Kubernetes.** The Ingress routed only `/api`, `/auth` and `/public` to
  the API; `/scim/v2` went to the web app and returned 404, so every directory sync would fail.
- **Same-host pings would be throttled at the edge.** One Ingress applied `limit-rps: 50` per client
  IP to both hosts; a server running many cron jobs pings from one IP and bursts at the top of the
  hour (the R47 bug, one layer up). The chart now has two Ingresses: app host 50 rps per IP, ingest
  host 1000 (`ingress.appLimitRps` / `ingress.ingestLimitRps`), with per-job limits enforced in the app.

## Verified
- Chart renders with defaults, staging and production values (both Ingresses checked: `/scim` → API,
  separate limits, separate TLS secrets).
- **Emulated deployment:** full stack + production web build with separate app and ingest URLs behind
  a proxy that routes exactly like the new Ingresses: smoke test 8/8, including a real ping end to
  end through the ingest host; the ingest URL is compiled into 25 page bundles.
- Backend 625 passed / 0 failed; Playwright 60 passed / 0 failed.

## Rollback note
The workflow rolls back the application, not the database. Migration 0016 (hashed tokens) is not
backward compatible with releases before R41; take a database backup before deploying a release
whose changelog lists a migration that drops or renames something (`docs/DEPLOY.md`).

## Not done here (needs your accounts)
Pushing to your repository, creating the GitHub Environments and secrets, and the first real deploy.
Steps are in `docs/DEPLOY.md`.

---

# R48 — import from Healthchecks.io, with ping URLs that keep working

## What ships
- **Jobs → Import from Healthchecks** (admins): paste a Healthchecks project API key (healthchecks.io
  or self-hosted), preview, then import. The key is used for the request only and never stored.
  The Healthchecks base URL goes through the SSRF guard.
- **Mapping** (`cronsentinel/importers/healthchecks.py`):
  - cron checks → same schedule, time zone and grace;
  - interval checks → a cron that fires every period when one exists (1 min … 1 day, 1 week), with
    grace = period + grace because interval checks keep their own phase; flagged "Schedule converted";
  - intervals with no cron equivalent (e.g. 90 min) → imported without a schedule, flagged "Needs a schedule";
  - systemd OnCalendar checks → reported, not imported (JobWatch schedules are cron);
  - paused, tags and description carried over; names already in the workspace are left alone, so
    re-running the import is safe; the plan's job limit is respected.
- **Ping URLs keep working.** With a read-write key, each job keeps its Healthchecks UUID as its
  ping token, and ingest now answers the Healthchecks ping protocol under `/hc/`:
  `/hc/<uuid>`, `/start`, `/fail`, `/<exit status 0-255>`, `/log`, `?rid=` run IDs, GET/POST/HEAD,
  POST body kept as output, plain-text `OK` responses. Migrating a script is
  `hc-ping.com/` → `<ingest>/hc/`. With a read-only key, jobs get new ping URLs, shown once.
- New setting `INGEST_PUBLIC_URL` (empty = API host) for the ping URLs the API reports.
- Landing FAQ and `/compare` mention the migration path.

## Verified against a real Healthchecks server
Healthchecks (open source, latest `main`) ran locally; checks were created through its own v3 API
(cron with time zone, hourly and 5-minute intervals, a 90-minute interval, an OnCalendar schedule).
The live tests (`HC_LIVE_URL`, `HC_LIVE_KEY`, `HC_LIVE_RO_KEY`) import them and then ping exactly
as a Healthchecks script would: start + exit 0 with the same `rid` pair into one run, `/log` is
accepted, `/fail` records a failure, unknown UUIDs get 404; a re-run creates nothing; a read-only
key issues working new URLs. Without a server the live tests skip; the mapping test always runs.

## Fixed while building it
- A ping sent to `/hc/<uuid>` **before** the import is cached as "unknown" for 60 s, which would
  have rejected that job's pings right after the import. The import now clears the cache for every
  token it assigns (mutation-checked: the live test fails without it).
- Test isolation: the integration fixture also clears the resolve cache between tests.

## Verification
- Backend: 626 passed, 0 failed; ruff clean. Web: typecheck, production build, Playwright 60/0.

---

# R47 — ingest under load: one real bug, one leak, one round trip saved

New `tools/loadtest/`: seeds a fresh org with N heartbeat jobs, drives `GET /ping/<token>` with a
stdlib-only Go generator against the full stack, waits for processing to drain, and checks that
every accepted ping became exactly one execution (exits non-zero otherwise).

## Bugs found and fixed
- **Valid pings were rejected with 429 (introduced in R39).** The guard that slows down token
  guessing (60 lookups per minute per IP) charged every cache miss, including valid tokens not yet
  cached. One server — or one NAT gateway — with more than ~60 jobs had pings refused every time the
  5-minute cache expired; in the first load run 96% of pings were refused. Now only lookups that
  find no job count. Regression test: 100 valid jobs from one host all accepted (60 of 100 on the
  old code), and guessing is still limited.
- **Plaintext ping tokens in Redis.** The per-ping rate-limit key was `rl:hb:<token>`; R41 hashed
  the resolve cache but missed this key. It now uses the token's hash. The R41 test now scans all
  Redis keys for the plaintext (it fails on the R46 code).

## Performance
- The resolve-cache read and the rate-limit script now share one pipelined Redis round trip
  (`ratelimit.check_pipelined`). Profiling showed the two sequential round trips dominating sampled
  time; throughput on this box did not change because the single ingest process is CPU-bound, but
  Redis traffic per ping is halved, which matters once Redis is on another host.
- Measured (one shared vCPU running generator + ingest + workers + NATS + Postgres + Redis, one
  ingest process): warm cache about 320 pings/s at 20 clients (p50 55 ms) and 380/s at 100 clients;
  cold cache (2,000 never-seen tokens) 90-160/s. Exact accounting on a fresh org: 3,822 accepted,
  3,822 recorded — no loss, no duplicates. For scale, 10,000 jobs pinging every minute is ~170/s.
  Scale by ingest replicas (Helm default 2).

## Tests
- Integration tests now clear per-IP rate-limit windows before each test; counters from one test
  (or the previous run, within 60 s) were throttling the next.
- New: per-ping rate limit still enforced after the pipelining change.
- Backend: 620 passed, 0 failed; ruff clean across `apps/api` and `tools/`.

---

# R46 — Kubernetes agent compiled and tested against the real Kubernetes libraries

Until now the K8s agent had only been type-checked against hand-written stand-ins for the
Kubernetes packages (their module hosts are unreachable from the build sandbox). This round fetched
client-go v0.31.3, api and apimachinery and every transitive module through their GitHub mirrors,
using redirects generated from client-go's own `go.mod`, in a scratch copy of the agent.

## Results
- `go build ./...` and `go vet ./...`: clean, first real compile. The source compiled is
  byte-identical to the repo (checked by hash).
- Existing tests pass (disk queue, outage/restart delivery).
- **New `internal/watcher/fakecluster_test.go`** runs the real watcher — real informers, real API
  types — against client-go's fake clientset and a recording ingest server:
  - discovery reports only in-scope CronJobs, with schedule and concurrency policy;
  - a successful Job sends start then success; a failed Job sends fail carrying Kubernetes' reason
    (`BackoffLimitExceeded`);
  - three later updates of a finished Job send nothing more;
  - deleting a Job frees its per-Job state.
- Mutation check: with the R39 duplicate-event fix disabled, the same Job's success is sent
  **4 times**; with it, once.
- CI now runs `go test ./...` for the K8s agent (it only built and vetted before).

## Not changed
- No `go.sum` is committed: hashes produced through the mirrors are keyed differently from the
  real module hosts, so CI/Docker keep running `go mod tidy` (as before). Commit the `go.sum` that
  a networked build produces to make the image build reproducible.
- Not run on a real cluster (no Docker/kind in the sandbox). The fake clientset exercises the same
  informer and type code; a kind-based smoke test in CI would close the remaining gap.

---

# R45 — SSO and SCIM verified against a real Keycloak

R43/R44 were tested against simulated servers. This round ran them against **Keycloak 26.0.7**, with
a second Keycloak realm acting as a customer's identity provider, through real browser sign-ins.

## Results (live)
8/8 checks pass with the new `tools/sso-e2e` runner:
- Keycloak Admin API accepts the OIDC and SAML identity-provider representations (create and update).
- OIDC: user routed by email domain to the customer IdP, signs in, lands in the org with the default role.
  The `idp` claim from the realm mapper arrives in real tokens.
- Returning user signs in after SSO was disabled and re-enabled (the bug below).
- An IdP user asserting an address outside the org's verified domains is refused at the callback.
- SCIM-provisioned user links to the same record on first SSO sign-in and keeps the role set in JobWatch;
  after an Entra-style SCIM deactivation, SSO sign-in is refused.
- SAML with signed assertions: attribute mappers supply email and name; user lands in the org.

## Bugs found and fixed
- **Disabling SSO locked users out after re-enabling.** Disabling deleted the identity provider in
  Keycloak, which deletes every user's federated link. On re-enable, returning SSO-only users hit
  Keycloak's "account already exists, confirm by signing in" page with no password to confirm with.
  Disabling now switches the provider off (`enabled: false`); it is deleted only when SSO is removed
  or the organization is deleted. Unit test asserts the router never deletes on disable; live check passes.
- **Realm export listed `openid` as a client scope** (Keycloak warned and ignored it) and omitted
  `basic`, which since Keycloak 25 carries `sub` in access tokens. Bearer-token auth needs `sub`.
  Default scopes are now `basic, email, profile`; verified the access token contains `sub` and the
  re-import is warning-free. Re-run `deploy/keycloak/import.sh` (or add `basic` to the client's
  default scopes) on existing Keycloaks.

## New tool: `tools/sso-e2e/`
`customer_realm.sh` builds a fake customer IdP realm (OIDC and SAML clients, test users including one
that asserts a foreign address) and clears leftovers; `run.py` runs the checks above and exits non-zero
on failure, cleaning up its orgs and IdPs. Use it on staging after Keycloak upgrades or realm changes.

## Verification
- Backend: 618 passed, 0 failed; ruff clean (including the new tool). No web changes this round.
- Still not covered: Okta, Entra ID or ADFS specifically. Keycloak-as-IdP exercises the same OIDC
  and SAML paths, but each vendor has quirks; run one real sign-in per vendor a customer uses.

---

# R44 — SCIM directory sync, light default theme, Obsidian Gold theme

## Upgrade notes
- **Migration 0019** adds `org_scim_tokens` and `scim_users` (row-level security like every tenant
  table). SCIM is part of the Business and Enterprise plans (same `sso` feature as single sign-on).
- Nothing to configure server-side. An owner creates a SCIM token in Settings → Single sign-on and
  pastes it, with the base URL `<API_PUBLIC_URL>/scim/v2`, into Okta / Entra ID / another directory.

## SCIM 2.0 (RFC 7643/7644), users only
- Endpoints: ServiceProviderConfig, ResourceTypes, Schemas, `GET/POST /Users`, `GET/PUT/PATCH/DELETE
  /Users/{id}`, filters `userName eq`, `externalId eq`, `emails eq`. Groups answer with an empty list
  (writes 501): roles are assigned in JobWatch. Errors use the SCIM error schema and
  `application/scim+json`. Kept out of the web API's OpenAPI document (it is an IdP-facing protocol).
- Handles both PATCH dialects: Okta (`{"op":"replace","value":{"active":false}}`) and Entra ID
  (`{"op":"Replace","path":"active","value":"False"}` with string booleans).
- **Deactivation removes access on the next request**: it deletes the org membership, so cookie
  sessions, Keycloak bearer tokens and SSO logins all lose the org; the role is remembered and
  restored on reactivation. Delete removes the person from this org only (people can be in several).
- **Same domain rule as SSO:** only addresses in the org's verified domains can be provisioned.
- **Owners are never changed by SCIM** (deactivate/delete → 403), so a bad directory sync cannot
  remove the people who can fix it. Tokens can only be created and revoked by owners, are stored
  hashed, shown once, rate-limited (600/min) and record their last use.
- **SSO no longer re-admits deactivated people:** just-in-time membership on SSO login is refused
  for anyone the directory deactivated.
- Provisioned people have no Keycloak identity yet; their first SSO sign-in links to the row by email.
- Settings → Single sign-on gains "4. Directory sync (SCIM)": base URL, token list with last use,
  create (shown once) and revoke. `/compare` now marks single sign-on as supported, adds a
  directory-sync row, and lists group sync as the remaining gap.

## Light is the default theme
- First-time visitors now get the light theme (set before first paint, no flash). Dark (the
  WeCrew/Finspot tokens) and Obsidian Gold remain one click away; the switch cycles
  light → dark → gold and the choice is remembered per browser.
- Anyone who had never touched the switch was on dark before and will now see light; anyone who
  explicitly picked dark keeps it. Verified in a fresh browser: first visit is light, three clicks
  cycle all themes, a reload keeps the choice.
- Without JavaScript the page falls back to the dark values in `:root` (unchanged).

## Obsidian Gold theme
- A third theme alongside light (default) and dark: the CSM Silks palette — obsidian surfaces, warm
  ivory text, gold accent — with Playfair Display on page headings (numbers and tables stay in the
  sans-serif for legibility). The theme switch cycles light → dark → gold.
- **Approximated:** the CSM Silks site blocks automated access, so the values come from the CSM
  Silks reference portal's design language. Replace the `.gold` block in `apps/web/app/globals.css`
  with the site's exact tokens when you have them.

## Verification
- Backend: 617 passed, 0 failed; ruff clean; migrations through 0019.
- New: `tests/integration/test_scim.py` (discovery and auth, Okta lifecycle with role restore, Entra
  string booleans and path ops, deactivation ends an existing session, unverified domain refused,
  owners protected, token revocation, plan gate) and an SSO case proving a deactivated person cannot
  rejoin through JIT.
- Web: typecheck, production build, Playwright 60 passed / 2 skipped / 0 failed.
- Not tested against live Okta or Entra ID provisioning. Run each directory's own SCIM validator
  against staging before customers rely on it.

---

# R43 — single sign-on (SAML and OIDC), brokered through Keycloak

## Upgrade notes
- **Migration 0018** adds `org_sso` and `org_domains` (row-level security like every tenant table)
  and puts `sso` back on the Business plan. Enterprise already has everything.
- **New Keycloak client.** Run `deploy/keycloak/import.sh` again: it adds the `jobwatch-admin`
  service-account client (identity-provider roles only) and an `idp` claim mapper on
  `cronsentinel-web`, and prints `KEYCLOAK_ADMIN_CLIENT_SECRET` — set it on the API. Without it
  everything else works; only configuring SSO returns 503. Docker Compose dev gets it automatically.
- **New dependency:** `dnspython` (DNS TXT domain verification).
- Sessions now carry the identity provider they came from. Existing sessions keep working; they
  count as password sessions, which matters only once an org turns enforcement on.

## What ships
- **Settings → Single sign-on** (admins): connect an OpenID Connect provider (issuer, client ID,
  secret; endpoints are read from its discovery document) or SAML 2.0 (entity ID, SSO URL, signing
  certificate). JobWatch creates the identity provider in Keycloak and shows the redirect/ACS URL to
  register. The client secret is stored encrypted and never returned.
- **Verified email domains:** add a domain, publish the TXT record, press Check DNS. Public mailbox
  domains (gmail.com etc.) are refused, and a domain can be verified by one organization only.
- **Sign in with SSO** on the login page: enter a work email, go straight to that company's IdP.
- **Just-in-time membership:** first SSO sign-in joins the org with the role the admin chose.
- **Require single sign-on** (owners): every member except owners must come through the IdP —
  enforced on new logins, org switching, existing cookie sessions and Keycloak bearer tokens.
  Owners keep password sign-in as a break-glass. API keys are unaffected. Disabling the IdP turns
  enforcement off with it so nobody is locked out.
- Deleting an organization removes its identity provider from Keycloak first.

## Security properties (each has a test)
- An org's IdP can only sign in addresses in **that org's verified domains**. Without this, any org
  admin could configure an IdP asserting someone else's email and take over their account.
  Mutation-checked: removing the domain join makes the test fail.
- Issuer, discovery endpoints and SAML SSO URL go through the SSRF guard before Keycloak (which runs
  inside your network) is told to call them; all must be https.
- The `idp` login parameter accepts only `org-<uuid>` aliases.
- The Keycloak admin client can manage identity providers and nothing else.

## Verification
- Backend: 587 passed, 0 failed; ruff clean; migrations 0017 ⇄ 0018 clean.
- New tests: `test_sso_admin.py` (config, secret never returned, public domains refused, DNS
  verification, one-org-per-domain, owner-only enforcement, enforcement drops when IdP disabled,
  SAML validation, Business-plan gate), `test_keycloak_admin.py` (create vs update, SAML mappers,
  PKCE and discovered endpoints), and four SSO cases in `test_auth_flow.py` (routing by domain, JIT
  role, foreign-domain refusal, enforcement with owner break-glass).
- Web: typecheck, production build, Playwright 60 passed / 2 skipped / 0 failed.
- **Not tested against a live Keycloak or a real Okta/Entra/ADFS.** Keycloak's Admin API and the
  broker flow were exercised against mocks built from Keycloak's documented representations. Before
  offering SSO to customers, run one end-to-end sign-in per protocol on staging.
- Not built: SCIM provisioning (deprovisioning still happens in JobWatch). Listed as a gap on `/compare`.

---

# R42 — PagerDuty and Opsgenie, resolved on recovery

## Upgrade notes
- **Migration 0017** adds `pagerduty` and `opsgenie` to the Team and Business plans (Enterprise
  already has everything). Downgrade removes them.
- No configuration needed on the JobWatch side. Customers create a channel with a PagerDuty
  Events API v2 integration key or an Opsgenie API integration key, and choose region `us` or `eu`.

## What ships
- **PagerDuty (Events API v2)** and **Opsgenie (Alert API v2)** channels
  (`cronsentinel/alerting/oncall.py`). Every alert for a job uses one stable key
  (`jobwatch-job-<job id>`), so repeated failures update one incident instead of paging again.
- **Auto-resolve on recovery.** The notifier records which on-call channels hold an open alert for a
  job; when the job recovers, the rule engine resolves/closes them, even if no "recovered" rule
  exists and even during a maintenance window. Nobody is left paged by a job that already recovered.
- Severity maps to PagerDuty severity (critical/error/warning/info) and Opsgenie priority (P1–P4).
  PagerDuty events can link back to the job page (`dashboard_url`). Opsgenie `responders` supported.
- **Test button** triggers and immediately resolves, under a key that cannot touch a real alert.
- Keys are validated when the channel is created (format and region), and stored encrypted like
  every other channel secret. Vendor hosts are fixed by us, never taken from tenant input.
- Alerting page offers both types; landing, product tour and `/compare` updated. The R35
  brand-review test now allows "PagerDuty" and "Opsgenie" on public pages, since they ship.

## Bug fixed (pre-existing since before R39)
- **Every recovery of a job with an open incident crashed the rule engine.** The incident
  auto-resolve SQL embedded the JSON literal `{"auto":true}`; SQLAlchemy's `text()` read `:true` as
  a bind parameter with no value and raised after the incident had been marked resolved, so the
  rest of the handler (including recovery notifications) never ran. Now a bound parameter.
  Mutation-checked: the new end-to-end test fails on the old code. A scan found no other instance.

## Verification
- Backend: 553 passed, 0 failed; ruff clean; migrations 0015 → 0017 → 0015 → 0017 clean.
- New tests: `tests/test_oncall.py` (payloads, regions, resolve keys, test-closes-itself, vendor
  errors trigger retry) and `tests/integration/test_oncall_e2e.py` (key validation, plan gating,
  failure → page → recovery → resolve with no recovered rule).
- Web: typecheck, production build, Playwright 60 passed / 2 skipped / 0 failed.
- Not tested against live PagerDuty or Opsgenie accounts (requests checked against a mock transport
  built from the vendors' documented formats). Send a test notification from each before relying on it.

---

# R41 — hashed ping tokens, dark design system, new landing and comparison pages

## Upgrade notes
- **Migration 0016 hashes every heartbeat token.** Existing ping URLs keep working (the hash of the
  old token is stored), but the plaintext is gone: the UI can no longer re-display an existing URL.
  Users who need it again choose **New ping URL** on the job page. Downgrading issues fresh tokens.
- **Agents report by fingerprint.** `/agent/v1/discovery` now returns an empty `tokens` map (kept
  for wire compatibility). Deployed agents already fall back to fingerprints; no agent upgrade needed.
- **Dark is the default theme** (WeCrew/Finspot tokens). Light is one click away and remembered per browser.

## Security
- Ping tokens are stored as SHA-256 + a 4-character hint (`cronsentinel/pingtokens.py`). The full
  token is returned only by job create and `rotate-token`; every read returns `heartbeat_token: null`.
  The ingest cache is keyed by the hash. A database dump, a backup or a viewer-role API key no longer
  exposes working ping URLs. Regression test checks the jobs row and Redis for the plaintext.

## Product and design
- **Design system:** Finspot dark tokens (`#0A0F13`→`#1E3038` surfaces, `#22D3EE` accent, desaturated
  status colours) as CSS variables with a matching light set; Space Grotesk for headings, IBM Plex for
  text and code, all bundled. Theme applied before first paint.
- **App shell:** sidebar grouped into Monitor / Infrastructure / Insights / Configure with icons,
  active marker, command palette, theme switch. Page headers with subtitles; panels and tables on the
  new surface tokens; overview status numbers link to filtered job lists; charts follow the theme.
- **Landing page (`/welcome`)** rebuilt around a schedule tape: five job types over 24 hours showing
  runs that happened, failed, ran late and never started, with a "now" line. Then: three ways to
  connect, how a missed run becomes an alert, security controls, comparison summary, pricing, FAQ.
- **New `/compare` page:** JobWatch vs Healthchecks.io, Cronitor, Better Stack, Sentry Crons and
  Uptime Kuma across detection, onboarding, enterprise operation and pricing shape; head-to-head
  filter; "Where JobWatch is behind" (SSO, on-call integrations, licence, track record) and "When to
  choose something else". Data in `apps/web/lib/compare.ts`.
- **Comparison verified 1 October 2026** against vendor pages, with a Sources list on `/compare`.
  Corrections made: Cronitor on-call integrations are Business-only (now partial); Cronitor SSO is a
  $5/user add-on on Business; Cronitor discovery covers crontab and Windows Task Scheduler, not
  systemd; Better Stack schedule cell explains the interval-vs-cron-syntax conflict in its own docs;
  price-shape row now gives actual rates. Healthchecks.io unlimited team members confirmed (Feb 2026).
  Still unconfirmed and marked partial: whether Cronitor's agent buffers events on disk.
- **Job page:** "New ping URL" shows the new URL once with a copy button; snippets show
  `<token ending abcd>` otherwise. Onboarding says the URL is shown once.
- **Product tour (`/product`)** uses the shared site header and footer; fixed a mobile overflow.
- Jobs filter tabs scroll on narrow screens; landing tape scrolls horizontally on phones.

## Verification
- Backend: 546 passed, 0 failed (Postgres 16, Redis, NATS); ruff clean; migrations 0015⇄0016 clean.
- Web: typecheck, 21 unit tests, production build; Playwright e2e (desktop + Pixel 7) against the
  production build: 60 passed, 2 skipped (unchanged pre-existing skips), 0 failed.
- All 21 pages checked at 390 px in both themes: no horizontal overflow, no page errors.

---

# R40 — follow-ups

- **Editing a job's schedule always failed with a 500** (pre-existing since before R39): the audit
  entry carried a `datetime` that `json.dumps` cannot encode. Fixed. *(mutation-checked against the original)*
- **Rescheduling left stale slots:** future slots of the old schedule stayed `pending`, later went
  `missed` and alerted, and the new schedule was not materialised for the horizon already covered.
  A change to `schedule_expr`, `tz`, `grace_s` or `expected_runtime_s` now drops untouched future
  slots and regenerates from now. *(mutation-checked)*
- **`PATCH /api/v1/jobs/{id}` can clear fields.** Only fields the client sends are applied; explicit
  `null` clears `description`, `schedule_expr`, `expected_runtime_s`, `sla_target` (and resets `tags`
  to `[]`), and is a 422 for required fields. Previously every `null` was silently ignored, so a job
  could not be turned back into a pure heartbeat job. *(mutation-checked)*
- **K8s agent disk queue:** events are written to `/var/lib/cronsentinel/events.jsonl` (the state
  volume; `CS_BUFFER_PATH` overrides) and removed only after the server accepts them, so they survive
  agent restarts and ingest outages. Capped at 12 MiB; beyond that the in-memory fallback (20 000
  events) is used. Tested: outage → restart → recovery delivers every event exactly once.
- **Web:** "Rotate ping token" button on the job page (uses the R39 endpoint, with a confirmation).

Verification: backend 545 passed / 0 failed; ruff clean; web typecheck + unit tests pass; K8s agent
`go vet` + tests pass against stub k8s.io packages (still no real k8s.io compile in this sandbox).

---

# R39 — code-level security and reliability pass

Baseline: the `wecrew-jobwatch.zip` snapshot of 2026-09-29 (R38). Every item below was found by
reading or running the code. Every backend fix has a regression test; where marked *(mutation-checked)*,
the test was also run against the original code and failed there.

## Upgrade notes — read before deploying

1. **`SECRET_ENCRYPTION_KEY` is now mandatory and must be real.** The API refuses to start if it is
   empty, a known placeholder (`change-me`, `change-me-32-bytes-base64`, …) or shorter than 32
   characters. Generate one with `openssl rand -base64 48`. Keep the value you already run with if
   it passes; changing it logs every user out and makes stored channel configs unreadable.
   `ALLOW_INSECURE_SECRET=true` exists for tests only.
2. **docker-compose** now reads the key from `.env` and fails fast without it; use
   `docker compose --env-file .env -f infra/docker/docker-compose.yml …` (README updated).
3. **Redis ≥ 6.2** is required (`GETDEL`). The compose/Helm defaults (Redis 7) already satisfy this.
4. **Linux agents:** create the spool directory on existing hosts so non-root crontabs are monitored:
   `install -d -m 1733 /var/lib/cronsentinel/spool`. New installs get it from `install.sh`.
   Release artifacts must now include `SHA256SUMS` (`make release` produces it).
5. **K8s agent Helm chart:** `persistence.enabled` defaults to `true` (16 MiB PVC) so the enrolled
   identity survives pod rescheduling. Pods now run as uid/gid 65532.
6. **Web image** uses Next.js standalone output; `npm start` now runs `node .next/standalone/server.js`
   (copy `.next/static` into `.next/standalone/.next/` first, as the Dockerfile and CI do).
7. **Logins:** sign-in now requires `email_verified=true` from the IdP, and a user whose email is
   already bound to a different IdP subject gets a 409 instead of being silently re-linked.

## Security

| Sev | Fix | Where |
|---|---|---|
| Critical | Root secret defaulted to `"change-me"` → forgeable session cookies for any user/org on any install that forgot to set it. Now refused at first use. | `config.py`, `keys.py` |
| Critical | Next.js 15.1.0 / React 19.0.0 carried the RSC "flight" RCE, middleware auth bypass and ~30 other advisories. Now Next 15.5.27, React 19.0.8, postcss 8.5.28; production `npm audit` clean. | `apps/web/package*.json` |
| High | Open redirect after login: `/auth/login?next=@evil.com` → `https://app@evil.com`. `safe_next()` keeps only same-site absolute paths. | `routers/auth.py` |
| High | Account takeover by email: unverified emails were accepted and `keycloak_sub` was overwritten on email match. Now `email_verified` required and re-linking refused. | `routers/auth.py` |
| High | SMTP SSRF: the email channel connected to any tenant-supplied host/port with no guard; STARTTLS did not verify certificates. Now `netguard.smtp()` (resolve → validate → connect to the validated address, verified TLS) plus a config-time check. Telegram tokens validated. | `netguard.py`, `alerting/tasks.py`, `routers/alerting.py` |
| High | Cross-tenant execution-id collision: ids are client-chosen but keyed globally, so org B's events were dropped as duplicates of org A's, and a `start` could UPDATE A's execution row. Contested ids are now scoped to the job. *(mutation-checked)* | `processor.py` |
| Medium | Bootstrap tokens were reusable under concurrency (GET … DELETE). Now `GETDEL`. *(mutation-checked)* | `routers/agents.py` |
| Medium | Any viewer could export member emails + API-key inventory. Export now requires admin. *(mutation-checked)* | `routers/gdpr.py` |
| Medium | API-key role unvalidated (`"superuser"` stored, 500s later) and not capped at the creator's role. *(mutation-checked)* | `routers/org.py`, `auth.py` |
| Medium | Bearer JWTs: algorithms not pinned; JWKS cached forever (key rotation broke auth until restart); error text leaked internals; bad `X-Org-Id` → 500. | `auth.py` |
| Medium | Job create/update accepted another org's workspace/environment/team ids (FK checks bypass RLS). *(mutation-checked)* | `routers/jobs.py` |
| Medium | Unknown heartbeat tokens hit the DB on every request before any rate limit. Now per-IP limited + negative cache. | `routers/heartbeat.py` |
| Medium | Heartbeat/agent payloads unbounded (tails, meta, discovery lists, ids). Now bounded. *(mutation-checked)* | `schemas.py`, `routers/agents.py` |
| Low | Logout was CSRF-able; legacy OAuth state without nonce accepted; API-key prefix collisions could reject valid keys. | `routers/auth.py`, `auth.py`, `apps/web` |
| Low | Containers ran as root; web image shipped dev dependencies; agent installer did not verify downloads. | `infra/docker/*`, `install.sh` |

## Reliability / correctness

- **URL-mode heartbeats never paired:** `/heartbeat/<t>/start` then `/success` produced two executions,
  the first stuck "running". Completions now pair with the job's open id-less start. *(mutation-checked)*
- **Timestamps:** naive, unparseable or absurd (`>7 d` past / `>1 h` future) `agent_ts` crashed the
  processor (NATS redelivered 10× then dropped the run). Now normalised; rejected values kept in meta. *(mutation-checked)*
- **Unknown event kinds** reaching the processor were recorded as failures. Now ignored. *(mutation-checked)*
- **Pause/delete/rotate** were ignored for up to 5 min (token cache). Cache now invalidated; new
  `POST /api/v1/jobs/{id}/rotate-token`. *(mutation-checked)*
- **Invalid time zones** → 500. Now 422/400. *(mutation-checked)*
- **Agent enroll** failed when the client address was not an IP (audit `inet` cast). *(mutation-checked)*
- **Linux agent buffer:** one torn or >1 MiB line stopped delivery permanently; compaction could race
  wrapper appends. Lines are now validated/skipped, and all buffer I/O holds `flock(2)`.
  *(corrupt/partial-line tests mutation-checked; the compaction race is too narrow to reproduce on demand)*
- **Linux agent, non-root crontabs:** wrappers could neither read the config nor write the buffer, so
  those jobs ran unmonitored. They now spool per-run files; the daemon imports them and re-derives the
  fingerprint from the file owner, so a user cannot report runs of another user's jobs.
- **K8s agent did not compile** (unused variable in `client.go`). Also: `Pod`/`Node` shared one JSON tag,
  so neither was ever sent; restarts re-enrolled with the spent bootstrap token and crash-looped;
  success/fail were re-sent on every update and resync; per-job maps grew forever; event `count` was
  sent as a Unicode character; the retry queue was unbounded.

## Tooling

- Ruff rules and major version pinned (an unpinned newer ruff failed CI's first step with 227 findings).
- CI migration check: `alembic downgrade 0001` (0001's downgrade raises by design; `downgrade base`
  could never pass).
- Integration-test isolation: platform heartbeats/gaps reset before every test — the cause of the
  R38 "wall-clock flake" in `test_slot_lifecycle` / `test_unknown_suppression`.
- Agent `Makefile release` writes `SHA256SUMS`.

## Verification (this sandbox)

- Backend: 542 passed / 37 skipped / 0 failed against Postgres 16, Redis 7, NATS JetStream
  (skips: full-stack tests needing `scripts/fullstack.sh up`, two external-service cases).
- `ruff check .` clean; alembic `downgrade 0001` → `upgrade head` clean.
- Linux agent: `go vet`, `go test` pass (Go 1.22 toolchain; module declares 1.23).
- K8s agent: `go vet` against stub k8s.io packages only — the real modules were unreachable here.
  CI (`go mod tidy && go build`) is the first real compile.
- Web: typecheck, 21 unit tests, `next build`, standalone server smoke test (8 routes 200).
  Playwright e2e not run (browser download unreachable here).
- Helm: both charts render with `tools/mini-helm`; agent chart checked with persistence on and off.
- Full stack (`scripts/fullstack.sh up` — api, ingest, exec-processor, schedule-generator, reconciler,
  rule-engine, outbound-exporter, notifier as real processes): `tests/fullstack/` 9 passed, including the
  Linux-agent end-to-end test against the patched agent binary.

## Not done

- Heartbeat tokens are still stored in plaintext (needed to display ping URLs).
