# Handling Missing Translation Keys Gracefully in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker serves translations from KV and a new locale is added mid-sprint without full translation coverage. Missing keys silently return `undefined`, which renders as empty strings or JavaScript's literal `"undefined"` in the UI. You need a `t()` helper that falls back through the locale chain, logs missing keys to Analytics Engine for developer review, and never crashes or returns `undefined` to the client.

---

## Context

The locale chain for `pt-BR` is `pt-BR → pt → en`; for `zh-Hant-TW` it is `zh-Hant-TW → zh-Hant → zh → en`. When a key is absent at all levels the raw key string is returned as a visible last resort — this is intentional: it is more debuggable than an empty string and easier to spot in QA. Each missing key is written into an Analytics Engine dataset (`missing_i18n_keys`) tagged with locale and key name. A Cron Trigger running daily queries Analytics Engine via the REST API and writes a summary report row to D1 for the i18n team to review. A background KV write accumulates a `Set`-like list at `missing_keys:<locale>` using a JSON array; the Cron compacts these into D1.

---

## Section 1 — wrangler.toml configuration

```toml
name            = "i18n-worker"
compatibility_date = "2024-01-01"

[[kv_namespaces]]
binding = "TRANSLATIONS"
id      = "YOUR_TRANSLATIONS_KV_ID"

[[kv_namespaces]]
binding = "MISSING_KEYS_KV"
id      = "YOUR_MISSING_KV_ID"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "missing_i18n_keys"

[[d1_databases]]
binding     = "DB"
database_id = "YOUR_D1_DB_ID"
database_name = "i18n"

[[triggers]]
crons = ["0 6 * * *"]   # Daily at 06:00 UTC
```

---

## Section 2 — Translation helper with fallback chain

```typescript
// src/i18n/t.ts
export interface Env {
  TRANSLATIONS:    KVNamespace;
  MISSING_KEYS_KV: KVNamespace;
  AE:              AnalyticsEngineDataset;
}

type TranslationValue = string | Record<string, string>;
type TranslationMap   = Record<string, TranslationValue>;

// Isolate-level cache: avoids repeated KV round-trips within one request burst.
const mapCache = new Map<string, TranslationMap>();

async function loadMap(
  kv: KVNamespace,
  locale: string
): Promise<TranslationMap> {
  if (mapCache.has(locale)) return mapCache.get(locale)!;
  const raw = await kv.get<TranslationMap>(`translations:${locale}`, { type: 'json' });
  const map  = raw ?? {};
  mapCache.set(locale, map);
  return map;
}

/**
 * Build the fallback locale chain for any BCP 47 tag.
 * Examples:
 *   pt-BR      → ['pt-BR', 'pt', 'en']
 *   zh-Hant-TW → ['zh-Hant-TW', 'zh-Hant', 'zh', 'en']
 *   en-US      → ['en-US', 'en']
 *   en         → ['en']
 */
export function buildChain(locale: string): string[] {
  const chain: string[] = [];
  const parts = locale.split('-');
  // Build all subtag prefixes from longest to shortest.
  for (let i = parts.length; i > 0; i--) {
    chain.push(parts.slice(0, i).join('-'));
  }
  // Ensure 'en' is always at the end as ultimate fallback.
  if (!chain.includes('en')) chain.push('en');
  return chain;
}

/**
 * Log a missing key to Analytics Engine (non-blocking) and accumulate it
 * in a KV set for the daily Cron report.
 */
function reportMissingKey(
  env: Env,
  locale: string,
  key: string,
  ctx: ExecutionContext
): void {
  // Analytics Engine write — fire-and-forget, never await in the hot path.
  try {
    env.AE.writeDataPoint({
      blobs:   [locale, key],
      indexes: [locale],
    });
  } catch {
    // Analytics Engine failures must never break the translation lookup.
  }

  // Background KV accumulation — use waitUntil so it outlives the response.
  ctx.waitUntil(
    (async () => {
      const kvKey = `missing_keys:${locale}`;
      const existing = await env.MISSING_KEYS_KV.get<string[]>(kvKey, { type: 'json' });
      const keys = new Set(existing ?? []);
      if (!keys.has(key)) {
        keys.add(key);
        await env.MISSING_KEYS_KV.put(kvKey, JSON.stringify([...keys]), {
          expirationTtl: 86400 * 7,  // 7-day rolling window
        });
      }
    })()
  );
}

/**
 * Main translation helper.
 *
 * @param env  - Worker bindings
 * @param ctx  - ExecutionContext (needed for waitUntil)
 * @param locale - The user's requested locale (BCP 47)
 * @param key    - The translation key
 * @param vars   - Optional interpolation variables
 * @returns      - The translated string, never undefined
 */
export async function t(
  env: Env,
  ctx: ExecutionContext,
  locale: string,
  key: string,
  vars: Record<string, string | number> = {}
): Promise<string> {
  const chain = buildChain(locale);

  for (const loc of chain) {
    const map = await loadMap(env.TRANSLATIONS, loc);
    if (key in map) {
      const value = map[key];
      const text  = typeof value === 'string' ? value : JSON.stringify(value);
      return interpolate(text, vars);
    }
  }

  // Key not found anywhere in the chain — report and return raw key.
  reportMissingKey(env, locale, key, ctx);
  return key;
}

function interpolate(
  template: string,
  vars: Record<string, string | number>
): string {
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) =>
    name in vars ? String(vars[name]) : `{{${name}}}`
  );
}
```

---

## Section 3 — Cron handler: export missing keys to D1

```typescript
// src/cron.ts  (export alongside fetch in src/index.ts)

import type { Env } from './i18n/t';

export async function handleCron(env: Env): Promise<void> {
  // List all missing_keys:* entries in KV.
  const list = await env.MISSING_KEYS_KV.list({ prefix: 'missing_keys:' });

  for (const { name } of list.keys) {
    const locale     = name.replace('missing_keys:', '');
    const keys       = await env.MISSING_KEYS_KV.get<string[]>(name, { type: 'json' });
    if (!keys || keys.length === 0) continue;

    const reportedAt = new Date().toISOString();

    // Upsert a row per key into D1 for the i18n team dashboard.
    const stmts = keys.map(key =>
      env.DB
        .prepare(`
          INSERT INTO missing_translation_keys (locale, key, reported_at)
          VALUES (?, ?, ?)
          ON CONFLICT(locale, key) DO UPDATE SET reported_at = excluded.reported_at
        `)
        .bind(locale, key, reportedAt)
    );

    await env.DB.batch(stmts);

    // Clear the KV accumulator after successful D1 write.
    await env.MISSING_KEYS_KV.delete(name);
  }
}

// D1 table (create once):
// CREATE TABLE IF NOT EXISTS missing_translation_keys (
//   locale      TEXT NOT NULL,
//   key         TEXT NOT NULL,
//   reported_at TEXT NOT NULL,
//   PRIMARY KEY (locale, key)
// );

// src/index.ts — wire up cron alongside fetch:
// import { handleCron } from './cron';
// export default {
//   async fetch(request, env, ctx) { ... },
//   async scheduled(_event, env, _ctx) { await handleCron(env); },
// };
```

---

## Anti-patterns

- **Returning `undefined` or empty string for missing keys** — Both are invisible in the UI, making missing keys undetectable until a manual content audit; always return the raw key string as a visible last resort.
- **Throwing an error for missing keys** — A missing translation should degrade gracefully, not crash the Worker and return a 500 to the user.
- **Awaiting the missing-key report in the hot path** — KV writes and Analytics Engine calls add latency; always use `ctx.waitUntil()` for non-critical side effects.
- **Falling back directly to `en` without trying intermediate subtags** — `pt-BR` users may have `pt` translations that are closer than `en`; walk the full chain.

---

## Gotchas

- `ctx.waitUntil()` extends the Worker's lifetime after the response is sent, but only up to the platform's CPU time limit (typically 30 s on Workers Paid). Keep background writes lightweight.
- `env.MISSING_KEYS_KV.list()` returns at most 1,000 keys per call; if you have more than 1,000 locales with missing keys, paginate with the `cursor` field in the Cron handler.
- Analytics Engine `writeDataPoint` accepts up to 20 `blobs` and up to 20 `doubles`; `indexes` is limited to 1 value. Keep the key name reasonably short or hash it if it exceeds 64 bytes.
- The isolate-level `mapCache` Map persists across requests in the same isolate but is cleared on cold start. Do not store mutable state in it — only treat it as a read-through cache.
- If two concurrent requests both attempt `waitUntil` KV writes for the same missing key, the second write will overwrite the first with the same Set contents — this is benign but means the KV write is not perfectly atomic. For high-concurrency scenarios, consider Durable Objects instead.

---

## Verification

```bash
# 1. Create D1 table
npx wrangler d1 execute MY_DB --local --command "
CREATE TABLE IF NOT EXISTS missing_translation_keys (
  locale TEXT NOT NULL, key TEXT NOT NULL, reported_at TEXT NOT NULL,
  PRIMARY KEY (locale, key)
);"

# 2. Seed only English translations (leave fr empty to trigger missing-key path)
npx wrangler kv:key put --binding=TRANSLATIONS 'translations:en' \
  '{"greeting":"Hello","farewell":"Goodbye"}' --local

# 3. Run dev server
npx wrangler dev

# 4. Request a key that exists in English but not in French
curl 'http://localhost:8787/?locale=fr&key=greeting'
# Expected: "Hello"  (fell through to en)

# 5. Request a key that exists nowhere
curl 'http://localhost:8787/?locale=fr&key=<redacted-secret>
# Expected: "unknown_key"  (raw key returned, missing-key logged)

# 6. Verify KV accumulation
npx wrangler kv:key get --binding=MISSING_KEYS_KV 'missing_keys:fr' --local
# Expected: ["unknown_key"]

# 7. Trigger the Cron manually
npx wrangler dev --test-scheduled
curl 'http://localhost:8787/__scheduled?cron=0+6+*+*+*'

# 8. Check D1 report table
npx wrangler d1 execute MY_DB --local \
  --command "SELECT * FROM missing_translation_keys;"
# Expected row: { locale: 'fr', key: 'unknown_key', reported_at: '<ISO8601>' }
```

---

## Related

- `plural-rules-intl-pluralrules-workers.md`
- `locale-negotiation-accept-language-workers.md`
- `currency-formatting-intl-numberformat-workers.md`

---

## Sources

- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- BCP 47 Language Tag Syntax — https://www.rfc-editor.org/rfc/rfc5646
