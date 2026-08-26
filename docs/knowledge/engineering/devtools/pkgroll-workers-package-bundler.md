# pkgroll: Zero-Config Package Bundler for Workers Libraries

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Shared libraries in a Cloudflare Workers monorepo need to be bundled with minimal configuration. pkgroll reads `package.json` `exports`, `main`, `module`, and `types` fields to infer every output file automatically — there is no separate config file to maintain, and it handles TypeScript declarations, ESM/CJS dual output, and source maps with a single command.

## Context
pkgroll (by Hiroki Osame, the author of tsx and get-tsconfig) is a Rollup-based package bundler that treats `package.json` as its sole configuration source. It infers entry points from the `exports` map, detects output format from file extensions (`.mjs` → ESM, `.cjs` → CJS, `.js` → determined by `"type"` field), and runs `tsc --declaration` for type files. For Cloudflare Workers libraries the pattern is straightforward: set `"type": "module"`, declare `exports` with `.js` files pointing to `dist/`, and pkgroll produces correctly formatted ESM with full declaration files.

## Installation

```bash
pnpm add -D pkgroll typescript
```

No config file is required. pkgroll reads everything from `package.json`.

## package.json Configuration

pkgroll derives all build targets from the `exports` field and the `types` / `main` / `module` fields. The simplest setup for a Workers-only library:

```json
{
  "name": "@repo/cf-utils",
  "version": "1.0.0",
  "type": "module",
  "files": ["dist"],
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    },
    "./headers": {
      "types": "./dist/headers.d.ts",
      "import": "./dist/headers.js"
    },
    "./cache": {
      "types": "./dist/cache.d.ts",
      "import": "./dist/cache.js"
    }
  },
  "scripts": {
    "build": "pkgroll",
    "build:watch": "pkgroll --watch",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "pkgroll": "^2.0.0",
    "typescript": "^5.5.0",
    "@cloudflare/workers-types": "^4.0.0"
  }
}
```

pkgroll scans `exports`, discovers `./dist/index.js`, `./dist/headers.js`, `./dist/cache.js`, and `*.d.ts` files, then resolves their source counterparts in `src/` automatically.

## TypeScript Configuration

`tsconfig.json` in the package root:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "outDir": "dist",
    "rootDir": "src",
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["dist", "node_modules", "**/*.test.ts"]
}
```

pkgroll calls the TypeScript compiler API directly to emit declarations — the `outDir` in `tsconfig.json` is ignored by pkgroll; it always writes to the location declared in `exports`.

## Source Structure

```
packages/cf-utils/
├── src/
│   ├── index.ts          → dist/index.js + dist/index.d.ts
│   ├── headers.ts        → dist/headers.js + dist/headers.d.ts
│   └── cache.ts          → dist/cache.js + dist/cache.d.ts
├── package.json
└── tsconfig.json
```

`src/headers.ts` example:

```typescript
/**
 * Merge Response headers from multiple sources.
 * Cloudflare Workers safe — uses the global Headers constructor.
 */
export function mergeHeaders(
  ...sources: Array<HeadersInit | Headers | null | undefined>
): Headers {
  const merged = new Headers();
  for (const source of sources) {
    if (!source) continue;
    const headers = source instanceof Headers ? source : new Headers(source);
    for (const [key, value] of headers.entries()) {
      merged.set(key, value);
    }
  }
  return merged;
}

/**
 * Extract a typed header value with a fallback.
 */
export function getHeader(
  request: Request,
  name: string,
  fallback: string = ""
): string {
  return request.headers.get(name) ?? fallback;
}

/**
 * Build a CORS preflight Response.
 */
export function corsHeaders(origin: string): Headers {
  return new Headers({
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  });
}
```

## Dual ESM + CJS Output (Node Consumers)

When the library is also consumed by Node.js tooling (test runners, build scripts), add CJS exports using the `.cjs` extension:

```json
{
  "type": "module",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js",
      "require": "./dist/index.cjs"
    }
  },
  "main": "./dist/index.cjs",
  "module": "./dist/index.js"
}
```

pkgroll detects `require: "./dist/index.cjs"` and automatically builds a CJS bundle in addition to ESM. No additional configuration needed.

## Handling cloudflare:* External Imports

pkgroll externalizes packages listed in `peerDependencies` and `dependencies` by default. For `cloudflare:*` specifiers, add them to a `pkgroll` key in `package.json`:

```json
{
  "pkgroll": {
    "external": [
      "cloudflare:workers",
      "cloudflare:email",
      "cloudflare:sockets"
    ]
  }
}
```

Alternatively, declare them as `peerDependencies` with `"*"` version (they are resolved by the runtime, not npm):

```json
{
  "peerDependencies": {
    "cloudflare:workers": "*"
  }
}
```

## Watch Mode for Monorepo Development

In a pnpm workspace, run pkgroll in watch mode for the shared package while wrangler dev consumes it:

```bash
# Terminal 1 — rebuild the library on changes
pnpm --filter @repo/cf-utils build:watch

# Terminal 2 — wrangler dev picks up rebuilt dist/ via workspace symlink
pnpm --filter @repo/api-worker dev
```

Because pnpm symlinks workspace packages into `node_modules`, wrangler sees the updated `dist/` files immediately without reinstalling.

## CI Build and Verification Script

`.github/workflows/library-ci.yml`:

```yaml
name: Library CI

on:
  push:
    paths:
      - "packages/cf-utils/**"
      - ".github/workflows/library-ci.yml"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build library
        run: pnpm --filter @repo/cf-utils build

      - name: Verify dist exists and has content
        run: |
          test -f packages/cf-utils/dist/index.js
          test -f packages/cf-utils/dist/index.d.ts
          test -f packages/cf-utils/dist/headers.js
          test -s packages/cf-utils/dist/index.js  # non-empty

      - name: Check no node_modules leaked into output
        run: |
          if grep -r "require(" packages/cf-utils/dist/*.js 2>/dev/null; then
            echo "CJS require() found in ESM output — check pkgroll config"
            exit 1
          fi
          echo "Output is clean ESM"

      - name: Typecheck consuming Worker
        run: pnpm --filter @repo/api-worker typecheck
```

## Anti-patterns

- **Missing `"type": "module"` in package.json** — Without it, `.js` output is treated as CJS by Node; Workers will fail to import the package as ESM.
- **Pointing `exports` at `src/` files instead of `dist/`** — pkgroll derives output paths from `exports`; if you point at `src/`, it writes the bundle there and overwrites source files.
- **Using `paths` in tsconfig.json for cross-package imports inside the library** — pkgroll does not resolve TypeScript path aliases; use pnpm workspace protocols (`workspace:*`) and import by package name.
- **Adding `cloudflare:*` to `dependencies`** — These are runtime-provided specifiers with no npm packages; listing them in `dependencies` causes `pnpm install` to fail with a registry 404.
- **Forgetting to rebuild after source changes before running vitest** — In CI without wireit/turborepo, a stale `dist/` from a previous run can mask failures. Always run `build` before `test` in CI steps.

## Gotchas

- pkgroll requires TypeScript 5.0+ for declaration emit; earlier versions silently produce empty `.d.ts` files.
- The `pkgroll.external` array uses exact string matching, not glob patterns; `"cloudflare:*"` is not a valid glob entry — list each `cloudflare:` specifier individually.
- pkgroll does not support `tsup`-style `esbuildOptions` passthrough; for advanced esbuild transforms (custom loaders, define constants) use tsup or a raw esbuild config instead.
- Rollup (pkgroll's underlying bundler) inlines small `node_modules` by default unless they are listed in `external` or `peerDependencies`/`dependencies` — check `dist/` output for unexpected inlined third-party code.
- pkgroll's watch mode exits on TypeScript type errors; tsup's watch mode continues. Choose based on whether you want strict error-gating during development.

## Verification

```bash
# Run the build
pnpm --filter @repo/cf-utils build

# Inspect what was generated
ls -la packages/cf-utils/dist/
# Expected: index.js, index.d.ts, headers.js, headers.d.ts, cache.js, cache.d.ts

# Confirm the output is valid ESM
head -5 packages/cf-utils/dist/index.js
# Expected: starts with "export" or "import", NOT "require("

# Confirm declarations are non-trivial
wc -l packages/cf-utils/dist/index.d.ts
# Expected: > 5 lines

# Import the built package from a Worker source file (type-check)
cd apps/api-worker
pnpm tsc --noEmit
```

## Related
- `tsup-workers-library-publishing.md`
- `wireit-build-orchestration-workers-monorepo.md`
- `changesets-monorepo-versioning.md`
- `pnpm-workspace-setup.md`
- `typescript-path-aliases-workers.md`

## Sources
- https://github.com/privatenumber/pkgroll
- https://nodejs.org/api/packages.html#conditional-exports
- https://developers.cloudflare.com/workers/wrangler/bundling/#external-packages
