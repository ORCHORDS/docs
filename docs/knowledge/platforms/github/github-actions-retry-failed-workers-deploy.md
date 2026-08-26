# GitHub Actions Retry Failed Cloudflare Workers Deploy

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers deploy step fails intermittently with a 429 rate-limit or a transient
502 from the Workers API, causing the entire CI workflow to fail and requiring a developer to
manually re-run the workflow. Implementing structured retry logic directly in the workflow
eliminates false negative deploy failures without masking real errors or infinite-looping on
genuine bad builds.

## Context

The Cloudflare Workers REST API (`api.cloudflare.com`) imposes per-zone rate limits on
`PUT /accounts/{account_id}/workers/scripts/{script_name}`. Transient errors (429, 502, 503)
are common during traffic spikes on the Cloudflare control plane. The `wrangler deploy`
command exits non-zero on any HTTP error including these transients. GitHub Actions has no
built-in step-level retry — only `jobs.<id>.steps[*].continue-on-error` which ignores the
failure entirely, which is not what you want. The correct approach uses a shell retry loop
with exponential back-off for transient errors while still propagating genuine failures
(e.g., invalid bindings, missing secrets, or bundler errors) immediately.

## Shell Retry Loop with Exponential Back-off

A POSIX-compatible retry function wraps `wrangler deploy`. The retry count and back-off are
tuned for Cloudflare API rate-limit windows (typically 60-second buckets).

```yaml
# .github/workflows/deploy.yml
name: Deploy to Cloudflare Workers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      id-token: write   # Required for OIDC token exchange

    environment:
      name: production
      url: https://api.example.com

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
      - run: pnpm run build

      - name: Deploy with retry
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          MAX_ATTEMPTS: "5"
          INITIAL_DELAY: "15"
        run: |
          set -euo pipefail

          attempt=1
          delay=$INITIAL_DELAY

          while [[ $attempt -le $MAX_ATTEMPTS ]]; do
            echo "Deploy attempt $attempt of $MAX_ATTEMPTS"

            if pnpm wrangler deploy --env production 2>&1 | tee /tmp/deploy-output.txt; then
              echo "Deploy succeeded on attempt $attempt"
              exit 0
            fi

            exit_code=${PIPESTATUS[0]}
            output=$(cat /tmp/deploy-output.txt)

            # Propagate immediately on non-transient errors
            if echo "$output" | grep -qE "(Validation error|Authentication error|10006|10007|10021)"; then
              echo "Non-transient error detected, failing immediately:"
              echo "$output"
              exit $exit_code
            fi

            if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
              echo "Transient failure (exit $exit_code). Retrying in ${delay}s..."
              sleep "$delay"
              delay=$(( delay * 2 ))
            fi

            attempt=$(( attempt + 1 ))
          done

          echo "All $MAX_ATTEMPTS deploy attempts failed."
          cat /tmp/deploy-output.txt
          exit 1
```

## Detecting Transient vs. Permanent Errors

The retry loop must distinguish transient API errors from deployment errors that will never
succeed. Grep the wrangler output for known Cloudflare error codes to short-circuit.

```typescript
// scripts/classify-deploy-error.ts
// Used in advanced pipelines that call the Workers API directly

interface DeployError {
  transient: boolean;
  code: number;
  message: string;
}

const TRANSIENT_HTTP_STATUS = new Set([429, 500, 502, 503, 504]);
const PERMANENT_CF_CODES = new Set([
  10006, // Unknown script
  10007, // Exceeded scripts limit
  10021, // Invalid binding
  10026, // Script too large
  10037, // Exceeded Workers KV namespace limit
]);

export function classifyDeployError(
  httpStatus: number,
  cfErrorCode?: number
): DeployError {
  if (cfErrorCode !== undefined && PERMANENT_CF_CODES.has(cfErrorCode)) {
    return { transient: false, code: cfErrorCode, message: "Permanent error" };
  }
  if (TRANSIENT_HTTP_STATUS.has(httpStatus)) {
    return { transient: true, code: httpStatus, message: "Transient error" };
  }
  // Default to non-transient for unknown errors to avoid masking bugs
  return { transient: false, code: httpStatus, message: "Unknown error" };
}
```

## Notifying on Exhausted Retries

When all retry attempts are exhausted, post a GitHub step summary and optionally a Slack
notification so the team knows the deploy failed without requiring manual log inspection.

```yaml
      - name: Report exhausted retries
        if: failure()
        run: |
          echo "## Deploy Failed After Retries" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**Commit:** ${{ github.sha }}" >> $GITHUB_STEP_SUMMARY
          echo "**Branch:** ${{ github.ref_name }}" >> $GITHUB_STEP_SUMMARY
          echo "**Attempts:** $MAX_ATTEMPTS" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          tail -50 /tmp/deploy-output.txt >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
        env:
          MAX_ATTEMPTS: "5"
```

## Anti-patterns

- Using `continue-on-error: true` on the deploy step and checking the outcome in a later step
  — this reports the workflow as succeeded even when the deploy failed, giving a false green
  check on the commit.
- Retrying without inspecting the error output — infinite-loops on permanent errors like
  `10026: Script too large` which will never succeed regardless of retries.
- Setting `MAX_ATTEMPTS` higher than 5 with no back-off — hammers the Cloudflare API during
  the rate-limit window and extends the outage for other users.

## Gotchas

- `set -o pipefail` is required when using `| tee`; without it, the exit code reflects `tee`
  (always 0), not `wrangler deploy`, making the failure undetectable.
- Wrangler 3.x prints progress spinners to stderr; redirect both stdout and stderr with
  `2>&1` when grepping the output for error codes.
- The `PIPESTATUS` array is bash-specific and is not available in `sh`; the workflow runner
  shebang must be `bash`, which is the default on GitHub-hosted runners but not guaranteed
  on self-hosted runners with a minimal shell install.

## Verification

```bash
# Simulate a transient failure by temporarily revoking the token and checking exit path
CLOUDFLARE_API_TOKEN=invalid pnpm wrangler deploy --dry-run 2>&1 || true

# Confirm grep patterns match known error strings
echo "Authentication error: 10000" | grep -qE "(Authentication error|10006|10007)" && echo "matched"

# Check that back-off values are correct for 5 attempts
delay=15; for i in 1 2 3 4 5; do echo "attempt $i delay ${delay}s"; delay=$((delay*2)); done
```

## Related

- `github/github-actions-cloudflare-deploy-workflow.md`
- `github/github-actions-oidc-cloudflare-deploy.md`
- `github/github-actions-deployment-gates.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/evaluate-expressions-in-workflows-and-actions
