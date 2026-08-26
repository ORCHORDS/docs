# GitHub Actions Environment Variable Scope Inheritance and Secret Masking

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A secret leaks into a log because it was echoed through an intermediate variable, or a
step-level `env:` override silently shadows a job-level value and causes unexpected
behaviour.  Understanding the three-tier env var scope (workflow → job → step) and
how GitHub's log masker intercepts registered values prevents accidental disclosure.

## Context

GitHub Actions resolves environment variables through a precedence chain:

```
step env: > job env: > workflow-level env: > runner OS env
```

Values set via `$GITHUB_ENV` (the environment file) accumulate within a job and are
visible to all *subsequent* steps in that job only.  Secrets registered via
`::add-mask::` are intercepted by the runner before log upload, replacing occurrences
with `***`.  Dynamic values derived from secrets must be explicitly masked or they
will appear in plaintext.

---

## 1. Scope Precedence — Declaration Order Matters

```yaml
# .github/workflows/scope-demo.yml
env:
  DEPLOY_ENV: production          # workflow scope — visible to all jobs/steps

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      DEPLOY_ENV: staging         # job scope — shadows workflow scope for this job
      API_BASE: https://api.example.com

    steps:
      - name: Step uses job-level DEPLOY_ENV (staging)
        run: echo "Deploying to $DEPLOY_ENV"   # prints: staging

      - name: Step overrides to preview
        env:
          DEPLOY_ENV: preview     # step scope — shadows job scope for this step only
        run: echo "Deploying to $DEPLOY_ENV"   # prints: preview

      - name: Back to job scope
        run: echo "Deploying to $DEPLOY_ENV"   # prints: staging again
```

---

## 2. Propagating Values with $GITHUB_ENV

`$GITHUB_ENV` writes variables that persist across all *subsequent* steps in the same
job.  Values set this way are NOT visible in the step that sets them.

```yaml
      - name: Compute derived config
        run: |
          # Derive a non-secret value from a secret for downstream steps
          WORKER_SUFFIX="${{ secrets.CF_ACCOUNT_ID }}-workers"
          echo "WORKER_SUFFIX=$WORKER_SUFFIX" >> "$GITHUB_ENV"
          # WORKER_SUFFIX is NOT available in this step's env yet

      - name: Use derived config
        run: echo "Worker namespace: $WORKER_SUFFIX"   # available here
```

Avoid writing secrets directly to `$GITHUB_ENV` — prefer passing them as step `env:`
inputs to limit their scope to the step that needs them.

---

## 3. Manual Masking of Derived Secret Values

GitHub automatically masks values of `secrets.*` references in logs.  Derived values
(substrings, hashes, encoded forms) are NOT automatically masked.

```yaml
      - name: Build signed upload URL (derived secret must be masked)
        env:
          R2_SECRET_KEY: ${{ secrets.R2_SECRET_KEY }}
        run: |
          # HMAC-derived value is NOT auto-masked
          SIGNED_TOKEN=$(echo -n "upload" | \
            openssl dgst -sha256 -hmac "$R2_SECRET_KEY" -binary | base64)

          # Explicitly mask it before using in any subsequent command
          echo "::add-mask::$SIGNED_TOKEN"

          # Now safe to pass to wrangler or curl
          curl -s -X PUT "$R2_ENDPOINT" \
            -H "Authorization: Bearer $SIGNED_TOKEN" \
            --upload-file dist/worker.js
```

---

## 4. Scoped Secrets Using Step-Level env:

Limit secret exposure to only the step(s) that genuinely require them.

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build (no secrets needed)
        run: pnpm build

      - name: Deploy to Cloudflare (secret scoped to this step only)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: pnpm wrangler deploy --env production

      - name: Post-deploy smoke test (no secrets in scope)
        run: curl -sf https://api.example.com/health
```

If `CLOUDFLARE_API_TOKEN` were set at job level, it would be in the process environment
of every step, including any third-party actions that might log or exfiltrate it.

---

## 5. Detecting Scope Leaks in CI

Add a debug step that checks which secret-shaped values are visible at each scope level
without printing their content.

```yaml
      - name: Env audit (debug, remove before merge)
        if: runner.debug == '1'
        run: |
          echo "=== Env keys at this step ==="
          env | cut -d= -f1 | sort
          # Note: env prints keys only, not values, so secrets are not exposed
          echo "=== GITHUB_ENV contents ==="
          cat "$GITHUB_ENV" | cut -d= -f1   # keys only

      - name: Assert no stray secrets in env
        run: |
          # Fail if a known-secret-shaped key leaked into the default env
          if env | grep -qE '^(CF_API_TOKEN|R2_SECRET_KEY|JWT_SECRET)='; then
            echo "Secret key found in step environment without explicit scoping" && exit 1
          fi
```

---

## 6. Cloudflare Workers Wrangler Secret Precedence

Wrangler reads configuration in this order (later overrides earlier):

1. `wrangler.toml` `[vars]` (plaintext, committed)
2. `.dev.vars` (local dev only, gitignored)
3. `--env` flag selects the `[env.NAME]` stanza
4. Cloudflare dashboard secrets (encrypted at rest, injected at runtime)
5. GitHub Actions step `env:` → inherited by the `wrangler` process

Prefer dashboard secrets for runtime credentials.  Pass only deployment-time tokens
(e.g. `CLOUDFLARE_API_TOKEN`) via Actions step `env:`.

```yaml
      - name: Deploy with environment-specific vars
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          # Do NOT pass STRIPE_SECRET_KEY here — it lives in CF dashboard secrets
        run: pnpm wrangler deploy --env ${{ inputs.environment }}
```

---

## Anti-patterns

- Setting `secrets.*` at workflow-level `env:` — every job and step, including third-
  party actions, inherits it.
- Piping a secret through `echo` before masking: `echo "token=$SECRET"` prints the
  value before `add-mask` has a chance to intercept it.
- Relying on `env:` at job level for secrets that are only needed by one step — use
  step-level `env:` to minimise blast radius.
- Using `set -x` (xtrace) in shell steps — this logs every variable expansion,
  bypassing the masker for derived values.
- Writing secrets to `$GITHUB_OUTPUT` — outputs are visible to all downstream steps and
  to calling workflows in reusable workflow chains.

## Gotchas

- `::add-mask::` only masks the *exact string* provided; if the value appears URL-
  encoded or base64-encoded elsewhere in logs, those variants are not masked.
- Variables set via `$GITHUB_ENV` are available to subsequent steps but NOT to the
  current step's `run:` block or `with:` inputs.
- `$GITHUB_ENV` is a file on the runner; if an untrusted action writes to it before
  your step reads, it can inject arbitrary env vars (env injection attack).
- Secrets are masked in step logs but NOT in `$GITHUB_ENV` file snapshots uploaded as
  debug artifacts — never upload the runner's env file as an artifact.

## Verification

```bash
# Enable debug logging to inspect scope at each step (adds Runner.Debug secret)
gh secret set ACTIONS_STEP_DEBUG --body true -R {owner}/{repo}

# Re-run the failed job with debug logging
gh run rerun {run_id} --debug

# Review masked lines in the log
gh run view {run_id} --log | grep '\*\*\*'
```

## Related

- `github-actions-environment-file-delimiter-injection.md`
- `github-actions-dynamic-environment-variables-d1-config.md`
- `github-actions-secrets-management.md`
- `github-actions-security-hardening.md`
- `github-actions-step-debug-secret-exposure.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-secrets
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#masking-a-value-in-a-log
