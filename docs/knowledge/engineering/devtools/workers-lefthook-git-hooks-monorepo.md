# Lefthook Git Hooks in a Cloudflare Workers Monorepo

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Workers monorepo has multiple packages — shared libraries, API workers, scheduled workers, and a frontend — and you need consistent pre-commit type checking, commit message linting, and pre-push test runs without the overhead of Husky + lint-staged cobbled together across dozens of `package.json` scripts. Developers skip hooks with `--no-verify`, CI runs clean while local machines don't, and the monorepo root has no unified place to declare what runs when.

## Context

Applies when:
- Monorepo managed with pnpm workspaces or npm workspaces
- Multiple `wrangler.toml` files across packages
- TypeScript strict mode enabled per package
- Wrangler 3.x in use
- Node 20+ runtime for tooling

Lefthook is a single Go binary (zero runtime dependency) that reads `lefthook.yml` at the repo root. It executes hooks in parallel by default, supports glob filtering so only touched packages run their checks, and integrates cleanly with CI by respecting `LEFTHOOK=0` or `CI=true` environment variables.

## Solution

Install Lefthook as a dev dependency at the monorepo root:

```bash
pnpm add -Dw lefthook
```

Create `lefthook.yml` at the repo root:

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  commands:
    type-check-workers:
      glob: "packages/*/src/**/*.{ts,tsx}"
      run: |
        # Identify which packages have changed files and type-check only those
        CHANGED_PKGS=$(echo {staged_files} | tr ' ' '\n' \
          | grep '^packages/' \
          | cut -d'/' -f2 \
          | sort -u)
        for pkg in $CHANGED_PKGS; do
          echo "Type-checking packages/$pkg"
          pnpm --filter "./packages/$pkg" exec tsc --noEmit
        done
      stage_fixed: false

    lint-staged-files:
      glob: "**/*.{ts,tsx,js,mjs}"
      run: pnpm exec eslint {staged_files} --max-warnings 0
      stage_fixed: false

    wrangler-check:
      glob: "packages/*/wrangler.toml"
      run: |
        for toml in {staged_files}; do
          pkg_dir=$(dirname $toml)
          echo "Validating wrangler config in $pkg_dir"
          pnpm --filter "$pkg_dir" exec wrangler types --env local 2>&1 | grep -v "^\s*$"
        done

commit-msg:
  commands:
    conventional-commits:
      run: |
        MSG=$(cat {1})
        # Enforce Conventional Commits: type(scope): description
        if ! echo "$MSG" | grep -qE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9-]+\))?: .{1,100}$'; then
          echo "ERROR: Commit message must follow Conventional Commits format."
          echo "  Good:  feat(api-worker): add rate limiting middleware"
          echo "  Bad:   fixed stuff"
          echo "Got: $MSG"
          exit 1
        fi

pre-push:
  parallel: false
  commands:
    test-affected:
      run: |
        BASE_BRANCH=$(git rev-parse --abbrev-ref HEAD@{upstream} 2>/dev/null || echo 'origin/main')
        CHANGED=$(git diff --name-only $BASE_BRANCH...HEAD | grep '^packages/' | cut -d'/' -f2 | sort -u)
        if [ -z "$CHANGED" ]; then
          echo "No package changes detected, skipping tests."
          exit 0
        fi
        for pkg in $CHANGED; do
          echo "Running tests for packages/$pkg"
          pnpm --filter "./packages/$pkg" run test --run
        done

skip:
  - ref: main
  - ref: origin/main
```

Initialise the hooks so Git registers them:

```bash
pnpm exec lefthook install
```

This writes tiny shell stubs into `.git/hooks/` that delegate to the Lefthook binary.

## Implementation Details

### Monorepo layout assumed

```
monorepo/
  lefthook.yml
  pnpm-workspace.yaml
  package.json            # root
  packages/
    api-worker/
      src/
      wrangler.toml
      tsconfig.json
      package.json
    cron-worker/
      src/
      wrangler.toml
      tsconfig.json
      package.json
    shared-lib/
      src/
      tsconfig.json
      package.json
```

### Root `package.json` scripts

```json
{
  "scripts": {
    "prepare": "lefthook install",
    "lefthook:uninstall": "lefthook uninstall"
  },
  "devDependencies": {
    "lefthook": "^1.7.0"
  }
}
```

The `prepare` script ensures any contributor running `pnpm install` automatically installs the hooks.

### Per-package `tsconfig.json` for wrangler type-check

Each worker package should extend a root base config and enable strict Cloudflare types:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022"],
    "module": "ES2022",
    "moduleResolution": "bundler",
    "types": ["@cloudflare/workers-types/2023-07-01"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noEmit": true
  },
  "include": ["src/**/*.ts", "worker-configuration.d.ts"]
}
```

### Parallel hook execution explained

With `parallel: true` under `pre-commit`, Lefthook forks each command into its own process. For a monorepo with 4 packages, type-checking, linting, and wrangler config validation can all run simultaneously, cutting a 12-second sequential run down to ~4 seconds.

Commands under `pre-push` use `parallel: false` because test runners competing for port 8787 (Miniflare's default) will collide. Serial execution avoids this.

### Skipping hooks in CI

Set the environment variable before running any git operations:

```bash
# In your GitHub Actions workflow
env:
  LEFTHOOK: 0
```

Or use Lefthook's built-in CI detection — it checks `CI=true` and automatically disables hooks when that variable is present in the environment.

### Generating `worker-configuration.d.ts` as a pre-commit step

If your team committed generated types, add a sync command:

```yaml
pre-commit:
  commands:
    generate-types:
      glob: "packages/*/wrangler.toml"
      run: |
        for toml in {staged_files}; do
          pkg_dir=$(dirname $toml)
          pnpm --filter "$pkg_dir" exec wrangler types
          git add "$pkg_dir/worker-configuration.d.ts"
        done
      priority: 1   # runs before other pre-commit commands
```

## Anti-patterns

**Do not** run `wrangler deploy` inside a pre-commit hook. Deployments take 15-30 seconds, block commits, and have no place in a local hook — use CI for deployments.

**Do not** use `--no-verify` as a team convention to work around slow hooks. Slow hooks mean the hook is doing too much. Move expensive checks (full test suites, E2E) to `pre-push` or CI.

**Do not** commit the `.git/hooks/` directory. Lefthook regenerates hooks from `lefthook.yml` via `lefthook install`. Committing generated hook stubs leads to version drift.

**Do not** use Husky alongside Lefthook. Pick one. Having both means hooks fire twice and produce confusing double-error output.

## Gotchas

**`{staged_files}` is a Lefthook template variable**, not a shell variable. It expands to the list of staged files filtered by the command's `glob` pattern. If your glob matches nothing in the current commit, the command is skipped entirely — no error, just silence. This is the intended behaviour for incremental checks.

**`pnpm --filter` path syntax** requires a `./` prefix for directory filters (`./packages/api-worker`) versus a package name filter (`api-worker`). The path form is more reliable in hooks because it does not depend on the `name` field in `package.json` matching your directory name.

**Wrangler `types` command** writes `worker-configuration.d.ts` relative to the `wrangler.toml` location. If that file is `.gitignore`d but your `tsconfig.json` `include` points to it, `tsc --noEmit` will fail for contributors who have never run `wrangler types`. Add the generation step before type-check in the hook or document it in `CONTRIBUTING.md`.

**Hook binary location on Apple Silicon Macs**: Lefthook installed via npm/pnpm ships the correct architecture binary inside `node_modules/.bin/lefthook`. Avoid installing Lefthook globally via Homebrew if the version differs from the one in `package.json` — the Git stub calls `node_modules/.bin/lefthook` directly, so the local version always wins.

## Verification

After running `pnpm exec lefthook install`, verify the hooks are registered:

```bash
ls -la .git/hooks/
# You should see: pre-commit, commit-msg, pre-push pointing to lefthook stubs

# Run a dry-run without actually committing
pnpm exec lefthook run pre-commit --all-files

# Test commit-msg hook directly
echo 'bad message' | pnpm exec lefthook run commit-msg --stdin
# Expected: error output with format instructions

echo 'feat(api): add new endpoint' | pnpm exec lefthook run commit-msg --stdin
# Expected: clean exit (no output)
```

Check that CI skips hooks correctly:

```bash
LEFTHOOK=0 git commit -m 'ci: skip hooks'
# Hooks should not execute
```

## Related

- `wrangler-config-typescript-types.md` — typed wrangler bindings that make `wrangler types` output useful
- `workers-turbo-remote-cache-r2.md` — speeding up the CI pipeline that hooks feed into
- `workers-changesets-version-release-pipeline.md` — commit-msg conventions used in changesets workflow

## Sources

- https://lefthook.dev/configuration/
- https://developers.cloudflare.com/workers/wrangler/commands/#types
- https://www.conventionalcommits.org/en/v1.0.0/
- https://pnpm.io/filtering
