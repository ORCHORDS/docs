# Locale-Aware Push Notification Scheduling with Workers Queues

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A global SaaS platform sends push notifications (Web Push / FCM) to users across 30+
locales and timezone regions. Blasting all users at the same UTC time means German users
receive "daily digest" notifications at 3 AM and Brazilian users at midnight. You need a
system that schedules each notification for a locale-appropriate delivery window
(e.g. 09:00–11:00 in the user's local timezone), translates the notification payload
into the user's locale on the fly, and routes messages through Workers Queues for
reliable at-least-once delivery.

## Context

Cloudflare Workers Queues support delayed message delivery via `delaySeconds` (up to 12
hours). Combined with user timezone data in KV and translated notification templates in
D1, you can compute the delay needed to land each notification in the target delivery
window and fan messages out to locale-grouped queues. Workers AI handles dynamic
personalization of notification copy.

Applicable stack: Workers, Workers Queues, KV, D1, optional Workers AI.

---

## 1. User Preference Storage (KV)

```typescript
// src/lib/user-prefs.ts
import type { KVNamespace } from '@cloudflare/workers-types';

export interface UserPrefs {
  locale: string;       // BCP 47, e.g. "pt-BR"
  timezone: string;     // IANA, e.g. "America/Sao_Paulo"
  fcmToken: string;
  notifyWindowStart: number; // local hour, e.g. 9
  notifyWindowEnd: number;   // local hour, e.g. 11
  optedOut: boolean;
}

export async function getUserPrefs(
  kv: KVNamespace,
  userId: string,
): Promise<UserPrefs | null> {
  const raw = await kv.get(`user:${userId}:prefs`);
  return raw ? (JSON.parse(raw) as UserPrefs) : null;
}

export async function setUserPrefs(
  kv: KVNamespace,
  userId: string,
  prefs: UserPrefs,
): Promise<void> {
  // Validate timezone
  Intl.DateTimeFormat(undefined, { timeZone: prefs.timezone });
  // Validate locale
  new Intl.Locale(prefs.locale);
  await kv.put(`user:${userId}:prefs`, JSON.stringify(prefs), {
    expirationTtl: 86400 * 90,
  });
}
```

---

## 2. Computing Delivery Delay in Seconds

```typescript
// src/lib/delivery-delay.ts
import { Temporal } from '@js-temporal/polyfill';

interface DeliveryWindow {
  startHour: number; // inclusive, local time
  endHour: number;   // exclusive, local time
}

/**
 * Returns the number of seconds from `nowUtc` until the next occurrence
 * of the delivery window in the user's timezone. Returns 0 if already
 * inside the window.
 */
export function secondsUntilDeliveryWindow(
  nowUtc: Temporal.Instant,
  timeZone: string,
  window: DeliveryWindow,
): number {
  const zonedNow = nowUtc.toZonedDateTimeISO(timeZone);
  const localHour = zonedNow.hour;

  if (localHour >= window.startHour && localHour < window.endHour) {
    return 0; // already in window — deliver now
  }

  // Next window start: today or tomorrow
  let targetDate = zonedNow.toPlainDate();
  if (localHour >= window.endHour) {
    targetDate = targetDate.add({ days: 1 });
  }

  const targetZoned = Temporal.ZonedDateTime.from({
    timeZone,
    year: targetDate.year,
    month: targetDate.month,
    day: targetDate.day,
    hour: window.startHour,
    minute: 0,
    second: 0,
  });

  const delayNs = targetZoned.toInstant().epochNanoseconds - nowUtc.epochNanoseconds;
  const delaySec = Math.ceil(Number(delayNs) / 1e9);

  // Workers Queues max delay is 43200 seconds (12 hours)
  return Math.min(delaySec, 43200);
}
```

---

## 3. Notification Template Storage in D1

```sql
-- migration 001_notification_templates.sql

CREATE TABLE notification_templates (
  id          TEXT NOT NULL,         -- e.g. "daily_digest"
  locale      TEXT NOT NULL,
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,         -- ICU MessageFormat pattern
  -- e.g. "You have {count, plural, one {# new message} other {# new messages}}"
  image_url   TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (id, locale)
);

-- Fallback row for 'en' must always exist per template id
```

```typescript
// src/lib/templates.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface NotificationTemplate {
  title: string;
  body: string;
  image_url: string | null;
}

export async function getTemplate(
  db: D1Database,
  templateId: string,
  locale: string,
): Promise<NotificationTemplate> {
  // Try exact locale, then language subtag, then 'en' fallback
  const localeTag = new Intl.Locale(locale);
  const candidates = [locale, localeTag.language, 'en'];

  for (const candidate of candidates) {
    const row = await db
      .prepare(
        `SELECT title, body, image_url
         FROM notification_templates
         WHERE id = ? AND locale = ?
         LIMIT 1`,
      )
      .bind(templateId, candidate)
      .first<NotificationTemplate>();
    if (row) return row;
  }

  throw new Error(`No template found for ${templateId} in any fallback locale`);
}
```

---

## 4. Queueing Notifications with Computed Delay

```typescript
// src/lib/notify-scheduler.ts
import type { Queue, KVNamespace, D1Database } from '@cloudflare/workers-types';
import { Temporal } from '@js-temporal/polyfill';
import { getUserPrefs } from './user-prefs';
import { secondsUntilDeliveryWindow } from './delivery-delay';
import { getTemplate } from './templates';

export interface PushJob {
  userId: string;
  templateId: string;
  params: Record<string, string | number>;
}

export interface PushMessage {
  userId: string;
  fcmToken: string;
  locale: string;
  title: string;
  body: string;
  imageUrl: string | null;
}

export async function scheduleNotification(
  queue: Queue<PushMessage>,
  kv: KVNamespace,
  db: D1Database,
  job: PushJob,
): Promise<void> {
  const prefs = await getUserPrefs(kv, job.userId);
  if (!prefs || prefs.optedOut) return;

  const template = await getTemplate(db, job.templateId, prefs.locale);

  // Resolve ICU MessageFormat pattern (basic implementation)
  const body = resolveTemplate(template.body, job.params, prefs.locale);
  const title = resolveTemplate(template.title, job.params, prefs.locale);

  const nowUtc = Temporal.Now.instant();
  const delaySec = secondsUntilDeliveryWindow(nowUtc, prefs.timezone, {
    startHour: prefs.notifyWindowStart,
    endHour: prefs.notifyWindowEnd,
  });

  await queue.send(
    {
      userId: job.userId,
      fcmToken: prefs.fcmToken,
      locale: prefs.locale,
      title,
      body,
      imageUrl: template.image_url,
    },
    { delaySeconds: delaySec },
  );
}

function resolveTemplate(
  pattern: string,
  params: Record<string, string | number>,
  locale: string,
): string {
  // Minimal substitution — replace {key} and basic plural
  return pattern.replace(/\{(\w+)(?:,\s*plural,\s*[^}]*)?\}/g, (match, key) => {
    const val = params[key];
    return val !== undefined ? String(val) : match;
  });
}
```

---

## 5. Batch Fan-out for Campaign Notifications

When sending a campaign to all users in a locale group, read user IDs from D1 and
fan out to the queue in batches:

```typescript
// src/lib/campaign.ts
import type { D1Database, Queue, KVNamespace } from '@cloudflare/workers-types';
import { scheduleNotification } from './notify-scheduler';

export async function dispatchCampaign(
  db: D1Database,
  queue: Queue,
  kv: KVNamespace,
  templateId: string,
  params: Record<string, string | number>,
  localePattern = '%', // SQL LIKE pattern, '%' = all locales
  batchSize = 100,
): Promise<number> {
  let cursor: string | null = null;
  let totalDispatched = 0;

  do {
    const rows = await db
      .prepare(
        `SELECT user_id FROM user_notification_prefs
         WHERE locale LIKE ? AND opted_out = 0
           AND (? IS NULL OR user_id > ?)
         ORDER BY user_id
         LIMIT ?`,
      )
      .bind(localePattern, cursor, cursor, batchSize)
      .all<{ user_id: string }>();

    if (!rows.results.length) break;

    await Promise.all(
      rows.results.map((r) =>
        scheduleNotification(queue, kv, db, {
          userId: r.user_id,
          templateId,
          params,
        }),
      ),
    );

    totalDispatched += rows.results.length;
    cursor = rows.results[rows.results.length - 1].user_id;
  } while (true);

  return totalDispatched;
}
```

---

## 6. Queue Consumer: Sending via FCM

```typescript
// src/consumers/push-consumer.ts
import type { MessageBatch } from '@cloudflare/workers-types';
import type { PushMessage } from '../lib/notify-scheduler';

const FCM_URL = 'https://fcm.googleapis.com/v1/projects/{PROJECT_ID}/messages:send';

export async function handlePushBatch(
  batch: MessageBatch<PushMessage>,
  fcmServiceAccountToken: string,
): Promise<void> {
  for (const message of batch.messages) {
    const { fcmToken, title, body, imageUrl } = message.body;
    try {
      const res = await fetch(FCM_URL, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${fcmServiceAccountToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: {
            token: fcmToken,
            notification: { title, body, image: imageUrl ?? undefined },
          },
        }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        console.error('FCM error:', res.status, errBody);
        // 404 = stale token; don't retry
        if (res.status === 404) {
          message.ack();
        } else {
          message.retry();
        }
        continue;
      }

      message.ack();
    } catch (err) {
      console.error('Push delivery error:', err);
      message.retry();
    }
  }
}
```

---

## Anti-patterns

- **Computing delay as a fixed UTC hour offset per locale** — UTC offsets change with
  DST. Always use IANA timezone IDs and `Temporal.ZonedDateTime`, never fixed offsets.
- **Queueing all users at the same time and relying on the consumer to delay** —
  Queues consumers process messages as they arrive; per-message `delaySeconds` at enqueue
  time is the correct mechanism for delivery-window targeting.
- **Sending the message body in English to all users regardless of locale** — the
  consumer should receive pre-translated payload; do not look up templates in the
  consumer (it adds D1 latency per message and risks fetching a different template
  version than the scheduler intended).
- **Using Workers Queues `delaySeconds` > 43200** — the maximum is 12 hours. For
  notifications more than 12 hours away, enqueue at a later time (e.g. use a Durable
  Object alarm or a re-queue pattern).
- **Ignoring the `opted_out` flag** — GDPR/CCPA require honouring opt-outs. Check the
  flag at scheduling time AND in the consumer in case the user opted out after the
  message was queued.

## Gotchas

- `Temporal.ZonedDateTime.from()` throws on ambiguous wall-clock times during DST
  transitions (e.g. 01:30 local during fall-back). Use `disambiguation: 'earlier'` to
  pick the first occurrence.
- Workers Queues `delaySeconds` is approximate; actual delivery may be a few seconds
  later. Do not use it for sub-minute precision.
- FCM registration tokens expire. A 404 from FCM means the token is invalid; ack the
  message and trigger a token-refresh flow rather than retrying.
- D1 cursor pagination via `user_id > ?` requires `user_id` to be indexed and its
  ordering to be stable (e.g. UUID v4 or an auto-increment INTEGER).
- `@js-temporal/polyfill` must be bundled if native Temporal is not yet available in the
  Workers runtime. Check `typeof Temporal !== 'undefined'` before importing.

## Verification

```typescript
// test/delivery-delay.test.ts
import { secondsUntilDeliveryWindow } from '../src/lib/delivery-delay';
import { Temporal } from '@js-temporal/polyfill';

describe('secondsUntilDeliveryWindow', () => {
  it('returns 0 when already in window', () => {
    // 10:00 UTC in UTC timezone, window 09:00–11:00
    const now = Temporal.Instant.from('2025-06-15T10:00:00Z');
    expect(secondsUntilDeliveryWindow(now, 'UTC', { startHour: 9, endHour: 11 })).toBe(0);
  });

  it('schedules for next morning if outside window', () => {
    // 14:00 UTC+0, window 09:00–11:00
    const now = Temporal.Instant.from('2025-06-15T14:00:00Z');
    const delay = secondsUntilDeliveryWindow(now, 'UTC', { startHour: 9, endHour: 11 });
    // Next 09:00 UTC = 19 hours away = 68400 seconds, capped at 43200
    expect(delay).toBe(43200);
  });

  it('accounts for DST in America/New_York', () => {
    // 03:00 UTC on a summer day = 23:00 EDT previous night; window starts 09:00 local
    const now = Temporal.Instant.from('2025-06-15T03:00:00Z');
    const delay = secondsUntilDeliveryWindow(now, 'America/New_York', {
      startHour: 9,
      endHour: 11,
    });
    // 09:00 EDT = 13:00 UTC; delay = 10 hours = 36000 seconds
    expect(delay).toBe(36000);
  });
});
```

Inspect queued messages:

```bash
wrangler queues consumer list <QUEUE_NAME>
```

## Related

- `transactional-email-push-localization.md`
- `workers-queues-async-translation-pipeline.md`
- `locale-persistence-cookies-storage-2026.md`
- `temporal-api-polyfill-workers-edge-deployment-2026.md`
- `dst-safe-scheduling-ui-2026.md`

## Sources

- Cloudflare Queues delayed delivery: https://developers.cloudflare.com/queues/configuration/delays/
- Temporal API (TC39): https://tc39.es/proposal-temporal/
- FCM HTTP v1 API: https://firebase.google.com/docs/cloud-messaging/http-server-ref
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- IANA timezone database: https://www.iana.org/time-zones
