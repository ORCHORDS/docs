# Durable Objects: Concurrent Fetch Deadlock

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two Durable Objects (DO) called each other via `fetch()` during the same request cycle. Both stubs were awaiting a response from each other simultaneously. The Worker handling the original request hung for the full 30-second wall-clock limit before terminating with a 524 timeout error.

## Context

- Cloudflare Workers + Durable Objects
- TypeScript, Wrangler v3
- Production incident on 2026-08-20; affected ~400 req/min for ~12 minutes
- Two DOs: `SessionDO` (manages user session state) and `PresenceDO` (manages online presence)

## Timeline

1. 14:03 UTC — Deploy pushed; new code path added a `PresenceDO.fetch()` call inside `SessionDO`'s alarm handler
2. 14:05 UTC — Error rate climbs; tail Worker starts emitting `fetchFailed: subrequest limit` and silent 524s
3. 14:07 UTC — On-call notified via PagerDuty
4. 14:08 UTC — Team identifies circular call: `SessionDO → PresenceDO → SessionDO`
5. 14:15 UTC — Rollback deployed; error rate returns to baseline

## Root Cause

Cloudflare's subrequest model prohibits circular dependencies between Durable Objects within a single execution context. When `SessionDO` called `PresenceDO.fetch()`, and `PresenceDO`'s handler in turn called `SessionDO.fetch()`, both objects were blocking on each other. Because Durable Objects are single-threaded per instance, neither could proceed—a classic deadlock.

The Cloudflare runtime does not raise an immediate error for circular subrequests in all cases; instead the request hangs until the 30-second CPU/wall-clock limit is reached.

```
SessionDO.alarm()
  └─ await presenceDO.fetch('/sync')      ← blocks here
        └─ PresenceDO handler
              └─ await sessionDO.fetch('/state')  ← blocks here
                    └─ (never resolves)
```

## Fix

Replace the synchronous circular call with an **async queue pattern**: `SessionDO` writes sync data into a Cloudflare Queue message. `PresenceDO` subscribes as a Queue consumer and processes updates without calling back into `SessionDO`.

```typescript
// wrangler.toml additions
// [[queues.producers]]
// queue = "presence-sync"
// binding = "PRESENCE_QUEUE"
//
// [[queues.consumers]]
// queue = "presence-sync"
// max_batch_size = 10

// SessionDO — no longer calls PresenceDO directly
export class SessionDO implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async alarm(): Promise<void> {
    const sessionData = await this.state.storage.get<SessionData>('session');
    if (!sessionData) return;

    // Enqueue instead of calling PresenceDO directly
    await this.env.PRESENCE_QUEUE.send({
      userId: sessionData.userId,
      lastSeen: Date.now(),
      sessionId: this.state.id.toString(),
    });

    // Reschedule alarm
    await this.state.storage.setAlarm(Date.now() + 30_000);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/state') {
      const data = await this.state.storage.get<SessionData>('session');
      return Response.json(data ?? {});
    }
    return new Response('Not found', { status: 404 });
  }
}

// PresenceDO — consumes Queue messages, never calls SessionDO
export class PresenceDO implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/presence') {
      const map = await this.state.storage.get<Record<string, number>>('presence') ?? {};
      return Response.json(map);
    }
    return new Response('Not found', { status: 404 });
  }

  // Called by Queue consumer Worker, not by another DO
  async syncPresence(userId: string, lastSeen: number): Promise<void> {
    const map = await this.state.storage.get<Record<string, number>>('presence') ?? {};
    map[userId] = lastSeen;
    await this.state.storage.put('presence', map);
  }
}

// Queue consumer Worker
export default {
  async queue(batch: MessageBatch<PresenceSyncMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const stub = env.PRESENCE_DO.get(
        env.PRESENCE_DO.idFromName('global')
      );
      await stub.fetch(new Request('https://do/sync', {
        method: 'POST',
        body: JSON.stringify(msg.body),
      }));
      msg.ack();
    }
  },
};
```

## Prevention

Use a tail Worker to detect DO-to-DO subrequest chains before they cause incidents:

```typescript
// tail-worker.ts
export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      const subrequests = event.diagnosticsChannelEvents ?? [];
      const doFetches = subrequests.filter(
        (e) => typeof e.message === 'object' && (e.message as any)?.type === 'subrequest'
      );

      // Alert on deep subrequest chains (potential circular risk)
      if (doFetches.length > 5) {
        await env.ALERTS_QUEUE.send({
          type: 'deep-subrequest-chain',
          scriptName: event.scriptName,
          count: doFetches.length,
          timestamp: Date.now(),
        });
      }
    }
  },
};
```

Also add a static analysis lint rule:

```typescript
// scripts/lint-do-calls.ts  — run in CI
import { parse } from '@typescript-eslint/typescript-estree';
import * as fs from 'fs';
import * as glob from 'glob';

const files = glob.sync('src/**/*.ts');
for (const file of files) {
  const src = fs.readFileSync(file, 'utf8');
  // Naive heuristic: flag any DO class that calls another DO stub fetch inside its own fetch/alarm
  if (/class.*DurableObject/.test(src) && /stub\.fetch/.test(src)) {
    const calledDOs = src.match(/env\.(\w+DO)\.get/g) ?? [];
    if (calledDOs.length > 1) {
      console.warn(`[lint-do-calls] ${file}: multiple DO stubs obtained — verify no circular calls`);
    }
  }
}
```

## Anti-patterns

- Calling `stubB.fetch()` inside DO class A when DO class B also calls `stubA.fetch()` — even indirectly
- Using Durable Objects for synchronous request/response patterns that require data from another DO
- Alarm handlers that trigger full DO-to-DO synchronization chains
- Not configuring a tail Worker to observe subrequest depth

## Gotchas

- The Cloudflare runtime does not always immediately surface a `circular subrequest` error; the hang is the first observable symptom
- CPU time and wall-clock time limits are both relevant; DOs may hit wall-clock (30 s) before CPU
- Queue consumers run in a separate execution context, breaking the circular dependency cleanly
- `MessageBatch.messages` must all be `ack()`'d or `retry()`'d; an uncaught exception will retry the whole batch

## Verification

```bash
# 1. Deploy the fix
npx wrangler deploy

# 2. Trigger a session alarm manually via the DO REST API
curl -X POST https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/durable_objects/namespaces/$DO_NAMESPACE_ID/objects/$DO_ID/storage \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json"

# 3. Watch tail Worker output for subrequest depth alerts
npx wrangler tail presence-sync-consumer --format pretty

# 4. Confirm Queue messages are being produced and consumed
npx wrangler queues messages list presence-sync

# 5. Load test with k6 to verify no 524s under concurrent load
k6 run --vus 50 --duration 60s scripts/k6-session-load.js
```

## Related

- `lessons-queues-consumer-exception-infinite-retry.md` — Queue consumer error handling
- `lessons-workers-fetch-no-abort-signal-hang.md` — Worker fetch timeout patterns

## Sources

- https://developers.cloudflare.com/durable-objects/best-practices/create-durable-object-stubs-and-send-requests/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/durable-objects/reference/limits/
