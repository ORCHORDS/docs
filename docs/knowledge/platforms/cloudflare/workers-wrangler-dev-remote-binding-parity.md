# Cloudflare Workers `wrangler dev --remote` — Binding Parity, Secrets Access, and Test-Prod Divergence

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker behaves correctly in `wrangler dev` (local mode) but fails or returns wrong data
in staging/production. Conversely, a `wrangler dev --remote` session crashes with "binding
not found" or reads stale secrets that have been rotated. Engineers waste hours chasing
environment divergence that a flag difference silently introduced.

## Context

Wrangler offers two dev modes:

| Mode | Where code runs | Bindings | Secrets |
|---|---|---|---|
| `wrangler dev` (default) | Miniflare (local) | Simulated / local mocks | `.dev.vars` file |
| `wrangler dev --remote` | Cloudflare edge | Real production bindings | Real Secrets Store / env secrets |

The distinction matters enormously for D1, KV, R2, Durable Objects, AI, Queues, Pipelines,
and Workers AI — all of which behave differently or are unavailable locally without
additional flags.

---

## Choosing the Right Mode

Use **local mode** when:
- Rapid iteration on business logic; no real data needed.
- Unit/integration tests via `vitest` with `@cloudflare/vitest-pool-workers`.
- You want a reproducible state machine (D1 `:memory:`, KV in-process).

Use **`--remote`** when:
- Testing binding-specific behaviour (D1 read-replica routing, DO geography, R2 ETags).
- Verifying secrets have been rotated and the Worker picks up the new value.
- Debugging production edge behaviour that Miniflare cannot reproduce.

---

## Local Mode Binding Simulation Gaps

Miniflare mocks are close but not identical to production. Known gaps as of 2026-08:

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "mydb"
database_id = "abc123"

[ai]
binding = "AI"
```

```ts
// In local mode, env.AI uses a stub that does NOT call Workers AI;
// you must use --remote or mock it yourself.
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // This throws locally unless you pass --remote:
    // "Workers AI is not available in local mode"
    const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      prompt: 'hello',
    });
    return Response.json(result);
  },
};
```

Workaround for local unit tests — inject a mock binding:

```ts
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        miniflare: {
          // Replace AI stub with a hand-rolled mock
          serviceBindings: {
            AI: async (req) => {
              return new Response(JSON.stringify({ response: 'mocked' }));
            },
          },
        },
      },
    },
  },
});
```

---

## Secrets Parity: `.dev.vars` vs Real Secrets

Local mode reads secrets from `.dev.vars` (never committed). Remote mode reads from
Cloudflare's Secrets Store (or legacy `wrangler secret put`).

```bash
# .dev.vars — local only, gitignored
STRIPE_SECRET_KEY=sk_test_abc
DATABASE_URL=postgres://localhost/dev

# Production secret (remote)
wrangler secret put STRIPE_SECRET_KEY   # prompts for value
```

Verify the remote value is active before `--remote` testing:

```bash
# List secrets without revealing values
wrangler secret list

# Check which version the deployed Worker is reading
# (requires Secrets Store, not legacy env secrets)
wrangler secrets-store secret get STRIPE_SECRET_KEY --store-id <id>
```

---

## Durable Object Name Resolution in Remote Mode

In remote mode, DO stubs resolve against the real namespace. A `wrangler dev --remote`
session **shares** the production DO namespace unless you use a separate environment.

```toml
# Isolate dev DOs with a staging environment
[env.staging.durable_objects]
bindings = [
  { name = "CHAT", class_name = "ChatRoom", script_name = "my-worker-staging" }
]
```

```bash
# Always target staging when testing DO mutation
wrangler dev --remote --env staging
```

Failing to isolate DO namespaces means your dev sessions corrupt production state in
Durable Objects that hold real user data.

---

## R2 Presigned URL Hostname Divergence

In local mode, `env.BUCKET.createPresignedUrl()` returns `http://localhost:…` URLs. In
remote mode the correct `<account>.r2.cloudflarestorage.com` hostname appears. Any code
that embeds those URLs in responses (e.g. video manifests) will break if tested locally
and deployed unchanged.

```ts
// Safe: always use the relative path in downstream manifests
const key = `uploads/${userId}/${filename}`;
const { url } = await env.BUCKET.createMultipartUpload(key);

// Never store env.BUCKET.createPresignedUrl() URL in D1 during local dev
// — the localhost URL will leak to production records
```

---

## Anti-patterns

- Treating `.dev.vars` as the authoritative secrets list; production may have secrets
  not reflected there, or deleted secrets still present in `.dev.vars`.
- Running `wrangler dev --remote` against the production D1 database to "quickly check
  a query" — writes are real and instant.
- Omitting `--env` with `--remote`; defaults to the production environment.
- Testing DO alarm scheduling locally — Miniflare alarm tick is synchronous/immediate;
  edge alarms have a ≥30 s minimum interval.

---

## Gotchas

- `wrangler dev --remote` counts against your Workers request quota (billed plan).
- Hot-reload (`--hot-reload`) is unavailable in remote mode.
- `wrangler dev` local mode silently accepts invalid KV key sizes; production throws.
- `compatibility_date` in `wrangler.toml` applies to both modes, but Miniflare may
  ship compatibility flag support weeks behind the edge.
- `--ip 0.0.0.0` is required to expose local dev to a LAN device (e.g. mobile testing).

---

## Verification

```bash
# Confirm mode and environment before destructive testing
wrangler dev --remote --env staging --log-level debug 2>&1 | head -20
# Should print: "Using remote bindings" and "env: staging"

# Confirm secrets are present in the target environment
wrangler secret list --env staging

# Dry-run a D1 query without committing
wrangler d1 execute mydb --env staging --command "SELECT count(*) FROM users" --preview
```

---

## Related

- `wrangler-check-startup-local-profile-boundary.md`
- `wrangler-production-build-test-harness.md`
- `workers-vitest-pool-integration-testing.md`
- `d1-best-practices.md`
- `secrets-store-binding-selection-and-blast-radius-control.md`

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/testing/local-development/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/d1/reference/local-development/
