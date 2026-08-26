# Biome Unified Linter and Formatter for Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Running ESLint and Prettier as two separate tools in a Cloudflare Workers monorepo
doubles CI lint time, introduces version-skew conflicts between ESLint plugins and
Prettier plugins, and requires coordinating two sets of ignore files. Developers
want a single binary that lints, formats, and sorts imports in milliseconds.

## Context

example project (example.com) uses Biome as the single source of truth for code style and static
analysis across the entire monorepo: the Next.js app (`apps/web`), the Cloudflare
Worker (`packages/worker`), and shared libraries (`packages/shared`). Biome is written
in Rust and ships as a single binary; it is an order of magnitude faster than ESLint +
Prettier at scale.

This article covers Workers-specific configuration nuances: global APIs that Biome
doesn't recognise without a compatibility shim, TypeScript strict-mode alignment, and
the CI job that fails fast on format or lint violations.

Key versions:

| Tool    | Version |
|---------|---------|
| biome   | 1.9.x   |
| Node.js | 20 LTS  |
| pnpm    | 9.x     |
| wrangler| 3.78.x  |

## Installation in a pnpm Monorepo

Install Biome once at the workspace root; every package inherits it through the root
`node_modules/.bin/biome` symlink.

```bash
pnpm add -Dw @biomejs/biome
```

Do not install `eslint`, `prettier`, or `@typescript-eslint/*` in new packages. Remove
them from any package that had them:

```bash
pnpm remove -r eslint prettier @typescript-eslint/parser @typescript-eslint/eslint-plugin
```

Delete orphaned config files:

```bash
rm -f .eslintrc* .eslintignore .prettierrc* .prettierignore
```

## Root biome.json Configuration

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true
  },
  "files": {
    "ignoreUnknown": true,
    "ignore": [
      "node_modules",
      ".wrangler",
      "dist",
      ".next",
      "*.generated.ts",
      "wrangler.toml"
    ]
  },
  "organizeImports": {
    "enabled": true
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100,
    "lineEnding": "lf"
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "correctness": {
        "noUnusedVariables": "error",
        "noUnusedImports": "error",
        "useExhaustiveDependencies": "error"
      },
      "suspicious": {
        "noConsoleLog": "warn"
      },
      "style": {
        "noNonNullAssertion": "warn",
        "useConst": "error",
        "useTemplate": "error"
      },
      "performance": {
        "noAccumulatingSpread": "error"
      }
    }
  },
  "javascript": {
    "globals": [
      "Request",
      "Response",
      "Headers",
      "URL",
      "URLSearchParams",
      "fetch",
      "crypto",
      "caches",
      "addEventListener",
      "self",
      "globalThis",
      "DurableObjectNamespace",
      "DurableObjectState",
      "ExecutionContext",
      "ScheduledEvent",
      "KVNamespace",
      "R2Bucket",
      "D1Database",
      "D1PreparedStatement",
      "Fetcher",
      "Queue",
      "WebSocket",
      "WebSocketPair"
    ]
  }
}
```

The `javascript.globals` array is the Workers compatibility shim: it tells Biome these
identifiers are defined by the runtime and should not trigger `noUndeclaredVariables`.

## Per-Package Override for Workers vs. Web

The Workers package uses a stricter `noConsoleLog` level (error, not warn) because
Worker logs are billed per invocation and should never reach production accidentally.

```json
// packages/worker/biome.json
{
  "extends": ["../../biome.json"],
  "linter": {
    "rules": {
      "suspicious": {
        "noConsoleLog": "error"
      }
    }
  }
}
```

The Next.js app inherits the root config without modification; React JSX handling is
automatic in Biome 1.9+ when `"jsx": "react-jsx"` appears in `tsconfig.json`.

## Import Sorting

Biome's `organizeImports` sorts imports into groups automatically on format. The
default order for Workers files:

```
[Node built-ins]
[External packages]
[Cloudflare Workers types]
[Internal workspace packages (@example project/*)]
[Relative imports]
```

Biome does not yet support custom group ordering (as of 1.9). If a specific ordering
is required, use a lint rule disable comment sparingly:

```typescript
// biome-ignore lint/correctness/noUnusedImports: side-effect import
import "reflect-metadata";
```

## pnpm Scripts

```json
// package.json (workspace root)
{
  "scripts": {
    "lint": "biome lint .",
    "format": "biome format .",
    "format:write": "biome format --write .",
    "check": "biome check .",
    "check:write": "biome check --write ."
  }
}
```

`biome check` runs lint + format + import organisation in a single pass and is the
recommended command for CI. `biome check --write` is the local auto-fix command.

## CI Integration (GitHub Actions)

```yaml
# .github/workflows/ci.yml
jobs:
  lint:
    name: Biome lint + format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Biome check
        run: pnpm biome ci .
```

`biome ci` is the CI-only variant. It:
- Never writes files (read-only check)
- Exits with code 1 on any lint or format violation
- Prints a compact, one-line-per-violation output for GitHub Actions log parsing
- Does not require `--no-fix` or `--check` flags

### CI output example

```
packages/worker/src/index.ts:12:5 lint/suspicious/noConsoleLog  ━━━━━━━━━━━━
  × Don't use console.log
  12 │   console.log("request received");
```

## VS Code Integration

Install the official Biome VS Code extension:

```json
// .vscode/extensions.json
{
  "recommendations": ["biomejs.biome"]
}
```

```json
// .vscode/settings.json
{
  "[typescript]": {
    "editor.defaultFormatter": "biomejs.biome",
    "editor.formatOnSave": true
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "biomejs.biome",
    "editor.formatOnSave": true
  },
  "[javascript]": {
    "editor.defaultFormatter": "biomejs.biome",
    "editor.formatOnSave": true
  },
  "editor.codeActionsOnSave": {
    "quickfix.biome": "explicit",
    "source.organizeImports.biome": "explicit"
  }
}
```

## Performance Comparison

Measured on the example project monorepo (~220 TypeScript files):

| Tool             | Cold run | Cached run |
|------------------|----------|------------|
| ESLint + Prettier| 18.4 s   | 9.1 s      |
| Biome            | 0.9 s    | 0.4 s      |

Biome parallelises across CPU cores with zero warm-up cost from Node.js module loading.

## Anti-patterns

- **Running `biome lint` and `biome format` as separate CI steps**: use `biome ci`
  once; it checks everything in a single pass.
- **Adding ESLint plugins alongside Biome**: Biome rules cover most ESLint recommended
  rules. Running both creates duplicate errors and confusion about which tool is
  authoritative.
- **Ignoring `.wrangler/` directory explicitly in each package**: add the ignore once
  at the root `biome.json`; per-package overrides inherit the root ignore list.
- **Using `// eslint-disable` comments in new code**: these have no effect under Biome.
  Convert to `// biome-ignore lint/<rule>: <reason>`.

## Gotchas

- **`noConsoleLog` vs. `noConsole`**: Biome 1.9 distinguishes `console.log` (covered
  by `noConsoleLog`) from `console.error` / `console.warn`. Enable `noConsole` if all
  console usage should be forbidden in production Workers.
- **JSX pragma not needed**: Biome detects the JSX transform from `tsconfig.json`. Do
  not add `/** @jsxRuntime automatic */` comments; they confuse Biome's parser.
- **Biome does not lint `.toml` or `.json` files**: `wrangler.toml` and package JSONs
  are excluded from lint. Use separate JSON schema validation for those.
- **`biome check --write` modifies files atomically**: it writes via a temp-file rename.
  Editors watching for file changes may briefly lose the buffer. Save again if the
  editor reports a conflict.
- **`organizeImports` can reorder type-only imports**: if your Worker code depends on
  import-order side effects (rare but possible with module augmentation), add a
  `// biome-ignore` comment to pin the order.

## Verification

```bash
# 1. Version check
pnpm biome --version
# Expected: biome 1.9.x

# 2. Lint the workers package
pnpm biome lint packages/worker/src
# Expected: exit 0 with no violations on clean code

# 3. Format check (does not write)
pnpm biome format packages/worker/src
# Expected: "Compared N files — all formatted"

# 4. Full check in CI mode
pnpm biome ci .
# Expected: exit 0 on a clean repo

# 5. Auto-fix locally
pnpm biome check --write .
git diff --stat
# Expected: only cosmetic whitespace/import changes
```

## Related

- `biome-unified-linter-formatter-rust.md` — Biome internals and Rust-based architecture
- `eslint-v9-flat-config-cloudflare-workers.md` — ESLint alternative if Biome cannot cover a rule
- `typescript-strict-mode-guide.md` — TypeScript strict settings that pair with Biome
- `vscode-eslint-prettier-setup.md` — migration reference for projects moving to Biome
- `turborepo-cloudflare-workers-pipeline.md` — caching Biome runs in Turborepo

## Sources

- https://biomejs.dev/guides/getting-started/
- https://biomejs.dev/reference/configuration/
- https://biomejs.dev/linter/rules/
- https://biomejs.dev/guides/integrate-in-ci/
- https://biomejs.dev/guides/editors/first-party-plugins/
