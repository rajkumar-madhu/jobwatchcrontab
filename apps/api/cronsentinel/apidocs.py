"""R69: the public API description.

FastAPI generates the shapes (paths, parameters, request and response schemas). This module adds
what a reader of the reference needs and FastAPI cannot infer:

- a written summary and description for every operation (a test fails if a new endpoint has none);
- how to authenticate (security schemes) and the minimum role, read from each route's
  `require_role(...)` dependency, as `x-min-role`;
- the error responses every authenticated call can return (401, 403, 429);
- the reader-facing grouping (tags with names, descriptions and order);
- the ping endpoints, which are served by the separate ingest host (`servers` per operation);
- `x-internal` on browser-only flows (sign-in redirects, the website's contact form), which the
  reference leaves out but Swagger at /docs still shows.

The auth header parameters (Authorization, X-API-Key, X-Org-Id) are removed from each operation:
they are described once, as security schemes, instead of on 120 endpoints."""
from __future__ import annotations

import re

from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

# (tag, display name, description) in reference order.
TAGS: list[tuple[str, str, str]] = [
    ("jobs", "Jobs", "Scheduled jobs: what should run, when, and how long it may take. Each job has a ping URL its runs report to."),
    ("executions", "Runs", "One run of a job: when it started and finished, its outcome, exit code, duration, output and metrics."),
    ("pings", "Pings", "Report runs from your jobs. Served by the ingest host, authenticated by the job's ping token in the URL."),
    ("incidents", "Incidents", "Related failures grouped into one incident, with acknowledgement, resolution and a timeline of notes."),
    ("alerting", "Alerting", "Where alerts go (channels), when they fire (rules), when they are held back (maintenance windows), and what was sent (ledger)."),
    ("oncall", "On-call", "Rotations, overrides and escalation policies that decide who is paged, and the escalations in progress."),
    ("analytics", "Analytics", "Success rates, run counts, durations, time to recovery and unusual runs across the organization."),
    ("logs", "Logs", "Search the output of runs."),
    ("topology", "Dependencies and topology", "Declare that one job depends on another, see what a failure affects, and the server and cluster tree."),
    ("kubernetes", "Kubernetes", "Clusters reporting through the Kubernetes agent and the CronJobs discovered in them."),
    ("agents", "Agents", "Server and cluster agents: enrollment tokens, rotation and revocation."),
    ("team", "Team and access", "Members and their roles, invitations, and the organization's sign-in policy."),
    ("api-keys", "API keys", "Keys for scripts, CI and infrastructure-as-code. Each key carries a role."),
    ("sso", "Single sign-on and SCIM", "SAML or OIDC identity provider, verified domains, enforcement, SCIM tokens and group-to-role mapping."),
    ("audit", "Audit log", "Who changed what, and streams that deliver every audit event to your SIEM."),
    ("integrations", "Integrations", "Signal destinations, delivery history and metric exports to Datadog."),
    ("import", "Import", "Bring jobs over from Healthchecks.io, Cronitor or Sentry Crons, keeping existing ping URLs working."),
    ("status-pages", "Status pages", "Public pages that show the health of chosen jobs."),
    ("copilot", "AI copilot", "Ask questions about failures. Read-only; sees redacted telemetry."),
    ("organization", "Organization", "The signed-in identity, workspaces, data export and deletion."),
    ("billing", "Billing", "Plan, usage and the hosted checkout and billing portal."),
    ("platform", "Platform", "The health of Argus's own monitoring of your organization."),
    ("public", "Public", "Endpoints that need no authentication."),
    ("auth", "Browser sign-in", "Redirect-based sign-in used by the web app. Not for API clients."),
]

# Operations that move between FastAPI's router tags and the reference's groups.
RETAG: dict[str, str] = {
    "GET /api/v1/me": "organization", "GET /api/v1/workspaces": "organization", "POST /api/v1/workspaces": "organization",
    "GET /api/v1/org/export": "organization", "DELETE /api/v1/org/": "organization",
    "GET /api/v1/api-keys": "api-keys", "POST /api/v1/api-keys": "api-keys", "DELETE /api/v1/api-keys/{key_id}": "api-keys",
    "GET /api/v1/audit-logs": "audit",
    "GET /api/v1/org/invites": "team", "POST /api/v1/org/invites": "team", "DELETE /api/v1/org/invites/{invite_id}": "team",
    "GET /api/v1/org/security": "team", "PUT /api/v1/org/security": "team",
    "GET /api/v1/org/members": "team", "PATCH /api/v1/org/members/{user_id}": "team", "DELETE /api/v1/org/members/{user_id}": "team",
}

INTERNAL_PREFIXES = ("/auth/",)
INTERNAL = {"POST /public/contact", "GET /api/v1/billing/checkout"}
HIDDEN = {"/healthz", "/readyz", "/metrics"}

# "METHOD path" -> (summary, description). Descriptions are Markdown.
DOCS: dict[str, tuple[str, str]] = {
    # Jobs
    "GET /api/v1/jobs": ("List jobs", "Jobs in the organization, ordered by name. Filter by state, workspace or tag. Paginated: pass `next_cursor` from one page as `cursor` to get the next; it is `null` on the last page."),
    "POST /api/v1/jobs": ("Create a job", "Creates a job and returns it with its ping URL. The ping URL contains a secret token and is returned **only in this response**; store it where the job runs. Schedules accept cron expressions, systemd `OnCalendar` expressions or a fixed interval."),
    "GET /api/v1/jobs/{job_id}": ("Get a job", "One job with its schedule, current state, last run and alerting settings."),
    "GET /api/v1/jobs/{job_id}/host": ("Get a job's host", "The server the job runs on: agent state, host facts (OS, kernel, CPUs, memory, disk, uptime), the latest sample, 24 hours of CPU, memory, load and disk, and the other jobs on that server. Ping-only jobs have no server; `last_host` is the host name the latest run reported."),
    "PATCH /api/v1/jobs/{job_id}": ("Update a job", "Changes only the fields you send. Changing the schedule takes effect for the next expected run."),
    "DELETE /api/v1/jobs/{job_id}": ("Delete a job", "Deletes the job and its run history. Its ping URL stops working immediately."),
    "POST /api/v1/jobs/{job_id}/rotate-token": ("Rotate a ping token", "Replaces the job's ping URL, for example after it leaked, without losing the job's history. The old URL stops working at once; the new one is returned only in this response."),
    "GET /api/v1/jobs/{job_id}/next-runs": ("Preview upcoming runs", "The next `n` times the job is expected to run, in UTC, computed from its schedule and time zone."),
    "GET /api/v1/jobs/{job_id}/executions": ("List a job's runs", "The job's most recent runs, newest first."),
    "POST /api/v1/jobs/schedule/preview": ("Preview a schedule", "Validates a schedule expression without creating a job and returns its next run times and a plain-language description."),
    # Runs
    "GET /api/v1/executions/{execution_id}": ("Get a run", "One run with its timing, outcome, exit code, redacted output, reported metrics and any unusual-run findings."),
    "GET /api/v1/executions/{execution_id}/logs": ("Download a run's output", "The run's stdout, stderr or both as a text file. The agent keeps the last 32 KiB of each stream, redacted."),
    "GET /api/v1/executions/{execution_id}/compare/{other_id}": ("Compare two runs", "Differences between two runs of the same job: duration, exit code, metrics and output lines that appear in only one of them."),
    # Incidents
    "GET /api/v1/incidents": ("List incidents", "Incidents, newest first. Filter by `status` (`open`, `acknowledged`, `resolved`)."),
    "GET /api/v1/incidents/{incident_id}": ("Get an incident", "One incident with the jobs involved and its timeline."),
    "POST /api/v1/incidents/{incident_id}/ack": ("Acknowledge an incident", "Marks the incident as being handled and stops further escalation."),
    "POST /api/v1/incidents/{incident_id}/resolve": ("Resolve an incident", "Closes the incident. A new failure opens a new incident."),
    "POST /api/v1/incidents/{incident_id}/notes": ("Add a note", "Adds a note to the incident's timeline."),
    # Alerting
    "GET /api/v1/alerts/channels": ("List alert channels", "Channels alerts can be sent to. Credentials are never returned."),
    "POST /api/v1/alerts/channels": ("Create an alert channel", "Adds a channel: email, Slack, Microsoft Teams, PagerDuty, Opsgenie, webhook and others. Credentials are encrypted at rest and cannot be read back."),
    "POST /api/v1/alerts/channels/{channel_id}/test": ("Send a test alert", "Sends a sample alert through the channel now and reports whether the provider accepted it."),
    "DELETE /api/v1/alerts/channels/{channel_id}": ("Delete an alert channel", "Deletes the channel. Rules that only targeted it stop sending."),
    "GET /api/v1/alerts/rules": ("List alert rules", "Rules that decide which events alert, and where."),
    "POST /api/v1/alerts/rules": ("Create an alert rule", "Sends matching events (failed, missed, late, recovered, unusual run and others) for matching jobs to one or more channels."),
    "PATCH /api/v1/alerts/rules/{rule_id}": ("Enable or disable a rule", "Turns the rule on or off without deleting it."),
    "DELETE /api/v1/alerts/rules/{rule_id}": ("Delete an alert rule", ""),
    "GET /api/v1/alerts/maintenance": ("List maintenance windows", "Windows that are active, upcoming, or ended in the last 7 days. Recurring windows stay listed while they still have occurrences."),
    "GET /api/v1/alerts/maintenance/{mw_id}": ("Get a maintenance window", "One window by id, whatever its dates."),
    "POST /api/v1/alerts/maintenance": ("Create a maintenance window", "Holds back alerts for chosen jobs, tags or the whole organization for a period, once or on a recurring schedule. Runs are still recorded."),
    "POST /api/v1/alerts/maintenance/{mw_id}/end": ("End a maintenance window", "Ends a one-off window now, for example when work finished early. Recurring windows are deleted instead."),
    "DELETE /api/v1/alerts/maintenance/{mw_id}": ("Delete a maintenance window", ""),
    "GET /api/v1/alerts/ledger": ("List sent alerts", "Every alert sent or suppressed, newest first, with the channel, outcome and reason."),
    # On-call
    "GET /api/v1/oncall/schedules": ("List on-call schedules", "Rotations with who is on call now."),
    "GET /api/v1/oncall/schedules/{sid}": ("Get an on-call schedule", "One schedule with its layers, overrides and upcoming shifts."),
    "POST /api/v1/oncall/schedules": ("Create an on-call schedule", "A rotation of members with a hand-off time and time zone."),
    "PUT /api/v1/oncall/schedules/{sid}": ("Replace an on-call schedule", "Replaces the whole schedule definition."),
    "DELETE /api/v1/oncall/schedules/{sid}": ("Delete an on-call schedule", ""),
    "POST /api/v1/oncall/schedules/{sid}/overrides": ("Add an override", "Puts someone else on call for a period, for example to cover a holiday."),
    "DELETE /api/v1/oncall/schedules/{sid}/overrides/{oid}": ("Delete an override", ""),
    "GET /api/v1/oncall/policies": ("List escalation policies", ""),
    "POST /api/v1/oncall/policies": ("Create an escalation policy", "Steps that page a schedule or person, then the next step if nobody acknowledges in time."),
    "PUT /api/v1/oncall/policies/{pid}": ("Replace an escalation policy", "Replaces the whole policy definition."),
    "DELETE /api/v1/oncall/policies/{pid}": ("Delete an escalation policy", ""),
    "POST /api/v1/oncall/policies/{pid}/channel": ("Create a channel for a policy", "Creates the alert channel that routes alerts to this policy, so alert rules can target it."),
    "GET /api/v1/oncall/escalations": ("List escalations", "Escalations in progress and recently finished."),
    "POST /api/v1/oncall/escalations/{rid}/ack": ("Acknowledge an escalation", "Stops the escalation from paging the next step."),
    "GET /api/v1/oncall/people": ("List people for on-call", "Organization members who can be put on a rotation or paged by a step."),
    # Analytics
    "GET /api/v1/analytics/overview": ("Get the overview", "Counts by state, recent failures and open incidents: the data behind the dashboard's overview."),
    "GET /api/v1/analytics/series": ("Get run outcomes over time", "Succeeded, failed and missed runs per bucket (`hour` or `day`) for the last `days` days."),
    "GET /api/v1/analytics/unusual-runs": ("List unusual runs", "The most recent runs that succeeded but were far outside their job's history (duration or a reported metric), newest first."),
    "GET /api/v1/analytics/jobs": ("Get per-job statistics", "Success rate, run count, failures and duration percentiles per job for the last `days` days. Sort by `failures`, `p95`, `trend` or `success_rate`."),
    "GET /api/v1/analytics/mttr": ("Get time to detect and recover", "Average time from a failure to its alert and from an incident opening to its resolution."),
    "GET /api/v1/analytics/report": ("Get a reliability report", "A summary for a `period` (week or month) suitable for sharing: success rate, incidents, worst jobs and SLA attainment."),
    # Logs
    "GET /api/v1/logs/search": ("Search run output", "Full-text search over redacted run output. Filter by job, stream, host, outcome and time range."),
    # Topology
    "GET /api/v1/dependencies": ("List dependencies", "Every declared \"job A depends on job B\" edge."),
    "POST /api/v1/dependencies": ("Add a dependency", "Declares that a job depends on another. When the upstream job fails, alerts for the downstream job say so."),
    "DELETE /api/v1/dependencies": ("Remove a dependency", ""),
    "GET /api/v1/jobs/{job_id}/impact": ("Get a job's impact", "Jobs that depend on this one, directly or indirectly."),
    "GET /api/v1/topology": ("Get the topology", "Organization → server → user → job, and organization → cluster → namespace → CronJob. States roll up worst-first."),
    # Kubernetes
    "GET /api/v1/clusters": ("List clusters", "Clusters reporting through the Kubernetes agent."),
    "GET /api/v1/clusters/{cluster_id}/cronjobs": ("List a cluster's CronJobs", "CronJobs discovered in the cluster and the jobs they map to."),
    # Agents
    "POST /api/v1/agents/bootstrap-token": ("Create an enrollment token", "A short-lived token an agent uses once to enroll. Returned only in this response."),
    "GET /api/v1/agents": ("List agents", "Server and cluster agents with their version and last contact."),
    "GET /api/v1/agents/{agent_id}": ("Get an agent", "One agent with its server's facts, the latest host sample, 24 hours of samples and the jobs discovered on it."),
    "POST /api/v1/agents/{agent_id}/rotate": ("Rotate an agent key", "Issues a new key for the agent. The old key stops working after the agent picks up the new one."),
    "POST /api/v1/agents/{agent_id}/revoke": ("Revoke an agent", "The agent's key stops working immediately."),
    # Team
    "GET /api/v1/org/members": ("List members", "Everyone in the organization with their role. Members provisioned over SCIM are marked `managed_by_directory`."),
    "PATCH /api/v1/org/members/{user_id}": ("Change a member's role", "Admins can change roles up to developer…devops; only owners can make someone an admin. Owners cannot be changed here, and directory-managed members follow their SCIM groups."),
    "DELETE /api/v1/org/members/{user_id}": ("Remove a member", "Removes the person from the organization. Their account and other organizations are untouched. Owners cannot be removed."),
    "GET /api/v1/org/invites": ("List invitations", "Pending, accepted, expired and revoked invitations."),
    "POST /api/v1/org/invites": ("Invite a member", "Creates an invitation for an email address with a role. The response contains `invite_url` **once**; send it to the person. It works once, expires after 7 days and only joins that email address."),
    "DELETE /api/v1/org/invites/{invite_id}": ("Revoke an invitation", "The invitation link stops working."),
    "GET /api/v1/org/security": ("Get sign-in policy", "Whether multi-factor sign-in is required and whether this server can check it."),
    "PUT /api/v1/org/security": ("Set sign-in policy", "Require multi-factor sign-in for members who use a password. Google and GitHub sign-in are then refused for the organization. Returns `409` if the server's Keycloak admin client is not configured."),
    # API keys
    "GET /api/v1/api-keys": ("List API keys", "Keys with their role, creator and last use. The key itself is never returned again."),
    "POST /api/v1/api-keys": ("Create an API key", "Creates a key with a role. The key is returned **only in this response**; it is stored as a hash."),
    "DELETE /api/v1/api-keys/{key_id}": ("Revoke an API key", "The key stops working immediately."),
    # SSO
    "GET /api/v1/sso": ("Get single sign-on settings", "The identity provider configuration, verified domains and enforcement. Secrets are never returned."),
    "PUT /api/v1/sso": ("Configure single sign-on", "Sets the SAML 2.0 or OpenID Connect identity provider."),
    "DELETE /api/v1/sso": ("Remove single sign-on", "Removes the identity provider. Members sign in with passwords or social providers again."),
    "POST /api/v1/sso/domains": ("Add a domain", "Adds an email domain and returns the DNS TXT record that proves you own it."),
    "POST /api/v1/sso/domains/{domain_id}/verify": ("Verify a domain", "Checks the DNS TXT record. People with verified-domain emails sign in through your identity provider."),
    "DELETE /api/v1/sso/domains/{domain_id}": ("Remove a domain", ""),
    "PUT /api/v1/sso/enforce": ("Enforce single sign-on", "Requires single sign-on for everyone except owners, who keep a password as a break-glass path. Existing password sessions of other members end."),
    "GET /api/v1/sso/scim-tokens": ("List SCIM tokens", ""),
    "POST /api/v1/sso/scim-tokens": ("Create a SCIM token", "A bearer token for your identity provider's SCIM 2.0 client at `/scim/v2`. Returned only in this response. Owner only: a SCIM token can remove every non-owner member."),
    "DELETE /api/v1/sso/scim-tokens/{token_id}": ("Revoke a SCIM token", ""),
    "GET /api/v1/sso/scim-groups": ("List directory groups", "Groups pushed by your identity provider and the role each maps to."),
    "PUT /api/v1/sso/scim-groups/{group_id}/role": ("Map a group to a role", "Members of the directory group get this role. Owner only: a mapping can grant admin to a whole group."),
    # Audit
    "GET /api/v1/audit-logs": ("List audit events", "Sign-ins, role changes, invitations, configuration changes and deletions, newest first, with actor, time and source address."),
    "GET /api/v1/audit-streams": ("List audit streams", "Destinations that receive every audit event as it happens."),
    "POST /api/v1/audit-streams": ("Create an audit stream", "Streams audit events to Splunk (HTTP Event Collector), Datadog Logs or a signed webhook, in order and at least once."),
    "PATCH /api/v1/audit-streams/{stream_id}": ("Pause or resume an audit stream", "Paused streams keep their position and catch up when resumed."),
    "DELETE /api/v1/audit-streams/{stream_id}": ("Delete an audit stream", ""),
    "POST /api/v1/audit-streams/{stream_id}/test": ("Test an audit stream", "Sends one synthetic event now and reports the result. The stream's position is not changed."),
    # Integrations
    "GET /api/v1/integrations/schema": ("Get the signal schema", "The published contract of the events sent to signal destinations. Public."),
    "GET /api/v1/integrations/destinations": ("List signal destinations", ""),
    "POST /api/v1/integrations/destinations": ("Create a signal destination", "Sends job events (state changes, runs, incidents) to an HTTPS endpoint, signed with a shared secret."),
    "PUT /api/v1/integrations/destinations/{dest_id}": ("Update a signal destination", ""),
    "DELETE /api/v1/integrations/destinations/{dest_id}": ("Delete a signal destination", ""),
    "POST /api/v1/integrations/destinations/{dest_id}/test": ("Test a signal destination", "Sends a sample `job.state_changed` event now and reports the outcome."),
    "GET /api/v1/integrations/deliveries": ("List deliveries", "Recent deliveries to signal destinations with status codes and retries."),
    "GET /api/v1/metric-exports": ("List metric exports", ""),
    "POST /api/v1/metric-exports": ("Create a metric export", "Sends job metrics (run counts, durations, states) to Datadog."),
    "PATCH /api/v1/metric-exports/{export_id}": ("Pause or resume a metric export", ""),
    "DELETE /api/v1/metric-exports/{export_id}": ("Delete a metric export", ""),
    "POST /api/v1/metric-exports/{export_id}/test": ("Test a metric export", "Checks the Datadog API key."),
    # Import
    "POST /api/v1/import/healthchecks": ("Import from Healthchecks.io", "Creates a job for each check. Ping URLs keep working when you change only the host. The API key is used for this request only."),
    "POST /api/v1/import/cronitor": ("Import from Cronitor", "Creates a job for each monitor. Neither key is stored; existing telemetry URLs keep working on the ingest host."),
    "POST /api/v1/import/sentry": ("Import from Sentry Crons", "Creates a job for each cron monitor. Sentry SDK check-ins keep working when you point the DSN at the ingest host. The auth token is used for this request only."),
    # Status pages
    "GET /api/v1/status-pages": ("List status pages", ""),
    "POST /api/v1/status-pages": ("Create a status page", "A public page at `/status/{slug}` showing the health of the jobs you choose."),
    "DELETE /api/v1/status-pages/{page_id}": ("Delete a status page", ""),
    # Copilot
    "POST /api/v1/copilot/ask": ("Ask the copilot", "Answers a question about your jobs using redacted, pseudonymised telemetry. Suggested commands are returned as text; nothing is executed. Limited to 20 questions per minute per user."),
    "GET /api/v1/copilot/history": ("List copilot history", "Your recent questions and answers."),
    "GET /api/v1/copilot/suggestions": ("Get suggested questions", "Questions worth asking now, based on recent failures."),
    # Organization
    "GET /api/v1/me": ("Get the current identity", "Who the request is authenticated as: the user or API key, the organization and the role."),
    "GET /api/v1/workspaces": ("List workspaces", "Workspaces group jobs inside the organization."),
    "POST /api/v1/workspaces": ("Create a workspace", ""),
    "GET /api/v1/org/export": ("Export organization data", "Everything stored for the organization as JSON: jobs, runs, incidents, alerting configuration and audit log. Secrets are excluded."),
    "DELETE /api/v1/org/": ("Delete the organization", "Permanently deletes the organization and all its data. Cannot be undone."),
    # Billing
    "GET /api/v1/billing": ("Get plan and usage", "The current plan, its limits and usage."),
    "POST /api/v1/billing/checkout": ("Start a checkout", "Returns a hosted checkout URL for the chosen plan."),
    "POST /api/v1/billing/portal": ("Open the billing portal", "Returns a URL to the hosted billing portal for invoices and payment methods."),
    # Platform
    "GET /api/v1/platform/monitoring-gaps": ("List monitoring gaps", "Periods when Argus itself was not watching your schedules, and how many expected runs could not be checked. Shown so you never mistake our outage for your jobs being fine."),
    # Public
    "GET /public/status/{slug}": ("Get a public status page", "The data behind a public status page. No authentication."),
    "GET /auth/invite/{token}": ("Preview an invitation", "Who sent an invitation, to which organization and with which role. Rate limited per address."),
    "POST /public/contact": ("Contact sales", "The website's contact form. Rate limited per address."),
    # Browser sign-in
    "GET /auth/sso": ("Start single sign-on", "Finds the organization that verified the email's domain and redirects to its identity provider."),
    "GET /auth/discover": ("Discover sign-in options", "What the sign-in page should offer for an email address. Reveals only whether a domain uses single sign-on."),
    "GET /auth/signup": ("Start sign-up", "Redirects to the identity provider's registration, or to the company's identity provider for a domain with single sign-on."),
    "GET /auth/providers": ("List sign-in providers", "Social providers the sign-in page may offer."),
    "GET /auth/login": ("Start sign-in", "Redirects to the identity provider."),
    "GET /auth/callback": ("Complete sign-in", "OpenID Connect callback. Creates the session cookie."),
    "POST /auth/logout": ("Sign out", "Ends the browser session."),
    "GET /auth/session": ("Get the browser session", "The signed-in user, their organizations and the CSRF token."),
    "POST /auth/orgs": ("Create an organization", "First step of onboarding: creates an organization with the signed-in user as owner."),
    "POST /auth/switch/{org_id}": ("Switch organization", "Changes the organization of the browser session."),
    # Pings (ingest host)
    "GET /ping/{token}": ("Report a successful run", "The simplest integration: request this URL when the job finishes successfully.\n\n```sh\n0 2 * * * /opt/backup.sh && curl -fsS -m 10 --retry 5 https://ingest.example.com/ping/<token>\n```"),
    "POST /heartbeat/{token}/{status}": ("Report a run event", "`status` is `start`, `success` or `fail`. Send `start` before the job runs to measure duration and detect runs that hang. GET is also accepted."),
    "GET /heartbeat/{token}/{status}": ("Report a run event (GET)", "The same as the POST form, for tools that can only send GET requests."),
    "POST /api/v1/heartbeat/{token}": ("Report a run with details", "Reports a run event with an exit code, duration, output (redacted before it is stored) and metrics. Metrics feed unusual-run detection."),
}


# Field descriptions for the generated schemas. "Model.field" wins over "field". Kept here rather than
# as Field(description=...) on 100 models so the wording is reviewed in one place.
FIELD_DOCS: dict[str, str] = {
    "id": "Unique identifier (UUID).",
    "name": "Human-readable name, unique within its kind in the organization.",
    "description": "Free-text description.",
    "created_at": "When it was created (UTC, ISO 8601).",
    "updated_at": "When it was last changed (UTC).",
    "enabled": "Whether it is active. Disabled objects are kept but do nothing.",
    "role": "Role: `viewer`, `developer`, `sre`, `devops`, `admin` or `owner`. Each role can do everything the ones before it can.",
    "job_id": "The job's id.",
    "job_ids": "Ids of the jobs it applies to.",
    "job_name": "The job's name.",
    "execution_id": "The run's id.",
    "incident_id": "The incident's id.",
    "workspace_id": "Workspace the job belongs to. `GET /api/v1/workspaces` lists them.",
    "workspace_ids": "Workspaces it applies to.",
    "environment_id": "Optional environment (for example production or staging).",
    "environment_ids": "Environments it applies to.",
    "team_id": "Optional owning team.",
    "user_id": "The user's id.",
    "org_id": "The organization's id.",
    "email": "Email address.",
    "tz": "IANA time zone the schedule is evaluated in, for example `Europe/London`. Defaults to `UTC`.",
    "tags": "Free-form labels. Used to filter jobs and to scope alert rules and maintenance windows.",
    "schedule_expr": "When the job should run: a cron expression (`0 2 * * *`), a systemd `OnCalendar` expression (`Mon..Fri 02:00`) or an interval (`@every 15m`). Omit for a heartbeat-only job that is checked by `grace_s` alone.",
    "schedule_human": "The schedule in words.",
    "expected_runtime_s": "How long a run normally takes, in seconds. A run still going after this is reported as `runtime_exceeded`.",
    "grace_s": "Seconds after the expected time before a run that has not started is reported late, then missed.",
    "sla_target": "Target success rate in percent, for example `99.5`. Shown on reports and used by `sla_breach` rules.",
    "assertions": "Checks on each run's output or metrics, for example `size_bytes > 1000000`. A run that fails an assertion is a failure even if it exited 0.",
    "anomaly_sensitivity": "Unusual-run detection: `off`, `low`, `normal` or `high`. Higher flags smaller departures from the job's history.",
    "anomaly_action": "What an unusual run does: `warn` (alerts only through `anomaly` rules) or `fail` (the run counts as failed).",
    "JobOut.status": "Current state: `unknown`, `healthy`, `running`, `late`, `missed`, `failed`, `timeout`, `recovered` or `paused`.",
    "JobOut.kind": "How runs are reported: `heartbeat` for ping URLs, or the agent type that discovered it.",
    "JobCreate.kind": "How runs are reported. `heartbeat` (the default) for jobs that call their ping URL.",
    "ping_url": "URL the job calls to report runs. Contains the secret token; returned only when the job is created or its token rotated.",
    "heartbeat_token": "The secret part of the ping URL. Returned only once.",
    "heartbeat_token_hint": "The last characters of the ping token, to recognise it.",
    "last_run_at": "When the last run started.",
    "last_status": "Outcome of the last run.",
    "last_success_at": "When the last successful run finished.",
    "next_expected_at": "When the next run is due.",
    "next_cursor": "Pass as `cursor` to get the next page. `null` on the last page.",
    "items": "The objects on this page.",
    "ExecutionOut.status": "Outcome: `scheduled`, `running`, `success`, `failed`, `timeout` or `missed`.",
    "started_at": "When the run started (UTC).",
    "finished_at": "When the run finished (UTC). `null` while running.",
    "duration_ms": "How long the run took, in milliseconds.",
    "exit_code": "The process exit code, when reported.",
    "host": "Host the run was reported from.",
    "metrics": "Numbers the run reported, for example `{\"rows\": 1200, \"size_bytes\": 4200000000}`. Used by assertions and unusual-run detection.",
    "anomalies": "What was unusual about the run: the metric or duration, its value, the typical value and a message.",
    "skew_ms": "Difference between the reporting host's clock and Argus's, in milliseconds.",
    "stdout_tail": "The end of the run's standard output, redacted.",
    "stderr_tail": "The end of the run's standard error, redacted.",
    "assertion_failures": "Assertions the run failed.",
    "HeartbeatBody.status": "`start`, `success` or `fail`.",
    "HeartbeatBody.output": "Output to keep with the run. Secrets are redacted before it is stored.",
    "meta": "Extra key-value data stored with the run.",
    "sequence": "Optional increasing number, so a retried report is not counted twice.",
    "IncidentOut.status": "`open`, `acknowledged` or `resolved`.",
    "severity": "`critical`, `high`, `medium` or `low`.",
    "title": "Title.",
    "root_cause": "Likely cause, when known.",
    "resolution": "How it was resolved.",
    "detected_at": "When the first failure was detected.",
    "acknowledged_at": "When someone acknowledged it.",
    "resolved_at": "When it was resolved.",
    "affected_job_ids": "Jobs involved in the incident.",
    "correlation_key": "What grouped the failures into one incident (a host, cluster or shared dependency).",
    "timeline": "Events in order: detection, alerts sent, acknowledgement, notes, resolution.",
    "note": "Text of the note.",
    "ChannelIn.kind": "Channel type: `email`, `slack`, `teams`, `discord`, `telegram`, `webhook`, `pagerduty`, `opsgenie`, `datadog` or `escalation`.",
    "ChannelIn.config": "Settings for the channel type. Required keys — email: `host`, `from`, `to`; slack, teams, discord: `webhook_url`; telegram: `bot_token`, `chat_id`; webhook: `url`; pagerduty: `routing_key`; opsgenie, datadog: `api_key`; escalation: `policy_id`. Stored encrypted; never returned.",
    "ChannelOut.kind": "Channel type.",
    "condition": "What triggers the rule: `failed`, `missed`, `late`, `runtime_exceeded`, `recovered`, `consecutive_failures`, `sla_breach` or `anomaly`.",
    "scope": "Which jobs it applies to: by `job_ids`, `tags`, `workspace_ids` or `environment_ids`. Empty means every job.",
    "params": "Parameters for the condition, for example `{\"count\": 3}` for `consecutive_failures`.",
    "channel_ids": "Channels to notify.",
    "business_hours": "Only notify during business hours.",
    "repeat_interval_s": "Re-send while the problem lasts, every this many seconds (minimum 60). `null` sends once.",
    "starts_at": "Start (UTC).",
    "ends_at": "End (UTC).",
    "repeat": "`none`, `daily` or `weekly`, expanded in `tz`.",
    "rrule": "Advanced: an RFC 5545 RRULE (DAILY or WEEKLY). Overrides `repeat`.",
    "active_now": "Whether the window is in effect now.",
    "rotation": "Who rotates, in order.",
    "members": "Members, in order.",
    "shift_hours": "Length of each shift in hours.",
    "handoff_at": "When the first shift starts; later shifts follow from it.",
    "restrict_days": "Only these weekdays (0 = Monday).",
    "restrict_start": "Daily start of on-call time (HH:MM).",
    "restrict_end": "Daily end of on-call time (HH:MM).",
    "layers": "Rotation layers. Later layers take precedence where they have someone on call.",
    "steps": "Escalation steps, in order.",
    "targets": "Who a step pages: schedules or people.",
    "delay_min": "Minutes to wait for an acknowledgement before the next step.",
    "repeat_count": "How many times to run through the steps if nobody acknowledges.",
    "on_call_now": "Who is on call now.",
    "overrides": "Temporary replacements.",
    "token": "Secret token. Returned only in this response.",
    "prefix": "First characters of the token, to recognise it.",
    "last_used_at": "When it was last used.",
    "expires_at": "When it stops working.",
    "revoked_at": "When it was revoked.",
    "invite_url": "Link to send to the invited person. Returned only when the invitation is created.",
    "InviteOut.status": "`pending`, `accepted`, `expired` or `revoked`.",
    "joined_at": "When the person joined the organization.",
    "managed_by_directory": "Provisioned over SCIM: the role follows directory groups and cannot be changed here.",
    "require_mfa": "Members who sign in with a password must also use an authenticator app.",
    "mfa_checkable": "Whether this server can check second factors (its Keycloak admin client is configured).",
    "sso_enforced": "Whether single sign-on is enforced for members other than owners.",
    "protocol": "`saml` or `oidc`.",
    "issuer": "The identity provider's issuer URL (OIDC).",
    "client_id": "OIDC client id.",
    "client_secret": "OIDC client secret. Stored encrypted; never returned.",
    "sso_url": "The identity provider's single sign-on URL (SAML).",
    "signing_cert": "The identity provider's signing certificate, PEM (SAML).",
    "display_name": "Name shown on the sign-in button.",
    "domain": "Email domain, for example `example.com`.",
    "verified_at": "When ownership of the domain was verified.",
    "txt_name": "DNS name of the TXT record to create.",
    "txt_value": "Value of the TXT record.",
    "enforce": "Require single sign-on for everyone except owners.",
    "default_role": "Role given to people who join through single sign-on.",
    "StreamIn.kind": "`webhook`, `splunk_hec` or `datadog_logs`.",
    "site": "Datadog site, for example `datadoghq.com` or `datadoghq.eu`.",
    "api_key": "API key for the other service. Used as described on the endpoint; never returned.",
    "secret": "Shared secret used to sign deliveries (HMAC-SHA256). Never returned.",
    "url": "HTTPS URL. Private and internal addresses are refused.",
    "base_url": "Base URL of the other service, for a self-hosted instance.",
    "dry_run": "Report what would happen without changing anything.",
    "results": "One entry per item: what was or would be done.",
    "warnings": "Things to check after the import.",
    "event_types": "Event types to send. Empty means all.",
    "headers": "Extra HTTP headers to send.",
    "last_error": "The last delivery error, if any.",
    "slug": "URL name, lower case.",
    "visibility": "`public` or `unlisted`.",
    "question": "Your question, in plain language.",
    "bucket": "Bucket size: `hour` or `day`.",
    "t": "Start of the bucket (UTC).",
    "ok": "Successful runs.",
    "failed": "Failed runs.",
    "missed": "Missed runs.",
    "success_rate": "Successful runs as a percentage of runs.",
    "p50_ms": "Median duration in milliseconds.",
    "p95_ms": "95th-percentile duration in milliseconds.",
    "drift_pct": "Change in p95 duration compared with the previous period, in percent.",
    "reliability_score": "0–100 score combining success rate, missed runs and recovery time.",
    "mttd_min": "Average minutes from a failure to its alert.",
    "mttr_min": "Average minutes from an incident opening to its resolution.",
    "version": "Version.",
    "last_seen_at": "When it last reported.",
    "bootstrap_token": "One-time enrollment token. Returned only in this response.",
    "ttl_hours": "Hours until the token expires.",
    "depends_on_job_id": "The upstream job.",
}


U1, U2, U3 = "3f2a8c1e-6b7d-4e0a-9c51-2d8e4f1a7b90", "b71c0e94-2a3f-4d58-8e16-5f9a0c3d2e71", "0d9e5a72-8c41-4b3e-a6f0-7e2b1c9d4a58"
TS = "2026-10-01T02:00:07Z"
OK = {"ok": True}
# Example bodies for endpoints that return plain dicts (no response_model). Documentation only:
# nothing here changes what the API returns.
RESPONSE_EXAMPLES: dict[str, object] = {
    "GET /api/v1/jobs/{job_id}/next-runs": {"human": "At 02:00 every day", "runs": ["2026-10-02T02:00:00Z", "2026-10-03T02:00:00Z", "2026-10-04T02:00:00Z"]},
    "POST /api/v1/jobs/schedule/preview": {"expr": "0 2 * * *", "human": "At 02:00 every day", "next": ["2026-10-02T02:00:00Z", "2026-10-03T02:00:00Z"]},
    "GET /api/v1/executions/{execution_id}": {"execution": {"id": U1, "job_id": U2, "status": "failed", "started_at": TS, "finished_at": "2026-10-01T02:01:39Z",
        "duration_ms": 92000, "exit_code": 1, "host": "db-01", "stderr_tail": "pg_dump: error: connection to server failed", "metrics": {}, "anomalies": []},
        "timeline": [{"ts": TS, "kind": "start"}, {"ts": "2026-10-01T02:01:39Z", "kind": "fail"}]},
    "GET /api/v1/executions/{execution_id}/compare/{other_id}": {"a": {"id": U1, "status": "failed", "duration_ms": 92000}, "b": {"id": U2, "status": "success", "duration_ms": 88000},
        "delta": {"duration_ms": 4000, "exit_code": [1, 0], "only_in_a": ["pg_dump: error: connection to server failed"], "only_in_b": []}},
    "GET /api/v1/me": {"org_id": U1, "role": "devops", "user_id": None, "api_key_id": U2},
    "POST /api/v1/workspaces": {"id": U1, "name": "Payments"},
    "GET /api/v1/api-keys": [{"id": U1, "name": "terraform", "prefix": "cs_7Hc2", "role": "devops", "last_used_at": TS, "revoked_at": None, "created_at": TS}],
    "POST /api/v1/api-keys": {"id": U1, "prefix": "cs_7Hc2", "key": "cs_7Hc2.9fQ…", "note": "shown once; store securely"},
    "GET /api/v1/audit-logs": [{"id": U1, "actor_id": U2, "actor_type": "user", "action": "job.update", "target_type": "job", "target_id": U3, "ip": "203.0.113.7", "ts": TS, "payload": {"fields": ["grace_s"]}}],
    "POST /api/v1/alerts/channels": {"id": U1, "kind": "slack", "name": "#ops-alerts"},
    "POST /api/v1/alerts/channels/{channel_id}/test": {"queued": True},
    "POST /api/v1/alerts/rules": {"id": U1},
    "PATCH /api/v1/alerts/rules/{rule_id}": {"id": U1, "enabled": False},
    "GET /api/v1/alerts/ledger": [{"id": U1, "incident_id": U2, "channel_id": U3, "kind": "slack", "name": "#ops-alerts", "dedup_key": "job:failed:…", "sent_at": TS, "status": "sent", "error": None}],
    "GET /api/v1/incidents/{incident_id}": {"incident": {"id": U1, "title": "3 related jobs failing on db-01", "severity": "high", "status": "open", "detected_at": TS, "affected_job_ids": [U2, U3]},
        "downstream_impact": [{"id": U3, "name": "billing-reconciliation"}], "timeline": [{"ts": TS, "kind": "detected", "text": "nightly-database-backup failed"}],
        "notifications": [{"sent_at": TS, "kind": "slack", "name": "#ops-alerts", "status": "sent", "error": None}]},
    "POST /api/v1/incidents/{incident_id}/ack": OK, "POST /api/v1/incidents/{incident_id}/resolve": OK, "POST /api/v1/incidents/{incident_id}/notes": OK,
    "POST /api/v1/agents/bootstrap-token": {"token": "bt_4kQ…", "expires_in_s": 86400, "install": "curl -fsSL https://app.example.com/install.sh | sudo sh -s -- --token bt_4kQ…", "install_problem": None},
    "POST /api/v1/agents/{agent_id}/rotate": {"agent_key": "ak_Z2m…", "note": "update /etc/cronsentinel/agent.json and restart agent"},
    "POST /api/v1/status-pages": {"id": U1, "url": "/status/payments"},
    "GET /public/status/{slug}": {"title": "Acme scheduled jobs", "overall": "operational", "jobs": [{"name": "nightly-database-backup", "status": "healthy", "last_run_at": TS, "uptime_90d": 99.89}]},
    "GET /api/v1/clusters/{cluster_id}/cronjobs": {"cronjobs": [{"namespace": "billing", "name": "settle-batch", "schedule": "*/15 * * * *", "job_id": U1, "status": "healthy"}], "events": []},
    "POST /api/v1/dependencies": OK,
    "GET /api/v1/jobs/{job_id}/impact": {"upstream": [{"id": U2, "name": "nightly-database-backup"}], "downstream": [{"id": U3, "name": "billing-reconciliation"}]},
    "GET /api/v1/analytics/mttr": {"incidents": 12, "mttd_min": 1.4, "mtta_min": 6.2, "mttr_min": 42.5, "resolved": 11},
    "GET /api/v1/analytics/report": {"period": "week", "since": "2026-09-24T00:00:00+00:00", "runs": 1004, "success_rate": 97.2, "success_rate_prev": 97.0, "delta_pts": 0.2},
    "POST /api/v1/copilot/ask": {"id": U1, "answer": "The backup failed because the database was unreachable at 02:00…", "context": {"jobs": 1, "runs": 5}, "model": "claude", "latency_ms": 2140},
    "GET /api/v1/copilot/history": [{"id": U1, "question": "Why did nightly-database-backup fail last night?", "answer": "…", "job_id": U2, "incident_id": None, "model": "claude", "latency_ms": 2140, "created_at": TS}],
    "GET /api/v1/copilot/suggestions": {"questions": ["Which jobs got slower this week?", "What failed overnight and why?"]},
    "GET /api/v1/billing": {"subscription": {"plan": "team", "status": "active"}, "plans": [{"id": "team", "jobs": 100}], "usage": {"jobs": 42}, "limits": {"jobs": 100}, "configured": True},
    "POST /api/v1/billing/checkout": {"url": "https://checkout.stripe.com/c/pay/…"},
    "POST /api/v1/billing/portal": {"url": "https://billing.stripe.com/p/session/…"},
    "POST /api/v1/integrations/destinations": {"id": U1},
    "PUT /api/v1/integrations/destinations/{dest_id}": OK,
    "POST /api/v1/integrations/destinations/{dest_id}/test": {"ok": False, "error": "connection refused by hooks.example.com"},
    "GET /api/v1/org/export": {"organization": {"id": U1, "name": "Acme"}, "jobs": [], "executions": [], "incidents": [], "alert_rules": [], "audit_logs": []},
    "POST /api/v1/sso/scim-tokens": {"id": U1, "prefix": "scim_8Kq", "created_at": TS, "token": "scim_8Kq…", "base_url": "https://app.example.com/scim/v2"},
    "PUT /api/v1/sso/scim-groups/{group_id}/role": {"id": U1, "role": "sre", "members_updated": 14},
    "POST /api/v1/audit-streams/{stream_id}/test": OK,
    "POST /api/v1/metric-exports/{export_id}/test": OK,
    "POST /api/v1/oncall/schedules/{sid}/overrides": {"id": U1},
    "POST /api/v1/oncall/escalations/{rid}/ack": {"status": "acknowledged"},
    "POST /api/v1/oncall/policies/{pid}/channel": {"id": U1, "name": "Escalate: Platform on-call"},
    "GET /ping/{token}": {"ok": True, "execution_id": None},
    "POST /heartbeat/{token}/{status}": {"ok": True, "execution_id": None},
    "GET /heartbeat/{token}/{status}": {"ok": True, "execution_id": None},
    "POST /api/v1/heartbeat/{token}": {"ok": True, "execution_id": U1},
}
# Endpoints that return a documented model without declaring response_model.
RESPONSE_REFS = {"POST /api/v1/oncall/schedules": "ScheduleOut", "PUT /api/v1/oncall/schedules/{sid}": "ScheduleOut",
                 "POST /api/v1/oncall/policies": "PolicyOut", "PUT /api/v1/oncall/policies/{pid}": "PolicyOut"}

ROLE_TEXT = {"viewer": "Viewer", "developer": "Developer", "sre": "SRE", "devops": "DevOps", "admin": "Admin", "owner": "Owner"}
AUTH_HEADERS = {"authorization", "x-api-key", "x-org-id"}
_ERR = {"$ref": "#/components/schemas/Error"}


def _routes(routes):
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":       # FastAPI >= 0.140 wraps included routers
            yield from _routes(r.original_router.routes)
        elif hasattr(r, "routes") and not isinstance(r, APIRoute):
            yield from _routes(r.routes)
        else:
            yield r


def _auth(dep, found: dict):
    call = dep.call
    if call is not None:
        q = getattr(call, "__qualname__", "")
        if q == "require_role.<locals>.dep":
            found["role"] = call.__closure__[0].cell_contents
        elif q == "current_principal":
            found.setdefault("role", "viewer")
    for d in dep.dependencies:
        _auth(d, found)


def route_roles(app) -> dict[str, str]:
    """"METHOD path" -> minimum role, for every route that authenticates a principal."""
    out: dict[str, str] = {}
    for r in _routes(app.routes):
        if isinstance(r, APIRoute):
            found: dict = {}
            _auth(r.dependant, found)
            if "role" in found:
                for m in r.methods:
                    out[f"{m} {r.path}"] = found["role"]
    return out


def _clean(text: str) -> str:
    """Docstrings carry round references ("R43: ...") useful in the codebase but not in public docs."""
    return re.sub(r"\(?\bR\d+[a-z]?\b:?\)?\s*", "", text or "").strip()


def build(app, ingest_app=None) -> dict:
    spec = get_openapi(title="Argus API", version=app.version, routes=app.routes,
                       description="REST API for WeCrew Argus. See /docs/api in the web app for the full reference.")
    roles = route_roles(app)
    if ingest_app is not None:
        ing = get_openapi(title="ingest", version=app.version, routes=ingest_app.routes)
        for path, ops in ing["paths"].items():
            if path.startswith(("/ping/", "/heartbeat/", "/api/v1/heartbeat/")):
                for m, op in ops.items():
                    op["tags"] = ["pings"]
                    op["servers"] = [{"url": "https://ingest.example.com", "description": "Ingest host"}]
                    op["x-auth"] = "ping-token"
                spec["paths"].setdefault(path, {}).update(ops)
        for name, schema in ing.get("components", {}).get("schemas", {}).items():
            spec.setdefault("components", {}).setdefault("schemas", {}).setdefault(name, schema)

    comps = spec.setdefault("components", {})
    comps.setdefault("schemas", {})["Error"] = {
        "type": "object", "title": "Error", "required": ["detail"],
        "properties": {"detail": {"title": "Detail", "description": "What went wrong, in words. Validation errors (422) return a list of field errors instead.",
                                  "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "object"}}]}},
        "example": {"detail": "requires role >= devops"},
    }
    comps["securitySchemes"] = {
        "ApiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key",
                   "description": "An API key from Settings → API keys. The key's role decides what it may do."},
        "Bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                   "description": "A Keycloak access token for a user. Send the organization's id in `X-Org-Id`."},
        "Session": {"type": "apiKey", "in": "cookie", "name": "cs_session",
                    "description": "The web app's session cookie. State-changing requests also need the `X-CSRF-Token` header."},
    }
    for model, sch in comps["schemas"].items():
        for prop, ps in (sch.get("properties") or {}).items():
            if not ps.get("description"):
                d = FIELD_DOCS.get(f"{model}.{prop}") or FIELD_DOCS.get(prop)
                if d:
                    ps["description"] = d
    order = [t for t, _, _ in TAGS]
    spec["tags"] = [{"name": t, "x-displayName": n, "description": d} for t, n, d in TAGS]

    for path in list(spec["paths"]):
        if path in HIDDEN:
            del spec["paths"][path]
            continue
        for method, op in spec["paths"][path].items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            key = f"{method.upper()} {path}"
            if key in RETAG:
                op["tags"] = [RETAG[key]]
            elif not op.get("tags") or op["tags"][0] not in order:
                op["tags"] = ["public" if path.startswith("/public/") else (op.get("tags") or ["platform"])[0]]
            if key in DOCS:
                summary, desc = DOCS[key]
                op["summary"] = summary
                op["description"] = desc or _clean(op.get("description", ""))
            else:
                op["description"] = _clean(op.get("description", ""))
            if path.startswith(INTERNAL_PREFIXES) or key in INTERNAL:
                op["x-internal"] = True
            op["parameters"] = [p for p in op.get("parameters", []) if not (p.get("in") == "header" and p["name"].lower() in AUTH_HEADERS)]
            if not op["parameters"]:
                del op["parameters"]
            resp = op.setdefault("responses", {})
            two = next((c for c in resp if c.startswith("2")), None)
            if two and (key in RESPONSE_EXAMPLES or key in RESPONSE_REFS):
                media = resp[two].setdefault("content", {}).setdefault("application/json", {})
                if not media.get("schema"):
                    media["schema"] = {"$ref": f"#/components/schemas/{RESPONSE_REFS[key]}"} if key in RESPONSE_REFS and RESPONSE_REFS[key] in comps["schemas"] else {}
                if key in RESPONSE_EXAMPLES:
                    media["example"] = RESPONSE_EXAMPLES[key]
            role = roles.get(key)
            if role:
                op["x-min-role"] = role
                op["security"] = [{"ApiKey": []}, {"Bearer": []}, {"Session": []}]
                resp.setdefault("401", {"description": "Missing, invalid or expired credentials.", "content": {"application/json": {"schema": _ERR}}})
                resp.setdefault("403", {"description": f"The key or user's role is below {ROLE_TEXT[role]}, or the organization requires single sign-on.", "content": {"application/json": {"schema": _ERR}}})
                resp.setdefault("429", {"description": "Rate limit exceeded. Retry after the number of seconds in `Retry-After`.",
                                        "headers": {"Retry-After": {"schema": {"type": "integer"}, "description": "Seconds to wait."}},
                                        "content": {"application/json": {"schema": _ERR}}})
            elif op.get("x-auth") != "ping-token":
                op["security"] = []
            if "{" in path:
                resp.setdefault("404", {"description": "No such resource in this organization.", "content": {"application/json": {"schema": _ERR}}})
    return spec


def install(app):
    """Replace app.openapi with the documented build, cached like FastAPI's own."""
    def openapi():
        if not app.openapi_schema:
            try:
                from .ingest_main import app as ingest_app
            except Exception:                            # pragma: no cover - ingest optional in some deployments
                ingest_app = None
            app.openapi_schema = build(app, ingest_app)
        return app.openapi_schema
    app.openapi = openapi
