# github-actions-matrix-strategy-workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Cloudflare Worker deploys for example project (example.com) are committed one-environment-at-a-time in series: staging deploys, someone watches Slack, then prod deploys. A single deploy job file is duplicated for each environment with hand-edited `CLOUDFLARE_ENV` values. Drift accumulates between copies, fail-fast behavior is undefined, and total pipeline duration is the sum of all deploy times rather than the maximum.

## Context

GitHub Actions matrix strategy lets a single job definition expand across a set of dimension values. For multi-environment Cloudflare Worker deploys (preview, staging, production), matrix eliminates copy-paste workflow files, standardises the deploy invocation, and runs all environments in parallel. Careful configuration of `fail-fast`, `max-parallel`, and matrix `exclude` prevents a flaky preview deploy from gating production, and keeps the Cloudflare API rate limit from being hit simultaneously by too many concurrent Wrangler processes.

## Matrix definition patterns

A basic three-environment matrix with per-environment overrides:

```yaml
jobs:
  deploy:
    name: Deploy (${{ matrix.environment }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false          # do NOT let staging failure abort prod
      max-parallel: 2           # Cloudflare API: avoid burst rate-limit
      matrix:
        include:
          - environment: preview
            cf_env: preview
            wrangler_cmd: deploy --env preview
            required: false
          - environment: staging
            cf_env: staging
            wrangler_cmd: deploy --env staging
            required: true
          - environment: production
            cf_env: production
            wrangler_cmd: deploy --env production
            required: true
```

Each row produces one job. `include` rows are additive: they add keys alongside the matrix combinations, or produce a standalone row when no other dimensions exist. Prefer `include`-only matrices when each environment carries its own config blob rather than composing dimensions.

## fail-fast behaviour

| `fail-fast` value | Effect |
|---|---|
| `true` (default) | First job failure cancels all still-running and queued sibling jobs |
| `false` | All matrix jobs run to completion regardless of sibling outcomes |

For example project deploys, always set `fail-fast: false`. A preview deploy failing (e.g. preview-specific env var missing) must not cancel the production deploy that is already in-flight. Use `required: false` on the matrix row and a downstream conditional step to decide whether to fail the workflow:

```yaml
      - name: Fail workflow if required deploy failed
        if: failure() && matrix.required == true
        run: exit 1
```

## max-parallel and rate limiting

Cloudflare Wrangler calls the Workers API during deploy. Running six environments simultaneously can trigger HTTP 429 responses. `max-parallel` caps concurrent jobs from the matrix:

```yaml
    strategy:
      max-parallel: 2   # at most 2 Wrangler deploys run at once
```

| Environments | max-parallel | Approx. wall-clock (30 s/deploy) |
|---|---|---|
| 3 | 1 | ~90 s |
| 3 | 2 | ~60 s |
| 3 | 3 | ~30 s (may 429) |
| 6 | 2 | ~90 s |
| 6 | 3 | ~60 s |

Start at `max-parallel: 2` and raise if no 429s appear in Wrangler output.

## Matrix exclusions

Use `exclude` to drop a specific cell from a computed matrix. Exclusions match by key equality; partial matches are supported.

```yaml
    strategy:
      matrix:
        environment: [preview, staging, production]
        region: [us, eu]
        exclude:
          - environment: preview
            region: eu          # no EU preview Worker
          - environment: production
            region: us          # prod is EU-only for GDPR
```

`exclude` runs after the full cartesian product is built. `include` rows that were added explicitly are never excluded. When in doubt, prefer `include`-only matrices over `exclude` — exclusions of computed products are easy to mis-specify.

## Environment protection integration

Each matrix environment should map to a GitHub Actions Environment for approval gates and scoped secrets:

```yaml
    environment:
      name: ${{ matrix.environment }}
      url: ${{ steps.deploy.outputs.url }}
```

GitHub Actions creates a deployment record per matrix job. Protection rules (required reviewers, deployment branch policy) apply per-environment, so `production` can require a reviewer while `staging` deploys unattended.

```
matrix job: preview   → GitHub Environment: preview   (auto-approve)
matrix job: staging   → GitHub Environment: staging   (auto-approve)
matrix job: production → GitHub Environment: production (requires review)
```

## Anti-patterns

- Setting `fail-fast: true` (the default) on deploy matrices — a noisy preview failure cancels production.
- Duplicating entire workflow files per environment instead of using matrix — drift guaranteed within weeks.
- Using `max-parallel` larger than 3 against the Cloudflare Workers API without verifying rate limits in Wrangler verbose output (`--log-level debug`).
- Putting environment-specific secrets in the matrix definition — secrets must come from the GitHub Environment context, not the matrix row, to keep them out of workflow logs.
- Using `matrix.environment` as the Wrangler `--env` flag directly without an `include` mapping when `wrangler.toml` environment names differ from GitHub Environment names.

## Gotchas

- Job names from matrix are auto-generated as `deploy (preview)`, `deploy (staging)` — if required status checks reference the job name, the parenthetical suffix must be included exactly or the check is never satisfied.
- `strategy.matrix` properties are available in `env:` and `with:` blocks but NOT in `environment.name` before GitHub resolves matrix — use `${{ matrix.environment }}` directly, it works at expression-eval time.
- Reusable workflows called from a matrix job do not inherit `strategy` — the `fail-fast` and `max-parallel` settings apply to the caller's matrix, not to jobs inside the called workflow.
- `include` rows do not merge with `exclude` rows — a matrix row added via `include` is never removed by an `exclude` entry. This is the opposite of what most people expect.
- When a matrix job is skipped via `if:` condition, GitHub marks it as "skipped", which satisfies required status checks configured with "skipped jobs are passing" but fails those without it.

## Verification

1. Push to a feature branch and observe workflow run; all three environment jobs should appear as separate rows in the Actions UI.
2. Verify job names include the environment suffix: `Deploy (preview)`, `Deploy (staging)`, `Deploy (production)`.
3. Confirm `max-parallel` by watching the timeline — no more than N jobs should show "In progress" simultaneously.
4. Deliberately break the preview `wrangler_cmd` value; confirm staging and production jobs run to completion (fail-fast: false working).
5. Check the `production` environment in repo Settings → Environments — the deployment record from the matrix job should appear with the deploy URL populated.
6. Run `wrangler whoami` in the deploy step with `--log-level debug` and grep for 429 responses to validate rate limit headroom.

```yaml
      - name: Deploy Worker
        id: deploy
        run: |
          OUTPUT=$(npx wrangler ${{ matrix.wrangler_cmd }} --log-level debug 2>&1)
          echo "$OUTPUT"
          URL=$(echo "$OUTPUT" | grep -oP 'https://\S+\.workers\.dev' | head -1)
          echo "url=$URL" >> $GITHUB_OUTPUT
```

## Related

- `github-actions-environments.md`
- `github-actions-environment-protection.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-dynamic-matrix-and-fail-fast.md`
- `github-actions-concurrency-groups.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow
- https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategyfail-fast
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
