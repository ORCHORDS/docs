# Fuzz Testing Edge Cases for Workers Request Parsers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your Cloudflare Worker parses incoming request bodies, query parameters, headers, or URL paths. Hand-written unit tests cover the cases you thought of, but you ship a bug when a client sends:

- A body with `null` where your code expects an object.
- An integer overflow value in a numeric field.
- An emoji in a field you sort by.
- A header with commas that your CSV parser splits unexpectedly.
- A deeply nested JSON object that causes O(n²) parsing time.

You need a systematic approach to discover these edge cases automatically, before they reach production.

---

## Context

**Property-based fuzz testing** (using `fast-check`) generates hundreds of random inputs per test run, shrinks failures to the minimal reproducing case, and persists the corpus so CI can replay regressions. Combined with Miniflare's in-process Worker runtime, you can fuzz-test your request parser functions against the actual Worker environment without network overhead.

**Approach:**

1. Extract the parser logic from your `fetch` handler into a pure function.
2. Use `fast-check` to generate arbitrary inputs with structure that approximates valid-but-adversarial requests.
3. Assert **invariants** (properties that must always hold) rather than specific outputs.
4. Replay discovered failures as regression unit tests.

Stack: **Cloudflare Workers, fast-check 3, Vitest 2, `@cloudflare/vitest-pool-workers`**.

---

## 1. Project Setup

```bash
npm install --save-dev fast-check
```

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";

export default defineConfig({
  test: {
    projects: [
      defineWorkersProject({
        test: {
          poolOptions: {
            workers: {
              wranglerConfigPath: "./wrangler.toml",
              isolatedStorage: true,
            },
          },
        },
      }),
    ],
  },
});
```

---

## 2. Request Parser Under Test

```typescript
// src/parsers/search-params.ts

export interface SearchQuery {
  q: string;
  page: number;
  perPage: number;
  tags: string[];
  sortBy: "name" | "price" | "createdAt";
  order: "asc" | "desc";
}

export class ParseError extends Error {
  constructor(
    message: string,
    public readonly field: string
  ) {
    super(message);
    this.name = "ParseError";
  }
}

export function parseSearchParams(url: URL): SearchQuery {
  const q = url.searchParams.get("q") ?? "";

  const rawPage = url.searchParams.get("page");
  const page = rawPage !== null ? Number(rawPage) : 1;
  if (!Number.isInteger(page) || page < 1) {
    throw new ParseError("page must be a positive integer", "page");
  }

  const rawPerPage = url.searchParams.get("perPage");
  const perPage = rawPerPage !== null ? Number(rawPerPage) : 20;
  if (!Number.isInteger(perPage) || perPage < 1 || perPage > 100) {
    throw new ParseError("perPage must be between 1 and 100", "perPage");
  }

  const rawTags = url.searchParams.get("tags");
  const tags = rawTags ? rawTags.split(",").filter(Boolean) : [];

  const validSortFields = ["name", "price", "createdAt"] as const;
  const rawSortBy = url.searchParams.get("sortBy") ?? "createdAt";
  if (!validSortFields.includes(rawSortBy as any)) {
    throw new ParseError(`sortBy must be one of: ${validSortFields.join(", ")}`, "sortBy");
  }
  const sortBy = rawSortBy as SearchQuery["sortBy"];

  const rawOrder = url.searchParams.get("order") ?? "desc";
  if (rawOrder !== "asc" && rawOrder !== "desc") {
    throw new ParseError('order must be "asc" or "desc"', "order");
  }

  return { q, page, perPage, tags, sortBy, order: rawOrder };
}
```

---

## 3. Invariant Definitions

Good fuzz tests assert invariants — properties that must hold for any valid input. Define them separately from tests so they can be reused.

```typescript
// tests/fuzz/invariants.ts
import type { SearchQuery } from "../../src/parsers/search-params";

export const searchQueryInvariants = {
  pageIsPositiveInteger(q: SearchQuery) {
    return Number.isInteger(q.page) && q.page >= 1;
  },
  perPageInRange(q: SearchQuery) {
    return Number.isInteger(q.perPage) && q.perPage >= 1 && q.perPage <= 100;
  },
  sortByIsValidEnum(q: SearchQuery) {
    return ["name", "price", "createdAt"].includes(q.sortBy);
  },
  orderIsValidEnum(q: SearchQuery) {
    return q.order === "asc" || q.order === "desc";
  },
  tagsIsStringArray(q: SearchQuery) {
    return Array.isArray(q.tags) && q.tags.every((t) => typeof t === "string");
  },
  qIsString(q: SearchQuery) {
    return typeof q.q === "string";
  },
};
```

---

## 4. Arbitrary Generators

```typescript
// tests/fuzz/arbitraries.ts
import * as fc from "fast-check";

/**
 * Generates a URL object with valid, in-range search params.
 * fast-check will shrink failing cases toward minimal inputs.
 */
export const validSearchUrl = fc.record({
  q: fc.string({ minLength: 0, maxLength: 500 }),
  page: fc.integer({ min: 1, max: 10_000 }),
  perPage: fc.integer({ min: 1, max: 100 }),
  tags: fc.array(fc.string({ minLength: 1, maxLength: 50 }), { maxLength: 20 }),
  sortBy: fc.constantFrom("name", "price", "createdAt"),
  order: fc.constantFrom("asc", "desc"),
}).map(({ q, page, perPage, tags, sortBy, order }) => {
  const url = new URL("https://worker.example.com/search");
  if (q) url.searchParams.set("q", q);
  url.searchParams.set("page", String(page));
  url.searchParams.set("perPage", String(perPage));
  if (tags.length > 0) url.searchParams.set("tags", tags.join(","));
  url.searchParams.set("sortBy", sortBy);
  url.searchParams.set("order", order);
  return url;
});

/**
 * Generates adversarial URLs: missing fields, wrong types, boundary values.
 */
export const adversarialSearchUrl = fc.string({ minLength: 0, maxLength: 200 })
  .map((query) => {
    try {
      return new URL(`https://worker.example.com/search?${query}`);
    } catch {
      return new URL("https://worker.example.com/search");
    }
  });

/**
 * Generates near-miss inputs: valid structure but boundary/edge values.
 */
export const boundarySearchUrl = fc.record({
  page: fc.oneof(
    fc.constant("0"),
    fc.constant("-1"),
    fc.constant("1"),
    fc.constant("10000"),
    fc.constant("1.5"),
    fc.constant("NaN"),
    fc.constant("Infinity"),
    fc.constant(""),
    fc.constant("999999999999999999999")
  ),
  perPage: fc.oneof(
    fc.constant("0"),
    fc.constant("101"),
    fc.constant("100"),
    fc.constant("1"),
    fc.constant("-1"),
    fc.constant("1.1"),
  ),
  sortBy: fc.oneof(
    fc.constant("name"),
    fc.constant("__proto__"),
    fc.constant("constructor"),
    fc.constant(""),
    fc.constant("name; DROP TABLE products"),
  ),
}).map(({ page, perPage, sortBy }) => {
  const url = new URL("https://worker.example.com/search");
  url.searchParams.set("page", page);
  url.searchParams.set("perPage", perPage);
  url.searchParams.set("sortBy", sortBy);
  return url;
});
```

---

## 5. Fuzz Tests — Valid Input Invariants

```typescript
// tests/fuzz/search-params-valid.fuzz.test.ts
import { describe, it } from "vitest";
import * as fc from "fast-check";
import { parseSearchParams } from "../../src/parsers/search-params";
import { validSearchUrl } from "./arbitraries";
import { searchQueryInvariants } from "./invariants";

describe("parseSearchParams — valid input invariants", () => {
  it("always returns correct types for valid inputs", () => {
    fc.assert(
      fc.property(validSearchUrl, (url) => {
        const result = parseSearchParams(url);
        return (
          searchQueryInvariants.pageIsPositiveInteger(result) &&
          searchQueryInvariants.perPageInRange(result) &&
          searchQueryInvariants.sortByIsValidEnum(result) &&
          searchQueryInvariants.orderIsValidEnum(result) &&
          searchQueryInvariants.tagsIsStringArray(result) &&
          searchQueryInvariants.qIsString(result)
        );
      }),
      { numRuns: 1000, seed: 42 } // Fixed seed for reproducibility in CI
    );
  });

  it("round-trips page and perPage from URL params", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10_000 }),
        fc.integer({ min: 1, max: 100 }),
        (page, perPage) => {
          const url = new URL("https://worker.example.com/search");
          url.searchParams.set("page", String(page));
          url.searchParams.set("perPage", String(perPage));

          const result = parseSearchParams(url);
          return result.page === page && result.perPage === perPage;
        }
      ),
      { numRuns: 500, seed: 42 }
    );
  });

  it("tags split matches original array (no empty strings)", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.string({ minLength: 1, maxLength: 30 }).filter((s) => !s.includes(",")),
          { minLength: 0, maxLength: 10 }
        ),
        (tags) => {
          const url = new URL("https://worker.example.com/search");
          if (tags.length > 0) {
            url.searchParams.set("tags", tags.join(","));
          }

          const result = parseSearchParams(url);
          return (
            result.tags.length === tags.length &&
            result.tags.every((t, i) => t === tags[i])
          );
        }
      ),
      { numRuns: 500, seed: 42 }
    );
  });
});
```

---

## 6. Fuzz Tests — Adversarial and Boundary Inputs

```typescript
// tests/fuzz/search-params-adversarial.fuzz.test.ts
import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { parseSearchParams, ParseError } from "../../src/parsers/search-params";
import { adversarialSearchUrl, boundarySearchUrl } from "./arbitraries";

describe("parseSearchParams — adversarial inputs", () => {
  it("never throws anything other than ParseError or returns an invalid result", () => {
    fc.assert(
      fc.property(adversarialSearchUrl, (url) => {
        try {
          const result = parseSearchParams(url);
          // If parsing succeeds, the result must satisfy all invariants
          return (
            Number.isInteger(result.page) && result.page >= 1 &&
            Number.isInteger(result.perPage) && result.perPage >= 1 && result.perPage <= 100 &&
            ["name", "price", "createdAt"].includes(result.sortBy) &&
            (result.order === "asc" || result.order === "desc")
          );
        } catch (err) {
          // Only ParseError is expected — not TypeError, RangeError, etc.
          return err instanceof ParseError;
        }
      }),
      { numRuns: 2000, seed: 42 }
    );
  });

  it("boundary values either succeed with valid result or throw ParseError", () => {
    fc.assert(
      fc.property(boundarySearchUrl, (url) => {
        try {
          const result = parseSearchParams(url);
          // If it returned, invariants must hold
          if (result.page < 1 || !Number.isInteger(result.page)) return false;
          if (result.perPage < 1 || result.perPage > 100) return false;
          return true;
        } catch (err) {
          return err instanceof ParseError;
        }
      }),
      { numRuns: 500, seed: 42 }
    );
  });

  it("proto-pollution strings are rejected or treated as invalid sortBy", () => {
    const dangerousStrings = [
      "__proto__",
      "constructor",
      "prototype",
      "toString",
      "valueOf",
      "__defineGetter__",
    ];

    for (const dangerous of dangerousStrings) {
      const url = new URL("https://worker.example.com/search");
      url.searchParams.set("sortBy", dangerous);

      expect(() => parseSearchParams(url)).toThrow(ParseError);
    }
  });
});
```

---

## 7. Regression Corpus — Pinning Discovered Failures

When `fast-check` discovers a failure, save the minimal repro as a deterministic regression test:

```typescript
// tests/fuzz/regressions/search-params.regression.test.ts
/**
 * Pinned failures discovered by fuzz testing.
 * Each case here was first found by fast-check and then shrunk to the
 * minimal reproducing input. Add new cases when fuzz runs discover new bugs.
 */
import { describe, it, expect } from "vitest";
import { parseSearchParams, ParseError } from "../../../src/parsers/search-params";

describe("parseSearchParams — regression corpus", () => {
  it("REG-001: page=0 throws ParseError (not NaN-related silently)", () => {
    const url = new URL("https://worker.example.com/search?page=0");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
    expect(() => parseSearchParams(url)).toThrow(/positive integer/);
  });

  it("REG-002: page=1.5 throws ParseError (float is not integer)", () => {
    const url = new URL("https://worker.example.com/search?page=1.5");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
  });

  it("REG-003: perPage=101 throws ParseError (exceeds max)", () => {
    const url = new URL("https://worker.example.com/search?perPage=101");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
  });

  it("REG-004: perPage=0 throws ParseError (below min)", () => {
    const url = new URL("https://worker.example.com/search?perPage=0");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
  });

  it("REG-005: sortBy with SQL injection attempt is rejected", () => {
    const url = new URL("https://worker.example.com/search");
    url.searchParams.set("sortBy", "name; DROP TABLE products");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
  });

  it("REG-006: page=Infinity throws ParseError", () => {
    const url = new URL("https://worker.example.com/search?page=Infinity");
    expect(() => parseSearchParams(url)).toThrow(ParseError);
  });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Fuzzing the whole HTTP handler at once | Hard to shrink failures; errors come from anywhere in the handler | Extract and fuzz individual parser functions |
| Using `fc.anything()` as the generator | Too broad — generates data that bypasses structural constraints; low signal | Build domain-specific arbitraries that reflect realistic-but-adversarial inputs |
| Asserting specific output values in fuzz tests | Fuzz tests should assert invariants, not exact values; specific assertions will fail on most generated inputs | Assert properties (`result.page >= 1`) not values (`result.page === 5`) |
| `numRuns: 10` | Too few runs; most edge cases are not discovered | Use `numRuns: 500` minimum; `2000` for critical parsing paths |
| Skipping fixed seed in CI | Different seeds each run means new failures are not reproducible | Set `seed: 42` (or any constant) in CI; use `seed: Date.now()` locally for exploration |
| Treating any thrown error as acceptable | Hides panics and unhandled type errors | Only `ParseError` (your domain error) should be allowed to escape; assert `err instanceof ParseError` |

---

## Gotchas

- **`fc.assert` is synchronous by default** — if your parser is async (e.g., it reads from D1), use `fc.asyncProperty` and `await fc.assert(fc.asyncProperty(...))`.
- **Shrinking respects the arbitrary structure** — `fc.record` and `fc.map` both shrink correctly; avoid `fc.gen()` with manual URL construction unless you write a custom shrinker.
- **URL constructor throws on malformed URLs** — wrap `new URL(...)` in a try/catch inside `fc.map` to avoid the arbitrary itself throwing, which breaks `fast-check`'s shrinking.
- **`Number("999999999999999999999")` returns `Infinity` in JavaScript** — test numeric overflow explicitly; `Number.isInteger(Infinity)` returns `false`, so your integer check correctly rejects it, but `Number.isFinite` is a safer guard.
- **`fast-check` v3 `seed` behavior** — the seed only guarantees reproducibility for the same `fast-check` version and `numRuns`. Pin the `fast-check` version in `package.json` for deterministic CI.
- **`tags.join(",")` and commas in tag values** — if a user sends `tags=a%2Cb,c`, your comma-split will produce `["a,b", "c"]` not `["a", "b", "c"]`. The fuzz test for tags should filter out tags containing commas, matching what your API documents as valid input.

---

## Verification

```bash
# Run fuzz tests (uses fixed seed; fast, reproducible)
npx vitest run tests/fuzz/

# Run with verbose output to see property counts
npx vitest run tests/fuzz/ --reporter=verbose

# Explore mode: random seed each run, higher numRuns (do not commit)
FAST_CHECK_RUNS=5000 npx vitest run tests/fuzz/ --seed=$(date +%s)

# Run regression corpus separately (should always be green)
npx vitest run tests/fuzz/regressions/

# Expected output:
# ✓ always returns correct types for valid inputs (1000 tests)
# ✓ round-trips page and perPage from URL params (500 tests)
# ✓ never throws anything other than ParseError (2000 tests)
# ✓ boundary values either succeed or throw ParseError (500 tests)
# ✓ REG-001 through REG-006 (regression corpus)
```

---

## Related

- [`property-based-testing-fast-check-workers.md`](property-based-testing-fast-check-workers.md) — broader fast-check patterns for Workers
- [`property-based-testing-shrinking-and-reproducible-failures.md`](property-based-testing-shrinking-and-reproducible-failures.md) — shrinking and seed management
- [`fuzz-testing-basics.md`](fuzz-testing-basics.md) — general fuzz testing concepts
- [`workers-input-fuzzing-afl-libfuzzer.md`](workers-input-fuzzing-afl-libfuzzer.md) — AFL/libFuzzer approach for Workers
- [`zod-api-contract-testing-vitest.md`](zod-api-contract-testing-vitest.md) — schema-based validation with Zod

---

## Sources

- [fast-check Documentation](https://fast-check.dev)
- [fast-check — Property-based Testing](https://fast-check.dev/docs/core-blocks/arbitraries/)
- [fast-check — Seeding and Reproducibility](https://fast-check.dev/docs/configuration/seeding/)
- [Cloudflare Workers — URL API](https://developers.cloudflare.com/workers/runtime-apis/web-standards/#url)
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
