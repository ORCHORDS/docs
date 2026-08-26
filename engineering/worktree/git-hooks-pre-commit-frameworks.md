# Git Hooks and Pre-Commit Frameworks

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Developers push code that fails linting, contains formatting issues, or
has type errors — CI catches these issues minutes later, requiring
another commit to fix. Every engineer has a different local setup: some
run linters, some do not. Code review time is wasted on style
inconsistencies that should be caught automatically. Secrets
accidentally committed to the repository are discovered only after the
push.

## Context

Git hooks are scripts that run automatically at specific points in the
Git workflow — before commit, before push, after merge, etc. Pre-commit
hooks run before a commit is created, validating staged changes and
blocking the commit if checks fail. In 2026, three frameworks dominate
pre-commit hook management: Husky (JavaScript ecosystem, ~35k GitHub
stars), Lefthook (Go-based, polyglot, parallel execution), and
pre-commit (Python-based, largest hook ecosystem). The trend is toward
Lefthook for polyglot projects and speed-critical workflows, while Husky
+ lint-staged remains the default for JavaScript/TypeScript projects.

## Framework comparison

| Feature | Husky | Lefthook | pre-commit |
|---|---|---|---|
| Language | Node.js | Go (single binary) | Python |
| Config format | Shell scripts | YAML | YAML |
| Parallel execution | No (manual) | Built-in | Limited |
| Staged files only | With lint-staged | Built-in `{staged_files}` | Built-in |
| Speed (large repos) | Baseline | ~10x faster | Slower (venv setup) |
| Hook ecosystem | npm scripts | YAML commands | 1,000+ pre-built hooks |
| Runtime dependency | Node.js | None (binary) | Python |
| Install | `npx husky init` | `lefthook install` | `pre-commit install` |

## Husky + lint-staged

The industry standard for JavaScript/TypeScript projects:

```json
// package.json
{
  "scripts": {
    "prepare": "husky"
  },
  "lint-staged": {
    "*.{ts,tsx}": ["eslint --fix", "prettier --write"],
    "*.{json,md,yml}": ["prettier --write"],
    "*.css": ["stylelint --fix", "prettier --write"]
  }
}
```

```bash
# .husky/pre-commit
npx lint-staged
```

lint-staged runs linters only on staged files, not the entire codebase,
keeping pre-commit hooks fast regardless of project size.

## Lefthook

All-in-one alternative — replaces Husky + lint-staged with a single
YAML file:

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  commands:
    lint:
      glob: "*.{ts,tsx}"
      run: npx eslint --fix {staged_files}
      stage_fixed: true
    format:
      glob: "*.{ts,tsx,json,md,yml}"
      run: npx prettier --write {staged_files}
      stage_fixed: true
    types:
      glob: "*.{ts,tsx}"
      run: npx tsc --noEmit
    secrets:
      run: npx secretlint {staged_files}

pre-push:
  commands:
    test:
      run: npm test -- --bail

commit-msg:
  commands:
    lint-commit:
      run: npx commitlint --edit {1}
```

Key advantage: `parallel: true` runs all commands concurrently.
`stage_fixed: true` automatically re-stages files after auto-fix.

## pre-commit (Python framework)

Largest ecosystem of pre-built hooks:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-merge-conflict
      - id: detect-private-key
      - id: check-json
      - id: check-yaml

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
```

```bash
# Install hooks
pre-commit install

# Run on all files (CI or initial setup)
pre-commit run --all-files
```

## Common hook types

| Hook | When it runs | Common use |
|---|---|---|
| `pre-commit` | Before commit is created | Lint, format, type check |
| `commit-msg` | After commit message is entered | Validate conventional commits |
| `pre-push` | Before push to remote | Run tests, check branch name |
| `post-merge` | After merge completes | Run `npm install` if lockfile changed |
| `post-checkout` | After branch checkout | Run `npm install` if lockfile changed |
| `prepare-commit-msg` | Before editor opens | Add ticket number from branch name |

## Secret detection

```yaml
# Lefthook with gitleaks
pre-commit:
  commands:
    gitleaks:
      run: gitleaks protect --staged --no-banner

# pre-commit with detect-secrets
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

## Anti-patterns

- **Slow pre-commit hooks** — running the full test suite or type-
  checking the entire project on every commit. Pre-commit should take
  < 10 seconds. Run expensive checks on pre-push or in CI.
- **No staged-files filtering** — running linters on all files instead
  of only staged files. In a large codebase, this makes commits take
  minutes.
- **Skipping hooks with --no-verify** — if engineers routinely skip
  hooks, the hooks are too slow or too noisy. Fix the hooks, do not
  normalize skipping them.
- **No CI fallback** — relying solely on pre-commit hooks without CI
  checks. Hooks can be bypassed (`--no-verify`), new clones may not
  install hooks, and some tools behave differently locally vs. CI.

## Gotchas

- **Partial staging** — when a file is partially staged (`git add -p`),
  linters see the staged version but auto-fixers write to the working
  tree version. lint-staged and Lefthook handle this correctly; manual
  hook scripts often do not.
- **Monorepo performance** — in large monorepos, hooks must be scoped
  to the relevant package. Lefthook's `root` and `glob` options and
  lint-staged's path patterns enable package-scoped hooks.
- **CI consistency** — hooks run a specific version of tools (the local
  install). CI may run a different version. Pin tool versions in both
  environments.
- **Windows compatibility** — shell scripts in `.husky/` may not work
  on Windows. Lefthook and pre-commit are cross-platform by design.

## Verification

- Pre-commit hooks are installed automatically (npm `prepare` script
  or CI install step).
- Hooks run only on staged files and complete in < 10 seconds.
- Secret detection runs on every commit.
- Commit message format is validated (conventional commits).
- CI runs the same lint/format checks as hooks (defense in depth).
- No team members routinely use `--no-verify`.

## Related

- `documentation/categories/worktree/git-worktree-parallel-ci-patterns.md`
- `documentation/categories/worktree/monorepo-versioning-independent-releases.md`
- `documentation/categories/devtools/ide-configuration.md`

## Source URLs (verified 2026-08-16)

- Husky vs Lefthook vs pre-commit 2026 — https://www.pistack.xyz/posts/2026-04-26-pre-commit-vs-lefthook-vs-husky-git-hooks-management-guide-2026/
- Git hooks comparison — https://www.andymadge.com/2026/03/10/git-hooks-comparison/
- Lefthook vs Husky — https://gazar.dev/devops/lefthook-vs-husky-git-hooks
- Husky vs Lefthook vs lint-staged — https://www.pkgpulse.com/guides/husky-vs-lefthook-vs-lint-staged-git-hooks-nodejs-2026
