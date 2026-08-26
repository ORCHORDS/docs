# wrangler dev Local Development — Binding Mocking and Log Streaming

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A Cloudflare Worker that reads from KV, queries D1, and writes to
an R2 bucket cannot be tested locally without either deploying to a
staging environment or writing extensive mock objects in unit tests.
Hot-reload cycles that require a full `wrangler deploy` take 30–60
seconds and consume staging quota. Cron triggers cannot be fired
manually from the terminal. Tail logs from the live worker arrive
with 10–30 second delays via the dashboard.

## Context

The platform team runs Workers for API routing, background queue
processing, and scheduled tasks. Local development must mirror
production binding semantics without requiring network access to
Cloudflare's control plane on every save. `wrangler dev` powered
by Miniflare 3 provides local KV, D1, R2, and Queue emulation with
sub-second reload. `wrangler tail` streams production and staging
logs into the terminal for live debugging.

## Local Mode vs --remote Mode

```bash
# Local mode (default): bindings are emulated by Miniflare
wrangler dev

# Remote mode: bindings connect to real Cloudflare resources
wrangler dev --remote
```

| Dimension          | Local (Miniflare)         | Remote (`--remote`)        |
|--------------------|---------------------------|----------------------------|
| KV reads/writes    | in-process SQLite          | real KV namespace          |
| D1 queries         | libsql in-process          | real D1 database           |
| R2 operations      | local filesystem           | real R2 bucket             |
| Queue dispatch     | in-process queue           | real Queue                 |
| Network requests   | real (no intercept)        | real                       |
| Startup time       | ~1 s                       | ~5–10 s (auth roundtrip)   |
| Data persistence   | temp dir (wiped on stop)   | persistent                 |
| Rate limits        | none                       | account limits apply        |

Use `--remote` when you need to verify behavior against production
data shapes or test D1 migrations that haven't been applied locally.
Use local mode for all rapid iteration.

## Binding Mocking — D1, KV, R2

`wrangler.toml` declares bindings. In local mode Miniflare satisfies
them without credentials — `DB` becomes an in-process libsql DB,
`CACHE` an in-memory KV store, `DOCUMENTS` a temp directory under
`.wrangler/state/`.

```toml
[[d1_databases]]
binding = "DB"
database_name = "shipments"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "CACHE"
id = "yyyyyyyy"

[[r2_buckets]]
binding = "DOCUMENTS"
bucket_name = "shipment-docs"
```

```bash
# Apply migrations and seed fixture data locally
wrangler d1 migrations apply shipments --local
wrangler d1 execute shipments --local \
  --file=./test/fixtures/seed.sql
```

## Durable Objects and State Persistence

Durable Objects run in Miniflare's in-process runtime. State is
cleared on each `wrangler dev` restart by default. Persist across
restarts with:

```bash
wrangler dev --persist-to .wrangler/state
```

Commit `.wrangler/state/` to seed a shared local state for the
team, or add it to `.gitignore` to keep state personal.

## Testing Scheduled Cron Triggers

```toml
# wrangler.toml
[triggers]
crons = ["0 * * * *"]   # hourly
```

```bash
# Start dev server with cron test mode
wrangler dev --test-scheduled

# In a second terminal: fire the scheduled handler manually
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"
```

`--test-scheduled` exposes `/__scheduled` on the dev server URL.
The `cron` query parameter must match the format in the URL (spaces
encoded as `+`). The scheduled handler runs synchronously and the
response body contains any logged output.

## Environment Variable Injection

`.dev.vars` is the Workers-native equivalent of `.env`. Place it
in the project root — `wrangler dev` loads it automatically.

```
# .dev.vars  (gitignored)
STRIPE_KEY=sk_test_abc
LOG_LEVEL=debug
```

```
# .gitignore
.dev.vars
.wrangler/state/
```

Secrets set via `wrangler secret put` are unavailable in local mode
— mirror them in `.dev.vars`. `.dev.vars` values override same-name
`vars` entries in `wrangler.toml`.

## wrangler tail — Log Streaming

```bash
# Stream logs from staging; filter to errors only
wrangler tail shipment-worker --env staging --status error

# Trace a specific request by header
wrangler tail shipment-worker --header "x-request-id:req-abc123"

# JSON output for jq
wrangler tail shipment-worker --format json | jq '.logs[].message'
```

`wrangler tail` opens a WebSocket to Cloudflare's tail API. Events
arrive within ~1–2 seconds. `--status` accepts `ok`, `error`, or
`canceled`; multiple `--header` flags are ANDed.

## Anti-patterns

- Using `--remote` as the default dev mode — 5x slower feedback
  and mutations hit real data.
- Skipping `wrangler d1 migrations apply --local` after pulling
  schema changes — local schema diverges silently.
- Committing `.dev.vars` or `.wrangler/state/` — state contains
  SQLite WAL files; not portable across machines.
- Using `wrangler tail` instead of structured logging — tail is
  best-effort; use Logpush to R2 for durable log drains.

## Gotchas

- `.dev.vars` overrides `vars` in `wrangler.toml` — useful
  intentionally, confusing by accident.
- Default port is `localhost:8787`; use `--port 8788` if in use.
- Queue consumers with internal service bindings need
  `--local-protocol https` — plain HTTP causes a bind error.
- `--test-scheduled` and `--remote` are mutually exclusive.

## Verification

```bash
wrangler dev
# Startup output should include:
#   [d1] Loaded DB (local)
#   [kv] Loaded CACHE (local)

curl http://localhost:8787/health          # {"status":"ok"}
curl "http://localhost:8787/__scheduled?cron=0+*+*+*+*"
# {"scheduled":true}
```

## Related

- `devtools/orbstack-docker-desktop-apple-silicon.md`
- `cloudflare/d1-query-patterns.md`
- `cloudflare/kv-caching-strategy.md`
- `cloudflare/r2-storage-patterns.md`
- `cloudflare/queues-consumer-patterns.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/testing/miniflare/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/d1/wrangler-commands/#d1-migrations-apply
- https://developers.cloudflare.com/workers/configuration/secrets/#secrets-in-development
