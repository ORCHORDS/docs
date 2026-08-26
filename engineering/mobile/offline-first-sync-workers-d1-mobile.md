# Offline-First Sync Between React Native and Workers + D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your React Native app must work fully offline and sync changes when connectivity is restored. Users may edit data on multiple devices simultaneously. You need a sync protocol where the mobile client sends batched local mutations to a Cloudflare Worker, the Worker applies them to D1 with last-write-wins conflict resolution keyed on `updated_at`, and the Worker returns the set of server-side changes the client has not yet seen.

---

## Context
Offline-first sync is one of the hardest distributed-systems problems in mobile development. This implementation deliberately keeps it simple: each row carries an `updated_at` ISO timestamp, the client tracks the `last_synced_at` cursor in local storage, and conflict resolution is last-write-wins by timestamp. The sync endpoint is idempotent — replaying the same mutation batch is safe because each mutation carries the client's proposed `updated_at`, and the Worker only applies it if no newer server record exists. The response delta lets the client pull any rows changed on the server (by other devices or background jobs) since its last sync.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "sync-api"
main = "src/sync.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "mobile-db"
database_id = "<YOUR_D1_DATABASE_ID>"
```

```sql
-- D1 migration: 0002_notes.sql
CREATE TABLE IF NOT EXISTS notes (
  id          TEXT    PRIMARY KEY,        -- client-generated UUID
  user_id     TEXT    NOT NULL,
  content     TEXT    NOT NULL DEFAULT '',
  deleted     INTEGER NOT NULL DEFAULT 0, -- soft-delete flag
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user_updated
  ON notes(user_id, updated_at);
```

---

## Section 2 — Worker implementation

```typescript
// src/sync.ts
import { Hono } from 'hono';

type Bindings = { DB: D1Database };
const app = new Hono<{ Bindings: Bindings }>();

interface Mutation {
  id: string;
  content: string;
  deleted: boolean;
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
}

interface SyncRequest {
  userId: string;
  lastSyncedAt: string | null; // ISO 8601 or null for first sync
  mutations: Mutation[];
}

interface SyncResponse {
  appliedCount: number;
  skippedCount: number;
  delta: Mutation[];
  serverTime: string;
}

app.post('/sync', async (c) => {
  const { userId, lastSyncedAt, mutations } =
    await c.req.json<SyncRequest>();

  if (!userId) return c.json({ error: 'missing_user_id' }, 400);

  let appliedCount = 0;
  let skippedCount = 0;

  // ── apply mutations ─────────────────────────────────────────────────────
  const stmt = c.env.DB.prepare(`
    INSERT INTO notes (id, user_id, content, deleted, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      content    = CASE WHEN excluded.updated_at > notes.updated_at
                        THEN excluded.content    ELSE notes.content    END,
      deleted    = CASE WHEN excluded.updated_at > notes.updated_at
                        THEN excluded.deleted    ELSE notes.deleted    END,
      updated_at = CASE WHEN excluded.updated_at > notes.updated_at
                        THEN excluded.updated_at ELSE notes.updated_at END
    RETURNING (excluded.updated_at > notes.updated_at OR notes.id IS NULL) AS applied
  `);

  for (const m of mutations) {
    // Guard: only allow mutations belonging to the authenticated user
    // (in production, derive userId from the JWT; do not trust request body)
    const result = await stmt
      .bind(m.id, userId, m.content, m.deleted ? 1 : 0, m.created_at, m.updated_at)
      .first<{ applied: number }>();
    if (result?.applied) {
      appliedCount++;
    } else {
      skippedCount++;
    }
  }

  // ── fetch delta ──────────────────────────────────────────────────────────
  let delta: Mutation[] = [];
  if (lastSyncedAt) {
    const rows = await c.env.DB.prepare(`
      SELECT id, content, deleted, created_at, updated_at
      FROM notes
      WHERE user_id = ? AND updated_at > ?
      ORDER BY updated_at ASC
      LIMIT 500
    `).bind(userId, lastSyncedAt).all<Omit<Mutation, 'deleted'> & { deleted: number }>();

    delta = rows.results.map((r) => ({ ...r, deleted: r.deleted === 1 }));
  } else {
    // First sync: return all rows for this user
    const rows = await c.env.DB.prepare(`
      SELECT id, content, deleted, created_at, updated_at
      FROM notes WHERE user_id = ? ORDER BY updated_at ASC
    `).bind(userId).all<Omit<Mutation, 'deleted'> & { deleted: number }>();
    delta = rows.results.map((r) => ({ ...r, deleted: r.deleted === 1 }));
  }

  const serverTime = new Date().toISOString();
  return c.json<SyncResponse>({ appliedCount, skippedCount, delta, serverTime });
});

export default app;
```

---

## Section 3 — Client-side (React Native / Expo)

```typescript
// lib/syncEngine.ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiFetch } from './apiClient';

const CURSOR_KEY = 'sync_cursor';
const PENDING_KEY = 'sync_pending_mutations';

export interface Note {
  id: string;
  content: string;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

// ── local mutation queue ───────────────────────────────────────────────────
export async function enqueueMutation(note: Note): Promise<void> {
  const raw = await AsyncStorage.getItem(PENDING_KEY);
  const pending: Note[] = raw ? JSON.parse(raw) : [];

  // Upsert: replace existing mutation for same id
  const idx = pending.findIndex((n) => n.id === note.id);
  if (idx >= 0) pending[idx] = note;
  else pending.push(note);

  await AsyncStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}

// ── sync ───────────────────────────────────────────────────────────────────
export async function sync(
  userId: string,
  localNotes: Map<string, Note>,
  onDelta: (notes: Note[]) => void
): Promise<void> {
  const lastSyncedAt = await AsyncStorage.getItem(CURSOR_KEY);
  const raw = await AsyncStorage.getItem(PENDING_KEY);
  const mutations: Note[] = raw ? JSON.parse(raw) : [];

  const res = await apiFetch('/sync', {
    method: 'POST',
    body: JSON.stringify({ userId, lastSyncedAt, mutations }),
  });

  if (!res.ok) throw new Error(`sync_failed: ${res.status}`);

  const { delta, serverTime } = await res.json<{
    delta: Note[];
    serverTime: string;
    appliedCount: number;
    skippedCount: number;
  }>();

  // Apply delta to local store
  if (delta.length > 0) onDelta(delta);

  // Clear pending mutations that were included in this sync
  const sentIds = new Set(mutations.map((m) => m.id));
  const rawAfter = await AsyncStorage.getItem(PENDING_KEY);
  const stillPending: Note[] = rawAfter
    ? (JSON.parse(rawAfter) as Note[]).filter((n) => !sentIds.has(n.id))
    : [];

  await AsyncStorage.multiSet([
    [PENDING_KEY, JSON.stringify(stillPending)],
    [CURSOR_KEY, serverTime],
  ]);
}
```

---

## Anti-patterns
- **Trusting `userId` from the request body** — always derive the user identity from a verified JWT; an attacker can overwrite any user's data by spoofing the userId.
- **Using wall-clock time for conflict resolution without NTP** — mobile clocks drift; consider a logical clock (vector clock or server-assigned sequence) for stricter ordering.
- **Fetching unlimited delta rows** — without the `LIMIT 500` guard, a first-sync or long-offline client can cause a D1 timeout or excessive memory use.
- **Clearing the pending queue before the network call succeeds** — always clear only after a successful server acknowledgement.

---

## Gotchas
- D1's `ON CONFLICT DO UPDATE ... RETURNING` requires SQLite 3.35+; D1 runs SQLite 3.45+ so this is safe.
- ISO 8601 string comparison works for lexicographic ordering only when the format is consistent (`YYYY-MM-DDTHH:MM:SS.mmmZ`). Use `new Date().toISOString()` everywhere.
- The `LIMIT 500` on the delta query means a client that has been offline for a long time may need multiple sync rounds. Increment `lastSyncedAt` to the last row's `updated_at` after each round.
- `AsyncStorage.multiSet` is atomic per key but not a real transaction; if the app crashes between clearing PENDING and saving the new CURSOR the next sync will re-send already-applied mutations, which is safe because the `ON CONFLICT` logic is idempotent.

---

## Verification
```bash
# Apply migration
npx wrangler d1 execute mobile-db --file=0002_notes.sql

# Deploy
npx wrangler deploy

# First sync (no cursor)
curl -s -X POST https://sync-api.orchords.workers.dev/sync \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user:alice","lastSyncedAt":null,"mutations":[{"id":"note-1","content":"Hello","deleted":false,"created_at":"2026-08-24T10:00:00.000Z","updated_at":"2026-08-24T10:00:00.000Z"}]}' | jq .

# Subsequent sync with cursor
curl -s -X POST https://sync-api.orchords.workers.dev/sync \
  -H 'Content-Type: application/json' \
  -d '{"userId":"user:alice","lastSyncedAt":"2026-08-24T10:00:00.000Z","mutations":[]}' | jq .
```

---

## Related
- `react-native-expo-cloudflare-workers-api.md`
- `mobile-deep-link-routing-workers.md`

---

## Sources
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- SQLite ON CONFLICT — https://www.sqlite.org/lang_conflict.html
- React Native AsyncStorage — https://react-native-async-storage.github.io/async-storage/
