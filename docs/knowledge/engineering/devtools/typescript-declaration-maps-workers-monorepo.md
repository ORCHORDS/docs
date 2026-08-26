# TypeScript Declaration Maps for Workers Monorepo

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have a pnpm/Turborepo monorepo where shared library packages (e.g. `packages/utils`,
`packages/schema`) are consumed by multiple Cloudflare Workers. When a developer
"Go to Definition" navigates from a Worker into a shared package, the IDE lands on the
compiled `.d.ts` file in `dist/` rather than on the original TypeScript source. This breaks
source-level debugging and makes refactoring slower because contributors must manually
cross-reference the `.d.ts` back to the source.

The symptom worsens when packages use path aliases or barrel exports: the generated `.d.ts`
re-exports through re-exports and the IDE gives up, showing "Definition not available".

## Context

TypeScript's `declarationMap` compiler option instructs `tsc` to emit a `.d.ts.map` file
alongside each `.d.ts` file. This sourcemap links each declaration back to the original
`.ts` source. Editors that support "Go to Definition" (VS Code, JetBrains, Neovim with
tsserver) follow the `.d.ts.map` and open the original `.ts` file transparently.

In a Cloudflare Workers monorepo this matters because Workers themselves are not
published to npm — only internal packages are consumed locally via `workspace:*`
references. The package boundaries are real (`package.json` `exports` fields, separate
`tsconfig.json` files) but the source is available on disk, making declaration maps a
zero-cost ergonomic improvement with no production impact.

Declaration maps are a build-time and IDE-time concern only. They are not bundled by
esbuild or Wrangler and do not affect Worker bundle size or runtime behaviour.

## Enabling declarationMap in Library Packages

Add `declarationMap: true` alongside `declaration: true` in each library package's
`tsconfig.json`. Both options must be present for maps to be emitted.

```jsonc
// packages/utils/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "declaration": true,
    "declarationMap": true,       // <-- the new option
    "declarationDir": "dist/types",
    "outDir": "dist",
    "rootDir": "src",
    "sourceMap": true,
    "composite": true             // required for project references
  },
  "include": ["src"]
}
```

After building (`tsc -p tsconfig.json`), the `dist/types/` directory will contain:

```
dist/types/
  index.d.ts
  index.d.ts.map      ← points back to src/index.ts
  helpers.d.ts
  helpers.d.ts.map
```

## Configuring package.json Exports

For the declaration map to work the `types` (or `typings`) export condition must resolve
to the `.d.ts` file, and the package root must include the `.d.ts.map` files in the
published (or locally-linked) set.

```jsonc
// packages/utils/package.json
{
  "name": "@repo/utils",
  "version": "0.1.0",
  "type": "module",
  "exports": {
    ".": {
      "import": {
        "types": "./dist/types/index.d.ts",
        "default": "./dist/index.js"
      }
    },
    "./*": {
      "import": {
        "types": "./dist/types/*.d.ts",
        "default": "./dist/*.js"
      }
    }
  },
  "files": [
    "dist"          // includes dist/types/*.d.ts.map automatically
  ]
}
```

When packages are consumed via `workspace:*`, pnpm symlinks the package directory, so
`dist/types/` is directly accessible without publishing. The `.d.ts.map` files are always
available as long as the build has run.

## Worker tsconfig Integration

Worker packages typically extend a root `tsconfig.base.json` and include only their own
sources. They do not emit declarations (no `declaration: true`). The Workers tsconfig
references the library packages via TypeScript project references so `tsc --build` knows
the dependency order.

```jsonc
// workers/payment-worker/tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "rootDir": "src",
    "outDir": "dist",
    // Workers do NOT emit declarations — declaration is omitted or false
    "types": ["@cloudflare/workers-types"]
  },
  "references": [
    { "path": "../../packages/utils" },
    { "path": "../../packages/schema" }
  ],
  "include": ["src"]
}
```

```jsonc
// tsconfig.base.json (repo root)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true,
    "paths": {
      "@repo/utils": ["./packages/utils/src/index.ts"],
      "@repo/schema": ["./packages/schema/src/index.ts"]
    }
  }
}
```

Note: the `paths` mapping in `tsconfig.base.json` points directly to the source `src/`
entry. This is the "source-first" pattern and works with declaration maps to guarantee
the IDE always navigates to source regardless of whether `dist/` is stale.

## Turborepo Build Pipeline

Declaration maps must be emitted before dependent Workers type-check. The Turborepo
pipeline must express this dependency:

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "outputs": []
    },
    "dev": {
      "dependsOn": ["^build"],
      "cache": false,
      "persistent": true
    }
  }
}
```

`^build` means "build all workspace dependencies first". This ensures `packages/utils`
emits its `.d.ts.map` files before `workers/payment-worker` runs `tsc --noEmit`.

For watch mode during development, use `tsc --build --watch` in each library package in
parallel with `wrangler dev` in the Worker package. Turborepo's `--filter` flag scopes
the watch:

```bash
# Watch utils and schema packages for changes, rebuild their declarations
turbo run build --filter=@repo/utils --filter=@repo/schema --watch

# In a separate terminal, run the Worker dev server
wrangler dev --config workers/payment-worker/wrangler.toml
```

## VS Code Workspace Configuration

VS Code reads declaration maps automatically when `"typescript.preferences.importModuleSpecifier"` is set to `"shortest"` and the workspace TypeScript version matches the project version.

```jsonc
// .vscode/settings.json
{
  "typescript.tsdk": "node_modules/typescript/lib",
  "typescript.preferences.importModuleSpecifier": "shortest",
  // Enable this so VS Code follows .d.ts.map back to source
  "typescript.preferences.includePackageJsonAutoImports": "on",
  "editor.gotoLocation.multipleDefinitions": "goto"
}
```

If "Go to Definition" still lands on `.d.ts` after the above, run the VS Code command
"TypeScript: Restart TS Server" to flush the declaration cache. Alternatively, delete
`tsconfig.tsbuildinfo` files and rebuild.

## Anti-patterns

- Enabling `declarationMap` without `composite: true` in library packages — TypeScript
  project references require `composite` to function correctly; without it, incremental
  builds may not re-emit maps when source changes.
- Committing `.d.ts` and `.d.ts.map` files to git — these are build artifacts. Add
  `packages/*/dist/` to `.gitignore` and rely on CI to build before type-checking.
- Setting `paths` in `tsconfig.base.json` to point at `dist/types/` instead of `src/` —
  this negates the benefit of declaration maps because TypeScript will follow the path
  alias directly to source, bypassing the map.
- Excluding `dist/types/*.d.ts.map` from the `files` array in `package.json` — if maps
  are missing from the published package, downstream consumers get no source navigation
  even if they have `declarationMap: true` in their own tsconfig.
- Using `tsup` or `pkgroll` to build packages but forgetting to set `dts: { sourcemap: true }` —
  bundler-generated `.d.ts` files do not automatically inherit `tsc`'s declaration map
  setting.

## Gotchas

- `declarationMap` only maps to source files within the same package. If a type is
  re-exported from another package, "Go to Definition" follows the chain one hop at a time
  — each package must have its own `declarationMap: true`.
- When `moduleResolution` is `bundler` (required for most Workers toolchains), TypeScript
  may resolve imports differently than Node does. Ensure `paths` aliases in `tsconfig.base.json`
  use the same resolution semantics as the bundler (esbuild / Wrangler).
- `tsbuildinfo` caching means that if you change `declarationMap` from `false` to `true`
  on an existing build, you must delete the `.tsbuildinfo` file or run `tsc --build --force`
  to regenerate all declaration outputs.
- JetBrains IDEs (WebStorm/IntelliJ) follow declaration maps since 2024.1 but require
  the TypeScript language service to be set to "IDE bundled" or a project-local version —
  the "auto" setting may use an older version that ignores maps.

## Verification

1. Build a library package with `declarationMap: true`:

```bash
cd packages/utils
pnpm tsc -p tsconfig.json
ls dist/types/
# Should show: index.d.ts  index.d.ts.map  ...
```

2. Inspect the map file to confirm it references source:

```bash
cat packages/utils/dist/types/index.d.ts.map
# {"version":3,"file":"index.d.ts","sourceRoot":"","sources":["../../src/index.ts"],...}
```

3. Open `workers/payment-worker/src/index.ts` in VS Code, hover over an import from
   `@repo/utils`, and press F12 (Go to Definition). The editor should open
   `packages/utils/src/index.ts`, not `packages/utils/dist/types/index.d.ts`.

4. Run `tsc --build --dry` from the repo root and confirm no errors:

```bash
pnpm tsc --build --dry
```

## Related

- `typescript-project-references-and-build-boundary-integrity.md` — composite project setup
- `typescript-isolated-declarations-for-parallel-declaration-emit.md` — parallel emit strategy
- `turborepo-cloudflare-workers-pipeline.md` — Turborepo build ordering
- `typescript-path-aliases-workers.md` — path alias configuration for Workers

## Sources

- TypeScript Handbook: "Declaration Maps" — https://www.typescriptlang.org/tsconfig#declarationMap
- TypeScript 2.9 release notes (feature introduction) — https://www.typescriptlang.org/docs/handbook/release-notes/typescript-2-9.html
- Turborepo docs: "Task Dependencies" — https://turbo.build/repo/docs/crafting-your-repository/running-tasks
