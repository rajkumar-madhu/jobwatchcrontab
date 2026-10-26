# Contributing to JobWatch

Thanks for looking. The fastest way to help right now is to **run it on a real server and tell us what
was confusing** — open an issue titled "Install notes: …" with what you expected and what happened.
A screen-shared install with the founder is also welcome: contact@wecrew.in.

## Running the tests

```bash
# API (Postgres 16 and Redis on localhost; NATS optional — tests needing it skip without it)
cd apps/api && pip install -e '.[dev]' && alembic upgrade head && pytest -q        # ~80 s, 1,060+ tests
# Web
cd apps/web && npm ci && npm test && npm run test:e2e                              # vitest, then Playwright against tools/ui-review/mock_api.py
# Agents
cd agents/linux-agent && go test ./...
```
`docs/DEVELOPMENT.md` has the full setup, including the mock API the UI tests run against.

## Changes

- One pull request per change, against `main`. CI (`.github/workflows/ci.yml`) must be green.
- A behaviour change comes with a test in the suite that would have caught its absence, and a line in
  `CHANGELOG.md` under the next release heading.
- A schema change is an Alembic migration with a `downgrade()` (or a comment saying why not) and a bump
  of the head in `tests/integration/test_migrations.py`.
- Public API changes regenerate `apps/web/openapi.json` (`npm run types:gen`).
- Keep the style you find: short modules, SQL in plain text, comments that say *why*, a release tag
  (`R74:`) on anything a reader of the changelog would want to find.

## Licence of contributions

The server is AGPL-3.0 and the agents Apache-2.0 (see `LICENSE`, `agents/LICENSE`). By submitting a
change you agree it is licensed under the licence of the directory it touches, and you grant WeCrew the
right to offer the server under a commercial licence as well (this is what pays for the hosted service
and the maintenance). If that is not acceptable to you or your employer, say so in the PR and we will
talk before merging.

## Security issues

Not in a public issue, please: see `SECURITY.md`.
