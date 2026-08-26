# git push options: CI skip and selective Workers deploy control

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You push a documentation-only commit to a Cloudflare Workers monorepo and the full CI pipeline runs—wrangler deploy, D1 migrations, secret sync—wasting five minutes on a change that touched only `README.md`. Alternatively, you want to trigger a staging-only deploy without promoting to production. Git push options (`--push-option` / `-o`) let you embed structured hints in the push payload that GitHub Actions reads before deciding what to run.

## Context

Push options are key-value strings transmitted as part of the git push protocol (protocol v2). GitHub exposes them in Actions as `github.event.push.push_options` (a newline-joined string of all `-o` values). Because the options travel with the push itself—not in commit messages—they are invisible to history, ephemeral, and unambiguous. They require Git ≥ 2.10 on the client and a server that forwards them; GitHub.com has supported them since 2019.

In a pnpm + Turborepo monorepo with multiple Cloudflare Workers, coordinating deploy targets from the push command lets a single branch strategy replace a sprawl of environment branches.

## Sending push options from the command line

```bash
# Skip CI entirely for a docs-only push
git push origin main -o ci.skip

# Skip wrangler deploy but run tests
git push origin main -o deploy.skip

# Deploy only to staging, not production
git push origin main -o deploy.env=staging

# Combine options
git push origin main \
  -o deploy.env=staging \
  -o deploy.workers=api-gateway,auth-worker

# Alias in .gitconfig so you don't type it every time
git config alias.push-staging \
  "push origin main -o deploy.env=staging"
```

## Reading push options in GitHub Actions

```yaml
# .github/workflows/workers-deploy.yml
name: Workers Deploy

on:
  push:
    branches: [main, "release/**"]

jobs:
  parse-push-options:
    runs-on: ubuntu-latest
    outputs:
      ci_skip: ${{ steps.parse.outputs.ci_skip }}
      deploy_skip: ${{ steps.parse.outputs.deploy_skip }}
      deploy_env: ${{ steps.parse.outputs.deploy_env }}
      deploy_workers: ${{ steps.parse.outputs.deploy_workers }}
    steps:
      - id: parse
        run: |
          OPTIONS="${{ join(github.event.push.push_options, '\n') }}"
          echo "ci_skip=$(echo "$OPTIONS" | grep -c '^ci\.skip$')" >> $GITHUB_OUTPUT
          echo "deploy_skip=$(echo "$OPTIONS" | grep -c '^deploy\.skip$')" >> $GITHUB_OUTPUT
          ENV=$(echo "$OPTIONS" | grep '^deploy\.env=' | cut -d= -f2)
          echo "deploy_env=${ENV:-production}" >> $GITHUB_OUTPUT
          WORKERS=$(echo "$OPTIONS" | grep '^deploy\.workers=' | cut -d= -f2)
          echo "deploy_workers=${WORKERS:-all}" >> $GITHUB_OUTPUT

  deploy:
    needs: parse-push-options
    if: |
      needs.parse-push-options.outputs.ci_skip == '0' &&
      needs.parse-push-options.outputs.deploy_skip == '0'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - name: Deploy workers
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          DEPLOY_ENV: ${{ needs.parse-push-options.outputs.deploy_env }}
          DEPLOY_WORKERS: ${{ needs.parse-push-options.outputs.deploy_workers }}
        run: pnpm tsx scripts/selective-deploy.ts
```

## TypeScript selective deploy script

```typescript
// scripts/selective-deploy.ts
import { execSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

const DEPLOY_ENV = process.env.DEPLOY_ENV ?? "production";
const DEPLOY_WORKERS = process.env.DEPLOY_WORKERS ?? "all";

interface WorkerConfig {
  name: string;
  path: string;
  environments: string[];
}

function discoverWorkers(): WorkerConfig[] {
  const workersDir = join(process.cwd(), "workers");
  return readdirSync(workersDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => ({
      name: d.name,
      path: join(workersDir, d.name),
      environments: ["staging", "production"],
    }));
}

function shouldDeploy(worker: WorkerConfig): boolean {
  if (DEPLOY_WORKERS === "all") return true;
  return DEPLOY_WORKERS.split(",")
    .map((w) => w.trim())
    .includes(worker.name);
}

function deployWorker(worker: WorkerConfig): void {
  if (!worker.environments.includes(DEPLOY_ENV)) {
    console.log(`[skip] ${worker.name} has no env '${DEPLOY_ENV}'`);
    return;
  }
  console.log(`[deploy] ${worker.name} → ${DEPLOY_ENV}`);
  execSync(`pnpm wrangler deploy --env ${DEPLOY_ENV}`, {
    cwd: worker.path,
    stdio: "inherit",
  });
}

const workers = discoverWorkers().filter(shouldDeploy);
console.log(`Deploying ${workers.length} worker(s) to ${DEPLOY_ENV}`);
for (const w of workers) deployWorker(w);
```

## Commit-message skip vs push-option skip

```typescript
// lib/ci/should-skip.ts
// Push-option approach is preferred; commit-message skip is a fallback.

export type SkipSignal =
  | { source: "push-option"; reason: string }
  | { source: "commit-message"; reason: string }
  | null;

export function detectSkipSignal(
  pushOptions: string[],
  commitMessage: string
): SkipSignal {
  // Push option takes precedence (explicit, ephemeral, no history pollution)
  const ciSkip = pushOptions.find((o) => o === "ci.skip");
  if (ciSkip) return { source: "push-option", reason: "ci.skip option set" };

  // Fallback: commit message convention [skip ci] or [ci skip]
  const msgSkip = /\[(skip ci|ci skip)\]/i.test(commitMessage);
  if (msgSkip) {
    return { source: "commit-message", reason: "commit message contains skip" };
  }

  return null;
}
```

## Anti-patterns

- **Encoding skip logic in branch names** (`docs/update-readme`) — requires custom branch parsing, breaks when branch names are shared across worktrees, and leaks intent into permanent refs.
- **Hardcoding `[skip ci]` in squash merge commit messages** — pollutes history and is harder to audit than ephemeral push options.
- **Using push options to carry secrets or sensitive values** — push options are visible in GitHub Actions logs and webhook payloads; use repository secrets for credentials.
- **Making push options the sole deploy gate** — they are optional; always add path-filter-based conditions as a secondary guard so routine pushes without options still behave correctly.

## Gotchas

- `github.event.push.push_options` is only populated on `push` events, not on `pull_request`, `workflow_dispatch`, or `merge_group` events. Guard your parse step with `if: github.event_name == 'push'`.
- Push options are passed as a newline-joined string in the Actions expression context. Use `join(github.event.push.push_options, '\n')` or iterate the array; do not assume it is a plain string.
- Git clients older than 2.10 silently drop `-o` flags without error. Pin the git version in CI (`git --version` assertion in a pre-flight step).
- Some self-hosted GitHub Enterprise Server versions require explicit enablement of push option forwarding in the admin console.
- Options are discarded at the server after the push completes; they cannot be retrieved from the API after the fact.

## Verification

```bash
# Confirm your git client supports push options
git push --help | grep push-option

# Test locally with a dry-run (if your remote supports it)
git push origin main --dry-run -o deploy.env=staging

# In CI: print parsed outputs in the parse-push-options job
echo "ci_skip=${{ needs.parse-push-options.outputs.ci_skip }}"
echo "deploy_env=${{ needs.parse-push-options.outputs.deploy_env }}"

# Audit recent push-triggered workflows for option usage
gh run list --workflow workers-deploy.yml --limit 20 --json headBranch,conclusion
```

## Related

- `git-worktree-parallel-wrangler-environments.md` — parallel environment deploys from worktrees
- `git-hooks-pre-commit-frameworks.md` — client-side gates before push
- `wrangler-environments-staging-production.md` — environment configuration
- `monorepo-wrangler-selective-deploy.md` — turborepo-driven selective deploys
- `ci-cd-pipeline-2026.md` — pipeline architecture overview

## Sources

- Git documentation: `git help push` → `--push-option`
- GitHub Actions: `github.event.push` context reference (docs.github.com)
- Cloudflare Workers: Wrangler CLI environments documentation
- Git protocol v2 specification: `Documentation/technical/protocol-v2.txt` in the git source tree
