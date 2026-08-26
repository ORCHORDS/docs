# biome-linter-formatter-workers

**Issue:** A Cloudflare Workers project running ESLint + Prettier takes
12–18 s per lint pass in CI and requires maintaining two separate configs,
two sets of ignore files, and plugin version compatibility across ESLint,
`@typescript-eslint`, and Prettier. Biome replaces both tools with a
single Rust binary, drops cold-start lint time to under 1 s, and ships
Workers-relevant rules without additional plugins.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
pnpm lint
  eslint . --ext .ts,.tsx  — 14.3 s
  prettier --check .       — 3.1 s
  total: 17.4 s per CI push

# Frequent conflicts:
ERROR  "@typescript-eslint/parser" requires "eslint": "^8" but installed "^9"
ERROR  Prettier config and ESLint "prettier" plugin disagree on trailing commas
```

Two config files (`eslint.config.js` and `.prettierrc`), two ignore
files (`.eslintignore` / `.prettierignore`), and constant plugin version
churn. Workers-specific rules (no `setTimeout`, no `process.env`, no
Node built-ins) must be assembled from community plugins.

## Context

Biome (formerly Rome) is a Rust-based toolchain that performs parsing,
linting, and formatting in a single pass over the AST. It supports
TypeScript, JSX, JSON, and CSS natively. For Cloudflare Workers projects
the key advantages are: near-instant lint in both local and CI, no
plugin ecosystem to maintain, and a growing rule set that includes
checks directly relevant to the Workers runtime (banned globals, import
restrictions). Biome is not a perfect ESLint drop-in — approximately
90 % of commonly used ESLint rules are implemented, with the rest on the
roadmap.

## Installation in a pnpm monorepo

```bash
# Install at the workspace root — shared binary, one version to manage
pnpm add -D -w @biomejs/biome

# Scaffold the default config
pnpm biome init
```

For a example project monorepo (apps/worker, apps/web, packages/shared):

```
example project/
├── biome.json          ← root config (applies everywhere)
├── apps/
│   ├── worker/
│   │   └── biome.json  ← overrides for Workers runtime rules
│   └── web/
│       └── biome.json  ← overrides for Next.js (allows browser globals)
└── packages/
    └── shared/
        └── biome.json  ← strictest — shared code runs everywhere
```

## Root biome.json

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true,
    "defaultBranch": "main"
  },
  "files": {
    "ignoreUnknown": true,
    "ignore": [
      "**/.wrangler/**",
      "**/dist/**",
      "**/.next/**",
      "**/node_modules/**",
      "**/*.generated.ts"
    ]
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100,
    "lineEnding": "lf"
  },
  "organizeImports": {
    "enabled": true
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "correctness": {
        "noUnusedImports": "error",
        "noUnusedVariables": "error",
        "useExhaustiveDependencies": "warn"
      },
      "suspicious": {
        "noConsoleLog": "warn",
        "noExplicitAny": "warn"
      },
      "style": {
        "useConst": "error",
        "noVar": "error",
        "useTemplate": "error",
        "useNodejsImportProtocol": "error"
      },
      "performance": {
        "noDelete": "warn"
      }
    }
  },
  "javascript": {
    "formatter": {
      "trailingCommas": "es5",
      "semicolons": "always",
      "quoteStyle": "double",
      "jsxQuoteStyle": "double",
      "arrowParentheses": "always"
    }
  }
}
```

## Workers-specific overrides (apps/worker/biome.json)

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "extends": ["../../biome.json"],
  "linter": {
    "rules": {
      "suspicious": {
        "noConsoleLog": "error"
      },
      "correctness": {
        "noNodejsModules": "error"
      },
      "style": {
        "noRestrictedGlobals": {
          "level": "error",
          "options": {
            "deniedGlobals": ["process", "Buffer", "__dirname", "__filename", "setTimeout", "setInterval"]
          }
        }
      }
    }
  }
}
```

`noNodejsModules` prevents accidental `import fs from "node:fs"` in
Workers code where the Node.js compatibility layer is not enabled.
`noRestrictedGlobals` blocks `setTimeout` (Workers uses `scheduler.wait`)
and `process.env` (Workers uses `env` binding parameter).

## Next.js overrides (apps/web/biome.json)

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "extends": ["../../biome.json"],
  "linter": {
    "rules": {
      "correctness": {
        "noNodejsModules": "off"
      },
      "suspicious": {
        "noConsoleLog": "warn"
      }
    }
  }
}
```

## pnpm scripts

```json
// package.json (root)
{
  "scripts": {
    "lint":        "biome lint --write=false .",
    "lint:fix":    "biome lint --write .",
    "format":      "biome format --write .",
    "format:check":"biome format --write=false .",
    "check":       "biome check --write=false .",
    "check:fix":   "biome check --write ."
  }
}
```

`biome check` runs lint + format + import organisation in a single pass —
use it in CI and for pre-commit hooks.

## CI integration (GitHub Actions)

```yaml
# .github/workflows/ci.yml
- name: Biome check
  run: pnpm biome ci .
```

`biome ci` is identical to `biome check` but exits non-zero on any
finding and prints machine-readable output. It also omits ANSI colours
automatically when `CI=true`.

```yaml
# With Turborepo — run per package, cached
- name: Lint (turbo)
  run: turbo run lint --filter=...[origin/main]
```

Per-package `turbo.json` task for caching:

```jsonc
{
  "tasks": {
    "lint": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "biome.json", "../../biome.json"],
      "outputs": []
    }
  }
}
```

## Performance vs ESLint

| Metric | ESLint + Prettier | Biome |
|---|---|---|
| Cold lint (worker package) | ~14 s | ~0.4 s |
| Format check | ~3 s | included in 0.4 s |
| Config files | 4–6 | 1–3 |
| Plugin count | 8–12 | 0 |
| Binary download | ~350 MB (node_modules) | ~10 MB |

Biome parallelises across CPU cores by default. On a 8-core CI runner
the `--max-diagnostics` default of 20 keeps output clean; raise it
during migration: `biome check --max-diagnostics=200 .`.

## VSCode integration

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
  "[json]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "editor.codeActionsOnSave": {
    "quickfix.biome": "explicit",
    "source.organizeImports.biome": "explicit"
  }
}
```

## Migrating from ESLint + Prettier

```bash
# Biome ships a migration command (Biome >=1.6)
pnpm biome migrate eslint --write
pnpm biome migrate prettier --write

# Remove old tooling
pnpm remove -w eslint prettier \
  @typescript-eslint/eslint-plugin \
  @typescript-eslint/parser \
  eslint-config-prettier \
  eslint-plugin-react
```

Review `biome.json` after migration — some ESLint rules map to different
Biome rule names; the migration command adds comments noting unmapped rules.

## Anti-patterns

- **Running `biome format` and a separate Prettier** in the same project
  — they will conflict on trailing commas, quotes, or semicolons.
- **`noNodejsModules: "error"` at the root** — breaks the Next.js app
  which legitimately imports `node:path`; scope this to `apps/worker/`.
- **`recommended: true` without reviewing the rule set** — some
  recommended rules (e.g. `noParameterAssign`) have legitimate exceptions
  in Workers code; turn them to `"warn"` until reviewed.
- **Ignoring `.wrangler/`** — without this, Biome attempts to lint
  Wrangler's generated JS bundles; this is both slow and produces false
  positives.

## Gotchas

- Biome does not yet support `.vue`, `.svelte`, or CSS Modules — if the
  project uses these, ESLint remains necessary for those file types.
- `biome migrate eslint` handles flat config (`eslint.config.js`) but not
  legacy `.eslintrc.*`; convert to flat config first or migrate manually.
- Biome's import organiser groups differ from `eslint-plugin-import`;
  expect cosmetic import-order diffs in the first `--write` pass.
- `useNodejsImportProtocol` enforces `node:fs` over `fs` — consistent
  with Workers' Node.js compat mode but may need `// biome-ignore` in
  older shared utilities.

## Verification

```bash
# Lint with zero-exit on success
pnpm biome check --write=false . && echo "All clean"

# Confirm Workers rules fire
echo 'setTimeout(() => {}, 100)' > /tmp/test-worker.ts
pnpm biome lint /tmp/test-worker.ts
# Expect: noRestrictedGlobals error for setTimeout

# Benchmark vs ESLint
hyperfine --warmup 2 "pnpm biome check ." "pnpm eslint ."
```

## Related

- `documentation/categories/devtools/eslint-v9-flat-config-cloudflare-workers.md`
- `documentation/categories/devtools/eslint-concurrency-performance-governance.md`
- `documentation/categories/devtools/typescript-cloudflare-workers-strict.md`
- `documentation/categories/devtools/turborepo-cloudflare-workers-pipeline.md`
- `documentation/categories/devtools/rust-linters-biome-oxlint-migration.md`

## Sources

- https://biomejs.dev/guides/getting-started/
- https://biomejs.dev/guides/configure-biome/
- https://biomejs.dev/linter/rules/
- https://biomejs.dev/reference/cli/#biome-ci
- https://biomejs.dev/guides/migrate-eslint-prettier/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
