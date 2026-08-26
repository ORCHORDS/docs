# ESLint Import Ordering in Workers Monorepos

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
In a pnpm/Turborepo monorepo containing multiple Cloudflare Workers packages, import statements
are inconsistently ordered — mixing Node builtins, Cloudflare-specific modules (`cloudflare:*`),
internal workspace packages, and relative imports — making diffs noisy and code review harder.

## Context
Workers monorepos have import categories that standard eslint-plugin-import rules do not know about:
the `cloudflare:*` virtual modules (e.g., `cloudflare:test`, `cloudflare:sockets`), the `node:*`
explicit built-in prefix required by Workers `nodejs_compat`, and workspace packages accessed via
`@scope/pkg` aliases. ESLint v9 flat config, combined with `eslint-plugin-import` and a shared
config package, gives every Worker a consistent, auto-fixable import order.

## Shared ESLint Config Package

```
packages/
  eslint-config/
    index.ts      ← shared flat config
    package.json
  worker-api/
    eslint.config.ts
    src/
  worker-queue/
    eslint.config.ts
    src/
```

```json
// packages/eslint-config/package.json
{
  "name": "@repo/eslint-config",
  "version": "0.1.0",
  "main": "./index.ts",
  "exports": { ".": "./index.ts" },
  "dependencies": {
    "eslint-plugin-import": "^2.31.0",
    "eslint-import-resolver-typescript": "^3.7.0"
  }
}
```

## Shared Config: Import Order Groups

```ts
// packages/eslint-config/index.ts
import importPlugin from "eslint-plugin-import";
import type { Linter } from "eslint";

const workersImportOrderConfig: Linter.Config = {
  plugins: { import: importPlugin },
  settings: {
    "import/resolver": {
      typescript: { alwaysTryTypes: true },
    },
    "import/internal-regex": "^@repo/",
  },
  rules: {
    "import/order": [
      "error",
      {
        groups: [
          "builtin",       // node: prefixed built-ins
          "external",      // npm packages
          "internal",      // @repo/* workspace packages
          "parent",        // ../
          "sibling",       // ./
          "index",         // ./index
          "object",        // import type
          "type",          // type-only imports
        ],
        pathGroups: [
          // Cloudflare virtual modules treated as builtins
          {
            pattern: "cloudflare:*",
            group: "builtin",
            position: "before",
          },
          // Hono and Workers runtime as first external
          {
            pattern: "hono{,/**}",
            group: "external",
            position: "before",
          },
          // Internal workspace packages after externals
          {
            pattern: "@repo/**",
            group: "internal",
            position: "after",
          },
        ],
        pathGroupsExcludedImportTypes: ["builtin", "type"],
        "newlines-between": "always",
        alphabetize: { order: "asc", caseInsensitive: true },
      },
    ],
    "import/no-duplicates": "error",
    "import/first": "error",
    "import/newline-after-import": "error",
  },
};

export default [workersImportOrderConfig];
```

## Per-Worker Config

```ts
// packages/worker-api/eslint.config.ts
import sharedConfig from "@repo/eslint-config";
import type { Linter } from "eslint";

const config: Linter.Config[] = [
  ...sharedConfig,
  {
    files: ["src/**/*.ts"],
    rules: {
      // Worker-specific override: allow relative index imports
      "import/no-cycle": "warn",
    },
  },
  {
    // Test files may import from cloudflare:test without ordering requirements
    files: ["src/**/*.test.ts"],
    rules: {
      "import/order": [
        "error",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling"],
          pathGroups: [
            { pattern: "cloudflare:*", group: "builtin", position: "before" },
          ],
          "newlines-between": "always",
          alphabetize: { order: "asc" },
        },
      ],
    },
  },
];

export default config;
```

## Correct Import Order in a Worker

```ts
// ✅ Correct order after eslint --fix
import { env } from "cloudflare:test";          // cloudflare: built-in
import { scheduled } from "cloudflare:sockets"; // cloudflare: built-in

import { Hono } from "hono";                    // external (priority)
import { cors } from "hono/cors";
import { zValidator } from "@hono/zod-validator";
import { z } from "zod";

import { db } from "@repo/database";            // internal workspace
import { logger } from "@repo/logger";

import { handleAuth } from "../auth";           // parent
import { parseBody } from "./utils";            // sibling

import type { Env } from "./types";             // type
```

## Turborepo Lint Pipeline Integration

```json
// turbo.json (relevant excerpt)
{
  "tasks": {
    "lint": {
      "dependsOn": ["^build"],
      "inputs": ["src/**/*.ts", "eslint.config.ts"],
      "cache": true
    },
    "lint:fix": {
      "dependsOn": ["^build"],
      "cache": false
    }
  }
}
```

```bash
# In each package's package.json
{
  "scripts": {
    "lint": "eslint src --max-warnings 0",
    "lint:fix": "eslint src --fix"
  }
}
```

## Anti-patterns
- Do not mix `eslint-plugin-import` with `eslint-plugin-simple-import-sort` in the same config —
  they both manage import ordering and will conflict, producing contradictory autofix output.
- Do not rely solely on `import/order` for monorepos without setting `import/internal-regex`; ESLint
  cannot distinguish workspace packages from external npm packages without it.
- Do not use the legacy `.eslintrc.*` format; `eslint-plugin-import` v2.31+ drops support for it
  in ESLint v9.
- Do not skip `eslint-import-resolver-typescript` — without it, TypeScript path aliases and
  `tsconfig.paths` are not resolved, and `import/no-unresolved` produces false positives.

## Gotchas
- `cloudflare:*` modules are virtual and have no corresponding file; `import/no-unresolved` must
  be configured to ignore them: `"import/no-unresolved": ["error", { ignore: ["^cloudflare:"] }]`.
- The `node:` prefix for built-ins (required by Workers `nodejs_compat`) is not auto-detected by
  older resolver versions; upgrade `eslint-import-resolver-typescript` to ≥3.7.
- `pathGroupsExcludedImportTypes` must list `"builtin"` or the `cloudflare:*` pathGroup will not
  apply to `import type` statements.
- When using Biome alongside ESLint, disable Biome's `organizeImports` in favour of ESLint's rule
  to avoid competing autofix passes on the same files.

## Verification

```bash
# Check import order violations across the monorepo
pnpm turbo lint

# Auto-fix all import ordering in a single package
pnpm --filter worker-api lint:fix

# Verify a specific file's import order
pnpm eslint src/index.ts --rule '{"import/order": "error"}' --max-warnings 0

# Debug resolver resolution
pnpm eslint --print-config src/index.ts | jq '."import/order"'
```

## Related
- `eslint-v9-flat-config-cloudflare-workers.md` — flat config migration guide
- `biome-eslint-staged-migration-workers-monorepo.md` — migrating from ESLint to Biome
- `turborepo-cloudflare-workers-pipeline.md` — Turborepo task pipeline setup
- `pnpm-workspace-setup.md` — pnpm workspace and `@repo/*` package conventions

## Sources
- https://github.com/import-js/eslint-plugin-import
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://eslint.org/docs/latest/use/configure/configuration-files
- https://turbo.build/repo/docs/crafting-your-repository/configuring-tasks
