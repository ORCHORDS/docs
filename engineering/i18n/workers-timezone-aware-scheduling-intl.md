# Timezone-Aware Job Scheduling in Cloudflare Workers with Intl.DateTimeFormat

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to fire a recurring job (daily digest, weekly report, reminder notification) at a wall-clock time meaningful to each user—say 09:00 in their local timezone—but your Worker runs on UTC-only cron triggers. Naively scheduling at `0 9 * * *` UTC will be wrong for everyone outside UTC.

## Context

- Cloudflare Workers Cron Triggers (UTC only)
- D1 (SQLite) storing user records with IANA timezone strings (`America/New_York`, `Europe/Berlin`)
- Scheduled Worker that wakes every minute or every hour, computes which users are "due", and enqueues work via Queues or executes directly
- `Intl.DateTimeFormat` available in the V8 runtime (no npm package needed)

---

## Section 1: Storing IANA Timezone Strings in D1

Create the users table with a `timezone` column validated at write time.

```sql
-- migration: 0001_users.sql
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,
  email       TEXT NOT NULL UNIQUE,
  timezone    TEXT NOT NULL DEFAULT 'UTC',  -- IANA tz, e.g. 'America/Chicago'
  notify_hour INTEGER NOT NULL DEFAULT 9,   -- desired local hour (0-23)
  notify_min  INTEGER NOT NULL DEFAULT 0,
  last_fired  TEXT                          -- ISO-8601 UTC of last job run
);

CREATE INDEX idx_users_notify ON users(notify_hour, notify_min);
```

```typescript
// src/db/upsert-user.ts
import type { D1Database } from '@cloudflare/workers-types';

const VALID_TZ_RE = /^[A-Za-z]+\/[A-Za-z_]+(\/[A-Za-z_]+)?$/;

export async function upsertUser(
  db: D1Database,
  id: string,
  email: string,
  timezone: string,
  notifyHour: number,
  notifyMin: number,
): Promise<void> {
  if (!VALID_TZ_RE.test(timezone)) {
    throw new Error(`Invalid IANA timezone: ${timezone}`);
  }
  // Validate the timezone is actually recognised by the runtime
  try {
    new Intl.DateTimeFormat('en', { timeZone: timezone });
  } catch {
    throw new Error(`Unknown timezone: ${timezone}`);
  }

  await db
    .prepare(
      `INSERT INTO users (id, email, timezone, notify_hour, notify_min)
       VALUES (?1, ?2, ?3, ?4, ?5)
       ON CONFLICT(id) DO UPDATE SET
         email = excluded.email,
         timezone = excluded.timezone,
         notify_hour = excluded.notify_hour,
         notify_min = excluded.notify_min`,
    )
    .bind(id, email, timezone, notifyHour, notifyMin)
    .run();
}
```

---

## Section 2: Resolving Next-Fire-Time with Intl.DateTimeFormat

`Intl.DateTimeFormat` lets you decompose a UTC instant into local date parts for any IANA timezone without a library.

```typescript
// src/scheduler/next-fire.ts

/**
 * Returns true if the given UTC Date is within the same clock-minute
 * as the user's desired local notify_hour:notify_min.
 */
export function isDueNow(
  nowUtc: Date,
  timezone: string,
  notifyHour: number,
  notifyMin: number,
): boolean {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    hour: 'numeric',
    minute: 'numeric',
    hour12: false,
  });

  const parts = fmt.formatToParts(nowUtc);
  const get = (type: string) =>
    parseInt(parts.find((p) => p.type === type)?.value ?? '0', 10);

  const localHour = get('hour');   // 0-23
  const localMin  = get('minute'); // 0-59

  return localHour === notifyHour && localMin === notifyMin;
}

/**
 * Compute the next UTC timestamp at which notifyHour:notifyMin occurs
 * in the given timezone, starting from nowUtc + 1 minute.
 */
export function nextFireUtc(
  nowUtc: Date,
  timezone: string,
  notifyHour: number,
  notifyMin: number,
): Date {
  // Walk forward minute-by-minute (max 1440 iterations)
  const candidate = new Date(nowUtc);
  candidate.setUTCSeconds(0, 0);
  candidate.setUTCMinutes(candidate.getUTCMinutes() + 1);

  for (let i = 0; i < 1440; i++) {
    if (isDueNow(candidate, timezone, notifyHour, notifyMin)) {
      return candidate;
    }
    candidate.setUTCMinutes(candidate.getUTCMinutes() + 1);
  }
  throw new Error('Could not find next fire time within 24 h');
}
```

---

## Section 3: Cron Worker Converting UTC to Local and Firing Jobs

```typescript
// src/workers/scheduler.ts
import type { ScheduledController, Env } from './types';
import { isDueNow } from '../scheduler/next-fire';

export interface Env {
  DB: D1Database;
  JOB_QUEUE: Queue;
}

export default {
  async scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext) {
    const nowUtc = new Date(event.scheduledTime); // ms since epoch

    // Fetch all users — paginate in production
    const { results } = await env.DB
      .prepare(
        `SELECT id, email, timezone, notify_hour, notify_min, last_fired
         FROM users
         ORDER BY id`,
      )
      .all<{
        id: string;
        email: string;
        timezone: string;
        notify_hour: number;
        notify_min: number;
        last_fired: string | null;
      }>();

    const due = results.filter((u) => {
      // Guard: already fired within the last 30 min to avoid duplicate
      if (u.last_fired) {
        const lastMs = new Date(u.last_fired).getTime();
        if (nowUtc.getTime() - lastMs < 30 * 60 * 1000) return false;
      }
      return isDueNow(nowUtc, u.timezone, u.notify_hour, u.notify_min);
    });

    if (due.length === 0) return;

    // Enqueue jobs in a single batch
    await env.JOB_QUEUE.sendBatch(
      due.map((u) => ({ body: { userId: u.id, email: u.email } })),
    );

    // Mark last_fired
    const nowIso = nowUtc.toISOString();
    const stmt = env.DB.prepare(
      `UPDATE users SET last_fired = ?1 WHERE id = ?2`,
    );
    await env.DB.batch(due.map((u) => stmt.bind(nowIso, u.id)));
  },
};
```

Wrangler config (`wrangler.toml`):

```toml
name = "scheduler-worker"
main = "src/workers/scheduler.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "prod-db"
database_id = "<your-d1-id>"

[[queues.producers]]
binding = "JOB_QUEUE"
queue = "job-queue"

[triggers]
crons = ["* * * * *"]  # every minute — consider "0 * * * *" if sub-hour precision not needed
```

---

## Anti-patterns

- **Storing UTC offset integers** (`-5`) instead of IANA strings — offsets change with DST and are therefore unreliable.
- **Computing local time with arithmetic** (`utcHour + offset`) — breaks during DST transitions.
- **Running cron every minute for millions of users** without pagination — batch with `LIMIT`/`OFFSET` or Cursor pagination and distribute work across multiple invocations.
- **Not deduplicating** with `last_fired` — the same user may match two consecutive cron minutes if the cron fires slightly late.

## Gotchas

- `Intl.DateTimeFormat` `hour12: false` returns `'24'` for midnight in some locales instead of `'0'` — normalise with `% 24`.
- D1 has no native DATETIME timezone conversion; all timezone math must happen in application code.
- Workers scheduled time (`event.scheduledTime`) is in milliseconds, not seconds — pass `new Date(event.scheduledTime)`, not `new Date(event.scheduledTime * 1000)`.
- Queue `sendBatch` is limited to 100 messages per call — chunk `due` array if it may exceed 100.

---

## Verification

```bash
# Apply D1 migration locally
npx wrangler d1 execute prod-db --local --file=migrations/0001_users.sql

# Seed a test user in America/New_York, wants 09:00 local
npx wrangler d1 execute prod-db --local --command \
  "INSERT INTO users VALUES ('u1','test@example.com','America/New_York',9,0,NULL)"

# Run scheduled worker with a fake time matching 09:00 ET (= 13:00 UTC in EST)
npx wrangler dev --test-scheduled
# In another terminal:
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*&time=$(date -d '13:00 UTC' +%s)000"

# Confirm last_fired updated
npx wrangler d1 execute prod-db --local --command "SELECT id, last_fired FROM users"
```

---

## Related

- `documentation/categories/i18n/workers-collator-locale-sort-d1-sqlite.md`
- `documentation/categories/i18n/workers-intl-displaynames-locale-labels.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
