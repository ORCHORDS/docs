# Pages Functions Route Testing Pre-Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying Pages, API routes are silently bypassed — a misconfigured `_routes.json` exclude pattern causes the function to be skipped and a stale static asset is served instead. Alternatively, static asset paths hit a function and waste invocations. Neither failure produces an explicit error; you discover the problem from user reports or an unexpected billing spike. You need to validate `_routes.json` structure and function route coverage before merging.

## Context

Pages Functions routing determines whether a request is handled by a Function (server-side compute) or served directly from the static asset store. Priority is: (1) `_routes.json` explicit include/exclude rules, (2) `functions/` directory file-path matching, (3) catch-all `[[path]].ts` patterns. A broken exclude pattern means your function is silently skipped; a missing include means static assets accidentally route through compute. Pre-deploy route testing — schema validation, unit tests against the matching logic, and local integration with `wrangler pages dev` — catches these before production traffic is affected.

## 1. Validating `_routes.json` Schema

```typescript
// scripts/validate-routes.ts
import { readFile } from "fs/promises";

interface RoutesConfig {
  version: number;
  include?: string[];
  exclude?: string[];
}

const raw = await readFile("public/_routes.json", "utf8");
const config: RoutesConfig = JSON.parse(raw);

if (config.version !== 1) throw new Error(`Unknown _routes.json version: ${config.version}`);

const MAX_RULES = 100; // Cloudflare hard limit — excess rules are silently ignored
const totalRules = (config.include?.length ?? 0) + (config.exclude?.length ?? 0);
if (totalRules > MAX_RULES) throw new Error(`Too many route rules: ${totalRules} (limit ${MAX_RULES})`);

const validPattern = /^\/[a-z0-9\-_/*:.[\]()]*$/i;
for (const pattern of [...(config.include ?? []), ...(config.exclude ?? [])]) {
  if (!validPattern.test(pattern)) throw new Error(`Invalid route pattern: "${pattern}"`);
}

console.log(
  `_routes.json valid — ${config.include?.length ?? 0} include, ${config.exclude?.length ?? 0} exclude rules`
);
```

## 2. Unit-Testing Route Matching Logic

```typescript
// test/routes.test.ts
import { describe, it, expect } from "vitest";
import { readFile } from "fs/promises";

function matchesPattern(path: string, pattern: string): boolean {
  // Mirror Cloudflare Pages route matching: * is a wildcard segment
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`).test(path);
}

function shouldInvokeFunction(path: string, include: string[], exclude: string[]): boolean {
  // Exclude rules take precedence over include rules
  if (exclude.some(p => matchesPattern(path, p))) return false;
  return include.some(p => matchesPattern(path, p));
}

const { include = [], exclude = [] }: { include: string[]; exclude: string[] } = JSON.parse(
  await readFile("public/_routes.json", "utf8")
);

describe("_routes.json — function invocation", () => {
  it("routes /api/* paths to a function", () => {
    expect(shouldInvokeFunction("/api/users", include, exclude)).toBe(true);
    expect(shouldInvokeFunction("/api/health", include, exclude)).toBe(true);
    expect(shouldInvokeFunction("/api/v2/products/123", include, exclude)).toBe(true);
  });

  it("serves /assets/* as static — no function invocation", () => {
    expect(shouldInvokeFunction("/assets/logo.png", include, exclude)).toBe(false);
    expect(shouldInvokeFunction("/assets/bundle.js", include, exclude)).toBe(false);
  });

  it("serves HTML pages as static", () => {
    expect(shouldInvokeFunction("/", include, exclude)).toBe(false);
    expect(shouldInvokeFunction("/about", include, exclude)).toBe(false);
    expect(shouldInvokeFunction("/products/widget", include, exclude)).toBe(false);
  });
});
```

## 3. Audit Function Files Against `_routes.json` Coverage

```typescript
// scripts/audit-function-routes.ts — warn when a function file has no matching include rule
import { glob } from "glob";
import { readFile } from "fs/promises";

const functionFiles = await glob("functions/**/*.ts", {
  ignore: ["**/_middleware.ts", "**/_*.ts"],
});

const { include = [] }: { include: string[] } = JSON.parse(
  await readFile("public/_routes.json", "utf8")
);

let warnings = 0;
for (const file of functionFiles) {
  // Convert functions/api/users/[id].ts → /api/users/:id
  const route = "/" + file
    .replace(/^functions\//, "")
    .replace(/\.ts$/, "")
    .replace(/\[([^\]]+)\]/g, ":$1")
    .replace(/\/index$/, "");

  const covered = include.some(p => {
    const rx = new RegExp("^" + p.replace(/\*/g, ".*") + "($|/)");
    return rx.test(route);
  });

  if (!covered) {
    console.warn(`[WARN] ${file} → ${route} — not covered by any include rule`);
    warnings++;
  } else {
    console.log(`[OK]   ${route}`);
  }
}

if (warnings > 0) {
  console.error(`\n${warnings} function(s) not reachable via _routes.json include rules.`);
  process.exit(1);
}
```

## 4. Local Integration Test with `wrangler pages dev`

```bash
#!/usr/bin/env bash
# scripts/test-routes-local.sh — start Pages dev server and probe critical paths
set -euo pipefail

npx wrangler pages dev ./public --port 8788 &
WRANGLER_PID=$!
trap "kill $WRANGLER_PID 2>/dev/null || true" EXIT

# Wait for server ready (up to 15s)
for i in $(seq 1 15); do
  curl -sf http://localhost:8788/api/health &>/dev/null && break
  sleep 1
done

assert_status() {
  local path=$1 expected=$2
  local actual
  actual=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8788${path}")
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: ${path} returned ${actual} (expected ${expected})"; exit 1
  fi
  echo "PASS: ${path} → ${actual}"
}

# Function routes
assert_status "/api/health" "200"
assert_status "/api/users"  "200"

# Static routes (function should NOT be invoked)
assert_status "/assets/logo.png" "200"
assert_status "/"                "200"

# Verify static responses come from the asset store, not a function
WORKER_HEADER=$(curl -sI http://localhost:8788/about | grep -i "x-functions-invocations" || true)
[ -z "$WORKER_HEADER" ] || echo "WARN: /about appears to be invoking a function — check exclude rules"
```

## 5. CI Gate — Block Deploy on Route Validation Failure

```yaml
# .github/workflows/pages-route-check.yml
name: Pages Route Validation
on:
  pull_request:
    paths:
      - "functions/**"
      - "public/_routes.json"

jobs:
  validate-routes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Validate _routes.json schema
        run: npx tsx scripts/validate-routes.ts

      - name: Audit function-to-route coverage
        run: npx tsx scripts/audit-function-routes.ts

      - name: Run route unit tests
        run: npx vitest run test/routes.test.ts
```

## Anti-patterns

- Testing routes only in production — silent failures aren't caught until users see stale assets or unexpected 404s.
- Using a catch-all include `["/*"]` — defeats the purpose of static serving and wastes function invocations on every request, including images and fonts.
- Generating `_routes.json` with more than 100 rules — Cloudflare silently ignores excess rules; all requests fall through to functions.
- Placing static asset files inside `functions/` — they are treated as functions, not served from the asset store.
- Not testing the exclude list — a typo in an exclude pattern (`/assets` vs `/assets/*`) can send all asset requests to your function.

## Gotchas

- Exclude rules take precedence over include rules regardless of list order within `_routes.json`; a path that matches both an include and an exclude is always served as static.
- `[[path]].ts` (catch-all) always matches if no more-specific file-based route exists; pair it with asset exclude rules or it captures all static requests too.
- `_middleware.ts` applies to every route in its directory subtree; a runtime error in middleware prevents all function responses below it — test middleware independently.
- `wrangler pages dev` does not perfectly replicate production `_routes.json` handling in all edge cases; supplement local tests with a `wrangler pages deploy --dry-run` to catch bundle-time issues.
- The `functions/` file-path matching is case-sensitive on Linux CI but the deployed edge may differ — use lowercase route segments consistently.

## Verification

```bash
# Schema and coverage checks
npx tsx scripts/validate-routes.ts
npx tsx scripts/audit-function-routes.ts
npx vitest run test/routes.test.ts

# Local integration
bash scripts/test-routes-local.sh

# Post-deploy: inspect live routing via response headers
curl -sI https://your-project.pages.dev/api/health | grep -i "cf-ray"
curl -sI https://your-project.pages.dev/assets/logo.png | grep -i "cache-control"
```

## Related

- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-functions-middleware-deploy-chain-validation.md`
- `deploy-gate-e2e-tests-playwright-pages.md`
- `pages-functions-bundling-edge-cases.md`
- `cloudflare-pages-redirect-rule-deploy-validation.md`

## Sources

- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/advanced-mode/
- https://developers.cloudflare.com/pages/configuration/serving-pages/
- https://developers.cloudflare.com/workers/testing/local-development/
