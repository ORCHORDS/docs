# Debug Tooling for Durable Objects Local Development

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You are building a Cloudflare Durable Object — a stateful, single-instance class that coordinates
state across requests. Local debugging is harder than with a regular Worker: the DO instance lives
in a remote location, its SQLite storage is not directly inspectable, and alarm scheduling is
difficult to trigger manually. You need to understand which DO instance is being hit, inspect its
stored state, step through the handler logic in a debugger, and verify that alarms fire on the
correct schedule.

## Context

Durable Objects (DOs) are single-threaded, in-memory objects backed by durable SQLite storage.
Each DO instance has a globally unique `DurableObjectId` and is pinned to a single Cloudflare
data-centre location. During local development, Miniflare (the local Workers runtime embedded in
`wrangler dev`) simulates DO behaviour: it creates local SQLite files for each DO instance,
executes DO class methods in a local `workerd` process, and supports the V8 inspector protocol
for step-through debugging.

Key local development tools:
- `wrangler dev` — runs the Worker and DOs locally via Miniflare/workerd
- `wrangler dev --inspect` / Chrome DevTools — step-through debugging
- `.wrangler/state/` — local SQLite storage for DOs (inspectable with any SQLite client)
- `wrangler tail` — log streaming from local DO executions (limited locally)
- DO alarm testing patterns — manually triggering alarms in dev

## Basic Local Dev Setup

Declare the DO in `wrangler.toml`:

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[durable_objects.bindings]]
name = "CHAT_ROOM"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["ChatRoom"]
```

Using `new_sqlite_classes` (as opposed to the older `new_classes`) enables the SQLite storage
backend, which is the default and recommended option for new DOs.

Start the local dev server:

```bash
pnpm wrangler dev
# or: pnpm wrangler dev --local   (explicit, same as default in Wrangler 3+)
```

## Step-Through Debugging with Chrome DevTools

Enable the V8 inspector:

```bash
pnpm wrangler dev --inspect
```

Wrangler starts a debugging server on `127.0.0.1:9229` by default. Open Chrome and navigate to:

```
chrome://inspect
```

Under "Remote Target" you will see the Worker listed. Click **inspect** to open a DevTools window
connected to the `workerd` V8 isolate.

DO method calls are visible as separate call stacks. Set breakpoints inside your DO class:

```typescript
export class ChatRoom implements DurableObject {
  private storage: DurableObjectStorage;

  constructor(state: DurableObjectState, env: Env) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    // Set a breakpoint here in DevTools to inspect incoming requests
    const url = new URL(request.url);

    if (url.pathname === '/message') {
      const body = await request.json<{ text: string }>();
      // Breakpoint here: inspect body before writing to storage
      await this.storage.put(`msg:${Date.now()}`, body.text);
      return Response.json({ ok: true });
    }

    const messages = await this.storage.list({ prefix: 'msg:' });
    return Response.json(Object.fromEntries(messages));
  }
}
```

**Important**: `workerd` restarts on file save, which resets all active breakpoints. Use
conditional breakpoints or `debugger` statements in code for durable breakpoint positions.

## Inspecting Local DO Storage

Wrangler stores local DO SQLite databases under:

```
.wrangler/state/v3/durable_objects/<namespace-id>/blobs/
```

Each DO instance is a separate `.sqlite` file. Inspect with any SQLite client:

```bash
# List DO instance databases
ls .wrangler/state/v3/durable_objects/

# Open with sqlite3 CLI
sqlite3 .wrangler/state/v3/durable_objects/<namespace-id>/blobs/<instance-id>.sqlite

# Inside sqlite3
.tables
SELECT key, hex(value) FROM _cf_KV;   -- Durable Objects KV storage
```

For DO SQL (new API, available in 2024+):

```sql
-- Inside a DO using state.storage.sql
SELECT * FROM your_custom_table;
```

The SQLite file reflects the exact state of the DO instance after each request. You can:
- Read data to verify writes
- Seed data by inserting rows directly (useful for testing specific states)
- Delete the file to reset a DO instance to empty state

## Resetting a DO Instance

To reset a specific DO instance (wipe its storage) during development:

```bash
# Stop wrangler dev
# Delete the instance's SQLite file
rm .wrangler/state/v3/durable_objects/<namespace-id>/blobs/<instance-id>.sqlite
# Restart wrangler dev
```

To reset all DO instances for a binding:

```bash
rm -rf .wrangler/state/v3/durable_objects/<namespace-id>/
```

The DO will start fresh (empty storage) on the next request.

## Identifying DO Instances

In production and locally, each DO instance is identified by a `DurableObjectId`. Two ways to
obtain IDs in the Worker:

```typescript
// Named IDs: human-readable, deterministic
const id = env.CHAT_ROOM.idFromName('room-general');

// System-generated IDs: cryptographically random, not human-readable
const id = env.CHAT_ROOM.newUniqueId();
```

Log the ID string during development to correlate it with the SQLite filename:

```typescript
const id = env.CHAT_ROOM.idFromName('room-general');
console.log('[DO] instance id:', id.toString());
const stub = env.CHAT_ROOM.get(id);
```

The `id.toString()` value (a hex string) corresponds to the SQLite filename under
`.wrangler/state/v3/durable_objects/`.

## Testing DO Alarms Locally

DO alarms fire at a scheduled wall-clock time. Testing them locally requires either waiting for
the time to pass or using a short delay:

```typescript
// In your DO handler — set an alarm 5 seconds from now for quick local testing
async fetch(request: Request): Promise<Response> {
  if (new URL(request.url).pathname === '/arm-alarm') {
    await this.storage.setAlarm(Date.now() + 5_000);
    return Response.json({ scheduled: true });
  }
  return Response.json({ ok: true });
}

async alarm(): Promise<void> {
  console.log('[DO] alarm fired at', new Date().toISOString());
  // alarm logic here
}
```

Trigger via curl:

```bash
curl http://localhost:8787/arm-alarm
# Wait 5 seconds
# Observe wrangler dev output: "[DO] alarm fired at ..."
```

For automated tests, use the Miniflare `runMicrotasks()` / `runDurableObjectAlarm()` API in
Vitest (see `vitest-workers-miniflare-testing-setup.md`).

## Vitest Unit Tests for DO Logic

Isolate DO logic from the network by testing the class directly with Miniflare:

```typescript
// tests/chat-room.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env, createExecutionContext, SELF } from 'cloudflare:test';

describe('ChatRoom', () => {
  it('stores and retrieves messages', async () => {
    const id = env.CHAT_ROOM.idFromName('test-room');
    const stub = env.CHAT_ROOM.get(id);

    // Post a message
    const res1 = await stub.fetch('http://do/message', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ text: 'hello' }),
    });
    expect(res1.ok).toBe(true);

    // Retrieve messages
    const res2 = await stub.fetch('http://do/');
    const data = await res2.json();
    expect(Object.values(data)).toContain('hello');
  });
});
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

## Console Logging and Log Levels

`console.log` inside a DO handler outputs to the `wrangler dev` terminal. Prefix logs with
the DO class name and instance ID for easy filtering:

```typescript
export class ChatRoom implements DurableObject {
  private id: string;

  constructor(state: DurableObjectState, env: Env) {
    this.id = state.id.toString().slice(0, 8);  // short prefix for readability
  }

  async fetch(request: Request): Promise<Response> {
    console.log(`[ChatRoom:${this.id}] ${request.method} ${new URL(request.url).pathname}`);
    // ...
  }
}
```

Filter wrangler output in a separate terminal:

```bash
pnpm wrangler dev 2>&1 | grep '\[ChatRoom'
```

## Anti-patterns

**Testing DO behaviour exclusively via HTTP round-trips** — testing the full Worker → DO →
storage → response path is important, but unit-testing the DO class methods directly with
Miniflare is faster and more targeted for complex state logic.

**Hardcoding `Date.now()` for alarm scheduling in tests** — alarms based on `Date.now()` are
non-deterministic in tests. Use `vi.useFakeTimers()` or structure alarm delay as a configurable
constant.

**Sharing a DO instance between tests** — each test should use a unique `idFromName` (e.g.,
`idFromName(crypto.randomUUID())`) to prevent state bleed between tests.

**Inspecting `.wrangler/state/` during a running `wrangler dev` session** — SQLite may have
uncommitted pages in the WAL. Stop `wrangler dev` before running raw SQLite queries on the
files to avoid reading stale state.

## Gotchas

- `wrangler dev --inspect` opens the debugger on port `9229`. If another process is using that
  port, Wrangler will fail silently. Kill the conflicting process or use `--inspector-port 9230`.
- DO constructor runs once per isolate lifetime. Reloads (on save) restart the isolate and
  re-run the constructor. In-memory state (instance variables not persisted to `this.storage`)
  is lost on reload.
- The Cloudflare dashboard "Durable Objects" explorer does not work for local `wrangler dev`
  instances — it shows only production. Use the SQLite files or console logs for local inspection.
- `state.storage.sql` (the SQL API) and `state.storage` (the KV API) use separate tables. Do
  not mix them for the same conceptual data.
- Alarm handlers must complete within the Workers CPU time limit (30s on Paid plan). Log
  completion time during development to catch slow alarm handlers early.

## Verification

```bash
# Confirm DO is responding locally
curl http://localhost:8787/api/room/general

# Confirm storage file exists after first request
ls .wrangler/state/v3/durable_objects/

# Inspect storage
sqlite3 .wrangler/state/v3/durable_objects/**/*.sqlite ".tables"

# Run unit tests
pnpm vitest run tests/chat-room.test.ts

# Test alarm firing (5-second arm)
curl http://localhost:8787/arm-alarm
# Wait 5 seconds, observe wrangler output for alarm log
```

## Related

- `vitest-workers-miniflare-testing-setup.md` — unit testing Workers and DOs with Miniflare
- `wrangler-dev-local-d1-r2-kv.md` — local binding emulation for D1, R2, KV
- `wrangler-dev-local-mocking.md` — mocking external services in local dev
- `opentelemetry-workers-tracing-setup.md` — distributed tracing including DO spans
- `vscode-debugging-config.md` — VS Code launch.json for attaching to wrangler inspect

## Sources

- Cloudflare Workers documentation: "Durable Objects" — developers.cloudflare.com
- Cloudflare Workers documentation: "Local development" — Miniflare and wrangler dev
- Miniflare v3 release notes: SQLite Durable Objects support (2024)
- Cloudflare blog: "Durable Objects: now with SQL" (2024)
- Wrangler 3 changelog: `--inspect` flag and V8 inspector integration
