# Offline-First Mobile Sync with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Mobile users on flaky connections create and edit records while offline. When connectivity returns, changes must be merged with the server state without overwriting concurrent edits from other users or devices. A naive "last upload wins" strategy causes silent data loss that users discover days later.

---

## Context
The sync protocol uses a simple change-log approach: the client accumulates `{table, pk, op, payload, client_ts}` entries in an SQLite WAL while offline. On reconnect it POSTs the log to a Workers merge endpoint that applies each change with last-write-wins logic keyed on `server_ts`. The endpoint returns a monotonic `since` cursor so subsequent pulls fetch only the delta, keeping payloads small. Concurrent edits to the same primary key are surfaced as a conflict object the client UI can resolve. D1's global replication means the `server_ts` is authoritative regardless of which data-centre processes the write.

---

## Section 1 — D1 Schema & Wrangler Config

```toml
# wrangler.toml
name = "offline-sync-worker"
compatibility_date = "2025-06-01"

[[d1_databases]]
binding = "DB"
database_name = "sync_db"
database_id = "<YOUR_D1_DATABASE_ID>"
```

```bash
npx wrangler d1 execute sync_db --command "
CREATE TABLE IF NOT EXISTS items (
  pk         TEXT PRIMARY KEY,
  data       TEXT NOT NULL,
  server_ts  INTEGER NOT NULL,
  deleted    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_log (
  id         TEXT PRIMARY KEY,
  pk         TEXT NOT NULL,
  op         TEXT NOT NULL,   -- 'upsert' | 'delete'
  payload    TEXT,
  client_ts  INTEGER NOT NULL,
  server_ts  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sl_server_ts ON sync_log(server_ts);
"
```

---

## Section 2 — Workers Merge Endpoint

```typescript
// src/sync-worker.ts
export interface Env {
  DB: D1Database;
}

type ChangeOp = 'upsert' | 'delete';

type ClientChange = {
  table: string;   // only 'items' supported in this example
  pk: string;
  op: ChangeOp;
  payload?: Record<string, unknown>;
  client_ts: number;
};

type Conflict = {
  pk: string;
  client_ts: number;
  server_ts: number;
  server_data: unknown;
};

type SyncResponse = {
  applied: string[];
  conflicts: Conflict[];
  since: number;
  delta: unknown[];
};

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'POST' && url.pathname === '/sync/push') {
      return handlePush(req, env);
    }

    if (req.method === 'GET' && url.pathname === '/sync/pull') {
      return handlePull(req, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handlePush(req: Request, env: Env): Promise<Response> {
  const { changes } = await req.json<{ changes: ClientChange[] }>();

  if (!Array.isArray(changes) || changes.length > 500) {
    return Response.json({ error: 'Invalid payload' }, { status: 400 });
  }

  const applied: string[] = [];
  const conflicts: Conflict[] = [];
  const now = Date.now();

  for (const change of changes) {
    // Fetch current server state
    const existing = await env.DB
      .prepare('SELECT pk, data, server_ts, deleted FROM items WHERE pk = ?')
      .bind(change.pk)
      .first<{ pk: string; data: string; server_ts: number; deleted: number }>();

    // Conflict: server was modified AFTER the client read it
    if (existing && existing.server_ts > change.client_ts) {
      conflicts.push({
        pk: change.pk,
        client_ts: change.client_ts,
        server_ts: existing.server_ts,
        server_data: JSON.parse(existing.data),
      });
      continue;
    }

    if (change.op === 'upsert' && change.payload) {
      await env.DB
        .prepare(
          `INSERT INTO items (pk, data, server_ts, deleted)
           VALUES (?, ?, ?, 0)
           ON CONFLICT(pk) DO UPDATE SET
             data=excluded.data,
             server_ts=excluded.server_ts,
             deleted=0`,
        )
        .bind(change.pk, JSON.stringify(change.payload), now)
        .run();
    } else if (change.op === 'delete') {
      await env.DB
        .prepare('UPDATE items SET deleted=1, server_ts=? WHERE pk=?')
        .bind(now, change.pk)
        .run();
    }

    // Write to sync_log for audit and delta pulls
    await env.DB
      .prepare(
        `INSERT INTO sync_log (id, pk, op, payload, client_ts, server_ts)
         VALUES (?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        change.pk,
        change.op,
        change.payload ? JSON.stringify(change.payload) : null,
        change.client_ts,
        now,
      )
      .run();

    applied.push(change.pk);
  }

  const since = now;
  const response: SyncResponse = { applied, conflicts, since, delta: [] };
  return Response.json(response);
}

async function handlePull(req: Request, env: Env): Promise<Response> {
  const url = new URL(req.url);
  const since = Number(url.searchParams.get('since') ?? '0');

  const { results } = await env.DB
    .prepare('SELECT pk, op, payload, server_ts FROM sync_log WHERE server_ts > ? ORDER BY server_ts ASC LIMIT 500')
    .bind(since)
    .all<{ pk: string; op: string; payload: string | null; server_ts: number }>();

  const delta = results.map(r => ({
    pk: r.pk,
    op: r.op,
    payload: r.payload ? JSON.parse(r.payload) : null,
    server_ts: r.server_ts,
  }));

  const newSince = delta.length > 0 ? delta[delta.length - 1].server_ts : since;

  return Response.json({ delta, since: newSince });
}
```

---

## Section 3 — React Native Client Sync Manager

```typescript
// src/sync/manager.ts  (React Native side)
import AsyncStorage from '@react-native-async-storage/async-storage';

const SINCE_KEY = '@sync_since';
const QUEUE_KEY = '@sync_queue';
const WORKERS_URL = process.env.CF_WORKERS_BASE_URL ?? '';

type Change = {
  table: string;
  pk: string;
  op: 'upsert' | 'delete';
  payload?: Record<string, unknown>;
  client_ts: number;
};

export async function addChange(change: Omit<Change, 'client_ts'>) {
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  const queue: Change[] = raw ? JSON.parse(raw) : [];
  queue.push({ ...change, client_ts: Date.now() });
  await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

export async function sync(accessToken: string) {
  const raw = await AsyncStorage.getItem(QUEUE_KEY);
  const changes: Change[] = raw ? JSON.parse(raw) : [];

  if (changes.length > 0) {
    const res = await fetch(`${WORKERS_URL}/sync/push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ changes }),
    });

    const { applied, conflicts, since } = await res.json<{
      applied: string[];
      conflicts: Array<{ pk: string; server_data: unknown; server_ts: number }>;
      since: number;
    }>();

    if (conflicts.length > 0) {
      console.warn('[sync] conflicts detected', conflicts);
      // Emit event so UI can show a conflict resolution prompt
    }

    // Remove applied changes from queue
    const remaining = changes.filter(c => !applied.includes(c.pk));
    await AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
    await AsyncStorage.setItem(SINCE_KEY, String(since));
  }

  // Pull delta from server
  const sinceRaw = await AsyncStorage.getItem(SINCE_KEY);
  const since = sinceRaw ?? '0';
  const pullRes = await fetch(`${WORKERS_URL}/sync/pull?since=${since}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const { delta, since: newSince } = await pullRes.json<{ delta: unknown[]; since: number }>();

  await AsyncStorage.setItem(SINCE_KEY, String(newSince));
  return { delta };
}
```

---

## Anti-patterns
- **Using wall-clock `Date.now()` on the client as the authoritative timestamp** — clock skew between devices causes incorrect conflict detection; `server_ts` set by the Worker is the source of truth.
- **Sending the entire local database as a push on every sync** — diff only changed records; otherwise sync time grows linearly with data size.
- **Ignoring the `conflicts` array** — silently discarding conflicts causes data loss that users notice but cannot attribute.

---

## Gotchas
- D1 does not yet support transactions across multiple statements via the REST API; batch statements with `env.DB.batch([...])` to reduce round-trips but note each still commits independently.
- The `since` cursor is a millisecond timestamp — if two writes land within the same millisecond, the delta pull may miss one. Use a monotonic sequence if sub-millisecond write rates are expected.
- Deleting rows from `sync_log` must be done carefully; clients that haven't synced yet will miss changes if the log is pruned too aggressively.

---

## Verification

```bash
# Push a change
curl -X POST https://offline-sync-worker.example.workers.dev/sync/push \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <JWT>' \
  -d '{"changes":[{"table":"items","pk":"abc","op":"upsert","payload":{"name":"test"},"client_ts":0}]}'

# Pull the delta
curl "https://offline-sync-worker.example.workers.dev/sync/pull?since=0" \
  -H 'Authorization: Bearer <JWT>'

# Inspect D1
npx wrangler d1 execute sync_db --command "SELECT * FROM sync_log ORDER BY server_ts DESC LIMIT 10"
```

---

## Related
- `react-native-cloudflare-workers-api-client.md`
- `workers-biometric-webauthn-mobile-auth.md`

---

## Sources
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- CRDTs and last-write-wins — https://crdt.tech/
- React Native AsyncStorage — https://react-native-async-storage.github.io/async-storage/
