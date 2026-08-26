# Durable Objects ID from Name Collision Incident

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project user presence sessions began cross-contaminating: users reported seeing each other's live activity indicators, typing status, and online/offline events from unrelated sessions. Two distinct users in different communities would intermittently share a single Durable Object instance, causing their presence state to merge. The issue was intermittent and difficult to reproduce, appearing only under specific username patterns.

## Context

example project uses Durable Objects to manage per-user presence state (online status, active community, typing indicators). Each user gets a dedicated presence Durable Object identified by `DurableObjectNamespace.idFromName(username)`. Usernames on example project allow Unicode characters and are case-insensitive — stored lowercase in D1 but displayed in the casing the user registered with. A subtle normalisation mismatch between the storage layer and the Durable Object key derivation caused two different usernames to resolve to the same DO name, and therefore the same DO instance.

## Timeline

- **2026-08-20 11:00 UTC** — New user `Ñoño_2026` (U+00D1 uppercase N-tilde) registers on example.com.
- **2026-08-20 11:05 UTC** — Existing user `ñoño_2026` (U+00F1 lowercase n-tilde) reports seeing a stranger's typing indicator in their DMs.
- **2026-08-20 11:08 UTC** — First support ticket filed.
- **2026-08-20 14:30 UTC** — Second pair of affected users identified: `İstanbul_Dev` (U+0130 dotted capital I) and `istanbul_dev` (ASCII).
- **2026-08-21 09:00 UTC** — Engineering investigation begins; suspects DO namespace collision.
- **2026-08-21 10:15 UTC** — Root cause identified: `idFromName()` is called with `username` as-is from the request context, which is the display-cased version, not the canonical lowercase version.
- **2026-08-21 11:00 UTC** — Fix deployed: normalise to canonical form before `idFromName()`.
- **2026-08-21 11:30 UTC** — Affected DO instances purged; no further cross-contamination observed.

## Root Cause

Durable Object IDs derived via `idFromName()` are a deterministic hash of the exact string passed. If two different strings hash to identical bytes (or if the same logical user produces two different strings), they share a single DO instance.

In this case, the collision was not a hash collision — it was a logical equivalence failure. The username `Ñoño_2026` and `ñoño_2026` are distinct Unicode strings, but the platform's registration flow applied case-folding only at the D1 uniqueness check layer, not at the DO key derivation layer:

```typescript
// workers/presence.ts — BUGGY VERSION

export async function getPresenceStub(
  username: string,
  env: Env
): Promise<DurableObjectStub> {
  // BUG: username comes from the JWT claim, which preserves registration casing
  // "Ñoño_2026" and "ñoño_2026" produce DIFFERENT DO IDs — no collision here yet
  // BUT the auth middleware was normalising with .toLowerCase() which uses
  // locale-aware lowercasing on some JS engines:
  //   "İstanbul_Dev".toLowerCase() === "istanbul_dev"  ✓ (correct)
  //   "İstanbul_Dev".toLocaleLowerCase("tr") === "istanbul_dev"  ✓
  //   "İstanbul_Dev".toLocaleLowerCase("en") === "i̇stanbul_dev"  (dotless i — DIFFERENT!)
  // The auth Worker ran in a V8 context that lowercased "İ" as "i̇" (U+0069 U+0307)
  // but the registration Worker lowercased it as "i" (U+0069), creating two
  // different canonical forms that both passed the D1 uniqueness check.

  const id = env.PRESENCE.idFromName(username); // receives inconsistently normalised string
  return env.PRESENCE.get(id);
}
```

The effective result was that `İstanbul_Dev` registered successfully (D1 stored `istanbul_dev` with ASCII `i`), but the presence DO was keyed on the V8-lowercased form `i̇stanbul_dev` (two characters: `i` + combining dot). A second login produced a different DO key than the first login. While not a "collision" in the cryptographic sense, it produced inconsistent DO routing — and the reverse case (`ñoño_2026` / `Ñoño_2026`) did cause an actual collision when the registration check failed to catch the new username as a duplicate.

```typescript
// auth/register.ts — BUGGY registration uniqueness check
async function isUsernameTaken(username: string, db: D1Database): Promise<boolean> {
  const row = await db
    .prepare("SELECT id FROM users WHERE username = ?")
    .bind(username.toLowerCase()) // JS .toLowerCase() — locale varies by runtime
    .first();
  return row !== null;
}
// "Ñ".toLowerCase() === "ñ" — collision not caught; two users get same normalised key
```

## Impact

- **Users directly affected:** 4 confirmed user pairs with cross-contaminated presence state
- **Duration of exposure:** ~28 hours before fix deployed
- **Data exposed:** Typing indicators, online/offline events, active community name — no message content
- **Privacy severity:** Medium — metadata leakage, not content leakage
- **Registration flow:** ~12 affected usernames with inconsistent DO routing (presence state split across two DO instances)

## Fix

```typescript
// lib/username.ts — canonical normalisation module

/**
 * Canonical username form for all key derivation.
 * Uses Unicode NFKC normalisation followed by case-folding via
 * String.prototype.normalize("NFKC") + toLowerCase with explicit locale "en-US"
 * to produce deterministic output regardless of V8 ICU locale context.
 *
 * This function MUST be used everywhere a username is used as a key:
 * - D1 uniqueness checks
 * - Durable Object idFromName()
 * - KV cache keys
 * - JWT subject claim
 */
export function canonicalUsername(raw: string): string {
  return raw
    .normalize("NFKC")       // Decompose + recompose; "İ" (U+0130) → "İ" (no change at NFKC)
    .toLocaleLowerCase("en") // ASCII-safe fold: "İ" → "i̇" in some locales
    // Final ASCII-safe fold to avoid dotted-i issues:
    .replace(/̇/g, "")  // Remove combining dot above (from İ decomposition)
    .trim();
}

// Alternative: use a purpose-built Unicode case-folding library
// import { foldCase } from "unicode-case-fold";
// export const canonicalUsername = (raw: string) => foldCase(raw.normalize("NFKC")).trim();
```

```typescript
// workers/presence.ts — FIXED VERSION
import { canonicalUsername } from "../lib/username";

export async function getPresenceStub(
  username: string,
  env: Env
): Promise<DurableObjectStub> {
  const canonical = canonicalUsername(username);
  const id = env.PRESENCE.idFromName(`presence:${canonical}`);
  return env.PRESENCE.get(id);
}
```

```typescript
// auth/register.ts — FIXED registration uniqueness check
import { canonicalUsername } from "../lib/username";

async function isUsernameTaken(username: string, db: D1Database): Promise<boolean> {
  const canonical = canonicalUsername(username);
  const row = await db
    .prepare("SELECT id FROM users WHERE username_canonical = ?")
    .bind(canonical)
    .first();
  return row !== null;
}
```

```sql
-- migrations/0044_add_username_canonical.sql
ALTER TABLE users ADD COLUMN username_canonical TEXT;
UPDATE users SET username_canonical = LOWER(username); -- approximate; app layer re-canonicalises
CREATE UNIQUE INDEX idx_users_username_canonical ON users (username_canonical);
```

## Prevention

1. **Single canonical normalisation function** (`lib/username.ts`) used at every layer — registration, auth, DO key derivation, KV keys.
2. **Property-based tests** covering Unicode username edge cases: dotted I, n-tilde, Arabic, CJK, RTL characters.
3. **DO name prefix namespacing**: all `idFromName()` calls now include a type prefix (`presence:`, `room:`, `rate-limit:`) to prevent accidental cross-type collisions.
4. **Username allowlist/denylist** of confusable Unicode characters added to registration validator.
5. **DO instance audit script** added to ops runbook to detect users with multiple DO instances.

```typescript
// test/username.test.ts
import { describe, it, expect } from "vitest";
import { canonicalUsername } from "../lib/username";

describe("canonicalUsername", () => {
  it("is idempotent", () => {
    const u = "Hello_World";
    expect(canonicalUsername(canonicalUsername(u))).toBe(canonicalUsername(u));
  });
  it("treats case variants as equal", () => {
    expect(canonicalUsername("Ñoño")).toBe(canonicalUsername("ñoño"));
  });
  it("handles dotted capital I", () => {
    expect(canonicalUsername("İstanbul")).toBe(canonicalUsername("istanbul"));
  });
  it("normalises NFKC equivalents", () => {
    // U+FB01 LATIN SMALL LIGATURE FI → "fi"
    expect(canonicalUsername("ﬁle")).toBe(canonicalUsername("file"));
  });
});
```

## Anti-patterns

- Using JavaScript's `.toLowerCase()` without an explicit locale for usernames — V8 ICU context varies.
- Deriving Durable Object names from user-supplied strings without a canonical normalisation step.
- Applying uniqueness constraints at only one layer (e.g., DB only) while using a differently-normalised form for DO key derivation.
- Using `idFromName()` with unprefixed strings — collisions across different logical entity types become possible.
- Assuming Unicode normalisation is a single operation — NFKC and case-folding are separate steps with ordering effects.

## Gotchas

- `idFromName()` is a one-way hash — there is no way to enumerate or list DOs by name. A naming collision is permanent until the DO's state is manually migrated.
- Durable Object IDs created with `idFromName()` are bound to the specific namespace class. The same string in two different namespace classes produces different IDs (safe), but the same string in the same namespace always resolves to the same ID (dangerous if normalisation is inconsistent).
- SQLite `LOWER()` function in D1 only handles ASCII; it does not Unicode-fold `Ñ` to `ñ`. Application-layer normalisation is required before D1 inserts.
- Workers runtime inherits V8's ICU locale data, which may differ between Workers in different regions or after a runtime update.
- `String.prototype.toLocaleLowerCase()` without a locale argument uses the runtime's default locale, which is non-deterministic in a distributed system.

## Verification

```bash
# Check for duplicate canonical usernames in production D1
wrangler d1 execute example project-prod --command \
  "SELECT username_canonical, COUNT(*) as c FROM users GROUP BY username_canonical HAVING c > 1"
# Expected: 0 rows

# Smoke test: register two Unicode-equivalent usernames and confirm rejection
curl -X POST https://example.com/api/register \
  -d '{"username": "Ñoño_test", "password": "..."}' -w "%{http_code}"
# Should succeed: 201
curl -X POST https://example.com/api/register \
  -d '{"username": "ñoño_test", "password": "..."}' -w "%{http_code}"
# Should fail: 409 Conflict
```

## Related

- `durable-objects-namespace-rename-data-loss-incident.md`
- `durable-objects-storage-quota-limit-incident.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `dont-log-pii-in-production.md`
- `gdpr-by-design-not-retrofit.md`

## Sources

- https://developers.cloudflare.com/durable-objects/api/id-management/
- https://developers.cloudflare.com/durable-objects/best-practices/
- https://unicode.org/reports/tr15/ (Unicode Normalisation Forms)
- https://unicode.org/reports/tr44/#Simple_Case_Folding
- https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
