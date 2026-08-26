# wrangler dev --local vs --remote Mode Decision Tree

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A developer starting `wrangler dev` is unsure whether to use local mode (the default) or
remote mode (`--remote`). The two modes have fundamentally different performance profiles,
binding behaviour, and fidelity guarantees. Choosing the wrong mode leads to either false-
positive green tests (local quirks masking production bugs) or slow iteration cycles
(remote round-trips for every hot-reload).

Teams also hit the boundary when they try to use bindings — D1 databases, R2 buckets, KV
namespaces, Durable Objects, Queues — and discover that local mode uses in-memory or
SQLite-backed stubs while remote mode connects to live production (or preview) resources.

## Context

Wrangler v3+ ships Miniflare 3 as the local simulation engine. Local mode runs the entire
Workers runtime (V8 isolates via `workerd`) on the developer's machine, with bindings
backed by local SQLite (D1), in-memory maps (KV), local filesystem (R2), and in-process
Durable Object instances. No Cloudflare network calls are made for the Worker or its
bindings.

Remote mode (`wrangler dev --remote`) uploads the Worker bundle to Cloudflare and runs it
on a real edge PoP in Cloudflare's network. Bindings resolve to real resources in the
account. Requests travel from the developer's machine to the edge and back. This mode is
slower to start and slower for each request but guarantees full production parity.

Understanding which mode to use, and when, prevents both slow loops and subtle
production-only bugs.

## Decision Tree

Use the following questions in order to choose a mode:

```
Q1: Does your Worker use any Cloudflare-specific runtime APIs that Miniflare does not simulate?
    (e.g. AI bindings, Vectorize, D1 remote-only features, Hyperdrive, Browser Rendering)
    YES → use --remote
    NO  → continue to Q2

Q2: Is your primary goal rapid iteration on business logic, not infrastructure behaviour?
    YES → use local (default) — fastest hot-reload
    NO  → continue to Q3

Q3: Does your test require real data already in production/preview D1, R2, or KV?
    YES → use --remote
    NO  → continue to Q4

Q4: Are you debugging a production incident where local behaviour differs from edge?
    YES → use --remote
    NO  → continue to Q5

Q5: Do you need to test Durable Object state persistence across restarts?
    YES → use --remote (local DO state is volatile across wrangler restarts)
    NO  → use local (default)
```

In summary:
- **Local (default)**: unit-style development, fast iteration, binding stubs, no network
- **Remote (`--remote`)**: integration/E2E testing, production data, edge-specific APIs

## Local Mode Configuration

Local mode is the default when you run `wrangler dev` without flags. Configure local
binding stubs in `wrangler.toml` or use the `--local` flag explicitly (redundant but
self-documenting in scripts).

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
# In local mode, Wrangler/Miniflare ignores database_id and creates a local SQLite

[[kv_namespaces]]
binding = "KV"
id = "ffffffffffffffffffffffffffffffff"
# In local mode, in-memory KV; data does not persist across restarts by default

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "my-bucket"
# In local mode, stored in .wrangler/state/v3/r2/
```

```bash
# Explicit local mode (equivalent to default)
wrangler dev --local

# Persist local D1/KV/R2 state across restarts (stored in .wrangler/state/)
wrangler dev --persist-to .wrangler/state

# Use a custom port
wrangler dev --port 8787 --local
```

The `.wrangler/state/` directory should be in `.gitignore`:

```gitignore
# .gitignore
.wrangler/
```

## Remote Mode Configuration

Remote mode requires an active Cloudflare account with the Worker's bindings already
provisioned. The preview URL is a real `workers.dev` subdomain.

```bash
# Basic remote mode
wrangler dev --remote

# Remote mode against a named environment (e.g. staging bindings)
wrangler dev --remote --env staging

# Remote mode with a custom compatibility date override
wrangler dev --remote --compatibility-date 2025-06-01
```

When using remote mode you must authenticate first:

```bash
wrangler login
# or, in CI/CD with a service token:
CLOUDFLARE_API_TOKEN=<token> wrangler dev --remote
```

Remote mode creates a short-lived preview deployment under `wrangler.dev` that shares
bindings with the environment specified (default: `production` bindings unless `--env` is
set). Writes to KV, D1, or R2 in remote dev mode affect REAL data — be cautious.

## Hybrid Pattern: Local Worker + Remote Preview Bindings

Wrangler 3.x introduced `--experimental-local` with remote bindings:

```bash
# Run Worker locally but resolve KV/D1/R2 to Cloudflare preview resources
wrangler dev --local --experimental-remote-bindings
```

This mode is useful when:
- You want fast local hot-reload for Worker logic
- But your local SQLite does not have the seed data needed for the test
- And you do not want full remote round-trips for every request

Status: experimental as of Wrangler 3.x; check `wrangler dev --help` for availability.

## Durable Object Considerations

Local mode creates in-process Durable Object instances. State is written to
`.wrangler/state/v3/do/`. Between `wrangler dev` restarts, state persists only if
`--persist-to` is set. Without `--persist-to`, each restart starts with an empty DO
namespace.

Remote mode uses real Durable Objects. IDs are stable across restarts; state persists
normally. This is the mode to use when testing DO state migration logic or alarm
scheduling across restarts.

```toml
# wrangler.toml — DO binding
[[durable_objects.bindings]]
name = "MY_DO"
class_name = "MyDurableObject"
# In local mode, instantiated in-process by Miniflare
# In remote mode, runs on Cloudflare's global network
```

```bash
# Remote mode DO dev — state is real and persistent
wrangler dev --remote

# Local mode with persisted DO state
wrangler dev --local --persist-to .wrangler/state
```

## CI/CD Mode Selection

In CI pipelines, `wrangler dev` is rarely the right tool. Use Vitest with
`@cloudflare/vitest-pool-workers` for unit/integration tests (local Miniflare) and deploy
to a preview environment for E2E:

```yaml
# .github/workflows/ci.yml
jobs:
  unit-test:
    steps:
      - run: pnpm vitest run   # uses Miniflare locally, no wrangler dev needed

  e2e-test:
    steps:
      - run: wrangler deploy --env preview  # deploy to preview
      - run: pnpm playwright test           # hit the preview URL
```

## Anti-patterns

- Running `wrangler dev --remote` for all development — remote mode is 5–30× slower per
  request than local mode; it wastes time during rapid iteration.
- Assuming local mode perfectly replicates production — it does not; Miniflare's V8 build
  may differ from edge V8, and some APIs (AI, Vectorize, Browser Rendering) are not
  simulated.
- Writing to production KV/D1/R2 via `wrangler dev --remote` without an isolated
  preview environment — this corrupts production data.
- Not setting `--persist-to` in local mode when testing stateful Workers — state loss on
  each restart produces unreliable test results.
- Using `wrangler dev --env production` in CI — this connects to live production bindings
  and may generate load or write data.

## Gotchas

- `wrangler dev --remote` does NOT use the `[env.staging]` wrangler.toml section unless
  `--env staging` is explicitly passed.
- Local mode does not enforce Cloudflare's CPU and memory limits. A Worker that works
  locally may hit the 10 ms CPU limit in production.
- The local Worker URL is `http://localhost:8787` by default; the remote preview URL is a
  `*.workers.dev` or custom domain — ensure test scripts target the correct URL.
- Hot-reload in remote mode recompiles and re-uploads the bundle on every file save, which
  takes 2–10 seconds depending on bundle size and network latency.
- `wrangler dev` in local mode does not log to the Cloudflare dashboard; only `wrangler tail`
  (which requires remote deployment) streams production logs.

## Verification

```bash
# Verify local mode: check that requests do NOT appear in Cloudflare dashboard logs
wrangler dev --local
curl http://localhost:8787/

# Verify remote mode: request appears in wrangler tail
wrangler dev --remote &
DEV_PID=$!
wrangler tail my-worker --format json &
TAIL_PID=$!
sleep 2
curl https://<preview-id>.my-worker.workers.dev/
sleep 2
kill $DEV_PID $TAIL_PID
# Tail output should show one event from the curl request
```

## Related

- `wrangler-dev-local-d1-r2-kv.md` — local binding configuration details
- `wrangler-dev-remote-d1-r2-bindings.md` — remote binding setup
- `miniflare-v4-migration-guide.md` — Miniflare simulation engine
- `durable-objects-local-debugging.md` — DO local debugging specifics

## Sources

- Cloudflare Docs: "Local development" — https://developers.cloudflare.com/workers/local-development/
- Cloudflare Docs: "wrangler dev" command reference — https://developers.cloudflare.com/workers/wrangler/commands/#dev
- Miniflare docs: "How Miniflare works" — https://miniflare.dev/get-started/api
