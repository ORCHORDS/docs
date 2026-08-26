# Unicode Normalization (NFC/NFD/NFKC/NFKD) in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

D1 `LIKE` queries against user-submitted text produce inconsistent results — the same word typed on different operating systems returns different rows. Search indexes miss entries. Two visually identical strings compare as unequal. The root cause is Unicode normalization form mismatch between stored and queried text.

## Context

Unicode allows the same visible character to be encoded in multiple ways. The accented letter `é` can be stored as:

- **NFC** (composed): a single codepoint `U+00E9` — `é`
- **NFD** (decomposed): base letter `e` (`U+0065`) + combining acute accent (`U+0301`)

MacOS tends to produce NFD; Windows and Linux produce NFC. When one form is stored in D1 and the other is used in a `LIKE` query, SQLite's byte-level comparison produces a miss. The fix is to normalise all text to NFC at the API boundary before any write or search operation.

---

## Core Utility and Middleware

```typescript
/**
 * Normalization form reference:
 *   NFC  — canonical decomposition then canonical composition (recommended for storage)
 *   NFD  — canonical decomposition only
 *   NFKC — compatibility decomposition then canonical composition (good for search)
 *   NFKD — compatibility decomposition only
 */
export type NormForm = "NFC" | "NFD" | "NFKC" | "NFKD";

/**
 * normalizeText — normalize a string and optionally trim whitespace.
 *
 * @param input - Raw user input
 * @param form  - Normalization form (default NFC for storage)
 * @returns Normalized string
 */
export function normalizeText(input: string, form: NormForm = "NFC"): string {
  if (typeof input !== "string") return "";
  return input.normalize(form).trim();
}

/**
 * normalizeForSearch — NFKC normalization plus lowercase for case-insensitive
 * search indexes. Use on query strings, not stored values.
 */
export function normalizeForSearch(input: string): string {
  return input.normalize("NFKC").toLowerCase().trim();
}

/**
 * Workers middleware: normalize all string fields in a parsed JSON body to NFC
 * before they reach D1. Mutates in place for efficiency.
 */
function normalizeObject(obj: unknown): unknown {
  if (typeof obj === "string") return normalizeText(obj);
  if (Array.isArray(obj)) return obj.map(normalizeObject);
  if (obj !== null && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k,
        normalizeObject(v),
      ])
    );
  }
  return obj;
}

export async function withNormalization(
  request: Request,
  handler: (req: Request, body: unknown) => Promise<Response>
): Promise<Response> {
  let body: unknown = null;
  const ct = request.headers.get("Content-Type") ?? "";
  if (ct.includes("application/json") && request.body) {
    const raw = await request.json();
    body = normalizeObject(raw);
  }
  return handler(request, body);
}

// Example Worker using the middleware
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return withNormalization(request, async (_req, body) => {
      const { name, bio } = body as { name: string; bio: string };
      await env.DB.prepare(
        "INSERT INTO users (name, bio) VALUES (?, ?)"
      )
        .bind(name, bio)
        .run();
      return new Response("OK", { status: 201 });
    });
  },
};
```

---

## Why NFC vs NFD Breaks D1 LIKE Queries

SQLite uses byte-level comparison for `LIKE` by default (unless `PRAGMA case_sensitive_like = ON`):

```sql
-- Stored as NFC (U+00E9): 'café'
-- Queried as NFD (e + U+0301): 'café'
SELECT * FROM menu WHERE name LIKE '%café%'; -- 0 rows if forms differ
```

NFC-normalising both the stored value and the query string before hitting D1 guarantees consistent byte sequences:

```typescript
// Before D1 write:
const name = normalizeText(rawInput); // NFC

// Before D1 LIKE query:
const searchTerm = "%" + normalizeText(query) + "%"; // NFC
await env.DB.prepare("SELECT * FROM menu WHERE name LIKE ?").bind(searchTerm).first();
```

---

## NFKC for Search Normalisation

NFKC additionally folds compatibility equivalents: `ﬁ` (ligature) → `fi`, `²` → `2`, full-width `Ａ` → `A`. Use NFKC on search query strings (not stored values) to maximise recall:

```typescript
// Stored: normalizeText("ﬁle")     → "ﬁle" (NFC, ligature preserved)
// Query:  normalizeForSearch("file") → "file" (NFKC)
// SQLite FTS5 with ICU tokenizer handles this, but plain LIKE does not.
```

---

## Testing Normalization

```typescript
import { assertEquals } from "jsr:@std/assert";

const nfc = "é";            // é as single codepoint
const nfd = "é";           // é as base + combining

console.assert(nfc !== nfd, "raw strings differ");
console.assert(nfc.normalize("NFC") === nfd.normalize("NFC"), "NFC normalised equal");
console.assert(nfc.normalize("NFD") === nfd.normalize("NFD"), "NFD normalised equal");

// Regression test for common edge cases
const cases: [string, string][] = [
  ["café", "café"],      // café composed vs decomposed
  ["Å",      "Å"],         // Angstrom sign vs Latin Capital A with ring
  ["ﬁle",    "file"],           // fi ligature NFKC
];
for (const [input, expected] of cases) {
  assertEquals(normalizeText(input), expected.normalize("NFC"));
}
```

---

## Anti-patterns

- Normalizing only at query time but not at write time — inconsistent forms accumulate in the database.
- Using `NFKC` for stored values — destroys intentional distinctions like `²` (superscript 2) vs `2` in a math context.
- Assuming `===` equality on un-normalised user strings — always normalise before comparison.
- Skipping normalisation on string fields fetched from third-party APIs — external data may arrive in any form.

---

## Gotchas

- **`String.prototype.normalize()` is always available in Workers** — it is part of the JS engine, not a Web API, and does not depend on `compatibility_date`.
- **NFC can increase byte length**: composing NFD codepoints into NFC composites decreases codepoint count but may not decrease UTF-8 byte length for all characters.
- **SQLite ICU extension**: D1 does not expose the ICU extension. There is no built-in `UNICODE_NORMALIZE()` SQL function; normalisation must happen in the Worker before the query.
- **Emoji**: Emoji are typically already in NFC. `normalize()` on emoji is a no-op but safe.

---

## Verification

```bash
# Insert NFD-encoded name then query with NFC
curl -X POST https://your-worker.workers.dev/users \
  -H "Content-Type: application/json" \
  -d '{"name": "café", "bio": "test"}'

# Query should find the row despite different input form
curl "https://your-worker.workers.dev/users/search?q=caf%C3%A9"
# Expected: row returned
```

---

## Related

- `intl-segmenter-text-tokenization-workers.md`
- `locale-fallback-chain-kv-workers.md`
- `language-detection-workers-ai-d1.md`

## Sources

- Unicode Normalization Forms (UAX #15) — https://www.unicode.org/reports/tr15/
- MDN: `String.prototype.normalize()` — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/normalize
- SQLite LIKE operator — https://www.sqlite.org/lang_expr.html#like
