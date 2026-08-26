# Git Hooks Tooling — Husky, lint-staged, commitlint, and Lefthook

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

A developer pushes code with ESLint errors that break the CI build.
Another developer writes a commit message "fix stuff" which provides
no context for changelogs or code review. Your team agreed on
Conventional Commits but enforcement is manual — reviewers spend
time commenting on commit message format instead of reviewing code.
Meanwhile, your pre-commit hook runs the entire ESLint suite on
every commit, taking 45 seconds even when only one file changed.

## Context

Git hooks tooling automates code quality enforcement at commit time.
Husky v9 manages Git hooks as plain shell files in `.husky/`,
lint-staged runs linters only on staged files (not the entire
codebase), and commitlint enforces Conventional Commits format for
commit messages. Lefthook is a Go-based alternative that runs hooks
in parallel (reported 10x faster than Husky) with native monorepo
support and no Node.js runtime dependency. The standard 2026 JS/TS
stack is Husky + lint-staged + commitlint; polyglot or large
monorepos increasingly adopt Lefthook.

## Husky v9 setup

```bash
# Install
npm install --save-dev husky lint-staged \
  @commitlint/cli @commitlint/config-conventional

# Initialize — creates .husky/ directory and adds prepare script
npx husky init
```

```sh
# .husky/pre-commit
npx lint-staged
```

```sh
# .husky/commit-msg
npx commitlint --edit $1
```

```
Husky v9 changes from v8:
  → Hook scripts are plain shell files in .husky/
  → No more JSON or JS configuration
  → "prepare": "husky" in package.json (added by init)
  → HUSKY=0 environment variable disables hooks (for CI)
```

## lint-staged configuration

```json
// package.json or .lintstagedrc.json
{
  "lint-staged": {
    "**/*.{js,ts,tsx}": ["prettier --write", "eslint --fix"],
    "**/*.{json,md,html}": ["prettier --write"],
    "**/*.css": ["stylelint"],
    "**/*.scss": ["prettier --write", "stylelint --customSyntax=postcss-scss"]
  }
}
```

```
How lint-staged works:

  1. Git stages files (git add)
  2. Developer commits (git commit)
  3. Husky triggers pre-commit hook
  4. lint-staged identifies staged files
  5. Runs configured commands ONLY on staged files
  6. If any command fails, commit is aborted
  7. If all pass, commit proceeds

  Key benefit: runs linters on changed files only,
  not the entire codebase. 45-second lint becomes <2 seconds.
```

```json
// Monorepo pattern — root package.json
{
  "lint-staged": {
    "packages/web/**/*.{ts,tsx}": [
      "pnpm --filter web run lint:staged-file"
    ],
    "packages/api/**/*.{ts,tsx}": [
      "pnpm --filter api run lint:staged-file"
    ],
    "*.{json,md}": ["prettier --write"]
  }
}
```

## commitlint configuration

```javascript
// commitlint.config.js
module.exports = {
  extends: ['@commitlint/config-conventional'],
};
```

```
Conventional Commits format:

  type(scope): subject

  Types:
    feat     New feature
    fix      Bug fix
    docs     Documentation
    style    Formatting (no code change)
    refactor Code restructuring (no feature/fix)
    perf     Performance improvement
    test     Adding/updating tests
    chore    Build process, dependencies
    ci       CI configuration

  Examples:
    feat: add user authentication
    fix(api): resolve null pointer in user service
    docs: update API documentation
    chore(deps): upgrade React to v19

  Enforced by: commitlint + @commitlint/config-conventional
  Used by: semantic-release, release-please for auto-versioning
```

## Lefthook (alternative to Husky + lint-staged)

```yaml
# lefthook.yml — single file replaces Husky + lint-staged
pre-commit:
  parallel: true
  commands:
    lint:
      glob: "*.{js,ts,tsx}"
      run: npx eslint --fix {staged_files}
    format:
      glob: "*.{json,md}"
      run: npx prettier --write {staged_files}
    types:
      glob: "*.{ts,tsx}"
      run: npx tsc --noEmit

commit-msg:
  commands:
    commitlint:
      run: npx commitlint --edit {1}
```

```
Lefthook vs Husky:

  Aspect              Lefthook            Husky + lint-staged
  ──────────────────────────────────────────────────────────
  Runtime:            Go binary (none)    Node.js required
  Execution:          Parallel by default Sequential
  Speed:              ~10x faster         Baseline
  Config:             Single YAML file    Multiple files
  Monorepo:           Native root: option Shell script paths
  Polyglot:           No Node dependency  Requires Node.js

  Pick Husky when: JS/TS ecosystem, standard tooling expected
  Pick Lefthook when: polyglot, large monorepo, speed matters
```

## CI integration

```yaml
# GitHub Actions — enforce Conventional Commits on PRs
- name: Validate PR commits
  uses: CondeNast/conventional-pull-request-action@v0.2.0
  with:
    commitlintConfigFile: commitlint.config.js
```

```
CI enforcement complements local hooks:

  Local (pre-commit):
    → Fast feedback for the developer
    → Can be bypassed with --no-verify

  CI (PR check):
    → Cannot be bypassed
    → Validates all commits in the PR
    → Required status check blocks merge

  Both are needed: local for DX, CI for enforcement.
```

## Anti-patterns

- **Running full linter suite on every commit** — without
  lint-staged, pre-commit hooks lint the entire codebase, taking
  30-60 seconds. Use lint-staged to lint only staged files.
- **Relying only on local hooks** — `git commit --no-verify`
  bypasses all hooks. Always pair local hooks with CI checks
  that cannot be bypassed.
- **Husky in polyglot repos** — non-JS contributors (Go, Python,
  Rust engineers) need Node.js installed solely to get commit
  hooks. Use Lefthook for polyglot teams.
- **Complex shell scripts in hook files** — hook files should
  delegate to tools (lint-staged, commitlint), not contain
  business logic. Keep hook files to one or two lines.

## Gotchas

- **`husky: not found` in CI** — `npm ci --omit=dev` skips
  devDependencies, so the `"prepare": "husky"` script fails.
  Fix: set `HUSKY=0` in CI environment variables or guard the
  prepare script to no-op in CI.
- **`core.hooksPath` misconfiguration** — if
  `git config --get core.hooksPath` does not point to `.husky/`,
  hooks silently never fire. Verify after `npx husky init`.
- **lint-staged config inheritance** — configs do not merge.
  lint-staged uses the config file closest to each staged file.
  Shared rules must be composed via a JS config that imports a
  base configuration.
- **Stale hooks after branch switch** — switching branches with
  different hook configurations can leave stale hooks. Run
  `npx husky` after switching branches if hooks seem wrong.

## Verification

- Husky initialized with `.husky/pre-commit` and `.husky/commit-msg`.
- lint-staged configured to run linters only on staged files.
- commitlint enforces Conventional Commits format.
- CI check validates commit messages on all pull requests.
- `HUSKY=0` set in CI environment to skip hook installation.
- `core.hooksPath` verified to point to `.husky/` directory.

## Related

- `documentation/categories/worktree/pre-commit-hook-frameworks.md`
- `documentation/categories/worktree/conventional-commits-changelog.md`
- `documentation/categories/github/actions-security-hardening.md`

## Source URLs (verified 2026-08-16)

- Git Hooks with Husky and lint-staged Complete Guide — https://dev.to/_d7eb1c1703182e3ce1782/git-hooks-with-husky-and-lint-staged-the-complete-setup-guide-for-2025-53ji
- commitlint Local Setup Guide — https://commitlint.js.org/guides/local-setup.html
- Husky How-To Documentation — https://typicode.github.io/husky/how-to.html
- Lefthook vs Husky 2026 — https://www.edopedia.com/blog/lefthook-vs-husky/
