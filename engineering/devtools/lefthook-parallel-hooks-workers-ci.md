# Lefthook Parallel Hooks Configuration for Workers CI

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your pre-commit hook chain runs lint → typecheck → test sequentially and takes 45+ seconds. Developers skip hooks with `--no-verify`. You want independent checks to run in parallel and you need the hook behaviour to mirror what CI runs, including Wrangler type generation, without pulling in Husky or lint-staged.

## Context

Lefthook is a fast, dependency-free Git hooks manager written in Go. It ships as a single binary, integrates natively with pnpm workspaces, and supports parallel job execution within a hook stage. For Cloudflare Workers monorepos the key advantages over Husky are built-in parallelism, per-job `glob` filtering without lint-staged, and a `skip` condition system that avoids running Workers-specific checks on non-Workers packages.

Lefthook reads `lefthook.yml` at the repo root. It wraps each job in a pseudo-TTY so colour output is preserved in terminals. In CI you typically run `lefthook run pre-push` explicitly rather than relying on Git hooks.

---

## Installing Lefthook in a pnpm Workspace

```bash
pnpm add -Dw lefthook
```

Add the prepare script so every `pnpm install` reinstalls hooks:

```jsonc
// package.json (root)
{
  "scripts": {
    "prepare": "lefthook install"
  }
}
```

```bash
pnpm lefthook install   # first-time or after config changes
```

The binary is resolved from `node_modules/.bin/lefthook`; no global install required.

---

## Basic Parallel Pre-commit Configuration

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  jobs:
    - name: biome-check
      glob: "**/*.{ts,tsx,js,json}"
      run: pnpm biome check --no-errors-on-unmatched {staged_files}

    - name: tsc-workers
      glob: "apps/worker/**/*.ts"
      run: pnpm --filter ./apps/worker tsc --noEmit

    - name: wrangler-types
      glob: "wrangler.toml"
      run: pnpm --filter ./apps/worker wrangler types --output-path src/worker-configuration.d.ts && git add src/worker-configuration.d.ts
```

`{staged_files}` is a Lefthook template variable injected at runtime with the list of staged paths that match `glob`. Jobs with no matching staged files are skipped automatically.

---

## Pre-push Hook with Vitest Workers Tests

```yaml
# lefthook.yml (continued)
pre-push:
  parallel: true
  jobs:
    - name: unit-tests
      run: pnpm --filter ./apps/worker vitest run --pool workers

    - name: type-coverage
      run: pnpm --filter ./apps/worker tsc --noEmit --incremental false

    - name: wrangler-deploy-dry
      run: pnpm --filter ./apps/worker wrangler deploy --dry-run --outdir dist/dry
```

The `--dry-run` flag on Wrangler validates `wrangler.toml`, binding resolution, and esbuild output without uploading. This catches deploy-time errors before the push reaches CI.

---

## Skip Conditions for Non-Workers Packages

```yaml
# lefthook.yml
pre-push:
  parallel: true
  jobs:
    - name: wrangler-deploy-dry
      skip:
        - ref: "refs/heads/main"   # skip on direct main pushes (CI handles it)
      glob: "apps/worker/**"
      run: pnpm --filter ./apps/worker wrangler deploy --dry-run --outdir dist/dry

    - name: pages-build
      glob: "apps/web/**"
      run: pnpm --filter ./apps/web next build
```

`skip.ref` accepts a glob against the full ref name. Use it to avoid running expensive checks when force-pushing hotfix branches.

---

## Running Lefthook in GitHub Actions CI

```yaml
# .github/workflows/ci.yml
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # needed for changed-files detection

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run pre-push checks
        run: pnpm lefthook run pre-push --no-tty
```

`--no-tty` disables the spinner and outputs plain text suitable for CI log viewers. Lefthook exits non-zero if any job fails, failing the workflow step.

---

## Anti-patterns

- **Putting slow checks only in pre-commit** — developers rebase frequently and hit every staged checkpoint. Move anything over ~5 s (full tsc, vitest run) to pre-push.
- **Using `run: npx lefthook ...` inside the config** — lefthook.yml jobs should call project scripts (`pnpm …`), not invoke lefthook recursively.
- **Relying on `git stash` inside jobs** — lefthook runs after the index is snapshotted; stashing unstaged changes inside a job creates merge conflicts on pop. Use glob filtering instead of stash-based isolation.
- **Setting `parallel: true` on jobs that share a write target** — e.g. two jobs both writing to `dist/`. Serialise dependent jobs or write to separate output dirs.

---

## Gotchas

- `{staged_files}` is empty on `pre-push`; use `{push_files}` for files changed in the pushed commits.
- Lefthook resolves binaries from PATH; in pnpm workspaces add `node_modules/.bin` to the shell's PATH or prefix commands with `pnpm exec`.
- The `glob` key filters *which files trigger the job* but does not pass those files to the command unless you use the template variable explicitly.
- On macOS, Git hooks installed by `lefthook install` are placed in `.git/hooks/`. `.gitignore` never touches `.git/`, so there is no risk of committing them.
- `lefthook.yml` is committed; `lefthook-local.yml` is gitignored and can override any key for individual developer preferences (e.g. disabling slow checks locally).

---

## Verification

```bash
# Confirm hooks are installed
ls -la .git/hooks/pre-commit

# Dry-run a hook stage without triggering Git
pnpm lefthook run pre-commit --all-files

# Show what would run for a specific file change
pnpm lefthook run pre-push --files "apps/worker/src/index.ts"

# Output timing per job
pnpm lefthook run pre-push --no-tty 2>&1 | grep -E "SUMMARY|ms"
```

---

## Related

- `pre-commit-framework.md` — Python-based alternative hook manager
- `git-hooks-husky.md` — Husky v9 setup and comparison
- `vitest-coverage-threshold-workers-ci.md` — Coverage gates enforced in pre-push
- `wrangler-config-validation-ci.md` — Wrangler toml schema checks in CI

---

## Sources

- https://lefthook.dev/configuration/
- https://lefthook.dev/recipes/skip-in-ci/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/evilmartians/lefthook/blob/master/docs/configuration.md
