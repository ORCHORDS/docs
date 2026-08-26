# Prettier Config for Consistent Code Formatting in a Monorepo

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A pnpm monorepo with a dozen packages produces inconsistent formatting across packages: some use
2-space indentation, others 4; some have trailing commas in JavaScript, others do not; Markdown
files reflow differently depending on who ran the formatter last. Reviewers raise formatting nits
in every PR. Adding Prettier to each package individually means multiple config files to maintain
and no guarantee that the root CI check uses the same rules.

## Context

Prettier is an opinionated code formatter that enforces a consistent style across JavaScript,
TypeScript, JSON, CSS, Markdown, YAML, and other file types. In a monorepo the goal is:

1. A single source-of-truth Prettier config at the workspace root.
2. Package-level overrides only when genuinely necessary (rare).
3. `format` and `format:check` scripts wired into the CI pipeline.
4. Editor integration so developers format on save.
5. A pre-commit hook to block unformatted commits.

Prettier 3.x (released 2023, maintained through 2026) dropped the default support for Babel
parsing in favour of Acorn for `.js` files and requires explicit `--parser` flags for non-standard
inputs. All examples below target Prettier 3.x.

## Installation

Install at the workspace root only:

```bash
pnpm add -Dw prettier
```

Optionally add language plugins:

```bash
# Prettier plugin for Tailwind CSS class sorting
pnpm add -Dw prettier-plugin-tailwindcss

# Prettier plugin for package.json field ordering
pnpm add -Dw prettier-plugin-packagejson

# Prettier plugin for import sorting (alternative to ESLint import order)
pnpm add -Dw @ianvs/prettier-plugin-sort-imports
```

## Root Config File

Create `prettier.config.ts` at the workspace root (Prettier 3.x supports TypeScript config
files natively when `tsx` or similar is available; alternatively use `.prettierrc.json`):

```typescript
// prettier.config.ts
import type { Config } from 'prettier';

const config: Config = {
  // Core style choices
  printWidth: 100,
  tabWidth: 2,
  useTabs: false,
  semi: true,
  singleQuote: true,
  quoteProps: 'as-needed',
  jsxSingleQuote: false,
  trailingComma: 'all',
  bracketSpacing: true,
  bracketSameLine: false,
  arrowParens: 'always',
  endOfLine: 'lf',

  // Plugin order matters: tailwind must be last
  plugins: [
    '@ianvs/prettier-plugin-sort-imports',
    'prettier-plugin-packagejson',
    'prettier-plugin-tailwindcss',
  ],

  // Import sort configuration (@ianvs/prettier-plugin-sort-imports)
  importOrder: [
    '<TYPES>',
    '<BUILT_IN_MODULES>',
    '',
    '<THIRD_PARTY_MODULES>',
    '',
    '^@repo/(.*)$',
    '',
    '^[./]',
  ],
  importOrderParserPlugins: ['typescript', 'jsx', 'decorators-legacy'],

  // Per-language overrides
  overrides: [
    {
      files: ['*.json', '*.jsonc'],
      options: {
        trailingComma: 'none', // JSON does not allow trailing commas
      },
    },
    {
      files: ['*.md', '*.mdx'],
      options: {
        printWidth: 80,
        proseWrap: 'always',
      },
    },
    {
      files: ['*.yaml', '*.yml'],
      options: {
        singleQuote: false,
        tabWidth: 2,
      },
    },
    {
      files: ['*.css', '*.scss'],
      options: {
        singleQuote: false,
      },
    },
  ],
};

export default config;
```

If TypeScript configs cause issues (e.g., in plain Node environments without `tsx`), use
`.prettierrc.json` instead:

```json
{
  "printWidth": 100,
  "tabWidth": 2,
  "useTabs": false,
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "bracketSpacing": true,
  "endOfLine": "lf",
  "plugins": [
    "prettier-plugin-packagejson",
    "prettier-plugin-tailwindcss"
  ]
}
```

## .prettierignore

Create `.prettierignore` at the workspace root:

```
# Build outputs
dist/
.next/
.nuxt/
out/
build/

# Generated files
*.generated.ts
worker-configuration.d.ts
*.pb.ts

# Large data files
*.min.js
*.min.css

# Package manager internals
node_modules/
.pnpm-store/

# Wrangler / Cloudflare output
.wrangler/

# Changeset files (managed by changeset tooling)
.changeset/*.md
```

## Workspace Scripts

Add scripts in the root `package.json`:

```json
{
  "scripts": {
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "format:changed": "prettier --write $(git diff --name-only --diff-filter=ACMR HEAD | xargs)"
  }
}
```

`format:changed` formats only files changed since HEAD — useful in large monorepos to avoid
reformatting thousands of unchanged files during a PR.

## Per-Package Overrides

Occasionally a package needs different rules (e.g., a generated protobuf package that uses
4-space indentation to match the proto toolchain output). Place a `.prettierrc.json` inside that
package — Prettier uses the nearest config file:

```json
// packages/proto-generated/.prettierrc.json
{
  "tabWidth": 4
}
```

Avoid doing this unless strictly necessary; every per-package override is a maintenance burden.

## Editor Integration

### VS Code

```json
// .vscode/settings.json
{
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.formatOnSave": true,
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[typescriptreact]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[json]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[markdown]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "prettier.requireConfig": true,
  "prettier.useEditorConfig": false
}
```

Install the VS Code extension: `esbenp.prettier-vscode`. Add it to `.vscode/extensions.json`:

```json
{
  "recommendations": ["esbenp.prettier-vscode"]
}
```

### JetBrains IDEs

Enable in **Preferences → Languages & Frameworks → JavaScript → Prettier**:
- Set "Prettier package" to `{workspace}/node_modules/prettier`
- Enable "On save" and "On reformat code" checkboxes

## Pre-commit Hook

Using `lint-staged` and `husky` (or `simple-git-hooks`):

```bash
pnpm add -Dw lint-staged simple-git-hooks
```

```json
// package.json (root)
{
  "simple-git-hooks": {
    "pre-commit": "pnpm lint-staged"
  },
  "lint-staged": {
    "*.{ts,tsx,js,jsx,json,css,scss,md,yaml,yml}": [
      "prettier --write"
    ]
  }
}
```

Activate the hook:

```bash
pnpm simple-git-hooks
```

This ensures only staged files are formatted, making the hook fast even in a large monorepo.

## CI Check

Add a format check job to GitHub Actions:

```yaml
# .github/workflows/ci.yml
jobs:
  format:
    name: Prettier format check
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
      - run: pnpm format:check
```

Fail fast: place this job early in the pipeline before expensive build/test jobs.

## Anti-patterns

**Separate Prettier configs per package** — adds drift and contradicts the monorepo principle of
a single source of truth. Consolidate into the root config with `overrides` for exceptions.

**Mixing Prettier with ESLint formatting rules** — causes conflicts and double-processing.
Disable ESLint style rules with `eslint-config-prettier` and let Prettier own formatting:
`pnpm add -Dw eslint-config-prettier`.

**Running `prettier --write .` in CI** — CI should only check, never write. Use `--check` in
CI and `--write` locally.

**Omitting `prettier.requireConfig: true` in VS Code** — without this setting, VS Code Prettier
extension falls back to built-in defaults when the config file is missing, silently reformatting
code with different rules.

**Using `printWidth` as a hard column limit** — Prettier treats `printWidth` as a soft guide.
Some constructs will exceed it (e.g., long string literals, import paths). Do not set it very
low (e.g., 60) expecting a strict limit.

## Gotchas

- Prettier 3.x changed the default for `trailingComma` from `"es5"` to `"all"`. Upgrading from
  Prettier 2.x without an explicit `trailingComma` value will reformat function parameters.
- `prettier-plugin-tailwindcss` must be the **last** plugin in the `plugins` array; other plugins
  that transform the AST must run before it or their changes will be ignored.
- On Windows, `endOfLine: "lf"` requires that Git's `core.autocrlf` is set to `input` or `false`
  to prevent Git from re-adding CRLF after Prettier writes LF.
- TypeScript config files (`prettier.config.ts`) require a runtime that can execute TypeScript
  without prior compilation — `tsx` or `ts-node/esm`. If CI uses plain `node`, use `.json`.

## Verification

```bash
# Format the whole workspace
pnpm format

# Check for unformatted files (exit 1 if any)
pnpm format:check

# Verify the plugin is loading
prettier --version
prettier --find-config-path src/index.ts
prettier --config-precedence file-override src/index.ts --write
```

Expected `format:check` output when all files are clean:

```
Checking formatting...
All matched files use Prettier code style!
```

## Related

- `biome-linter-formatter-cloudflare-workers.md` — Biome as a faster Prettier + ESLint alternative
- `eslint-v9-flat-config-cloudflare-workers.md` — ESLint config (disable formatting rules)
- `editorconfig-team-consistency.md` — EditorConfig for baseline whitespace rules
- `commitlint-setup.md` — enforcing commit message style alongside formatting

## Sources

- Prettier 3.x documentation: prettier.io/docs
- `prettier-plugin-tailwindcss` README (Tailwind Labs, 2025)
- `@ianvs/prettier-plugin-sort-imports` README (2024)
- `eslint-config-prettier` README — disabling conflicting ESLint rules
- `lint-staged` documentation: lint-staged.js.org
