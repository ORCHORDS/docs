# Git Hooks with Lefthook in a pnpm Monorepo

**Author:** example.com
**Project:** example project (example.com) — pnpm monorepo, Cloudflare Workers + Pages
**Last updated:** 2026-08-22

---

## Overview

Git hooks enforce code quality at the moment a developer commits or pushes, before CI ever runs. For a pnpm monorepo, two popular frameworks handle this automation: **Husky** and **Lefthook**. This article compares them, explains why Lefthook is the better fit for a multi-package workspace, and provides a complete configuration for example project covering pre-commit linting, type-checking, and conventional commit message enforcement.

---

## Husky vs Lefthook for pnpm Monorepos

### Husky

Husky is the most widely used hook manager in the Node.js ecosystem. It installs shell scripts into `.git/hooks/` and relies on `npm run` (or `pnpm run`) to execute each step. Configuration lives in the `package.json` scripts section and individual shell files under `.husky/`.

**Strengths**
- Ubiquitous — almost every Node project tutorial uses it.
- Simple mental model: one file per hook.
- `lint-staged` integration is well-documented.

**Weaknesses in a monorepo**
- No native parallel execution — hooks run steps sequentially.
- Hook scripts are shell files, not structured config; hard to review as code.
- `pnpm` workspace context is not automatic — you must add `-w` flags manually.
- Running a hook in a specific workspace package requires custom shell logic.
- `prepare` lifecycle script installs hooks, which breaks `pnpm install --frozen-lockfile` in CI unless you add `--ignore-scripts`.

### Lefthook

Lefthook is a fast, language-agnostic hook manager written in Go. A single `lefthook.yml` at the repository root defines all hooks with explicit parallelism, per-glob filters, and package-scoped commands.

**Strengths over Husky for monorepos**
- **Parallel execution** — `parallel: true` runs lint and type-check concurrently, cutting pre-commit time in half.
- **Per-file globs** — `glob` filters mean only changed files are processed, just like `lint-staged` but built in.
- **Structured YAML config** — reviewable, diffable, no hidden shell scripts.
- **No `prepare` lifecycle** — hooks install via `lefthook install`, which is explicit and CI-safe.
- **Cross-language** — the same tool works for any language in the repo (Go, Python, Swift scripts alongside TypeScript).
- **Fail-fast control** — `fail_text` and `skip` give fine-grained control over which failures block the commit.

**Verdict:** Use Lefthook for example project The parallel execution alone makes the developer experience noticeably faster than Husky on a cold commit.

---

## Installation

```bash
# Install Lefthook as a dev dependency in the workspace root
pnpm add -D -w lefthook

# Install hooks into .git/hooks/ (run once per clone)
pnpm exec lefthook install
```

Add a `postinstall` script to `package.json` at the workspace root so new clones automatically install hooks:

```json
{
  "scripts": {
    "postinstall": "lefthook install"
  }
}
```

`lefthook install` is a no-op in CI environments where `LEFTHOOK=0` is set, so it does not conflict with `--frozen-lockfile` installs.

```yaml
# .github/workflows/ci.yml (excerpt)
env:
  LEFTHOOK: 0   # disable hook installation in CI
```

---

## lefthook.yml — Complete Configuration

```yaml
# lefthook.yml  (repository root)
# Docs: https://github.com/evilmartians/lefthook

# ─── PRE-COMMIT ──────────────────────────────────────────────────────────────
pre-commit:
  parallel: true      # lint and type-check run concurrently

  commands:
    # ── ESLint: only staged .ts/.tsx/.js files ─────────────────────────────
    eslint:
      glob: "**/*.{ts,tsx,js,jsx}"
      run: pnpm exec eslint --fix {staged_files}
      stage_fixed: true    # re-stage auto-fixed files

    # ── Prettier: all staged formattable files ─────────────────────────────
    prettier:
      glob: "**/*.{ts,tsx,js,jsx,json,yaml,yml,md,css}"
      run: pnpm exec prettier --write {staged_files}
      stage_fixed: true

    # ── TypeScript: type-check each affected workspace package ─────────────
    # Use turbo to only check packages that contain staged files
    typecheck:
      glob: "**/*.{ts,tsx}"
      run: pnpm turbo run typecheck --filter="...[HEAD]" --output-logs=errors-only
      # No stage_fixed — tsc does not modify files

    # ── Cloudflare Workers: validate wrangler.toml on change ───────────────
    wrangler-check:
      glob: "**/wrangler.toml"
      run: >
        for f in {staged_files}; do
          dir=$(dirname "$f");
          echo "Validating $dir/wrangler.toml";
          (cd "$dir" && pnpm exec wrangler types --dry-run 2>/dev/null || true);
        done

# ─── COMMIT-MSG ──────────────────────────────────────────────────────────────
commit-msg:
  commands:
    conventional-commits:
      run: pnpm exec commitlint --edit {1}
      fail_text: |
        ✖ Commit message does not follow Conventional Commits.

        Expected format:
          <type>(<scope>): <description>

        Types: feat, fix, chore, docs, refactor, test, ci, perf, revert
        Scopes: api, web, mobile, workers, shared, infra, release

        Examples:
          feat(api): add webhook signature validation
          fix(workers): handle KV timeout gracefully
          chore(deps): update wrangler to 3.x

# ─── PRE-PUSH ────────────────────────────────────────────────────────────────
pre-push:
  parallel: false    # run sequentially — tests after build

  commands:
    # Run unit tests for changed packages only before pushing
    test:
      run: pnpm turbo run test --filter="...[origin/main]" --output-logs=errors-only
      fail_text: "Tests failed. Fix before pushing to remote."
```

---

## commitlint Configuration

Install commitlint with the conventional commits config:

```bash
pnpm add -D -w @commitlint/cli @commitlint/config-conventional
```

```javascript
// commitlint.config.js  (repository root)
/** @type {import('@commitlint/types').UserConfig} */
export default {
  extends: ["@commitlint/config-conventional"],

  rules: {
    // Enforce the example project scope list
    "scope-enum": [
      2,    // level 2 = error
      "always",
      ["api", "web", "mobile", "workers", "shared", "infra", "release", "deps"],
    ],

    // Allow longer subject lines for descriptive commit messages
    "subject-max-length": [1, "always", 100],  // level 1 = warning

    // Do not require a body — keep commits lightweight
    "body-max-line-length": [0, "always", 200],

    // Disallow trailing period on subject
    "subject-full-stop": [2, "never", "."],

    // Enforce lower-case subject
    "subject-case": [2, "always", "lower-case"],
  },

  // Ignore automated commits (Release Please, Renovate, Dependabot)
  ignores: [
    (message) =>
      /^chore\(release\):/.test(message) ||
      /^chore\(deps\): update/.test(message) ||
      /^build\(deps-dev\):/.test(message),
  ],
};
```

---

## ESLint and Prettier Setup

```bash
# Workspace-root dev dependencies
pnpm add -D -w \
  eslint \
  @typescript-eslint/parser \
  @typescript-eslint/eslint-plugin \
  eslint-plugin-import \
  prettier \
  eslint-config-prettier
```

```javascript
// eslint.config.js  (repository root — flat config)
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import prettierConfig from "eslint-config-prettier";

export default [
  {
    ignores: ["**/dist/**", "**/.wrangler/**", "**/node_modules/**"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser: tsParser },
    plugins: { "@typescript-eslint": tsPlugin },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  prettierConfig,  // must be last — disables formatting rules
];
```

---

## Skipping Hooks When Needed

Lefthook respects `LEFTHOOK=0` and the `--no-verify` flag is a last resort for genuine emergencies. Both should be rare:

```bash
# Skip all hooks for this commit (emergency only — document why in the message)
LEFTHOOK=0 pnpm exec lefthook run pre-commit   # test the hook manually

# Standard skip via git (use sparingly)
# git commit --no-verify  ← prefer not to alias or habitually use this
```

To skip a specific command while keeping others:

```yaml
# lefthook.yml — per-developer local override (gitignored)
# lefthook-local.yml
pre-commit:
  commands:
    typecheck:
      skip: true   # temporarily disable while working on types
```

`lefthook-local.yml` is merged with `lefthook.yml` and should be listed in `.gitignore`.

---

## CI Integration

Hooks run locally. CI runs the same checks independently without hooks (idempotent):

```yaml
# .github/workflows/ci.yml
env:
  LEFTHOOK: 0

jobs:
  quality:
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

      - name: Lint
        run: pnpm turbo run lint

      - name: Type-check
        run: pnpm turbo run typecheck

      - name: Commitlint (PR title or last commit)
        run: echo "${{ github.event.pull_request.title }}" | pnpm exec commitlint
```

---

## Summary

| Concern | Tool | Config file |
|---------|------|-------------|
| Hook management | Lefthook | `lefthook.yml` |
| Linting | ESLint (flat config) | `eslint.config.js` |
| Formatting | Prettier | `.prettierrc.json` |
| Type checking | `tsc` via Turborepo | `turbo.json` |
| Commit format | commitlint | `commitlint.config.js` |

Lefthook's parallel pre-commit pipeline keeps developer feedback under five seconds even in a large monorepo, while commitlint's scope enforcement keeps the changelog generator (Release Please) working correctly.

**References**
- Lefthook: https://github.com/evilmartians/lefthook
- commitlint: https://commitlint.js.org
- Conventional Commits: https://www.conventionalcommits.org
