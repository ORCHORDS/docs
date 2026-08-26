# Knip Dead Code Detection in a Cloudflare Workers Monorepo

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Cloudflare Workers monorepos accumulate unused exports, re-exports, and stale type declarations across packages as APIs evolve. Knip statically analyses the full dependency graph to surface dead code — exports that are never imported anywhere in the workspace — and unused devDependencies, cutting bundle size and reducing cognitive overhead.

## Context

Knip differs from tree-shaking: it operates at the *source* level before bundling, reporting symbols that are exported but consumed nowhere in the project. In a monorepo with shared `packages/` consumed by multiple `workers/` the tool traces cross-package import chains so a type exported from `packages/types` that is used only in a deleted Worker is correctly flagged. Integration as a CI step prevents new dead code from being merged.

## Knip Configuration for a Workers Monorepo

```typescript
// knip.config.ts — place at monorepo root
import type { KnipConfig } from "knip";

const config: KnipConfig = {
  workspaces: {
    // Shared packages
    "packages/*": {
      entry: ["src/index.ts"],
      project: ["src/**/*.ts"],
    },
    // Individual Workers
    "workers/*": {
      entry: ["src/index.ts"],
      project: ["src/**/*.ts"],
      // wrangler.toml can declare additional entry points (cron triggers, queues)
      ignore: ["src/**/*.test.ts"],
    },
  },
  // Knip doesn't understand wrangler.toml bindings — ignore generated types
  ignore: [
    "**/worker-configuration.d.ts",
    "**/.wrangler/**",
  ],
  ignoreDependencies: [
    // wrangler is invoked via CLI, not imported
    "wrangler",
    // esbuild is referenced in wrangler.toml, not in TS imports
    "esbuild",
  ],
};

export default config;
```

## Annotating Intentional Public Exports

```typescript
// packages/shared-types/src/index.ts
// Mark exports consumed by external callers (outside the monorepo)
// so Knip does not flag them as unused.

/** @public */
export type Env = {
  DB: D1Database;
  QUEUE: Queue;
  CACHE: KVNamespace;
};

/** @public */
export type WorkerContext = ExecutionContext;

// Internal helper — Knip will flag this if unused across workers
export function buildCacheKey(prefix: string, id: string): string {
  return `${prefix}:${id}`;
}
```

## CI Integration with pnpm Workspaces

```typescript
// scripts/knip-ci.ts — fail CI on any new dead code
import { execSync } from "node:child_process";

const result = execSync("pnpm knip --reporter json", {
  encoding: "utf-8",
  // Do not throw — we'll inspect the output ourselves
  stdio: ["pipe", "pipe", "pipe"],
});

interface KnipIssue {
  type: string;
  filePath: string;
  symbols?: string[];
}

const report: { issues: KnipIssue[] } = JSON.parse(result);

// Fail only on export-related issues; warn on unused devDependencies
const hardErrors = report.issues.filter((i) =>
  ["exports", "types", "nsExports", "nsTypes"].includes(i.type)
);

if (hardErrors.length > 0) {
  console.error("Knip found unused exports:");
  for (const err of hardErrors) {
    console.error(`  ${err.filePath}: ${err.symbols?.join(", ")}`);
  }
  process.exit(1);
}
```

## package.json Scripts

```json
{
  "scripts": {
    "knip": "knip",
    "knip:fix": "knip --fix --allow-remove-files",
    "knip:report": "knip --reporter markdown > knip-report.md"
  },
  "devDependencies": {
    "knip": "^5.0.0"
  }
}
```

## Anti-patterns

- Running `knip --fix` in CI without review — it deletes files automatically and can remove code that is consumed via dynamic `import()` strings that Knip cannot statically trace.
- Ignoring the entire `workers/` directory to silence false positives instead of adding precise `ignoreDependencies` entries; this defeats the purpose of the tool in the packages most likely to accumulate dead code.
- Treating all `@public` annotations as a substitute for actually publishing the package; if a package is internal-only, remove the annotations and let Knip enforce that nothing is unused.

## Gotchas

- Wrangler's auto-generated `worker-configuration.d.ts` file (from `wrangler types`) re-exports every binding type. Without adding it to `ignore`, Knip will treat every binding type as a used export source and suppress real dead-code warnings in those files.
- Knip reads `tsconfig.json` `paths` aliases; if workers use `@workspace/*` aliases that TypeScript resolves via `compilerOptions.paths`, ensure those same paths are present in the root `tsconfig.json` that Knip loads or it will report false positives for every aliased import.

## Verification

```bash
# Dry-run at monorepo root — list all unused exports
pnpm knip

# Fix safe cases automatically (unused files only, no symbol removal)
pnpm knip --fix --exclude exports,types

# Check a single workspace in isolation
pnpm --filter @acme/auth-worker knip

# Output GitHub Actions annotations
pnpm knip --reporter github-actions
```

## Related

- `devtools/pnpm-workspace-setup.md`
- `devtools/turborepo-cloudflare-workers-pipeline.md`
- `devtools/typescript-cloudflare-workers-strict.md`

## Sources

- https://knip.dev/reference/configuration
- https://knip.dev/guides/monorepos-and-workspaces
- https://developers.cloudflare.com/workers/wrangler/commands/#types
