# Pages Functions Middleware Deploy Chain Validation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a Cloudflare Pages project with Pages Functions, middleware defined in
`functions/_middleware.ts` (or nested middleware files) fails silently: authentication
checks are skipped, CORS headers are not attached, or rate-limit logic never fires. The
issue is caused by the Pages middleware chain not being assembled in the expected order, or
by a middleware file exporting incorrectly, with no build-time error and no obvious runtime
signal. The goal is to validate the middleware chain structure statically in CI and verify
execution order dynamically after every deploy.

---

## Context

Pages Functions middleware follows the **Onion Model**: each `_middleware.ts` in the
directory tree wraps the handlers below it. The execution order is:

```
functions/
  _middleware.ts          ← outermost — runs first on request, last on response
  api/
    _middleware.ts        ← inner — runs after root middleware, before route handlers
    users/
      [id].ts             ← innermost route handler
```

A middleware file must export `onRequest` (or `onRequestGet`, `onRequestPost`, etc.) as an
array of `PagesFunction` handlers. If the file exports a single function (not wrapped in an
array), Cloudflare Pages silently drops the middleware.

Common failure modes:
- Export is a bare function instead of an array: `export const onRequest = fn` vs
  `export const onRequest = [fn]`.
- `context.next()` is not awaited — the request continues but the response body is lost.
- Middleware added to a subdirectory inadvertently shadows root middleware for that sub-tree.
- The middleware chain order is assumed incorrectly (e.g., auth before rate-limit when the
  deployed order is reversed).

---

## Middleware File Structure Reference

```typescript
// functions/_middleware.ts — valid export shapes

import type { PagesFunction } from "@cloudflare/workers-types";

// Shape 1: single-item array (most common)
export const onRequest: PagesFunction[] = [
  async (context) => {
    // pre-processing
    const response = await context.next();
    // post-processing
    return response;
  },
];

// Shape 2: multiple middleware in one file (ordered)
const authenticate: PagesFunction = async (context) => {
  const token = context.request.headers.get("Authorization");
  if (!token) return new Response("Unauthorized", { status: 401 });
  return context.next();
};

const addCors: PagesFunction = async (context) => {
  const response = await context.next();
  const newResponse = new Response(response.body, response);
  newResponse.headers.set("Access-Control-Allow-Origin", "*");
  return newResponse;
};

export const onRequest: PagesFunction[] = [authenticate, addCors];
```

---

## Static Middleware Chain Validator (TypeScript)

Run this script in CI before deploying to detect export shape errors and ordering issues.

```typescript
// scripts/validate-middleware-chain.ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

interface MiddlewareFile {
  path: string;
  relativePath: string;
  depth: number;
  content: string;
  issues: string[];
}

const FUNCTIONS_DIR = process.argv[2] ?? "functions";

function getDepth(filePath: string, base: string): number {
  const rel = relative(base, filePath);
  return rel.split("/").length - 1;
}

function collectMiddlewareFiles(dir: string): MiddlewareFile[] {
  const results: MiddlewareFile[] = [];

  function walk(currentDir: string): void {
    for (const entry of readdirSync(currentDir)) {
      const full = join(currentDir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
      } else if (entry === "_middleware.ts" || entry === "_middleware.js") {
        results.push({
          path: full,
          relativePath: relative(dir, full),
          depth: getDepth(full, dir),
          content: readFileSync(full, "utf-8"),
          issues: [],
        });
      }
    }
  }

  walk(dir);
  return results.sort((a, b) => a.depth - b.depth);
}

function validateExportShape(file: MiddlewareFile): void {
  const { content, relativePath } = file;

  // Check for bare function export (not wrapped in array)
  if (/export\s+const\s+onRequest\s*[:=]\s*async/.test(content)) {
    file.issues.push(
      `"onRequest" appears to export a bare async function, not an array. ` +
        `Wrap it: export const onRequest = [myFn];`
    );
  }

  // Check for missing await on context.next()
  const nextCalls = content.match(/context\.next\(\)/g) ?? [];
  const awaitedNextCalls = content.match(/await\s+context\.next\(\)/g) ?? [];
  if (nextCalls.length > awaitedNextCalls.length) {
    file.issues.push(
      `Found ${nextCalls.length} call(s) to context.next() but only ` +
        `${awaitedNextCalls.length} are awaited. Missing await causes response body loss.`
    );
  }

  // Check that onRequest is exported
  if (
    !content.includes("export const onRequest") &&
    !content.includes("export function onRequest") &&
    !content.includes("export { onRequest") &&
    !content.match(/export\s*\{[^}]*onRequest[^}]*\}/)
  ) {
    file.issues.push(
      `No "onRequest" export found. Pages will ignore this middleware file entirely.`
    );
  }

  // Warn if context.next() is called multiple times (response fan-out)
  if (nextCalls.length > 1) {
    file.issues.push(
      `context.next() called ${nextCalls.length} times. Only the first call produces a valid response.`
    );
  }
}

function printChain(files: MiddlewareFile[]): void {
  console.log("\nMiddleware chain (outermost → innermost):");
  for (const file of files) {
    const indent = "  ".repeat(file.depth);
    const status = file.issues.length === 0 ? "✔" : "✘";
    console.log(`${indent}${status}  ${file.relativePath} (depth ${file.depth})`);
  }
}

async function main(): Promise<void> {
  const files = collectMiddlewareFiles(FUNCTIONS_DIR);

  if (files.length === 0) {
    console.log("No _middleware files found. Nothing to validate.");
    return;
  }

  for (const file of files) {
    validateExportShape(file);
  }

  printChain(files);

  const failed = files.filter((f) => f.issues.length > 0);
  if (failed.length > 0) {
    console.error("\nValidation failures:");
    for (const file of failed) {
      console.error(`\n  ${file.relativePath}:`);
      for (const issue of file.issues) {
        console.error(`    - ${issue}`);
      }
    }
    process.exit(1);
  }

  console.log(`\nAll ${files.length} middleware file(s) are valid.`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
```

---

## Runtime Chain Verification Using a Canary Header

Instrument each middleware to inject a response header listing which middleware ran and in
what order. Strip the header in production; use it in staging smoke tests.

```typescript
// functions/_middleware.ts (root)
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  ENVIRONMENT: string;
}

const tracingMiddleware: PagesFunction<Env> = async (context) => {
  const isDev = context.env.ENVIRONMENT !== "production";
  const response = await context.next();

  if (!isDev) return response;

  const newResponse = new Response(response.body, response);
  const existing = newResponse.headers.get("X-Middleware-Chain") ?? "";
  newResponse.headers.set(
    "X-Middleware-Chain",
    existing ? `root,${existing}` : "root"
  );
  return newResponse;
};

export const onRequest: PagesFunction<Env>[] = [tracingMiddleware];
```

```typescript
// functions/api/_middleware.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  ENVIRONMENT: string;
}

const apiAuthMiddleware: PagesFunction<Env> = async (context) => {
  // ... auth logic ...
  const response = await context.next();
  if (context.env.ENVIRONMENT !== "production") {
    const newResponse = new Response(response.body, response);
    const existing = newResponse.headers.get("X-Middleware-Chain") ?? "";
    newResponse.headers.set("X-Middleware-Chain", `api-auth,${existing}`);
    return newResponse;
  }
  return response;
};

export const onRequest: PagesFunction<Env>[] = [apiAuthMiddleware];
```

Smoke test that validates chain order:

```bash
#!/usr/bin/env bash
# scripts/verify-middleware-chain.sh
set -euo pipefail

BASE_URL="${1:-https://my-project.pages.dev}"
EXPECTED_CHAIN="root,api-auth"

ACTUAL_CHAIN=$(curl -s -I "$BASE_URL/api/users/1" | \
  grep -i "x-middleware-chain" | \
  tr -d '\r' | \
  sed 's/x-middleware-chain: //')

if [ "$ACTUAL_CHAIN" != "$EXPECTED_CHAIN" ]; then
  echo "FAIL: Expected middleware chain '$EXPECTED_CHAIN', got '$ACTUAL_CHAIN'"
  exit 1
fi

echo "PASS: Middleware chain is '$ACTUAL_CHAIN'"
```

---

## GitHub Actions CI Pipeline

```yaml
# .github/workflows/pages-functions-deploy.yml
name: Pages Functions Deploy with Middleware Validation

on:
  push:
    branches: [main]

jobs:
  validate-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run build

      - name: Validate middleware chain structure
        run: npx tsx scripts/validate-middleware-chain.ts functions

      - name: Type-check Functions
        run: npx tsc --noEmit --project tsconfig.functions.json

      - name: Deploy to Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: pages deploy dist --project-name my-pages-project --branch main

  smoke-test:
    needs: validate-and-deploy
    runs-on: ubuntu-latest
    env:
      PAGES_URL: "https://my-pages-project.pages.dev"
    steps:
      - uses: actions/checkout@v4

      - name: Wait for deployment propagation
        run: sleep 20

      - name: Verify middleware chain execution order
        run: bash scripts/verify-middleware-chain.sh "$PAGES_URL"

      - name: Verify authentication middleware fires (expect 401 without token)
        run: |
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$PAGES_URL/api/users/1")
          if [ "$STATUS" != "401" ]; then
            echo "FAIL: Expected 401 from auth middleware, got $STATUS"
            exit 1
          fi
          echo "PASS: Auth middleware is intercepting unauthenticated requests."

      - name: Verify CORS headers are present on API routes
        run: |
          CORS=$(curl -s -I -X OPTIONS "$PAGES_URL/api/users" | \
            grep -i "access-control-allow-origin" || true)
          if [ -z "$CORS" ]; then
            echo "FAIL: CORS middleware not running"
            exit 1
          fi
          echo "PASS: $CORS"
```

---

## Nested Middleware Shadowing Audit

When a sub-directory middleware is too broad, it can shadow routes it was not meant to
cover. This script maps which routes each middleware file covers.

```typescript
// scripts/audit-middleware-coverage.ts
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const FUNCTIONS_DIR = "functions";

interface Coverage {
  middlewarePath: string;
  coversRoutes: string[];
}

function getRoutesUnder(dir: string, base: string): string[] {
  const routes: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      routes.push(...getRoutesUnder(full, base));
    } else if (!entry.startsWith("_") && (entry.endsWith(".ts") || entry.endsWith(".js"))) {
      const route = "/" + relative(base, full)
        .replace(/\.(ts|js)$/, "")
        .replace(/\/index$/, "")
        .replace(/\[([^\]]+)\]/g, ":$1");
      routes.push(route);
    }
  }
  return routes;
}

function findMiddlewareFiles(dir: string): string[] {
  const files: string[] = [];
  function walk(current: string): void {
    for (const entry of readdirSync(current)) {
      const full = join(current, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry === "_middleware.ts" || entry === "_middleware.js") {
        files.push(full);
      }
    }
  }
  walk(dir);
  return files;
}

const middlewareFiles = findMiddlewareFiles(FUNCTIONS_DIR);
for (const mw of middlewareFiles) {
  const parentDir = mw.replace(/_middleware\.(ts|js)$/, "");
  const routes = getRoutesUnder(parentDir, FUNCTIONS_DIR);
  const relMw = relative(FUNCTIONS_DIR, mw);
  console.log(`\nMiddleware: ${relMw}`);
  console.log(`  Covers ${routes.length} route(s):`);
  for (const r of routes) console.log(`    ${r}`);
}
```

---

## Anti-patterns

- **Exporting `onRequest` as a bare function** — `export const onRequest = async (ctx) =>
  ...` silently disables the middleware. Always use an array.
- **Not awaiting `context.next()`** — the inner handler runs but the response body is
  dropped, returning an empty 200.
- **Mutating the request object** — `request` is immutable in the Workers runtime. Use
  `new Request(request.url, { ...request, headers: newHeaders })` to pass modified headers
  downstream.
- **Performing expensive work after `context.next()`** — CPU time accumulated after
  `next()` returns still counts toward the Worker's CPU limit.
- **Assuming alphabetical evaluation of sibling middleware files** — only `_middleware.ts`
  files at each directory level are special. Sibling route files have no guaranteed
  execution order relative to each other.

---

## Gotchas

- When a `_middleware.ts` at `functions/api/` level exports `onRequest` for `onRequestGet`
  only, `POST /api/*` requests bypass that middleware entirely. Use `onRequest` (no method
  suffix) to catch all methods.
- Wrangler local dev (`wrangler pages dev`) reloads middleware on file change, but the
  chain assembly is re-evaluated. If the chain order appears correct locally but wrong in
  production, compare the deployed Functions bundle via the Pages dashboard.
- The `env` object in Pages Functions is the Pages project's environment variables — it is
  not the same as a `wrangler.toml` environment binding. Service bindings and Durable
  Object bindings are not available in Pages Functions unless declared via the Pages
  project's bindings configuration.
- Adding a new `_middleware.ts` file without redeploying has no effect — Pages bakes the
  middleware chain at build time.

---

## Verification

```bash
# 1. Run static middleware chain validator
npx tsx scripts/validate-middleware-chain.ts functions

# 2. Run local dev and hit an API route
npx wrangler pages dev dist -- functions

# 3. Inspect X-Middleware-Chain header (staging only)
curl -si https://my-project-branch.pages.dev/api/test | grep -i middleware

# 4. Audit middleware coverage
npx tsx scripts/audit-middleware-coverage.ts

# 5. Confirm type correctness of all Function files
npx tsc --noEmit --project tsconfig.functions.json
```

---

## Related

- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-middleware-versioned-deploy-strategy.md`
- `pages-functions-env-var-management.md`
- `cloudflare-pages-redirect-rule-deploy-validation.md`
- `workers-custom-error-page-deploy-configuration.md`

---

## Sources

- Cloudflare Docs: Pages Functions middleware — https://developers.cloudflare.com/pages/functions/middleware/
- Cloudflare Docs: Pages Functions routing — https://developers.cloudflare.com/pages/functions/routing/
- Cloudflare Docs: Pages Functions API — https://developers.cloudflare.com/pages/functions/api-reference/
- Cloudflare Blog: Pages Functions are now generally available — https://blog.cloudflare.com/pages-functions-are-now-generally-available/
- Workers Runtime: Request immutability — https://developers.cloudflare.com/workers/runtime-apis/request/
