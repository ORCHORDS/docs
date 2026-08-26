# Missing Translation Key Detection and Alerting in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves translations from KV. Occasionally a key exists in English
but not in Japanese or Polish — the page silently falls back to English. No one
notices until a user files a bug report. You need:

1. Workers to detect missing keys at request time and log them to D1.
2. A cron Worker to aggregate missing-key counts daily and post a Slack alert.
3. A KV fallback chain (`requested locale → base locale → English`) so users
   always see something while the alert is in flight.

## Context

- Runtime: Cloudflare Workers + Cron Triggers
- Storage: KV (translations) + D1 (missing-key audit log)
- Alerting: Slack Incoming Webhook
- TypeScript throughout

---

## 1. D1 Schema for Missing Key Audit Log

```sql
-- migrations/001_missing_keys.sql
CREATE TABLE missing_translation_keys (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  key_name   TEXT    NOT NULL,
  locale     TEXT    NOT NULL,
  url        TEXT    NOT NULL,
  hit_count  INTEGER NOT NULL DEFAULT 1,
  first_seen INTEGER NOT NULL,  -- Unix epoch
  last_seen  INTEGER NOT NULL,  -- Unix epoch
  alerted    INTEGER NOT NULL DEFAULT 0,  -- 0=pending, 1=alerted
  UNIQUE (key_name, locale)
);

CREATE INDEX idx_missing_unalerted ON missing_translation_keys (alerted, last_seen);
```

```bash
wrangler d1 execute <DB_NAME> --file migrations/001_missing_keys.sql
```

---

## 2. KV Translation Loader with Fallback Chain

```typescript
// src/translations.ts

export interface Env {
  TRANSLATIONS: KVNamespace;
  AUDIT_DB:     D1Database;
  SLACK_WEBHOOK: string;  // Secret via wrangler secret
}

/**
 * Translation key lookup with a three-level fallback chain:
 *   1. Exact locale (e.g. "ja")
 *   2. Base locale if region-specific (e.g. "pt" from "pt-BR")
 *   3. English fallback ("en")
 *
 * Returns the resolved value and whether a miss occurred.
 */
export async function getTranslation(
  key:    string,
  locale: string,
  env:    Env
): Promise<{ value: string; miss: boolean; resolvedLocale: string }> {
  // Build fallback chain
  const chain: string[] = [locale];
  const base = locale.split('-')[0];
  if (base !== locale) chain.push(base);
  if (base !== 'en')   chain.push('en');

  for (const candidate of chain) {
    const kvKey = `t:${candidate}:${key}`;
    const value = await env.TRANSLATIONS.get(kvKey);
    if (value !== null) {
      return { value, miss: candidate !== locale, resolvedLocale: candidate };
    }
  }

  // Absolute fallback: return the key itself so something renders
  return { value: key, miss: true, resolvedLocale: 'MISSING' };
}
```

---

## 3. Logging Missing Keys to D1

Use `INSERT OR IGNORE` + `UPDATE` (upsert pattern) to increment a counter
without locking conflicts from high-traffic Workers.

```typescript
// src/audit-logger.ts
import type { Env } from './translations';

export async function logMissingKey(
  key:    string,
  locale: string,
  url:    string,
  env:    Env,
  ctx:    ExecutionContext
): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  // Fire-and-forget: don't block the response
  ctx.waitUntil(
    (async () => {
      // Insert on first miss; ignore if row exists
      await env.AUDIT_DB
        .prepare(
          `INSERT INTO missing_translation_keys
             (key_name, locale, url, hit_count, first_seen, last_seen, alerted)
           VALUES (?, ?, ?, 1, ?, ?, 0)
           ON CONFLICT (key_name, locale) DO UPDATE SET
             hit_count = hit_count + 1,
             last_seen = excluded.last_seen,
             url       = excluded.url`
        )
        .bind(key, locale, url, now, now)
        .run();
    })()
  );
}
```

---

## 4. Worker Entry Point

```typescript
// src/index.ts
import { getTranslation } from './translations';
import { logMissingKey }  from './audit-logger';

export interface Env {
  TRANSLATIONS:  KVNamespace;
  AUDIT_DB:      D1Database;
  SLACK_WEBHOOK: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url    = new URL(request.url);
    const locale = url.searchParams.get('locale') ?? 'en';
    const key    = url.searchParams.get('key')    ?? 'greeting';

    const { value, miss, resolvedLocale } = await getTranslation(key, locale, env);

    if (miss && resolvedLocale !== 'en') {
      // Log asynchronously; never block the user response
      logMissingKey(key, locale, request.url, env, ctx);
    }

    return new Response(
      JSON.stringify({ key, locale, resolvedLocale, value, miss }),
      { headers: { 'Content-Type': 'application/json; charset=utf-8' } }
    );
  }
};
```

---

## 5. Cron Worker: Aggregate and Alert

Schedule this Worker to run once a day. It reads unalerted rows, batches them
into a Slack message, and marks them as alerted.

```typescript
// src/cron-alert.ts
import type { Env } from './index';

interface MissingRow {
  id:         number;
  key_name:   string;
  locale:     string;
  hit_count:  number;
  last_seen:  number;
  url:        string;
}

export async function runCronAlert(env: Env): Promise<void> {
  // Fetch all unalerted missing keys, sorted by impact (hit_count desc)
  const { results } = await env.AUDIT_DB
    .prepare(
      `SELECT id, key_name, locale, hit_count, last_seen, url
       FROM missing_translation_keys
       WHERE alerted = 0
       ORDER BY hit_count DESC
       LIMIT 50`
    )
    .all<MissingRow>();

  if (results.length === 0) return;

  // Build Slack Block Kit message
  const rows = results
    .map(r =>
      `• \`${r.key_name}\` [${r.locale}] — ${r.hit_count} hit(s), last seen <${r.url}>`
    )
    .join('\n');

  const payload = {
    text: `*Missing translation keys detected* (${results.length} key/locale pairs)`,
    blocks: [
      {
        type: 'section',
        text: { type: 'mrkdwn', text: `*Missing translation keys* (${results.length})` }
      },
      {
        type: 'section',
        text: { type: 'mrkdwn', text: rows }
      },
      {
        type: 'context',
        elements: [
          { type: 'mrkdwn', text: `Reported at <!date^${Math.floor(Date.now()/1000)}^{date_short_pretty} {time}|now>` }
        ]
      }
    ]
  };

  // Post to Slack
  const slackRes = await fetch(env.SLACK_WEBHOOK, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload)
  });

  if (!slackRes.ok) {
    console.error('Slack webhook failed:', await slackRes.text());
    return;
  }

  // Mark rows as alerted
  const ids = results.map(r => r.id).join(',');
  await env.AUDIT_DB
    .prepare(`UPDATE missing_translation_keys SET alerted = 1 WHERE id IN (${ids})`)
    .run();
}

// Export the scheduled handler
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runCronAlert(env));
  }
};
```

`wrangler.toml` cron configuration:

```toml
[triggers]
crons = ["0 8 * * *"]   # 08:00 UTC daily
```

---

## 6. Seeding Test Translations in KV

```bash
# Seed some keys for testing
wrangler kv key put --binding TRANSLATIONS 't:en:greeting' 'Hello!'
wrangler kv key put --binding TRANSLATIONS 't:fr:greeting' 'Bonjour!'
# Intentionally omit 'ja' to trigger a miss:
# wrangler kv key put --binding TRANSLATIONS 't:ja:greeting' 'こんにちは！'
```

---

## Anti-patterns

- **Blocking the response to write to D1** — D1 writes under load can add
  10–50 ms. Always use `ctx.waitUntil` for audit writes.
- **Logging every request individually** — use the `ON CONFLICT DO UPDATE SET
  hit_count = hit_count + 1` upsert so high-traffic missing keys produce one
  row, not millions.
- **Alerting on every miss in real time** — Slack rate limits are strict. Batch
  via a cron instead.
- **Not marking rows as `alerted`** — without this flag, the cron re-alerts
  the same keys every day.

## Gotchas

- The `IN (${ids})` pattern is safe here because `ids` is derived from integer
  primary keys fetched from D1, not from user input. Never build SQL `IN`
  clauses from user-supplied strings.
- `LIMIT 50` in the cron query prevents Slack messages from exceeding the
  Block Kit max (50 blocks). Process rows in batches if you expect more.
- D1's `ON CONFLICT DO UPDATE` syntax requires SQLite 3.24+. D1 uses SQLite
  3.46 — this is safe.
- KV `get` returns `null` for missing keys, not `undefined`. The triple-level
  fallback chain must check `!== null` explicitly.

## Verification

```bash
# Seed KV and run dev server
npx wrangler dev src/index.ts

# Hit a key that exists in English but not Japanese
curl 'http://localhost:8787/?locale=ja&key=greeting'
# → { "key": "greeting", "locale": "ja", "resolvedLocale": "en",
#     "value": "Hello!", "miss": true }

# Check D1 for the audit row
wrangler d1 execute <DB_NAME> --command \
  'SELECT key_name, locale, hit_count, alerted FROM missing_translation_keys'
# → [{ key_name: 'greeting', locale: 'ja', hit_count: 1, alerted: 0 }]

# Simulate cron manually
wrangler dev src/cron-alert.ts
curl -X POST http://localhost:8787/__scheduled  # triggers the cron handler

# Confirm row is marked alerted
wrangler d1 execute <DB_NAME> --command \
  'SELECT alerted FROM missing_translation_keys WHERE key_name = "greeting"'
# → [{ alerted: 1 }]
```

## Related

- `workers-locale-content-negotiation-d1.md` — locale selection from D1 content
- `workers-icu-message-format-complex-plural.md` — ICU keys that may go missing
- `workers-number-system-arabic-indic.md` — locale configs stored in KV

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://api.slack.com/block-kit
