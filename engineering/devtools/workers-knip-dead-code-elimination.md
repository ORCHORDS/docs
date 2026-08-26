# Dead Code Elimination with Knip in Cloudflare Workers Projects

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Workers codebase has grown over many months. Refactors left behind:
- Exported functions that nothing imports
- Unused TypeScript types and interfaces
- Dependencies listed in `package.json` that no source file references
- Dead utility modules that esbuild technically tree-shakes at build time but that still cost review and maintenance effort

The team wants an automated tool that surfaces these problems in CI before they accumulate further.

---

## Context

Knip is a static analysis tool that maps the full import graph of a TypeScript/JavaScript project, identifies what is unused, and reports it as a structured list. Unlike esbuild tree-shaking (which silently drops dead code at bundle time), Knip makes the dead code *visible* so developers can make an informed decision: delete it, document it, or exclude it intentionally.

For Cloudflare Workers projects, Knip needs guidance on:
- Which file is the Worker entry point (the module default export consumed by the runtime)
- Wrangler-generated type files that must be excluded
- Test runner entry points so test helpers are not flagged as unused

Knip version targeted: **5.x**. Wrangler version targeted: **3.x**.

---

## Solution

### 1. Install Knip

```bash
npm install --save-dev knip
```

### 2. knip.json — Workers-optimised configuration

```json
{
  "$schema": "https://unpkg.com/knip@5/schema.json",
  "entry": [
    "src/index.ts",
    "src/scheduled.ts",
    "src/queue-consumer.ts"
  ],
  "project": [
    "src/**/*.ts"
  ],
  "ignore": [
    "worker-configuration.d.ts",
    ".wrangler/**",
    "dist/**"
  ],
  "ignoreDependencies": [
    "wrangler",
    "@cloudflare/workers-types"
  ],
  "ignoreExportsUsedInFile": true,
  "rules": {
    "classMembers": "warn",
    "duplicates": "warn",
    "enumMembers": "warn",
    "exports": "error",
    "files": "error",
    "nsExports": "error",
    "nsTypes": "error",
    "types": "error",
    "unlisted": "error",
    "unresolved": "error"
  }
}
```

Key decisions:
- **`entry`** explicitly lists all Worker scripts. Knip uses these as roots for the import graph. Without this, every export in `src/` is considered dead.
- **`ignoreDependencies`** excludes `wrangler` (a CLI tool, not an imported module) and `@cloudflare/workers-types` (ambient types, never `import`-ed directly).
- **`ignoreExportsUsedInFile`** prevents false positives on patterns like a module that exports a helper and also calls it internally.

### 3. Entry point for a multi-handler Worker

```typescript
// src/index.ts — Knip root: all paths lead here
import type { Env } from "./types";
import { handleFetch } from "./handlers/fetch";
import { handleScheduled } from "./handlers/scheduled";
import { handleQueue } from "./handlers/queue";

export default {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
        return handleFetch(request, env, ctx);
    },

    async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
        return handleScheduled(event, env, ctx);
    },

    async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
        return handleQueue(batch, env);
    },
} satisfies ExportedHandler<Env>;
```

Knip traces from `src/index.ts` through every import and marks anything unreachable as unused.

### 4. Detecting unused exports in a utility module

```typescript
// src/utils/crypto.ts
// knip will flag `signPayload` if nothing imports it
export function hashPassword(input: string): Promise<ArrayBuffer> {
    const encoder = new TextEncoder();
    const data = encoder.encode(input);
    return crypto.subtle.digest("SHA-256", data);
}

// Unused — Knip will report this as an unused export
export function signPayload(_payload: string): string {
    return "";
}
```

After running Knip:

```
Unused exports (1)
  src/utils/crypto.ts: signPayload
```

### 5. package.json scripts

```json
{
  "scripts": {
    "knip": "knip",
    "knip:fix": "knip --fix",
    "knip:production": "knip --production"
  }
}
```

- `knip` — full analysis including dev dependencies and test files.
- `knip --production` — analysis scoped to production code only; ideal for pre-deploy checks.
- `knip --fix` — automatically removes unused exports (use with caution in CI; prefer local use).

### 6. CI integration — GitHub Actions

```yaml
# .github/workflows/knip.yml
name: Dead Code Check

on:
  pull_request:
  push:
    branches: [main]

jobs:
  knip:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - run: npm ci

      - name: Run Knip
        run: npx knip --reporter compact
```

`--reporter compact` produces a single-line-per-issue output well suited to CI logs and GitHub Actions annotations.

### 7. Progressive cleanup workflow

When Knip first runs on a legacy codebase it may report hundreds of issues. Use the `@knip/ignore` comment for a staged rollout:

```typescript
// src/legacy/old-helper.ts

// biome-ignore lint: legacy code under active migration
// knip-ignore-next-line -- scheduled for removal in Q3-2026
export function legacyTransform(input: unknown): unknown {
    return input;
}
```

Or use `ignoreExports` in `knip.json` to silence specific symbols while you work through the backlog:

```json
{
  "ignoreExports": [
    "src/legacy/**"
  ]
}
```

Remove the ignore entries as you delete the underlying code.

### 8. Handling wrangler-generated types

Running `wrangler types` generates `worker-configuration.d.ts`:

```typescript
// worker-configuration.d.ts (generated — do not edit)
interface Env {
    API_KEY: string;
    MY_KV: KVNamespace;
}
```

This file is an ambient declaration. It is never `import`-ed, so Knip would flag the `Env` type as unused if the file were included in the project scan. The `ignore` array in `knip.json` above handles this.

---

## Implementation Details

### Entry point specification for Durable Objects

Durable Objects are referenced in `wrangler.toml` by class name, not by import. Knip will flag the class as unused unless you list the DO handler file as an entry:

```json
{
  "entry": [
    "src/index.ts",
    "src/durable-objects/counter.ts"
  ]
}
```

```typescript
// src/durable-objects/counter.ts
export class Counter implements DurableObject {
    private state: DurableObjectState;

    constructor(state: DurableObjectState, _env: Env) {
        this.state = state;
    }

    async fetch(request: Request): Promise<Response> {
        const count = ((await this.state.storage.get<number>("count")) ?? 0) + 1;
        await this.state.storage.put("count", count);
        return Response.json({ count });
    }
}
```

### Monorepo configuration

For a monorepo with multiple Workers packages, use a root `knip.json` with workspace-aware configuration:

```json
{
  "workspaces": {
    "packages/worker-a": {
      "entry": ["src/index.ts"]
    },
    "packages/worker-b": {
      "entry": ["src/index.ts", "src/scheduled.ts"]
    }
  }
}
```

---

## Anti-patterns

- **Running `knip --fix` in CI.** The fix mode modifies source files. Auto-fixing in CI causes the working tree to diverge from the commit SHA being checked, which breaks reproducibility.
- **Omitting `wrangler` from `ignoreDependencies`.** Wrangler is a CLI dev dependency. It is never `import`-ed, so Knip will always flag it as unlisted unless explicitly ignored.
- **Adding every file to `entry`.** The point of Knip is graph reachability. If every file is an entry, every export is reachable and Knip reports nothing.
- **Silencing all warnings with a blanket ignore.** Use targeted `ignoreExports` patterns so the suppress list shrinks over time rather than growing.

---

## Gotchas

- Knip's `--production` flag excludes `devDependencies` from the analysis. If a type package (e.g., `@cloudflare/workers-types`) is in `devDependencies`, add it to `ignoreDependencies` when using `--production`.
- Dynamic `import()` calls are traced, but only when the path is a string literal. `import(someVariable)` is opaque to Knip.
- Re-exports through barrel files (`export * from "./handlers"`) are treated as used by Knip unless `nsExports` is set to `error`, which flags unused namespace re-exports.
- Knip does not understand `wrangler.toml` binding references. Any symbol referenced only by name in `wrangler.toml` (e.g., a DO class name) must be covered by an explicit `entry` declaration.

---

## Verification

```bash
# Run full analysis and review output
npx knip

# Scoped to production code
npx knip --production

# Count total issues (useful for tracking improvement)
npx knip --reporter json | jq '[.files[], .exports[], .types[], .dependencies[]] | length'

# Confirm no regressions after a PR (should exit 0)
npx knip && echo "Clean"
```

---

## Related

- `documentation/categories/devtools/workers-biome-linter-formatter.md`
- `documentation/categories/devtools/workers-release-please-automation.md`
- `documentation/categories/testing/workers-vitest-integration.md`

---

## Sources

- https://knip.dev/overview/getting-started
- https://knip.dev/reference/configuration
- https://knip.dev/guides/handling-issues
- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://developers.cloudflare.com/workers/runtime-apis/durable-objects/
