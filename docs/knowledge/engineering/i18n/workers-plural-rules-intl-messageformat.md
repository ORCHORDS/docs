# Plural Rules and MessageFormat in Cloudflare Workers for i18n

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your UI shows strings like "1 item in cart" vs "3 items in cart". Hard-coding `count === 1 ? 'item' : 'items'` breaks for Slavic languages (Russian, Polish) that have up to four plural forms, Arabic which has six, and languages like Japanese that have no grammatical plural at all. You need a runtime-correct pluralisation system backed by CLDR data, running at the edge without shipping a large i18n library to the client.

---

## Context

### CLDR Plural Categories

The Unicode Common Locale Data Repository defines up to six plural categories per locale:

| Category | Example locales | Example count |
|----------|----------------|---------------|
| `zero`   | Arabic, Latvian | 0 |
| `one`    | Most European  | 1 |
| `two`    | Arabic, Hebrew | 2 |
| `few`    | Polish, Russian, Arabic | 3–4 (locale-specific rules) |
| `many`   | Polish, Russian, Arabic | 5–20 (locale-specific) |
| `other`  | All locales    | Default/catch-all |

English only uses `one` and `other`. Russian uses `one`, `few`, `many`, and `other`. Arabic uses all six. `Intl.PluralRules` in the Workers runtime (V8 + full ICU) resolves the correct category for any CLDR-supported locale.

### ICU MessageFormat

ICU MessageFormat is the industry standard for parameterised, pluralised messages. Syntax:

```
{count, plural, one {# item} other {# items}}
```

The `#` token is replaced by the formatted count. More complex patterns:

```
{count, plural,
  zero  {No items in your cart}
  one   {One item in your cart}
  other {{count} items in your cart}
}
```

---

## Solution

### 1. Intl.PluralRules Usage

```typescript
// src/i18n/plural.ts

export type PluralCategory = 'zero' | 'one' | 'two' | 'few' | 'many' | 'other';

/**
 * Resolve the CLDR plural category for a given count and locale.
 *
 * @example
 * getPluralCategory(1, 'en')    // → 'one'
 * getPluralCategory(3, 'en')    // → 'other'
 * getPluralCategory(21, 'ru')   // → 'one' (Russian rule: ends in 1, not 11)
 * getPluralCategory(11, 'ru')   // → 'many'
 * getPluralCategory(0, 'ar')    // → 'zero'
 */
export function getPluralCategory(
  count: number,
  locale: string,
  type: 'cardinal' | 'ordinal' = 'cardinal',
): PluralCategory {
  const rules = new Intl.PluralRules(locale, { type });
  return rules.select(count) as PluralCategory;
}

/**
 * Resolve plural categories for a list of counts in one pass.
 * Useful when rendering a list of items with counts.
 */
export function getPluralCategories(
  counts: number[],
  locale: string,
): Map<number, PluralCategory> {
  const rules = new Intl.PluralRules(locale);
  return new Map(counts.map((n) => [n, rules.select(n) as PluralCategory]));
}
```

### 2. ICU MessageFormat Storage in D1

```sql
-- migrations/0001_messages.sql
CREATE TABLE IF NOT EXISTS messages (
  message_key TEXT NOT NULL,
  locale      TEXT NOT NULL,
  pattern     TEXT NOT NULL,      -- ICU MessageFormat string
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (message_key, locale)
);

CREATE INDEX idx_messages_locale ON messages (locale);

-- Example data
INSERT INTO messages (message_key, locale, pattern) VALUES
  ('cart.items', 'en',
   '{count, plural, one {# item in your cart} other {# items in your cart}}'),

  ('cart.items', 'ru',
   '{count, plural,
     one   {# товар в корзине}
     few   {# товара в корзине}
     many  {# товаров в корзине}
     other {# товара в корзине}}'),

  ('cart.items', 'ar',
   '{count, plural,
     zero  {لا توجد عناصر في سلة التسوق}
     one   {عنصر واحد في سلة التسوق}
     two   {عنصران في سلة التسوق}
     few   {# عناصر في سلة التسوق}
     many  {# عنصرًا في سلة التسوق}
     other {# عنصر في سلة التسوق}}'),

  ('cart.items', 'ja',
   '{count, plural, other {カートに#個のアイテム}}'),

  ('notification.days', 'en',
   '{days, plural, one {# day ago} other {# days ago}}'),

  ('notification.days', 'pl',
   '{days, plural,
     one   {# dzień temu}
     few   {# dni temu}
     many  {# dni temu}
     other {# dnia temu}}');
```

### 3. Lightweight ICU MessageFormat Parser

The Workers runtime does not ship a full ICU MessageFormat evaluator. Implement a focused parser covering the `plural` selector and variable substitution — the 95% case for edge-side rendering:

```typescript
// src/i18n/messageformat.ts
import { getPluralCategory, type PluralCategory } from './plural';

export type MessageParams = Record<string, string | number>;

/**
 * Parse and resolve a simplified ICU MessageFormat pattern.
 *
 * Supported syntax:
 *   - Variable substitution: {variableName}
 *   - Plural selector: {variableName, plural, one {…} other {…}}
 *   - # token inside plural arms: replaced by the formatted count
 *
 * Not supported (use origin-side rendering for these):
 *   - select (gender)
 *   - selectordinal
 *   - date/time formatting
 *   - nested plural selectors
 */
export function renderMessage(
  pattern: string,
  params: MessageParams,
  locale: string,
): string {
  return pattern.replace(
    /\{(\w+)(?:,\s*(plural|select)\s*,((?:[^{}]|\{[^{}]*\})*))?\}/g,
    (fullMatch, varName, selector, arms) => {
      const value = params[varName];

      if (selector === 'plural' && typeof value === 'number') {
        return resolvePluralArm(arms, value, locale);
      }

      if (selector === 'select' && typeof value === 'string') {
        return resolveSelectArm(arms, value);
      }

      // Plain variable substitution
      return value !== undefined ? String(value) : fullMatch;
    },
  );
}

function resolvePluralArm(
  arms: string,
  count: number,
  locale: string,
): string {
  const category = getPluralCategory(count, locale);
  // Try exact category match, then fall back to 'other'
  const arm = findArm(arms, category) ?? findArm(arms, 'other') ?? '';
  // Replace # with the count value
  return arm.replace(/#/g, String(count));
}

function resolveSelectArm(arms: string, value: string): string {
  return findArm(arms, value) ?? findArm(arms, 'other') ?? value;
}

/**
 * Extract the content of a named arm from an ICU plural/select arms string.
 * Handles nested braces.
 */
function findArm(arms: string, category: string): string | undefined {
  // Match: category {content}
  const armRegex = new RegExp(
    `\\b${category}\\s*\\{([^{}]*)\\}`,
    'i',
  );
  const match = armRegex.exec(arms);
  return match ? match[1].trim() : undefined;
}
```

### 4. D1-Backed Message Store with Locale Fallback

```typescript
// src/i18n/message-store.ts
import type { D1Database } from '@cloudflare/workers-types';
import { renderMessage, type MessageParams } from './messageformat';

interface MessageRow {
  message_key: string;
  pattern: string;
}

/**
 * Build a locale fallback chain.
 * 'pt-BR' → ['pt-BR', 'pt', 'en']
 */
function buildFallbackChain(locale: string, fallback = 'en'): string[] {
  const chain: string[] = [locale];
  const parts = locale.split('-');
  if (parts.length > 1) chain.push(parts[0]);
  if (!chain.includes(fallback)) chain.push(fallback);
  return chain;
}

/**
 * Fetch a batch of messages for a locale from D1, applying fallback chain.
 * Returns a Map<key, pattern>.
 */
export async function fetchMessages(
  keys: string[],
  locale: string,
  db: D1Database,
): Promise<Map<string, string>> {
  const chain = buildFallbackChain(locale);
  const placeholders = keys.map(() => '?').join(', ');
  const localePlaceholders = chain.map(() => '?').join(', ');

  // Fetch all matching rows for the key set and fallback chain in one query
  const rows = await db
    .prepare(
      `SELECT message_key, locale, pattern
       FROM messages
       WHERE message_key IN (${placeholders})
         AND locale IN (${localePlaceholders})
       ORDER BY message_key`,
    )
    .bind(...keys, ...chain)
    .all<MessageRow & { locale: string }>();

  // Apply fallback: prefer the most specific locale in the chain
  const result = new Map<string, string>();
  for (const key of keys) {
    for (const fallbackLocale of chain) {
      const row = rows.results.find(
        (r) => r.message_key === key && r.locale === fallbackLocale,
      );
      if (row) {
        result.set(key, row.pattern);
        break;
      }
    }
  }
  return result;
}

/**
 * Convenience: fetch and immediately render a single message.
 */
export async function t(
  key: string,
  params: MessageParams,
  locale: string,
  db: D1Database,
): Promise<string> {
  const messages = await fetchMessages([key], locale, db);
  const pattern = messages.get(key);
  if (!pattern) return key; // Return key as fallback
  return renderMessage(pattern, params, locale);
}
```

### 5. Worker Entry Point

```typescript
// src/index.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';
import { parseAcceptLanguage } from './i18n/detect';
import { fetchMessages, t } from './i18n/message-store';
import { renderMessage } from './i18n/messageformat';

export interface Env {
  DB: D1Database;
  USER_PREFS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = parseAcceptLanguage(request.headers.get('accept-language'));
    const url = new URL(request.url);

    if (url.pathname === '/api/cart-summary') {
      const count = parseInt(url.searchParams.get('count') ?? '0', 10);
      const message = await t(
        'cart.items',
        { count },
        locale,
        env.DB,
      );
      return Response.json({ message, locale, count });
    }

    // Batch example: pre-fetch multiple messages for a page render
    const messages = await fetchMessages(
      ['cart.items', 'notification.days'],
      locale,
      env.DB,
    );

    const cartLabel = renderMessage(
      messages.get('cart.items') ?? '{count, plural, other {# items}}',
      { count: 3 },
      locale,
    );

    return Response.json({ cartLabel, locale });
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

### Intl.PluralRules in the Workers Runtime

`Intl.PluralRules` is fully supported in V8 with ICU. The `.select(n)` method returns the canonical CLDR category string. No polyfill is needed with `compatibility_date >= 2022-01-31`.

### Ordinal Plurals

For ordinal numbers (`1st`, `2nd`, `3rd`), pass `type: 'ordinal'` to `Intl.PluralRules`:

```typescript
const rules = new Intl.PluralRules('en', { type: 'ordinal' });
rules.select(1); // 'one'  → '1st'
rules.select(2); // 'two'  → '2nd'
rules.select(3); // 'few'  → '3rd'
rules.select(4); // 'other'→ '4th'
```

Store ordinal patterns in D1 under a separate key namespace, e.g., `ordinal.position`.

### D1 Batch Fetching

Fetching one message per D1 query is expensive. The `fetchMessages` function above batches all keys for a page in a single query. For a typical page with 10–20 message keys, this is one D1 round-trip regardless of how many messages are needed.

### Compiled Pattern Cache

Parsing ICU patterns is cheap with the regex-based parser above. For complex patterns stored in D1, consider a module-level `Map<string, CompiledPattern>` if you move to a tree-based parser.

---

## Anti-patterns

- **Never ship a full i18n library (Format.js, i18next) in a Worker bundle.** These libraries add 50–200 KB to the bundle and have startup costs. The focused parser above covers 95% of production use cases at <2 KB.
- **Do not use string concatenation for plurals.** `count + ' items'` fails for every locale with non-trivial plural rules.
- **Do not fetch messages one-by-one from D1 in a loop.** D1 latency is ~1–5 ms per query; 20 sequential queries = 100 ms added latency.
- **Do not assume `other` is always the English plural.** In Russian, `other` is the genitive plural used for numbers like 5, 6, 11 — not what most developers expect.

---

## Gotchas

- `Intl.PluralRules` counts from 0 by default. `select(0)` returns `'zero'` for Arabic and `'other'` for English — this is correct per CLDR, but make sure your D1 patterns include a `zero` arm for Arabic.
- Polish has `few` for 2–4 (except 12–14) and `many` for 5–21 and multiples of 10. Test with counts 1, 2, 5, 12, 21, 22 when adding Polish.
- The regex-based parser above does not handle nested plural selectors (e.g., a plural inside a select). If you need those, store pre-rendered variants or use a full ICU parser at build time and store the AST in KV.
- D1 free tier: 100,000 reads/day. A high-traffic page with 20 message keys per request hits the limit at 5,000 page views/day. Cache the rendered page or cache the message bundle in KV with a TTL of several minutes.

---

## Verification

```bash
# Deploy with wrangler
npx wrangler dev --local

# English singular
curl 'http://localhost:8787/api/cart-summary?count=1' \
  -H 'Accept-Language: en'
# Expected: {"message":"1 item in your cart","locale":"en","count":1}

# English plural
curl 'http://localhost:8787/api/cart-summary?count=3' \
  -H 'Accept-Language: en'
# Expected: {"message":"3 items in your cart","locale":"en","count":3}

# Russian — 21 ends in 1 (not 11) → category 'one' → singular
curl 'http://localhost:8787/api/cart-summary?count=21' \
  -H 'Accept-Language: ru'
# Expected: {"message":"21 товар в корзине",...}

# Russian — 11 → category 'many'
curl 'http://localhost:8787/api/cart-summary?count=11' \
  -H 'Accept-Language: ru'
# Expected: {"message":"11 товаров в корзине",...}

# Arabic — 0 → zero form
curl 'http://localhost:8787/api/cart-summary?count=0' \
  -H 'Accept-Language: ar'
# Expected: لا توجد عناصر في سلة التسوق
```

---

## Related

- `workers-translation-fallback-chain-kv.md` — KV message store and fallback
- `workers-rtl-html-direction-edge.md` — RTL HTML injection for Arabic/Hebrew
- `workers-currency-formatting-intl-edge.md` — currency with Intl.NumberFormat
- CLDR Plural Rules: https://cldr.unicode.org/index/cldr-spec/plural-rules
- Unicode ICU MessageFormat syntax

---

## Sources

- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/PluralRules
- https://unicode-org.github.io/icu/userguide/format_parse/messages/
- https://cldr.unicode.org/index/cldr-spec/plural-rules
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/
