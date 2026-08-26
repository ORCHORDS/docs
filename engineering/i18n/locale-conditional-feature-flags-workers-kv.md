# Locale-Conditional Feature Flags Workers KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A platform needs to gate features by locale: a new right-to-left checkout flow launches to `ar`, `he`, and `fa` users first; a SEPA payment method is available only in EU locales; a holiday campaign runs only for users in `ja` and `ko` during specific date windows. Hardcoded locale lists scattered across Worker source code are unmaintainable and require redeployment for every rollout change. The solution is a KV-backed feature flag system where flag definitions — including locale matchers, date windows, and percentage rollouts — are managed at runtime without Worker redeployment.

---

## Context

Feature flags for locale-conditional behavior sit at the intersection of two concerns:

1. **Flag evaluation** — given a locale (and optionally a user ID, region, or device type), is a feature enabled?
2. **Flag management** — how are flag definitions stored, updated, and propagated to Workers at the edge without a deploy?

Cloudflare KV is the right fit: reads are fast at the edge, writes propagate globally within ~60 seconds (eventual consistency), and the flag schema is small (well under KV's 25 MB value limit). Flag definitions are stored as JSON values keyed by feature name. Workers read them with a short cache TTL (60 s) so rollout changes take effect quickly without per-request KV reads after the first cold fetch.

The example project platform combines KV flags with BCP 47 locale matching using `Intl.Locale` region and language subtags, optional date-window guards, and a deterministic percentage rollout hashed against the user ID.

---

## Flag Schema Definition

```typescript
// src/types/feature-flag.ts

/**
 * A single locale conditional feature flag stored in KV.
 */
export interface FeatureFlag {
  /** Flag identifier, also the KV key under the "flag:" prefix. */
  id: string;
  /** Human-readable description for the ops dashboard. */
  description: string;
  /** Whether the flag is globally enabled. A false value short-circuits all other checks. */
  enabled: boolean;
  /**
   * Locale matchers: the flag is active if the user's locale matches ANY entry.
   * Entries may be:
   *   - exact BCP 47 tags: "ar", "ar-EG", "zh-Hans-CN"
   *   - language wildcards: "ar-*" matches any Arabic locale
   *   - region wildcards: "*-EG" matches any locale with region EG
   *   - region group shortcuts: "EU" (EU member states), "MENA", "LATAM", "SEA"
   */
  localeMatchers?: string[];
  /**
   * If set, the flag is only active within this UTC date window.
   */
  dateWindow?: {
    from: string; // ISO 8601 date-time, e.g. "2026-12-01T00:00:00Z"
    to:   string; // ISO 8601 date-time
  };
  /**
   * If set, only this fraction of users (0–1) see the flag as enabled.
   * Uses a deterministic hash of userId + flagId for consistency.
   */
  rolloutPercentage?: number;
  /**
   * Explicit allow-list of user IDs that always see the flag as enabled,
   * regardless of locale or rollout percentage.
   */
  allowList?: string[];
}

// Example KV value for key "flag:rtl-checkout-v2":
// {
//   "id": "rtl-checkout-v2",
//   "description": "New RTL-first checkout flow",
//   "enabled": true,
//   "localeMatchers": ["ar-*", "he", "fa", "ur"],
//   "rolloutPercentage": 0.2,
//   "allowList": ["user_qa_001", "user_qa_002"]
// }
```

---

## Locale Matcher Evaluation

```typescript
// src/lib/locale-match.ts

// ISO 3166-1 alpha-2 region codes for common regional groupings.
// Keep in sync with the ops flag editor.
const REGION_GROUPS: Record<string, Set<string>> = {
  EU: new Set([
    "AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI",
    "FR","GR","HR","HU","IE","IT","LT","LU","LV","MT",
    "NL","PL","PT","RO","SE","SI","SK",
  ]),
  MENA: new Set([
    "AE","BH","DZ","EG","IQ","IR","JO","KW","LB","LY",
    "MA","OM","PS","QA","SA","SY","TN","YE",
  ]),
  LATAM: new Set([
    "AR","BO","BR","CL","CO","CR","CU","DO","EC","GT",
    "HN","MX","NI","PA","PE","PR","PY","SV","UY","VE",
  ]),
  SEA: new Set([
    "ID","KH","LA","MM","MY","PH","SG","TH","TL","VN",
  ]),
};

/**
 * Returns true if `locale` matches the given matcher pattern.
 * Patterns:
 *   "ar"       → exact language match (no region required)
 *   "ar-EG"    → exact language+region match
 *   "ar-*"     → language prefix match (any region)
 *   "*-EG"     → any language with region EG
 *   "EU"       → any locale whose region is in the EU group
 */
export function matchesPattern(locale: string, pattern: string): boolean {
  // Named region group shortcut
  if (REGION_GROUPS[pattern]) {
    try {
      const region = new Intl.Locale(locale).maximize().region;
      return region ? REGION_GROUPS[pattern].has(region) : false;
    } catch {
      return false;
    }
  }

  // Wildcard patterns
  if (pattern.endsWith("-*")) {
    const langPrefix = pattern.slice(0, -2).toLowerCase();
    return locale.toLowerCase().startsWith(langPrefix + "-") || locale.toLowerCase() === langPrefix;
  }
  if (pattern.startsWith("*-")) {
    const regionSuffix = pattern.slice(2).toUpperCase();
    try {
      const region = new Intl.Locale(locale).maximize().region;
      return region === regionSuffix;
    } catch {
      return false;
    }
  }

  // Exact match: normalize both to lowercase for comparison
  // but also allow "ar" to match "ar-EG" (language-only flag matches any sublang)
  const patternLoc = new Intl.Locale(pattern);
  const userLoc    = new Intl.Locale(locale);
  if (patternLoc.region) {
    // Pattern has a region: require exact language + region
    return patternLoc.language === userLoc.language
      && patternLoc.region === (userLoc.maximize().region ?? userLoc.region);
  }
  // Pattern has only language: match any region
  return patternLoc.language === userLoc.language;
}

export function matchesAnyPattern(locale: string, patterns: string[]): boolean {
  return patterns.some((p) => matchesPattern(locale, p));
}
```

---

## Deterministic Percentage Rollout Hash

```typescript
// src/lib/rollout.ts

/**
 * Returns a stable float in [0, 1) for a given userId + flagId pair.
 * Uses djb2 — fast, no crypto required, deterministic across restarts.
 */
export function rolloutBucket(userId: string, flagId: string): number {
  const key = `${userId}\x00${flagId}`;
  let h = 5381;
  for (let i = 0; i < key.length; i++) {
    h = Math.imul(h, 33) ^ key.charCodeAt(i);
  }
  // Map unsigned 32-bit to [0, 1)
  return (h >>> 0) / 0x100000000;
}

// For flags without a userId (anonymous users), use a session token
// or fall back to treating all anonymous traffic as a single bucket.
export function isInRollout(
  userId: string | null,
  flagId: string,
  percentage: number
): boolean {
  if (percentage >= 1) return true;
  if (percentage <= 0) return false;
  const bucket = rolloutBucket(userId ?? "anon", flagId);
  return bucket < percentage;
}
```

---

## Flag Evaluator with KV Caching

```typescript
// src/lib/flags.ts

import { type FeatureFlag } from "../types/feature-flag";
import { matchesAnyPattern } from "./locale-match";
import { isInRollout } from "./rollout";

export interface FlagEvalContext {
  locale: string;
  userId: string | null;
  now?: Date;
}

const FLAG_CACHE = new Map<string, { flag: FeatureFlag; expiresAt: number }>();
const FLAG_TTL_MS = 60_000; // 60 s in-memory cache per isolate

export async function getFlag(
  flagId: string,
  kv: KVNamespace
): Promise<FeatureFlag | null> {
  const now = Date.now();
  const cached = FLAG_CACHE.get(flagId);
  if (cached && cached.expiresAt > now) return cached.flag;

  const raw = await kv.get<FeatureFlag>(`flag:${flagId}`, "json");
  if (!raw) {
    FLAG_CACHE.set(flagId, { flag: null as unknown as FeatureFlag, expiresAt: now + FLAG_TTL_MS });
    return null;
  }
  FLAG_CACHE.set(flagId, { flag: raw, expiresAt: now + FLAG_TTL_MS });
  return raw;
}

export async function evaluateFlag(
  flagId: string,
  ctx: FlagEvalContext,
  kv: KVNamespace
): Promise<boolean> {
  const flag = await getFlag(flagId, kv);
  if (!flag) return false;
  if (!flag.enabled) return false;

  // Allow-list always wins
  if (ctx.userId && flag.allowList?.includes(ctx.userId)) return true;

  // Locale gate
  if (flag.localeMatchers && flag.localeMatchers.length > 0) {
    if (!matchesAnyPattern(ctx.locale, flag.localeMatchers)) return false;
  }

  // Date window
  if (flag.dateWindow) {
    const checkAt = ctx.now ?? new Date();
    const from = new Date(flag.dateWindow.from);
    const to   = new Date(flag.dateWindow.to);
    if (checkAt < from || checkAt > to) return false;
  }

  // Percentage rollout
  if (flag.rolloutPercentage !== undefined && flag.rolloutPercentage < 1) {
    if (!isInRollout(ctx.userId, flagId, flag.rolloutPercentage)) return false;
  }

  return true;
}

/**
 * Evaluate multiple flags in parallel.
 */
export async function evaluateFlags(
  flagIds: string[],
  ctx: FlagEvalContext,
  kv: KVNamespace
): Promise<Record<string, boolean>> {
  const results = await Promise.all(
    flagIds.map(async (id) => [id, await evaluateFlag(id, ctx, kv)] as const)
  );
  return Object.fromEntries(results);
}
```

---

## Worker Handler: Gate Features per Request

```typescript
// src/index.ts

import { evaluateFlags } from "./lib/flags";
import { type FlagEvalContext } from "./lib/flags";

export interface Env {
  FLAGS: KVNamespace;
}

const FEATURE_FLAGS = [
  "rtl-checkout-v2",
  "sepa-payment",
  "holiday-jp-ko",
  "new-currency-selector",
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = request.headers.get("X-Detected-Locale") ?? "en";
    const userId = request.headers.get("X-User-Id") ?? null;

    const ctx: FlagEvalContext = { locale, userId };
    const flags = await evaluateFlags(FEATURE_FLAGS, ctx, env.FLAGS);

    return new Response(JSON.stringify({ locale, userId, flags }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Managing Flags via the Cloudflare REST API

Write and update flag definitions from a CI pipeline or an admin UI without a Worker redeployment:

```bash
# Set a flag via wrangler
wrangler kv:key put --namespace-id=<FLAGS_NAMESPACE_ID> \
  "flag:sepa-payment" \
  '{"id":"sepa-payment","description":"SEPA payment method for EU","enabled":true,"localeMatchers":["EU"]}'

# Enable an RTL feature for Arabic with 20 % rollout
wrangler kv:key put --namespace-id=<FLAGS_NAMESPACE_ID> \
  "flag:rtl-checkout-v2" \
  '{
    "id": "rtl-checkout-v2",
    "description": "RTL checkout redesign",
    "enabled": true,
    "localeMatchers": ["ar-*", "he", "fa", "ur"],
    "rolloutPercentage": 0.2,
    "allowList": ["user_qa_001"]
  }'

# List all flags
wrangler kv:key list --namespace-id=<FLAGS_NAMESPACE_ID> --prefix="flag:"
```

---

## Anti-patterns

- **Storing flags per locale key** (e.g., `flag:rtl-checkout-v2:ar`). This explodes into O(locales × flags) KV keys and makes updating a flag's locale set require touching many keys atomically — which KV does not support.
- **Evaluating flags inside a tight loop.** `evaluateFlag` performs a KV read on cold cache. Evaluate all needed flags once per request with `evaluateFlags`, then pass the result map down to handlers.
- **Using the flag system for A/B tests that require statistical rigor.** The djb2 hash is good enough for gradual rollouts but not for balanced experiment splits. Use Cloudflare Zaraz or a dedicated A/B testing platform for scientific experiments.
- **Checking `Date.now()` directly in the date-window guard without injecting `now`.** Passing `now` as a context field makes flag evaluation deterministic in tests.
- **Forgetting to invalidate the in-memory cache after a KV write.** The isolate-level `FLAG_CACHE` map is not shared across Workers instances. After writing a new flag value, the old value may persist up to `FLAG_TTL_MS` in existing isolates. Design UI to show "changes take effect within 60 seconds."

---

## Gotchas

- KV global propagation is eventually consistent: a write on the US data center may take up to 60 seconds to appear in Asian PoPs. For time-critical launches (e.g., midnight campaign starts), set `dateWindow.from` a few minutes before the intended launch to absorb propagation lag.
- The isolate-level `FLAG_CACHE` (a module-level `Map`) persists across requests in the same isolate but is not shared across isolates or Worker instances. Total memory per isolate is 128 MB; a `Map` of 1000 small flag objects is well within budget.
- `new Intl.Locale(pattern)` throws `RangeError` for malformed BCP 47 tags. If operators can enter arbitrary patterns, wrap the constructor call in try/catch in `matchesPattern` and log the bad pattern.
- The `rolloutBucket` function uses `Math.imul` for 32-bit integer multiplication that avoids floating-point drift. `Math.imul` is available in Workers (V8 ≥ 6.0).
- Worker KV reads from the same PoP as the request are typically sub-millisecond for keys that were read recently. First-read latency (cache miss at the PoP) is 10–50 ms. Batch all flag reads with `evaluateFlags` to amortize this cost.

---

## Verification

```typescript
// tests/flags.test.ts
import { describe, it, expect, vi } from "vitest";
import { matchesAnyPattern } from "../src/lib/locale-match";
import { isInRollout, rolloutBucket } from "../src/lib/rollout";

describe("locale matcher", () => {
  it("matches language wildcard ar-*", () => {
    expect(matchesAnyPattern("ar-EG", ["ar-*"])).toBe(true);
    expect(matchesAnyPattern("ar",    ["ar-*"])).toBe(true);
    expect(matchesAnyPattern("de-AT", ["ar-*"])).toBe(false);
  });

  it("matches EU region group", () => {
    expect(matchesAnyPattern("de-DE", ["EU"])).toBe(true);
    expect(matchesAnyPattern("en-US", ["EU"])).toBe(false);
    expect(matchesAnyPattern("fr-FR", ["EU"])).toBe(true);
  });

  it("matches region wildcard *-EG", () => {
    expect(matchesAnyPattern("ar-EG", ["*-EG"])).toBe(true);
    expect(matchesAnyPattern("en-EG", ["*-EG"])).toBe(true);
    expect(matchesAnyPattern("en-US", ["*-EG"])).toBe(false);
  });
});

describe("rollout bucket", () => {
  it("is stable for same userId+flagId", () => {
    const a = rolloutBucket("user_123", "rtl-checkout-v2");
    const b = rolloutBucket("user_123", "rtl-checkout-v2");
    expect(a).toBe(b);
  });

  it("distributes across [0, 1)", () => {
    const buckets = Array.from({ length: 1000 }, (_, i) =>
      rolloutBucket(`user_${i}`, "test-flag")
    );
    const below50 = buckets.filter((b) => b < 0.5).length;
    // Should be approximately 500, allow ±10% tolerance
    expect(below50).toBeGreaterThan(430);
    expect(below50).toBeLessThan(570);
  });

  it("50% rollout enrolls ~half of users", () => {
    const enrolled = Array.from({ length: 1000 }, (_, i) =>
      isInRollout(`user_${i}`, "test-flag", 0.5)
    ).filter(Boolean).length;
    expect(enrolled).toBeGreaterThan(430);
    expect(enrolled).toBeLessThan(570);
  });
});
```

Run: `npx vitest run tests/flags.test.ts`

Verify live flag evaluation in the Workers dashboard by checking the `Content-Type: application/json` response from a request with `X-Detected-Locale: ar-SA` and confirming `rtl-checkout-v2` is `true`.

---

## Related

- `locale-negotiation-accept-language.md`
- `multi-locale-ab-testing-workers.md`
- `workers-durable-objects-locale-session-state.md`
- `translation-kv-caching-ttl-strategy.md`
- `kv-locale-key-sharding-high-traffic.md`

---

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- BCP 47 Language Tag syntax: https://www.rfc-editor.org/rfc/rfc5646
- CLDR Supplemental Territory Data (region memberships): https://github.com/unicode-org/cldr/blob/main/common/supplemental/supplementalData.xml
- ECMA-402 `Intl.Locale`: https://tc39.es/ecma402/#locale-objects
- Cloudflare Workers KV `get` with cache TTL: https://developers.cloudflare.com/kv/api/read-key-value-pairs/
