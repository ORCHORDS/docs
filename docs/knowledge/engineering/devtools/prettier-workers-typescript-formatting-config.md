# Prettier Workers TypeScript Formatting Config

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers project has inconsistent formatting: some files use 2-space
indentation, others 4; some use single quotes, others double; import statements wrap
at different widths depending on who last touched the file. You want a single Prettier
config that enforces a consistent style across TypeScript Worker source, Wrangler TOML
overrides, and test files — with optional Biome co-existence.

---

## Context

Prettier is an opinionated formatter that works well for TypeScript Workers codebases
because Wrangler bundles via esbuild (formatting has no runtime effect) and the
Workers runtime has no style constraints. The configuration decisions that matter
most in a Workers context are: print width (affects how D1 query chains wrap),
single vs double quotes (avoid conflicts with SQL strings), trailing commas (useful
for multi-line `fetch` option objects), and whether to format `.toml` files (Prettier
does not support TOML natively — use taplo separately).

---

## Installation

```bash
pnpm add -D prettier prettier-plugin-organize-imports
# Optional: sort package.json keys
pnpm add -D prettier-plugin-packagejson
```

---

## .prettierrc.json

```json
{
  "printWidth": 100,
  "tabWidth": 2,
  "useTabs": false,
  "semi": false,
  "singleQuote": true,
  "quoteProps": "as-needed",
  "jsxSingleQuote": false,
  "trailingComma": "all",
  "bracketSpacing": true,
  "bracketSameLine": false,
  "arrowParens": "always",
  "endOfLine": "lf",
  "plugins": [
    "prettier-plugin-organize-imports",
    "prettier-plugin-packagejson"
  ]
}
```

Key choices for Workers TypeScript:
- `singleQuote: true` — avoids escaping inside SQL string literals that use double
  quotes (e.g. `db.prepare('SELECT "id" FROM users')`).
- `trailingComma: "all"` — cleaner `git diff` when adding `fetch` options or binding
  properties.
- `printWidth: 100` — Workers source often has deeply nested types; 80 is too narrow.

---

## .prettierignore

```
# Build outputs
dist/
.wrangler/
*.d.ts

# Lock files
pnpm-lock.yaml

# Wrangler generates these
.dev.vars.example

# TOML is handled by taplo, not Prettier
*.toml
```

---

## package.json scripts

```json
{
  "scripts": {
    "format":       "prettier --write \"src/**/*.{ts,json}\" \"test/**/*.ts\"",
    "format:check": "prettier --check \"src/**/*.{ts,json}\" \"test/**/*.ts\"",
    "format:toml":  "taplo fmt wrangler.toml"
  }
}
```

---

## Formatting Workers-specific TypeScript patterns

Prettier handles all of these correctly with the config above:

```typescript
// Long env interface — wraps at 100 chars
export interface Env {
  DB: D1Database
  KV: KVNamespace
  AI: Ai
  ASSETS: Fetcher
  R2: R2Bucket
  API_SECRET: string
}

// Chained D1 query — wraps cleanly
const result = await env.DB
  .prepare(
    'SELECT id, email, created_at FROM users WHERE account_id = ? ORDER BY created_at DESC LIMIT ?',
  )
  .bind(accountId, limit)
  .all<UserRow>()

// fetch options object with trailing commas
const response = await fetch('https://api.example.com/data', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${env.API_SECRET}`,
  },
  body: JSON.stringify(payload),
})

// Hono route — single-quote strings, arrow parens
app.get('/users/:id', async (c) => {
  const id = c.req.param('id')
  return c.json({ id })
})
```

---

## VS Code integration

```json
// .vscode/settings.json
{
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "editor.formatOnSave": true,
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[json]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  // Disable Biome formatter if co-existing (Biome handles linting only)
  "[toml]": {
    "editor.defaultFormatter": "tamasfe.even-better-toml"
  }
}
```

---

## Biome co-existence

If you use Biome for linting (recommended) but keep Prettier for formatting, disable
Biome's formatter to avoid conflicts:

```json
// biome.json
{
  "formatter": {
    "enabled": false
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  }
}
```

This way Prettier owns all formatting decisions and Biome owns lint rules — no fights
over quote style or trailing commas.

---

## Pre-commit hook (lefthook)

```yaml
# lefthook.yml
pre-commit:
  commands:
    prettier:
      glob: '*.{ts,json}'
      run: prettier --write {staged_files}
      stage_fixed: true
    taplo:
      glob: '*.toml'
      run: taplo fmt {staged_files}
      stage_fixed: true
```

`stage_fixed: true` re-stages files after Prettier modifies them so the commit
includes the formatted version without requiring the developer to manually `git add`.

---

## Anti-patterns

- **`printWidth: 80`** — causes Workers bindings, long URL strings, and generic type
  signatures to wrap aggressively, making diffs harder to read.
- **`semi: true`** in a codebase that also uses ESLint `no-extra-semi` — the two
  tools fight; pick one source of truth for semi decisions.
- **Formatting `.toml` with Prettier via a community plugin** — TOML plugin support is
  experimental; taplo is the stable choice for `wrangler.toml`.
- **Running Prettier on generated `.d.ts` files** — Wrangler generates these from
  bindings; reformatting them breaks the regeneration workflow and clutters diffs.

---

## Gotchas

- `prettier-plugin-organize-imports` uses the TypeScript compiler API to sort imports;
  it must match the TypeScript version in your project. Pin both if you see parse errors.
- Prettier ignores files listed in `.gitignore` by default (`--ignore-path .gitignore`
  is the default). If `.wrangler/` is not in `.gitignore` add it to `.prettierignore`.
- `organize-imports` will remove unused imports. In Workers test files that use side-
  effect imports (e.g. `import 'cloudflare:test'`) add a `// prettier-ignore` comment
  above the import to prevent removal.
- Running `prettier --write` on a large Workers monorepo the first time can take 30-60s;
  subsequent runs are fast due to the cache at `node_modules/.cache/prettier`.

---

## Verification

```bash
# Check all TypeScript files are formatted
pnpm format:check

# Format in place and confirm no diff
pnpm format
git diff --name-only   # Should be empty if already formatted

# Check single file interactively
prettier --check src/index.ts
```

---

## Related

- `biome-linter-formatter-cloudflare-workers.md`
- `eslint-v9-flat-config-cloudflare-workers.md`
- `editorconfig-team-consistency.md`
- `lefthook-parallel-hooks-workers-ci.md`

---

## Sources

- https://prettier.io/docs/en/configuration.html
- https://github.com/simonhaenisch/prettier-plugin-organize-imports
- https://taplo.tamasfe.dev/
- https://biomejs.dev/guides/integrate-in-formatter/
