# Cron Trigger `scheduled()` Handler Not Firing During `wrangler dev` Local Testing

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker defines a `scheduled()` export to handle cron triggers, but the handler never fires when running `wrangler dev` locally. The Worker starts up, HTTP requests are handled normally, but the scheduled handler is silent regardless of how long the developer waits. There is no error message indicating the cron is broken — it simply never runs.

---

## Context

Cloudflare's cron trigger system fires `scheduled()` handlers on the Cloudflare global network according to the cron expression in `wrangler.toml`. When running `wrangler dev` locally, the Worker is served by Miniflare (or the newer `workerd` local runtime), which does *not* automatically emulate the Cloudflare cron scheduler. The scheduled handler is present in the Worker bundle but there is no local process that fires it on the configured schedule. Developers expecting the handler to fire locally — the way a Node.js `setInterval` would — are surprised to find it never runs. The fix requires either using the built-in `/__scheduled` HTTP endpoint exposed by `wrangler dev`, using the `--test-scheduled` flag, or writing a test harness that calls the handler directly.

---

## What Went Wrong

```toml
# wrangler.toml
name = "my-cron-worker"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[triggers]
crons = ["*/5 * * * *"]   # every 5 minutes
```

```typescript
// src/index.ts
import type { ScheduledEvent, Env, ExecutionContext } from '@cloudflare/workers-types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return new Response('Worker is up');
  },

  // ❌ Never fires automatically during `wrangler dev`
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log('Cron fired at', new Date(event.scheduledTime).toISOString());
    await doWork(env);
  },
};

async function doWork(env: Env): Promise<void> {
  // ... business logic
}
```

The developer runs:

```bash
wrangler dev
# Worker starts at http://localhost:8787
# Waits 5+ minutes... scheduled() never fires
```

## Root Cause

`wrangler dev` provides a local HTTP server for testing the `fetch()` handler but does not include a cron scheduler. The Cloudflare production scheduler is a separate system on the global network that dispatches `scheduled` events to Workers on the configured timetable. Miniflare / `workerd` intentionally does not replicate this scheduler to avoid unexpected background activity during local development. The `scheduled()` export exists in the compiled Worker but nothing calls it.

## The Fix

### Option 1 — Use the `/__scheduled` HTTP endpoint (no flags needed)

```bash
# Terminal 1: start wrangler dev normally
wrangler dev

# Terminal 2: manually trigger the scheduled handler via HTTP
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# The cron query parameter is URL-encoded: spaces become +
# For a specific cron expression, encode it:
curl "http://localhost:8787/__scheduled?cron=*%2F5+*+*+*+*"

# Expected: HTTP 200 and the scheduled() handler runs,
# printing its log output in the wrangler dev terminal.
```

### Option 2 — `--test-scheduled` flag (enables `/__scheduled` and logs cron dispatches)

```bash
wrangler dev --test-scheduled

# Now curl the endpoint as in Option 1.
# With --test-scheduled, wrangler also prints a reminder in the startup banner:
#   "Scheduled events can be tested using: curl /__scheduled"
```

### Option 3 — Call the handler directly in a Vitest / Workers test

```typescript
// src/index.test.ts
import { describe, it, expect, vi } from 'vitest';
import worker from './index';
import type { ScheduledController, Env, ExecutionContext } from '@cloudflare/workers-types';

describe('scheduled handler', () => {
  it('runs without throwing', async () => {
    const env = {
      // Mock bindings as needed
      DB: {
        prepare: vi.fn().mockReturnThis(),
        bind: vi.fn().mockReturnThis(),
        run: vi.fn().mockResolvedValue({ success: true }),
      },
    } as unknown as Env;

    const ctx = {
      waitUntil: vi.fn(),
      passThroughOnException: vi.fn(),
    } as unknown as ExecutionContext;

    const event = {
      scheduledTime: Date.now(),
      cron: '*/5 * * * *',
      noRetry: vi.fn(),
    } as unknown as ScheduledController;

    await expect(worker.scheduled(event, env, ctx)).resolves.toBeUndefined();
  });
});
```

### Option 4 — Validate cron expression with `cron-parser`

```bash
npm install --save-dev cron-parser
```

```typescript
// scripts/validate-crons.ts
import { parseExpression } from 'cron-parser';

const expressions = [
  '*/5 * * * *',
  '0 9 * * 1',   // every Monday at 09:00 UTC
  '0 0 1 * *',   // first day of month
];

for (const expr of expressions) {
  try {
    const interval = parseExpression(expr);
    const next = interval.next().toDate();
    console.log(`✓ "${expr}" — next fire: ${next.toISOString()}`);
  } catch (err) {
    console.error(`✗ "${expr}" — invalid: ${(err as Error).message}`);
    process.exit(1);
  }
}
```

```bash
npx tsx scripts/validate-crons.ts
```

## Verification

```bash
# 1. Start local dev server
wrangler dev --test-scheduled &

# 2. Trigger scheduled handler manually
curl -s "http://localhost:8787/__scheduled?cron=*+*+*+*+*"
# Expected output: HTTP 200 OK (empty body or {"success":true})

# 3. Confirm handler log appears in wrangler dev output
# Look for: Cron fired at <ISO timestamp>

# 4. Run vitest unit test for the handler
npx vitest run src/index.test.ts

# 5. Validate cron expressions in CI
npx tsx scripts/validate-crons.ts
```

---

## Anti-patterns

- **Waiting for the cron to fire naturally during `wrangler dev`** — The local dev server has no scheduler; the handler will never fire unless explicitly triggered via `/__scheduled` or a test.
- **Deploying to production to test the cron handler** — Wastes deploy cycles and makes iteration slow. Use `/__scheduled` locally first.
- **Hardcoding `scheduledTime` in tests as `0` or a fixed number** — Tests that depend on a specific `scheduledTime` value are fragile. Accept any valid timestamp.
- **Omitting the `ctx.waitUntil()` wrapper for async work inside `scheduled()`** — Work not wrapped in `waitUntil()` may be cancelled when the scheduled event budget expires, especially for operations slower than a few seconds.

---

## Gotchas

- The `/__scheduled` endpoint is only available in `wrangler dev`; it does not exist in production. Do not reference it in production monitoring or health-check scripts.
- The `cron` query parameter in `/__scheduled?cron=...` must be URL-encoded. Spaces in cron expressions should be encoded as `+` or `%20`, and `*` should be left as `*` (it is safe in query strings).
- Cloudflare cron expressions support 5-field standard cron syntax. They do not support seconds (6-field) or the `@hourly`/`@daily` shorthand macros — `cron-parser` supports these extensions by default; pass `{ strict: true }` or avoid non-standard syntax to match Cloudflare's parser.
- A `scheduled()` handler that throws will be retried by the Cloudflare scheduler up to 3 times. Design the handler to be idempotent so retries do not cause duplicate side effects.
- `wrangler tail` does not surface `scheduled()` invocation logs unless `--format pretty` is used and the Worker has been deployed with logging enabled. Local `wrangler dev` output is the most reliable way to see scheduled handler logs during development.

---

## Related

- `d1-prepare-throws-on-missing-column.md`
- `workers-crypto-randomuuid-not-available-old-compat.md`

---

## Sources

- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Wrangler dev --test-scheduled flag — https://developers.cloudflare.com/workers/wrangler/commands/#dev
- cron-parser npm package — https://www.npmjs.com/package/cron-parser
- Miniflare scheduled events — https://miniflare.dev/core/scheduled
