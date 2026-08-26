# TSC Incremental Build Workers Monorepo Performance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A monorepo containing 5–20 Cloudflare Workers packages runs `tsc --build` on every push and
the full type-check takes 45–90 seconds, blocking the CI fast-feedback loop. Switching to
`--incremental` shaves rebuild time to under 5 seconds on unchanged code, but the `tsbuildinfo`
files accumulate in unexpected locations, cache misses happen on clean CI clones, and composite
project references interact badly with path aliases and `@cloudflare/workers-types`.

## Context

TypeScript offers two orthogonal performance levers:

- **`--incremental`** (`incremental: true` in `tsconfig.json`) — writes `.tsbuildinfo` next to
  the output, stores a dependency graph and file hashes, and skips re-emitting unchanged files.
  Works for a single package; does not understand cross-package dependencies.
- **Project references** (`--build` / `tsc -b`) — composes multiple `tsconfig.json` files into
  a build graph, delegates incremental state per package. The correct choice for monorepos.

The common trap: enabling `incremental` globally without project references causes every package
to re-read every imported source file on every invocation, producing a `.tsbuildinfo` that is
larger than useful and offers minimal speedup.

## 1. Baseline: Project References in a pnpm Monorepo

```
packages/
  shared/          ← utility types and functions
    tsconfig.json
  api-worker/      ← depends on shared
    tsconfig.json
  auth-worker/     ← depends on shared
    tsconfig.json
tsconfig.json      ← root references file (no src files of its own)
```

```json
// tsconfig.json  (root — references only, no files)
{
  "files": [],
  "references": [
    { "path": "packages/shared" },
    { "path": "packages/api-worker" },
    { "path": "packages/auth-worker" }
  ]
}
```

```json
// packages/shared/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "composite": true,          // required for project references
    "incremental": true,        // implied by composite, explicit for clarity
    "declarationMap": true,     // source-map for go-to-definition across packages
    "declaration": true,        // required by composite
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src"]
}
```

```json
// packages/api-worker/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "composite": true,
    "incremental": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "references": [
    { "path": "../shared" }     // type-check shared, use its declarations
  ],
  "include": ["src"]
}
```

Build command:

```bash
tsc --build              # builds all references in dependency order
tsc --build --watch      # incremental watch mode across all packages
tsc --build --dry        # prints what would be rebuilt without doing it
tsc --build --verbose    # shows which files are reused vs rebuilt
```

## 2. Controlling tsbuildinfo Location

By default `tsbuildinfo` is written to `outDir`. In some monorepo setups the `dist/` directory
is gitignored and cleaned between CI runs, invalidating the incremental cache. Pin a stable
location:

```json
// packages/api-worker/tsconfig.json
{
  "compilerOptions": {
    "composite": true,
    "incremental": true,
    "tsBuildInfoFile": ".cache/.tsbuildinfo",  // survives dist/ cleans
    "outDir": "dist",
    "rootDir": "src"
  }
}
```

```bash
# .gitignore
packages/**/dist/
packages/**/.cache/
```

In CI, cache the `.cache/` directories between runs:

```yaml
# .github/workflows/typecheck.yml
- name: Restore tsbuildinfo cache
  uses: actions/cache@v4
  with:
    path: |
      packages/**/.cache/.tsbuildinfo
    key: tsbuildinfo-${{ runner.os }}-${{ hashFiles('packages/**/src/**/*.ts', 'packages/**/tsconfig.json') }}
    restore-keys: |
      tsbuildinfo-${{ runner.os }}-
```

## 3. Workers-Specific tsconfig Base

Cloudflare Workers types require special `lib` and `types` settings. Extract a shared base to
avoid duplication and drift:

```json
// tsconfig.workers-base.json  (repository root)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noEmit": false,
    "skipLibCheck": false,
    "isolatedModules": true,
    "verbatimModuleSyntax": true
  }
}
```

```json
// packages/api-worker/tsconfig.json
{
  "extends": "../../tsconfig.workers-base.json",
  "compilerOptions": {
    "composite": true,
    "incremental": true,
    "tsBuildInfoFile": ".cache/.tsbuildinfo",
    "outDir": "dist",
    "rootDir": "src"
  },
  "references": [{ "path": "../shared" }],
  "include": ["src"]
}
```

## 4. Type-only Check Script (noEmit Fast Path)

During development, skipping emit and using `noEmit: true` is faster than a full composite
build. Add a separate tsconfig for IDE and CI type-checking without generating output:

```json
// packages/api-worker/tsconfig.check.json
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "noEmit": true,
    "composite": false,      // composite is incompatible with noEmit
    "incremental": true,
    "tsBuildInfoFile": ".cache/.tsbuildinfo-check"
  }
}
```

```json
// package.json
{
  "scripts": {
    "typecheck": "tsc --project tsconfig.check.json",
    "typecheck:watch": "tsc --project tsconfig.check.json --watch",
    "build:types": "tsc --build tsconfig.json"
  }
}
```

Use `typecheck` in CI fast-feedback jobs (< 5 s incremental) and `build:types` only during
release to generate the actual `dist/` declarations.

## 5. Turborepo Pipeline for Incremental Builds

```json
// turbo.json
{
  "$schema": "https://turborepo.com/schema.json",
  "tasks": {
    "typecheck": {
      "dependsOn": ["^typecheck"],
      "inputs": ["src/**/*.ts", "tsconfig*.json"],
      "outputs": [".cache/.tsbuildinfo-check"],
      "cache": true
    },
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**/*.ts", "tsconfig.json"],
      "outputs": ["dist/**", ".cache/.tsbuildinfo"],
      "cache": true
    }
  }
}
```

```bash
# Run incremental type-checks only on changed packages and their dependents
turbo run typecheck

# Force full rebuild (clear cache) when tsconfig changes are structural
turbo run build --force
```

## 6. Diagnosing Incremental Cache Misses

```bash
# Show exactly which files caused a rebuild
tsc --build --verbose packages/api-worker 2>&1 | grep -E "Reusing|Rebuilding|Changed"

# Check tsbuildinfo validity manually (TypeScript 5.4+)
tsc --build --dry packages/api-worker

# Measure build time before and after cache warm
time tsc --build            # cold build
time tsc --build            # warm build — should be near 0 if cache is valid

# Invalidate all caches and force full rebuild
find . -name ".tsbuildinfo" -delete && tsc --build
```

```typescript
// scripts/check-tsbuildinfo-staleness.ts
// Warn in CI if any .tsbuildinfo files are missing (cache was not restored)
import { existsSync } from "node:fs";
import { globSync } from "glob";

const expected = globSync("packages/*/tsconfig.json").map((cfg) =>
  cfg.replace("tsconfig.json", ".cache/.tsbuildinfo")
);

const missing = expected.filter((p) => !existsSync(p));
if (missing.length > 0) {
  console.warn("[tsbuildinfo] Cache miss — full build will run:");
  missing.forEach((p) => console.warn(" ", p));
}
```

## Anti-patterns

- **`"incremental": true` without `"composite": true` in a multi-package repo** — each package
  type-checks its entire transitive dependency tree on every run; no cross-package sharing.
- **Committing `.tsbuildinfo` files** — they contain absolute host paths and are not portable
  across CI runners; cache them via the CI caching layer instead.
- **Using `"noEmit": true` with `"composite": true`** — TypeScript rejects this combination.
  Use separate tsconfig files for type-checking and for declaration emit.
- **`skipLibCheck: true` as a shortcut** — masks type errors from `@cloudflare/workers-types`
  version mismatches; fix the underlying mismatch instead.
- **Cleaning `dist/` without also cleaning `.tsbuildinfo`** — TypeScript believes its cache is
  valid and skips regenerating files that were deleted.

## Gotchas

- `tsc --build` (project references) does not support `--noEmit`; use a separate `tsconfig.check.json`
  for type-only checks.
- `@cloudflare/workers-types` must be in `types` (not `typeRoots`) and only in the leaf
  package tsconfigs that reference it; including it in the base causes `lib` conflicts when
  Workers types and DOM types coexist in the same composite build.
- `declarationMap: true` requires `declaration: true`; both are required for go-to-definition
  across package boundaries in VS Code.
- Turbo caches `.tsbuildinfo` by output glob; ensure the glob is tight enough to avoid
  over-caching when only type signatures (not file hashes) change.

## Verification

```bash
# Confirm composite project references are wired correctly
tsc --build --dry && echo "Build graph OK"

# Measure incremental speedup (compare cold vs warm)
find . -name ".tsbuildinfo" -delete
time tsc --build
time tsc --build  # Should be sub-second on unchanged code

# Run Turbo typecheck with cache hit reporting
turbo run typecheck -- --output-logs=hash-only
```

## Related

- `typescript-project-references-and-build-boundary-integrity.md`
- `typescript-declaration-maps-workers-monorepo.md`
- `typescript-isolated-declarations-for-parallel-declaration-emit.md`
- `turborepo-cloudflare-workers-pipeline.md`
- `wireit-build-orchestration-workers-monorepo.md`

## Sources

- https://www.typescriptlang.org/docs/handbook/project-references.html
- https://www.typescriptlang.org/tsconfig#incremental
- https://www.typescriptlang.org/tsconfig#tsBuildInfoFile
- https://turbo.build/repo/docs/crafting-your-repository/caching
- https://developers.cloudflare.com/workers/languages/typescript/
