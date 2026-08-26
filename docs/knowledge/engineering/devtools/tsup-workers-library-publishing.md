# tsup Bundler for Cloudflare Workers Library Publishing

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Shared utility packages consumed by Cloudflare Workers need to be bundled for both ESM and CJS consumers while also shipping TypeScript declaration files. Hand-rolling an esbuild configuration for this is repetitive; tsup provides a zero-boilerplate wrapper around esbuild that handles dual-format output, `.d.ts` generation, and Workers-compatible module splitting out of the box.

## Context
tsup is an esbuild-powered TypeScript bundler designed for library authors. When building packages consumed by Cloudflare Workers, the key requirements are: ESM output only (Workers runtime does not support CJS `require`), declaration files for downstream TypeScript consumers, and no bundling of `cloudflare:*` or `node:*` specifiers so the runtime resolves them. tsup satisfies all three with minimal configuration and is substantially faster than `tsc --declaration --emitDeclarationOnly` followed by a separate esbuild pass.

## Installation

```bash
pnpm add -D tsup typescript
```

## Basic tsup Configuration

`packages/auth/tsup.config.ts`:

```typescript
import { defineConfig } from "tsup";

export default defineConfig({
  // Entry points — can be a single file or a map for multiple exports
  entry: {
    index: "src/index.ts",
    middleware: "src/middleware.ts",
  },

  // Output formats — Workers only need ESM; add cjs for Node consumers
  format: ["esm"],

  // Generate .d.ts declaration files
  dts: true,

  // Split chunks — Workers benefit from code splitting when using dynamic import
  splitting: true,

  // Source maps for debugging in wrangler dev
  sourcemap: true,

  // Clean dist/ before each build
  clean: true,

  // Do NOT bundle these — let the Workers runtime resolve them
  external: [
    "cloudflare:workers",
    "cloudflare:email",
    "cloudflare:sockets",
    /^node:.*/,
  ],

  // Target the Workers runtime (V8, ES2022+)
  target: "es2022",

  // Suppress banner (no "use client" / "use server" directives)
  banner: {},

  // Tree-shake aggressively
  treeshake: true,

  // esbuild options passthrough
  esbuildOptions(options) {
    // Workers: keep conditions consistent with wrangler
    options.conditions = ["workerd", "worker", "browser", "import", "module"];
  },
});
```

## package.json Exports Configuration

The `exports` field tells Node, bundlers, and TypeScript which file to resolve for each condition. Workers bundlers respect `"worker"` and `"browser"` conditions.

`packages/auth/package.json`:

```json
{
  "name": "@repo/auth",
  "version": "1.0.0",
  "type": "module",
  "files": ["dist"],
  "exports": {
    ".": {
      "worker": "./dist/index.js",
      "import": "./dist/index.js",
      "require": "./dist/index.cjs",
      "types": "./dist/index.d.ts"
    },
    "./middleware": {
      "worker": "./dist/middleware.js",
      "import": "./dist/middleware.js",
      "require": "./dist/middleware.cjs",
      "types": "./dist/middleware.d.ts"
    }
  },
  "main": "./dist/index.cjs",
  "module": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "scripts": {
    "build": "tsup",
    "build:watch": "tsup --watch",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "tsup": "^8.0.0",
    "typescript": "^5.5.0"
  },
  "peerDependencies": {
    "@cloudflare/workers-types": "^4.0.0"
  }
}
```

## TypeScript Configuration for Library

`packages/auth/tsconfig.json`:

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
    "isolatedDeclarations": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "outDir": "dist",
    "rootDir": "src"
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist", "**/*.test.ts"]
}
```

`isolatedDeclarations: true` is critical — it ensures each file can emit its `.d.ts` without requiring a full type-check pass, which tsup uses for parallelism.

## Advanced: Multiple Entry Points with Subpath Exports

For a larger utility library with several independent submodules:

```typescript
// tsup.config.ts
import { defineConfig } from "tsup";
import { readdirSync } from "fs";
import { join } from "path";

// Automatically discover all top-level src/ modules as entry points
const srcEntries = readdirSync(join(__dirname, "src"))
  .filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts") && !f.endsWith(".spec.ts"))
  .reduce<Record<string, string>>((acc, file) => {
    const name = file.replace(/\.ts$/, "");
    acc[name] = `src/${file}`;
    return acc;
  }, {});

export default defineConfig({
  entry: srcEntries,
  format: ["esm"],
  dts: true,
  splitting: false, // keep one file per entry for predictable subpath exports
  sourcemap: true,
  clean: true,
  external: ["cloudflare:workers", /^node:.*/],
  target: "es2022",
  treeshake: true,
});
```

Generate the `exports` map from the same discovery logic in a `scripts/generate-exports.ts`:

```typescript
import { readdirSync, writeFileSync, readFileSync } from "fs";

const entries = readdirSync("src")
  .filter((f) => f.endsWith(".ts") && !f.includes(".test."))
  .map((f) => f.replace(".ts", ""));

const pkg = JSON.parse(readFileSync("package.json", "utf8"));

pkg.exports = entries.reduce<Record<string, unknown>>((acc, name) => {
  const key = name === "index" ? "." : `./${name}`;
  acc[key] = {
    worker: `./dist/${name}.js`,
    import: `./dist/${name}.js`,
    types: `./dist/${name}.d.ts`,
  };
  return acc;
}, {});

writeFileSync("package.json", JSON.stringify(pkg, null, 2) + "\n");
```

Run as a `prebuild` script: `"prebuild": "tsx scripts/generate-exports.ts"`.

## CI Pipeline Integration

`.github/workflows/publish.yml`:

```yaml
name: Publish

on:
  push:
    tags:
      - "@repo/auth@*"

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          registry-url: https://registry.npmjs.org

      - run: pnpm install --frozen-lockfile

      - name: Build
        run: pnpm --filter @repo/auth build

      - name: Verify exports resolve
        run: |
          node -e "
            import('@repo/auth').then(m => {
              if (!m.default && !m.createAuth) throw new Error('bad exports');
              console.log('exports OK');
            });
          "
        working-directory: packages/auth

      - name: Publish
        run: pnpm --filter @repo/auth publish --no-git-checks
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

## Anti-patterns

- **Bundling `node:*` built-ins into the output** — tsup will inline polyfills from your `node_modules` if `node:crypto` etc. are not listed in `external`; the Workers runtime provides its own implementations and the duplicated code wastes bundle budget.
- **Using `format: ["cjs"]` only** — Workers cannot consume CJS; always include `"esm"` as a format.
- **Skipping `dts: true` for internal monorepo packages** — Without declaration files, TypeScript consumers lose type inference and must add `// @ts-ignore` workarounds.
- **Setting `splitting: true` with multiple entry points and subpath exports** — Code splitting creates shared chunks named `chunk-HASH.js` that are not part of the declared exports map, breaking consumers that import subpaths.
- **Not pinning `tsup` version in CI** — tsup's esbuild dependency changes across minor versions; pin `tsup` and `esbuild` in `devDependencies` to avoid build drift.

## Gotchas

- `dts: true` uses the TypeScript compiler API internally; it reads `tsconfig.json` from the project root — a missing or misconfigured `tsconfig.json` causes silent `.d.ts` emit failures.
- `esbuildOptions.conditions` must match what wrangler uses when bundling the downstream Worker or type-resolution for `cloudflare:*` imports will fail in consuming packages.
- tsup's `--watch` mode does not re-run `dts` generation on every change by default; pass `--dts` explicitly: `tsup --watch --dts`.
- `isolatedDeclarations: true` in `tsconfig.json` rejects some valid TypeScript patterns (e.g., inferred return types on exported functions); all public API functions must have explicit return type annotations.
- The `files` array in `package.json` must include `"dist"` — forgetting it publishes a zero-file package that silently resolves to `undefined` at runtime.

## Verification

```bash
# Build the package
pnpm --filter @repo/auth build

# Verify ESM output exists
ls packages/auth/dist/
# Expected: index.js  index.d.ts  index.js.map  middleware.js  middleware.d.ts

# Check that cloudflare: imports are NOT bundled
grep -r "cloudflare:" packages/auth/dist/
# Expected: original import specifiers preserved, not inlined

# Validate exports from a consuming Worker
cd apps/api-worker
node --input-type=module --experimental-vm-modules - <<'EOF'
import { createAuth } from "@repo/auth";
console.log(typeof createAuth); // "function"
EOF

# Size check
pnpm --filter @repo/auth exec -- ls -lh dist/index.js
```

## Related
- `wireit-build-orchestration-workers-monorepo.md`
- `pkgroll-workers-package-bundler.md`
- `esbuild-metafile-bundle-analysis-workers.md`
- `typescript-path-aliases-workers.md`
- `changesets-monorepo-versioning.md`

## Sources
- https://tsup.egoist.dev/
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://www.typescriptlang.org/tsconfig/#isolatedDeclarations
