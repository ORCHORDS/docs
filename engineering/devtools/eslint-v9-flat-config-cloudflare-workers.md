# eslint-v9-flat-config-cloudflare-workers

**Issue:** Teams running a monorepo with Cloudflare Workers and Next.js
hit three compounding problems when upgrading to ESLint v9: the flat
config format is incompatible with every `.eslintrc.*` file they had;
Workers environments expose no Node globals, so rules written assuming
`process` or `require` fire false positives; and Biome has taken over
formatting, leaving ESLint doing lint-only work that needs its own
config contract.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
Error: Key "env" is not a recognized configuration key.
Error: Key "extends" is not recognized in this config format.
ReferenceError: process is not defined   (worker build, rule no-process-env)
"no-undef": error — "require" is not defined
```

After `eslint --version` shows `9.x`, running `eslint .` exits 1 with
schema errors before any source file is checked. Worker scripts that
correctly avoid Node globals still trip over `no-undef` because the
`"env": { "node": true }` stanza is silently ignored in flat config.

## Context

ESLint v9 shipped the flat config (`eslint.config.*`) as the only
supported format. The legacy `eslintrc` loader is still available
behind `ESLINT_USE_FLAT_CONFIG=false`, but it is deprecated and
removed in v10. Flat config replaces `extends` arrays and `env` maps
with `import`-based composition, making the Workers/Next.js split
explicit and type-safe. Biome v2 handles all formatting; ESLint is
kept purely for lint rules that Biome/Oxlint do not yet cover
(typescript-eslint type-aware rules, Next.js plugin rules).

## Migrating from .eslintrc

1. **Run the migrate codemod first** —
   `npx @eslint/migrate-config .eslintrc.json` emits a starter
   `eslint.config.mjs` and prints a report of constructs it could
   not automatically port; start from that file, not from scratch.
2. **Replace `env` keys with explicit globals packages** — install
   `globals` (`npm i -D globals`) and reference `globals.browser`,
   `globals.worker`, or `globals.node` explicitly per file-set
   rather than relying on the removed `env` map.
3. **Replace `extends` strings with imports** — each shareable
   config now exports an array you spread; `eslint:recommended`
   becomes `import js from "@eslint/js"` and `js.configs.recommended`
   in the spreaded config array.
4. **Scope rules by `files` glob, not by `overrides`** — flat config
   is already an array; each element has an optional `files` array,
   so per-folder overrides become separate array entries rather than
   nested `overrides` blocks.
5. **Delete `.eslintignore`** — ignored paths move into an `ignores`
   array in the config object; place it first in the array so later
   entries do not accidentally match ignored files.

## Workers-specific rules (no Node globals)

The Cloudflare Workers runtime provides the Web Standard globals
(`fetch`, `Request`, `Response`, `crypto`, `caches`, `URL`) but
deliberately omits Node's `process`, `Buffer`, `require`, `__dirname`,
and `module`. ESLint rules must reflect this.

```js
// eslint.config.mjs  (workers package only)
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    files: ["apps/worker/**/*.ts"],
    languageOptions: {
      globals: {
        // Web-standard globals only
        ...globals.worker,  // fetch, Request, Response, caches …
        // Do NOT spread globals.node here
      },
    },
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "process", message: "Not available in Workers." },
        { name: "Buffer",  message: "Use Uint8Array in Workers." },
        { name: "require", message: "Workers are ESM-only." },
      ],
    },
  },
);
```

| Global      | Node | Browser | Workers | Action          |
|-------------|------|---------|---------|-----------------|
| process     | yes  | no      | no      | ban + error     |
| Buffer      | yes  | no      | no      | ban + error     |
| fetch       | yes  | yes     | yes     | allow           |
| crypto      | yes  | yes     | yes     | allow           |
| caches      | no   | yes     | yes     | allow           |
| __dirname   | yes  | no      | no      | ban + error     |
| navigator   | no   | yes     | partial | warn in worker  |

## TypeScript integration

`typescript-eslint` v8 ships first-class flat config support. Wire
type-aware rules only in configs that pass `project: true` so they do
not run on non-TS files and do not re-invoke tsc for formatting passes.

```js
// eslint.config.mjs
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Type-aware rules: Workers package
  {
    files: ["apps/worker/**/*.ts"],
    extends: [
      ...tseslint.configs.strictTypeChecked,
    ],
    languageOptions: {
      parserOptions: {
        project: "./apps/worker/tsconfig.json",
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  // Type-aware rules: Next.js app
  {
    files: ["apps/web/**/*.{ts,tsx}"],
    extends: [
      ...tseslint.configs.recommendedTypeChecked,
    ],
    languageOptions: {
      parserOptions: {
        project: "./apps/web/tsconfig.json",
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
);
```

Keep type-aware passes (`strictTypeChecked`, `recommendedTypeChecked`)
off the `*.config.ts` / `*.test.ts` files in CI's fast path — use a
separate `files` entry with only `recommended` (no `TypeChecked`)
for those to avoid the tsc overhead on test files.

## Biome integration boundary

With Biome v2 handling all formatting and import sorting, ESLint must
not re-enable any formatting rule or it will conflict.

```js
// eslint.config.mjs — append last in the array
import biomePlugin from "eslint-config-biome"; // disables conflicting rules

export default tseslint.config(
  // … all lint configs above …
  biomePlugin,   // turns off ESLint rules Biome owns
);
```

```jsonc
// biome.json — tell Biome it owns formatting, not ESLint
{
  "formatter": { "enabled": true },
  "linter":    { "enabled": false }  // or keep enabled for Biome's own rules
}
```

The pattern: **ESLint → lint only, Biome → format + import sort**.
Pre-commit hook runs `biome check --write` first, then `eslint --fix`
for the lint-only rules ESLint still owns. Never run both tools in
parallel on the same files; they share no lock.

## Anti-patterns

- **Leaving `ESLINT_USE_FLAT_CONFIG=false` in CI env** — silences all
  migration errors but ensures v10 breaks the pipeline without warning.
- **Spreading `globals.node` in the Workers config** — masks real bugs
  where worker code accidentally imports a Node-only dep that polyfills
  `process`, making the lint pass but the Worker fail at runtime.
- **Type-aware rules on every file** — running `project: true` on
  `eslint.config.mjs` itself causes a circular parse error; always
  scope type-aware entries to source file globs only.
- **Keeping `.eslintignore`** — ignored in flat config; patterns must
  move to an `ignores` array or they are silently dropped.

## Gotchas

- `import.meta.dirname` is the flat-config idiom for `__dirname`; it
  requires Node 20.11+ or a `URL`-based shim in older Node.
- The `biome` npm package and `eslint-config-biome` are separate
  packages; the config package only disables conflicting ESLint rules —
  it does not install or run Biome itself.
- `globals.worker` from the `globals` package maps to the Service
  Worker spec globals, which is a superset of what Cloudflare Workers
  exposes; a handful of Service Worker globals (`clients`,
  `registration`) are not available in the Workers runtime.
- Per-package `eslint.config.mjs` files in a Turborepo work without
  extra config; but the root config is NOT automatically inherited —
  each package must import shared config explicitly.

## Verification

```bash
# confirm flat config is active
ESLINT_USE_FLAT_CONFIG=true npx eslint --print-config \
  apps/worker/src/index.ts | jq '.languageOptions.globals | keys'
# expect: ["caches","crypto","fetch","Request","Response", …]
# must NOT contain: "process", "Buffer", "require"

# full lint pass
pnpm --filter=worker exec eslint . --max-warnings=0
pnpm --filter=web    exec eslint . --max-warnings=0
```

- `no-restricted-globals` must fire on a test file that uses `process`
  inside the worker package.
- `@typescript-eslint/no-floating-promises` must fire on an unawaited
  promise in a Worker handler.
- `biome check --write` must produce no formatting diff after `eslint
  --fix` ran first (verify in CI via `biome check` with no `--write`).

## Related

- `documentation/categories/devtools/rust-linters-biome-oxlint-migration.md`
- `documentation/categories/devtools/typescript-cloudflare-workers-strict.md`
- `documentation/categories/devtools/turborepo-cloudflare-workers-pipeline.md`
- `documentation/categories/devtools/commitlint-setup.md`

## Sources

- https://eslint.org/docs/latest/use/configure/configuration-files
- https://typescript-eslint.io/getting-started/typed-linting
- https://biomejs.dev/guides/how-biome-works/#the-biome-linter
- https://developers.cloudflare.com/workers/runtime-apis/
- https://www.npmjs.com/package/globals
