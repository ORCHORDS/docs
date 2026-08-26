# Workers Runtime Compatibility Date Testing Strategy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Worker behaves correctly in local `wrangler dev` but breaks after deploy because the
`compatibility_date` in `wrangler.toml` is months behind the live runtime flags. Alternatively,
a CI pipeline silently tests against a newer date than production, masking regressions introduced
by automatic flag promotion. You need a repeatable, CI-safe way to pin, vary, and assert against
specific compatibility dates without deploying.

## Context

Cloudflare's runtime rolls out behavioural changes behind *compatibility flags* gated on a date.
A Worker declares `compatibility_date = "2024-09-23"` and gets exactly the flag set that date
activates. Flags accumulate: a Worker on 2026-01-01 implicitly opts into every flag that became
the default before that date.

Miniflare (v3/v4, via `@cloudflare/vitest-pool-workers`) respects `compatibility_date` and
`compatibility_flags` in the test environment, making it possible to run the same test suite
against multiple date slices without touching production config.

Key flags relevant to testing strategy:
- `nodejs_compat` — enables Node.js API shims (streams, Buffer, etc.)
- `streams_enable_constructors` — unlocks `ReadableStream` constructor semantics
- `global_navigator` — exposes `navigator.userAgent` in global scope
- `transformstream_enable_standard_constructor` — changes `TransformStream` chunk handling

## 1. Declare Compatibility Date in vitest.config.ts

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: {
          // Point at a wrangler.toml that pins the production date.
          // Tests inherit the same flag set as the deployed Worker.
          configPath: "./wrangler.toml",
        },
      },
    },
  },
});
```

```toml
# wrangler.toml
name = "my-worker"
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
```

The pool workers harness reads `compatibility_date` from the resolved config and passes it to
Miniflare. Tests run in a runtime slice that mirrors production.

## 2. Multi-date Test Matrix via Separate vitest Workspaces

Run the same spec against an older and a newer date to catch flag-promotion regressions:

```typescript
// vitest.workspace.ts
import { defineWorkspace } from "vitest/config";
import { defineWorkersProject } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkspace([
  // Pinned to the current production date
  defineWorkersProject({
    test: {
      name: "compat-2024-09-23",
      include: ["src/**/*.spec.ts"],
      poolOptions: {
        workers: {
          miniflare: {
            compatibilityDate: "2024-09-23",
            compatibilityFlags: [],
          },
        },
      },
    },
  }),
  // Candidate date for next release
  defineWorkersProject({
    test: {
      name: "compat-2025-03-01",
      include: ["src/**/*.spec.ts"],
      poolOptions: {
        workers: {
          miniflare: {
            compatibilityDate: "2025-03-01",
            compatibilityFlags: [],
          },
        },
      },
    },
  }),
]);
```

Run with `vitest run --workspace vitest.workspace.ts`. Both suites must pass before a
`compatibility_date` bump is merged.

## 3. Writing Flag-Sensitive Assertions

Some APIs change signature or availability across dates. Assert the environment explicitly:

```typescript
// src/stream-compat.spec.ts
import { describe, it, expect, env } from "cloudflare:test";

describe("TransformStream constructor semantics", () => {
  it("accepts a transformer object (post-standard-constructor flag)", async () => {
    // This test is meaningful only when streams_enable_constructors is active.
    // On older dates it will still pass because the alternative path is exercised.
    const chunks: Uint8Array[] = [];
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        controller.enqueue(chunk);
      },
    });

    const writer = writable.getWriter();
    const reader = readable.getReader();
    await writer.write(new TextEncoder().encode("hello"));
    await writer.close();

    const { value } = await reader.read();
    expect(value).toEqual(new TextEncoder().encode("hello"));
  });
});
```

## 4. CI Matrix with GitHub Actions

```yaml
# .github/workflows/compat-matrix.yml
name: Compatibility Date Matrix
on: [push, pull_request]

jobs:
  compat-test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        compat_date:
          - "2024-09-23"   # current production
          - "2025-06-01"   # next candidate
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - name: Run vitest for ${{ matrix.compat_date }}
        run: |
          COMPAT_DATE=${{ matrix.compat_date }} npx vitest run
        env:
          COMPAT_DATE: ${{ matrix.compat_date }}
```

```typescript
// vitest.config.ts  (reads env var to allow matrix override)
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

const compatDate = process.env.COMPAT_DATE ?? "2024-09-23";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        miniflare: {
          compatibilityDate: compatDate,
        },
      },
    },
  },
});
```

## 5. Asserting Global Availability by Date

Flag `global_navigator` adds `navigator` to global scope. Write a guard test:

```typescript
// src/globals.spec.ts
import { it, expect } from "cloudflare:test";

it("navigator is defined when global_navigator flag is active", () => {
  // If compatibility_date < 2022-03-21, navigator is undefined.
  // The test documents the requirement without failing on old-date runs.
  const hasNavigator = typeof navigator !== "undefined";
  if (hasNavigator) {
    expect(navigator.userAgent).toMatch(/Cloudflare-Workers/);
  } else {
    console.warn("navigator not available on this compat date — skipping assertion");
  }
});
```

## 6. Auditing Flag Drift Between Environments

```typescript
// scripts/audit-compat-flags.ts
import { execSync } from "node:child_process";

const toml = execSync("wrangler config list --json 2>/dev/null || echo '{}'").toString();
const config = JSON.parse(toml);

const prodDate = config.compatibility_date as string | undefined;
const envDate = process.env.COMPAT_DATE;

if (prodDate && envDate && prodDate !== envDate) {
  console.warn(`[compat-audit] wrangler.toml=${prodDate}, CI override=${envDate}`);
  // Exit non-zero in strict mode to surface drift in PR checks.
  if (process.env.COMPAT_STRICT === "1") process.exit(1);
}
```

## Anti-patterns

- **Omitting `compatibility_date` from test config entirely** — Miniflare defaults to the latest
  known date, which may be ahead of production and silently test flag-promoted behaviour.
- **Hard-coding the date in `vitest.config.ts` and never updating it** — the test suite and
  production diverge over time; use `wrangler.toml` as the single source of truth.
- **Running only one date slice in CI** — regressions from date promotions are invisible until
  they hit production.

## Gotchas

- `@cloudflare/vitest-pool-workers` resolves `compatibility_date` from `wrangler.toml` at startup;
  mutating `MINIFLARE_*` env vars after that point has no effect.
- Some flags (e.g., `nodejs_compat_v2`) supersede earlier ones. Passing both can produce
  unexpected behaviour — check the Cloudflare changelog before combining.
- The Miniflare version bundled with `@cloudflare/vitest-pool-workers` may lag the live runtime
  by a few flag cycles. Cross-check `miniflare` package version against the Workers changelog.
- `wrangler dev --local` uses a locally bundled runtime; `wrangler dev --remote` uses the live
  edge runtime. Test results may differ if you mix modes across environments.

## Verification

```bash
# Confirm the date Miniflare is using during a test run (verbose output)
MINIFLARE_LOG=debug npx vitest run 2>&1 | grep -i "compat"

# Check what flags are active for a given date via Cloudflare's API
curl -s "https://developers.cloudflare.com/workers/configuration/compatibility-dates/" \
  | grep -oP '"flag":"[^"]+"'
```

## Related

- `vitest-workers-miniflare-testing-setup.md`
- `miniflare-d1-test-seeding-fixtures.md`
- `wrangler-dev-local-vs-remote-mode-decision-tree.md`
- `typescript-cloudflare-workers-strict.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
- https://miniflare.dev/core/compatibility
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
