# Git Hooks with Husky for Workers Projects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Developers push TypeScript type errors, linting violations, and broken Worker bundles to `main`. CI catches these, but the feedback loop is 4–8 minutes. You want immediate, local enforcement: fail fast on the developer's machine before the commit or push lands in the remote.

## Context

Husky v9 installs git hooks into `.husky/` and activates them via a `prepare` npm script. Paired with `lint-staged`, it runs linters and type-checkers only on staged files (fast) rather than the whole project. A `commit-msg` hook enforces the conventional commits format. A `pre-push` hook runs `wrangler deploy --dry-run` to catch bundle errors before code reaches CI.

Husky v9 uses a shell-native approach — each hook file is a plain shell script, removing the JavaScript overhead of v8.

## Solution

**Install Husky and lint-staged:**

```bash
npm install --save-dev husky lint-staged
npx husky init
```

`npx husky init` creates `.husky/pre-commit` with a placeholder and adds `"prepare": "husky"` to `package.json`.

**Root `package.json` additions:**

```json
{
  "scripts": {
    "prepare": "husky"
  },
  "lint-staged": {
    "**/*.ts": [
      "eslint --fix --max-warnings=0",
      "bash -c 'tsc --noEmit -p tsconfig.json'"
    ],
    "**/*.{json,yaml,yml,md}": [
      "prettier --write"
    ]
  },
  "devDependencies": {
    "husky": "^9.1.0",
    "lint-staged": "^15.2.0",
    "@commitlint/cli": "^19.0.0",
    "@commitlint/config-conventional": "^19.0.0"
  }
}
```

**`.husky/pre-commit`** — type-check and lint staged files:

```sh
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

echo "[pre-commit] Running lint-staged..."
npx lint-staged

echo "[pre-commit] Done."
```

**`.husky/commit-msg`** — enforce conventional commits:

```sh
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

npx --no -- commitlint --edit "$1"
```

**`commitlint.config.ts`**:

```typescript
import type { UserConfig } from '@commitlint/types';

const config: UserConfig = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'style',
        'refactor',
        'perf',
        'test',
        'build',
        'ci',
        'chore',
        'revert',
        'deploy',
        'migration',
      ],
    ],
    'scope-enum': [
      1,
      'always',
      [
        'api-gateway',
        'auth',
        'payments',
        'notifications',
        'types',
        'utils',
        'middleware',
        'infra',
        'deps',
        'release',
      ],
    ],
    'subject-case': [2, 'always', 'lower-case'],
    'header-max-length': [2, 'always', 100],
    'body-max-line-length': [1, 'always', 120],
  },
};

export default config;
```

**`.husky/pre-push`** — dry-run wrangler deploy for all changed Workers:

```sh
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

set -e

# Determine which workers changed vs the upstream branch
UPSTREAM="${1:-origin}"
RANGE="${UPSTREAM}/$(git rev-parse --abbrev-ref HEAD)..HEAD"

CHANGED_WORKERS=$(git diff --name-only "$RANGE" 2>/dev/null \
  | grep '^workers/' \
  | cut -d'/' -f2 \
  | sort -u)

if [ -z "$CHANGED_WORKERS" ]; then
  echo "[pre-push] No worker changes detected, skipping dry-run."
  exit 0
fi

echo "[pre-push] Changed workers: $CHANGED_WORKERS"

for WORKER in $CHANGED_WORKERS; do
  WORKER_DIR="workers/$WORKER"
  if [ -f "$WORKER_DIR/wrangler.toml" ]; then
    echo "[pre-push] Dry-running deploy for $WORKER..."
    (cd "$WORKER_DIR" && npx wrangler deploy --dry-run --outdir /tmp/wrangler-dry-run-"$WORKER")
    echo "[pre-push] $WORKER bundle OK."
  fi
done

echo "[pre-push] All dry-runs passed."
```

**Monorepo variant — `pre-push` using Turborepo for affected packages:**

```sh
#!/usr/bin/env sh
. "$(dirname -- "$0")/_/husky.sh"

set -e

echo "[pre-push] Running wrangler dry-run for affected workers via Turborepo..."

# Run a custom 'dryrun' task only on packages changed vs origin/main
npx turbo run dryrun --filter='...[origin/main]' --log-order=stream

echo "[pre-push] All dry-runs passed."
```

Add the `dryrun` task to each worker's `package.json`:

```json
{
  "scripts": {
    "dryrun": "wrangler deploy --dry-run --outdir dist-dryrun"
  }
}
```

And register it in `turbo.json`:

```json
{
  "tasks": {
    "dryrun": {
      "dependsOn": ["^build"],
      "cache": false,
      "outputs": []
    }
  }
}
```

**CI guard — verify hooks are installed (`.github/workflows/hooks-check.yml`):**

```yaml
name: Hooks Check

on:
  pull_request:
    paths:
      - '.husky/**'
      - 'package.json'
      - 'commitlint.config.*'

jobs:
  validate-hooks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Verify commitlint config
        run: |
          echo "feat(auth): add token refresh endpoint" | npx commitlint
          echo "chore(deps): update wrangler to 3.80" | npx commitlint

      - name: Verify lint-staged config
        run: npx lint-staged --diff="HEAD~1..HEAD" --allow-empty
```

## Implementation Details

- Husky v9's `prepare` script runs on `npm install`, automatically installing hooks for all team members who clone the repo. No manual `npx husky install` step is needed (that was v8 behaviour).
- `lint-staged` receives only the list of staged files matching each glob. The `tsc --noEmit` command runs against `tsconfig.json` at the root, which is correct for a single-package repo. In a monorepo, scope `tsc` calls per package using the `bash -c` escape to avoid lint-staged passing filenames as tsc arguments.
- The `pre-push` hook receives the remote name and URL as positional arguments (`$1`, `$2`). Using `$1` as the remote allows the hook to diff correctly when pushing to forks.
- `wrangler deploy --dry-run` performs bundling and validation (including checking for missing bindings referenced in the config) without making any HTTP calls to Cloudflare's API. It does not require `CLOUDFLARE_API_TOKEN` to be set.

## Anti-patterns

- **`--no-verify` as a normal workflow**: Bypassing hooks should be an emergency-only escape hatch. If developers routinely use `--no-verify`, the hooks are too slow or noisy — fix them instead.
- **Running full `tsc` across the entire monorepo in lint-staged**: This defeats the purpose of staged-file filtering and makes the pre-commit hook take 30+ seconds. Scope type-checking to the affected package.
- **Storing secrets in hook scripts**: `pre-push` must not embed `CLOUDFLARE_API_TOKEN`. Dry-run does not need it; if a hook legitimately needs a secret, load it from a `.env.local` file that is gitignored.
- **Husky in `dependencies` instead of `devDependencies`**: Husky is a development tool. Including it in `dependencies` causes it to be installed in production environments (e.g., on Cloudflare Workers build runners) unnecessarily.

## Gotchas

- On macOS with nvm or asdf, the shell that Git uses to run hooks may not source `.zshrc` or `.bashrc`, so `node` and `npx` may not be on `PATH`. Fix by adding the nvm init block to `.husky/pre-commit`, or use a `.nvmrc`-aware shim.
- `lint-staged` passes filenames as trailing arguments to commands. `tsc` does not accept filenames the way eslint does — running `tsc <file>` ignores `tsconfig.json`. Use `bash -c 'tsc --noEmit'` (without `$1`) to prevent lint-staged from appending filenames.
- In GitHub Actions, `npm ci` runs `prepare`, which runs `husky`. If `husky` cannot find `.git`, it exits with an error. Add `HUSKY=0` to your CI environment or use `npm ci --ignore-scripts` and install only what you need explicitly.
- Husky hooks are not run in bare repositories or when `GIT_DIR` is set to a non-standard path (e.g., in some worktree setups). Verify with `git config core.hooksPath`.

## Verification

```bash
# Confirm hooks are installed
ls -la .husky/
git config core.hooksPath  # should output .husky

# Test pre-commit hook manually
git stash
git stash pop
npx lint-staged --diff="HEAD~1..HEAD" --allow-empty --verbose

# Test commit-msg hook
echo "bad commit message" | npx commitlint
# Should exit non-zero

echo "feat(auth): add token refresh" | npx commitlint
# Should exit 0

# Test pre-push dry-run against a specific worker
cd workers/api-gateway
npx wrangler deploy --dry-run --outdir /tmp/test-dryrun
echo "Exit code: $?"
```

## Related

- `workers-monorepo-turborepo-setup.md` — Turborepo `dryrun` task integration
- `conventional-commits-enforcement.md` — commitlint rules in depth
- `workers-semantic-versioning-automation.md` — conventional commits drive version bumps
- `workers-code-ownership-codeowners.md` — CODEOWNERS enforcement in CI

## Sources

- https://typicode.github.io/husky/
- https://github.com/okonet/lint-staged
- https://commitlint.js.org/
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
