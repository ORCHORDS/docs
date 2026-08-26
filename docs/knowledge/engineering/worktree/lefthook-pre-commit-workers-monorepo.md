# Lefthook Pre-commit Hooks for Cloudflare Workers Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Contributors push TypeScript errors and ESLint violations because CI is the only safety net and feedback is slow. You want fast, targeted pre-commit hooks that run `tsc --noEmit`, `eslint`, and `wrangler types` — but only on the Worker packages that have staged changes, not on the entire monorepo, so the hook completes in under 10 seconds.

## Context

[Lefthook](https://github.com/evilmartians/lefthook) is a fast, polyglot Git hooks manager written in Go. It ships as a single binary, supports parallel hook execution, glob-based file targeting, and a `skip:` directive that suppresses hooks during merge commits. Unlike Husky + lint-staged, Lefthook evaluates globs itself without spawning a Node.js process, making it significantly faster in monorepo setups.

---

## Full `lefthook.yml` for a Workers Monorepo

```yaml
# lefthook.yml  (repo root)
pre-commit:
  parallel: true

  commands:
    # ── TypeScript type-check: only packages with staged .ts files ──────────
    tsc-api:
      glob: 'packages/api/**/*.ts'
      run: pnpm --filter @acme/api-worker exec tsc --noEmit
      skip:
        - merge
        - rebase

    tsc-auth:
      glob: 'packages/auth/**/*.ts'
      run: pnpm --filter @acme/auth-worker exec tsc --noEmit
      skip:
        - merge
        - rebase

    tsc-webhooks:
      glob: 'packages/webhooks/**/*.ts'
      run: pnpm --filter @acme/webhooks-worker exec tsc --noEmit
      skip:
        - merge
        - rebase

    # ── ESLint: run on staged files only ───────────────────────────────────
    eslint:
      glob: 'packages/**/*.{ts,tsx}'
      run: pnpm exec eslint {staged_files} --max-warnings 0
      skip:
        - merge
        - rebase

    # ── wrangler types: regenerate type stubs if wrangler.toml changed ─────
    wrangler-types-api:
      glob: 'packages/api/wrangler.toml'
      run: |
        pnpm --filter @acme/api-worker exec wrangler types
        git add packages/api/worker-configuration.d.ts
      skip:
        - merge
        - rebase

    wrangler-types-auth:
      glob: 'packages/auth/wrangler.toml'
      run: |
        pnpm --filter @acme/auth-worker exec wrangler types
        git add packages/auth/worker-configuration.d.ts
      skip:
        - merge
        - rebase

    wrangler-types-webhooks:
      glob: 'packages/webhooks/wrangler.toml'
      run: |
        pnpm --filter @acme/webhooks-worker exec wrangler types
        git add packages/webhooks/worker-configuration.d.ts
      skip:
        - merge
        - rebase

commit-msg:
  commands:
    conventional:
      run: echo "{1}" | grep -qP '^(feat|fix|chore|docs|style|refactor|perf|test|build|ci)(\(.+\))?: .+$'
```

---

## Installation and Bootstrap

```bash
# Install Lefthook as a dev dependency (runs via pnpm)
pnpm add -Dw lefthook

# Install the Git hooks into .git/hooks/
pnpm exec lefthook install

# Verify the hook was written
ls -la .git/hooks/pre-commit
# -rwxr-xr-x 1 user user 93 Aug 24 2026 .git/hooks/pre-commit

# Run the hooks manually without committing (useful for debugging)
pnpm exec lefthook run pre-commit

# Run a single named command
pnpm exec lefthook run pre-commit --commands tsc-api
```

Add to `package.json` so new contributors automatically install hooks after `pnpm install`:

```jsonc
// package.json (root)
{
  "scripts": {
    "prepare": "lefthook install"
  }
}
```

---

## Targeting Only Staged Files with `{staged_files}`

Lefthook injects the list of staged files matching the `glob` pattern into the `{staged_files}` template variable. This is the key mechanism that makes the ESLint command fast:

```yaml
eslint:
  glob: 'packages/**/*.{ts,tsx}'
  run: pnpm exec eslint {staged_files} --max-warnings 0
```

If you stage only `packages/api/src/index.ts`, Lefthook passes only that file to ESLint — not the entire `packages/` tree.

For TSC, the `{staged_files}` variable is not useful because `tsc --noEmit` always processes the whole program graph. Instead, gate the command on the glob matching at least one staged file, but run the full type-check for that package:

```yaml
tsc-api:
  glob: 'packages/api/**/*.ts'
  # Runs only when the glob matches; always checks the full api package
  run: pnpm --filter @acme/api-worker exec tsc --noEmit
```

---

## Parallel Execution Deep-dive

```yaml
pre-commit:
  parallel: true   # All commands run concurrently
```

With `parallel: true`, Lefthook forks all commands simultaneously. On a 4-core laptop:

- `tsc-api`, `tsc-auth`, `tsc-webhooks` run concurrently — total time ≈ max(individual times) ≈ 4 s instead of 12 s
- `eslint` runs concurrently with TSC
- `wrangler-types-*` commands only run when `wrangler.toml` is staged, which is rare

The `git add` inside `wrangler-types-*` is safe under `parallel: true` because Git's index lock is per-file-add, not per-command. However, to be safe you can move those commands into a `pre-commit` serial group:

```yaml
pre-commit:
  parallel: true

  commands:
    tsc-api: { ... }
    eslint:  { ... }

pre-commit-serial:
  # This key is a custom hook name registered separately
  # Use separate lefthook groups if ordering matters
  parallel: false
  commands:
    wrangler-types-api: { ... }
```

---

## Anti-patterns

- **Running TSC on the entire monorepo root** — `tsc --noEmit` at the root with a monorepo `tsconfig.json` project references can take 30+ seconds. Always scope to the specific package with `pnpm --filter`.
- **Using `lint-staged` inside Lefthook** — Lefthook already handles staged-file filtering via `{staged_files}` and `glob`. Nesting `lint-staged` adds a second Node.js process and duplicate logic.
- **Omitting `skip: merge`** — during `git merge`, conflicting files appear as staged; running TSC on them always fails. The `skip: merge` directive suppresses the hook during merge commits entirely.
- **Running `wrangler types` on every commit** — the generated `worker-configuration.d.ts` only changes when `wrangler.toml` changes. Gate it on `glob: 'packages/*/wrangler.toml'` to avoid spurious regenerations.
- **Committing `lefthook.yml` without running `lefthook install`** — the YAML file alone does nothing; the binary must write hooks into `.git/hooks/`. The `prepare` script handles this automatically post-install.

---

## Gotchas

- Lefthook resolves `{staged_files}` relative to the repo root, but ESLint must be invoked from a directory where `eslint.config.ts` is visible. Use `run: pnpm exec eslint {staged_files}` from the repo root if ESLint config is at the root; otherwise use `root:` to change the working directory per command.
- `pnpm --filter <name> exec <cmd>` resolves `<name>` against `package.json#name`, not the directory name. Keep the two in sync.
- On Windows, Lefthook hooks require Git Bash or WSL2; PowerShell shebangs are not supported.
- If a developer installs hooks with Husky before switching to Lefthook, stale `.git/hooks/pre-commit` files may shadow Lefthook's hook. Run `lefthook install --force` to overwrite.
- `lefthook run pre-commit` in CI (for debugging) does not set the staged-files environment that Git sets; all `{staged_files}` expansions are empty. Use `--all-files` flag to target all tracked files instead.

---

## Verification

```bash
# Stage a file with a TypeScript error and attempt a commit
echo 'const x: string = 42' >> packages/api/src/index.ts
git add packages/api/src/index.ts
git commit -m "test: intentional type error"
# lefthook: tsc-api
# error TS2322: Type 'number' is not assignable to type 'string'.
# FAILED tsc-api
# lefthook: commit is blocked

# Fix the error, then commit succeeds
git checkout -- packages/api/src/index.ts
git commit -m "chore: verify lefthook pre-commit works"
# lefthook: tsc-api ...... OK
# lefthook: eslint ....... OK
# [main abc1234] chore: verify lefthook pre-commit works

# Confirm hooks are installed
pnpm exec lefthook list
# pre-commit
# commit-msg
```

---

## Related

- `github-actions-path-filter-selective-deploy-workers.md`
- `git-worktree-hotfix-production-without-stash.md`
- [Lefthook documentation](https://github.com/evilmartians/lefthook)
- [Wrangler types command](https://developers.cloudflare.com/workers/wrangler/commands/#types)

## Sources

- Lefthook README and wiki (2024)
- Cloudflare Workers Wrangler CLI documentation (2026)
- example.com internal runbook: "Pre-commit hooks for Workers monorepo" (2025)
