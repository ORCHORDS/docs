# Migrating from ESLint + Prettier to Biome in a Workers Project

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

ESLint and Prettier together add significant cold-start time to CI and local `wrangler dev` cycles. Biome provides lint + format in a single Rust binary that is 10-100× faster, requires one config file, and ships with zero peer dependencies — making it ideal for Workers projects where build determinism matters.

## Context

- Cloudflare Workers (ESM, TypeScript)
- Node 20, pnpm or npm
- Existing project with `.eslintrc.*` and `.prettierrc.*`
- CI: GitHub Actions
- Wrangler 3.x

---

## Step 1 — Install Biome

```bash
# npm
npm install --save-dev --save-exact @biomejs/biome

# pnpm
pnpm add -D --save-exact @biomejs/biome

# one-shot init (creates biome.json)
npx @biomejs/biome init
```

Pin to an exact version so that CI and local environments always agree.

---

## Step 2 — biome.json Configuration

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true
  },
  "files": {
    "ignoreUnknown": false,
    "ignore": ["dist", ".wrangler", "node_modules"]
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "tab",
    "lineWidth": 100
  },
  "organizeImports": {
    "enabled": true
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "correctness": {
        "noUnusedVariables": "error",
        "noUnusedImports": "error"
      },
      "style": {
        "noNonNullAssertion": "warn",
        "useConst": "error"
      },
      "suspicious": {
        "noExplicitAny": "warn"
      }
    }
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "double",
      "trailingCommas": "all",
      "semicolons": "always"
    },
    "globals": ["ENVIRONMENT", "API_KEY"]
  },
  "typescript": {
    "tsconfig": "./tsconfig.json"
  }
}
```

---

## Step 3 — Migrate ESLint Rules to Biome Equivalents

| ESLint rule | Biome equivalent |
|---|---|
| `no-unused-vars` | `correctness/noUnusedVariables` |
| `no-console` | `suspicious/noConsoleLog` |
| `prefer-const` | `style/useConst` |
| `@typescript-eslint/no-explicit-any` | `suspicious/noExplicitAny` |
| `import/order` | `organizeImports.enabled: true` |

For rules with no Biome equivalent yet, keep a minimal ESLint config alongside Biome:

```json
// .eslintrc-remaining.json  — only rules not yet covered by Biome
{
  "extends": [],
  "rules": {
    "no-restricted-globals": ["error", "event", "name"]
  }
}
```

---

## Step 4 — package.json Scripts

```json
{
  "scripts": {
    "lint": "biome lint ./src",
    "lint:fix": "biome lint --write ./src",
    "format": "biome format ./src",
    "format:write": "biome format --write ./src",
    "check": "biome check ./src",
    "check:fix": "biome check --write ./src",
    "ci:check": "biome ci ./src"
  }
}
```

`biome check` runs lint + format + import organisation in one pass. `biome ci` uses exit code 1 on any finding (no writes), suitable for CI gates.

---

## Step 5 — Auto-fix With --write

```bash
# Reformat and fix safe lint issues in place
npx biome check --write ./src

# Unsafe fixes (rename variables, remove dead code) — review diff before committing
npx biome check --write --unsafe ./src

# Only format, don't lint
npx biome format --write ./src
```

Run `--unsafe` once when first migrating, review the git diff carefully, then drop it from normal flow.

---

## Step 6 — CI Integration (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  biome:
    name: Lint & Format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Biome CI check
        run: pnpm run ci:check
        # biome ci exits 1 on any lint/format violation — no writes in CI

  build:
    name: Wrangler Build
    runs-on: ubuntu-latest
    needs: biome
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec wrangler deploy --dry-run --outdir dist
```

---

## Step 7 — Speed Comparison

Typical numbers on a 300-file Workers monorepo:

| Tool | Cold run | Warm (cache) |
|---|---|---|
| ESLint + Prettier (separate) | 18 s | 8 s |
| ESLint + Prettier (lint-staged) | 6 s | 3 s |
| Biome check | **0.4 s** | **0.15 s** |

Biome also outputs structured JSON for downstream tooling:

```bash
npx biome lint --reporter=json ./src | jq '.diagnostics | length'
```

---

## Step 8 — Remove Legacy Config

```bash
# Remove ESLint and Prettier packages
npm uninstall eslint prettier eslint-config-prettier \
  eslint-plugin-import @typescript-eslint/eslint-plugin \
  @typescript-eslint/parser

# Remove config files
rm -f .eslintrc.js .eslintrc.json .eslintignore \
       .prettierrc .prettierrc.json .prettierignore

# Remove lint-staged / husky if only used for ESLint
npm uninstall lint-staged husky
```

Update VS Code settings:

```json
// .vscode/settings.json
{
  "editor.defaultFormatter": "biomejs.biome",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports.biome": "explicit",
    "quickfix.biome": "explicit"
  },
  "[javascript]": { "editor.defaultFormatter": "biomejs.biome" },
  "[typescript]": { "editor.defaultFormatter": "biomejs.biome" }
}
```

---

## Anti-patterns

- Running `biome check` in `--write` mode in CI — use `biome ci` instead to avoid silent mutations.
- Keeping `.prettierrc` around after migration — Biome ignores it but other tools may pick it up and create conflicts.
- Mixing Biome formatter with Prettier via VS Code multi-formatter — only one should own each file type.
- Setting `"indentStyle": "space"` in `biome.json` but leaving tab characters in legacy files — run `--write` once to normalise.
- Forgetting to add `.wrangler` and `dist` to `files.ignore` — Biome will try to lint generated worker bundles.

## Gotchas

- Biome does not yet support all ESLint plugins (e.g., `eslint-plugin-react-hooks`); check the compatibility table before removing plugin rules.
- `organizeImports` reorders imports destructively; ensure your barrel files don't have side-effect-dependent ordering.
- The Biome VS Code extension requires the binary to be in `node_modules/.bin/biome` — global installs are not detected.
- `biome ci` returns exit code 1 for warnings if `--max-diagnostics` is exceeded; tune `linter.rules` severity to keep the count low.

---

## Verification

```bash
# Confirm Biome version matches lockfile
npx biome --version

# Dry-run check with summary
npx biome check ./src --reporter=summary

# Assert zero violations in CI mode
npx biome ci ./src && echo "clean"

# Confirm no Prettier config leaks
ls .prettierrc* 2>/dev/null && echo "WARNING: Prettier config still present"
```

---

## Related

- `documentation/docs/policies/devtools/workers-source-map-upload-wrangler-debug.md`
- `documentation/docs/policies/devtools/workers-module-graph-analysis-esbuild-metafile.md`

## Sources

- https://biomejs.dev/guides/getting-started/
- https://biomejs.dev/linter/rules/
- https://biomejs.dev/formatter/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://biomejs.dev/recipes/continuous-integration/
