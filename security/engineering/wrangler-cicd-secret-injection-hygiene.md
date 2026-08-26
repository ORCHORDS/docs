# Wrangler CI/CD Secret Injection Hygiene

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A developer rotates the production database password. They update the value in the GitHub Actions workflow as a repository secret, but they also notice that the old password appears in `wrangler.toml` under `[vars]` — checked into version control two years ago by a colleague who "just needed to get it working." The secret has been in git history ever since and is readable by anyone with repository access. Separately, a CI log from a failed `wrangler deploy` run shows the full Workers binding configuration, including secret names and their resolved values printed by a verbose debug flag left enabled.

---

## Context

Cloudflare Workers secrets are the platform's primary mechanism for injecting sensitive values — database passwords, API keys, signing secrets — at runtime without exposing them in source code or deployment artifacts. The Cloudflare platform distinguishes:

- **`[vars]`** in `wrangler.toml`: plaintext environment variables, stored in the Wrangler config file, committed to version control, visible to all repository contributors, and printed in `wrangler deploy` output.
- **`wrangler secret put`**: encrypted at rest in Cloudflare's infrastructure, never visible after upload (not even via API), injected at runtime as `env.SECRET_NAME`, not printed in deploy output.

The threat model for CI/CD secret injection covers:

1. **Plaintext secrets committed to version control** — hard to purge, accessible to any historical git clone.
2. **Secrets leaked in CI logs** — printed by debug flags, error messages, or overly verbose deployment tooling.
3. **Secrets in pull request previews** — Cloudflare Pages preview deployments and Worker preview environments inherit production secrets unless isolated.
4. **Unrotated bootstrap credentials** — the `CLOUDFLARE_API_TOKEN` used by CI to deploy must itself be a scoped, rotatable secret.
5. **Environment variable sprawl** — dozens of `[vars]` entries that should be secrets but were promoted as vars for convenience.

---

## Section 1 — Never Put Secrets in `wrangler.toml`

`wrangler.toml` is a configuration file committed to source control. It must never contain secret values.

```toml
# WRONG — do not do this
[vars]
DATABASE_URL = "postgres://admin:hunter2@db.example.com/prod"
STRIPE_SECRET_KEY = "sk_live_abc123"
JWT_SIGNING_SECRET = "my-secret-passphrase"
```

```toml
# CORRECT — vars are non-sensitive config; secrets are referenced by name only
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[vars]
LOG_LEVEL = "info"
ALLOWED_ORIGINS = "https://app.example.com,https://www.example.com"
MAX_UPLOAD_BYTES = "10485760"

# Secrets are NOT listed in wrangler.toml — they exist in Cloudflare's secret store
# and are available at runtime as env.DATABASE_URL, env.STRIPE_SECRET_KEY, etc.
```

Set secrets via the CLI before deployment:

```bash
# One-time setup — secrets are encrypted in Cloudflare's infrastructure
wrangler secret put DATABASE_URL
wrangler secret put STRIPE_SECRET_KEY --name my-worker --env production
wrangler secret put JWT_SIGNING_SECRET
```

List existing secrets (names only — values are never returned):

```bash
wrangler secret list --name my-worker --env production
```

---

## Section 2 — CI/CD Secret Injection via GitHub Actions

Inject secrets into `wrangler secret put` from GitHub Actions repository/environment secrets. Never write secrets to environment variables that may appear in logs.

```yaml
# .github/workflows/deploy.yml
name: Deploy Workers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production          # GitHub Actions environment with protection rules

    env:
      # Only non-sensitive config goes here
      CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - run: npm ci

      - name: Deploy Worker
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: npx wrangler deploy --env production

      - name: Sync Secrets
        # Only run when secrets have changed — guard with a separate workflow
        # or a dedicated secrets-sync job triggered by secret rotation events
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          STRIPE_SECRET_KEY: ${{ secrets.STRIPE_SECRET_KEY }}
          JWT_SIGNING_SECRET: ${{ secrets.JWT_SIGNING_SECRET }}
        run: |
          # Use --stdin to avoid secrets appearing in process list
          echo "$DATABASE_URL"      | npx wrangler secret put DATABASE_URL      --env production
          echo "$STRIPE_SECRET_KEY" | npx wrangler secret put STRIPE_SECRET_KEY --env production
          echo "$JWT_SIGNING_SECRET"| npx wrangler secret put JWT_SIGNING_SECRET --env production
```

Key practices in this workflow:

- Use a **GitHub Actions Environment** (`environment: production`) with required reviewers for production deployments.
- The `CLOUDFLARE_API_TOKEN` is a scoped Cloudflare API token — not an account-level Global API Key.
- Secrets are passed via stdin (`echo "$SECRET" | wrangler secret put`) rather than as command-line arguments, preventing secrets from appearing in `ps aux` output on the runner.
- The secrets sync step is separate from the deploy step. In a mature setup, decouple them: secrets are provisioned by a privileged "secrets sync" workflow; the deploy workflow does not need secrets values, only the API token.

---

## Section 3 — Scoped Cloudflare API Tokens for CI

The `CLOUDFLARE_API_TOKEN` used in CI must be scoped to the minimum necessary permissions. A Global API Key or an owner-level token is catastrophic if leaked.

Create a scoped token in the Cloudflare dashboard:

**Minimum permissions for `wrangler deploy`:**
- `Account > Workers Scripts > Edit`
- `Account > Workers KV Storage > Edit` (if KV bindings exist)
- `Account > D1 > Edit` (if D1 migrations run in CI)
- `Zone > Workers Routes > Edit` (if custom domains)

**Do NOT grant:**
- `Account > Account Settings > Edit`
- `Account > Access: Service Tokens > Edit`
- Any billing or DNS management permission

```bash
# Verify token scope before storing in CI
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/user/tokens/verify" | jq .result
```

Rotate the CI token every 90 days. Use Cloudflare's token expiry feature to enforce this automatically:

```bash
# Create a token expiring in 90 days via the Cloudflare API
# (Dashboard: Profile > API Tokens > Create Token > set Expiration)
```

---

## Section 4 — Preventing Secrets from Leaking in CI Logs

Misconfigured logging and debug flags are a common source of CI secret leaks.

```yaml
# WRONG — debug logging may print environment variables
- run: npx wrangler deploy --debug
```

```yaml
# CORRECT — no debug flag in production CI
- run: npx wrangler deploy --env production
```

Add secret masking to CI logs as a defence-in-depth measure. GitHub Actions automatically masks `${{ secrets.* }}` values, but custom tooling may not.

```yaml
# Explicitly mask a secret that might be computed or constructed at runtime
- name: Mask computed secret
  run: echo "::add-mask::$(echo $DATABASE_URL | base64)"
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

Scan CI workflow files for accidental secret exposure patterns with a pre-commit hook or CI lint step:

```bash
# Check for vars that look like secrets (common patterns)
grep -rn '\(password\|secret\|key\|token\|api_key\|auth\).*=' wrangler.toml | \
  grep -v '^\s*#' | \
  grep -v '\[vars\]' | \
  grep -v 'binding\s*=\|service\s*=\|database_id\s*=' && \
  echo "WARNING: possible secret in wrangler.toml" && exit 1 || true
```

---

## Section 5 — Preview Environment Secret Isolation

Cloudflare Workers environments (`--env staging`, `--env preview`) each have their own secret stores. Ensure preview environments use dedicated, low-privilege credentials — not production secrets.

```toml
# wrangler.toml
[env.staging]
name = "my-worker-staging"
vars = { LOG_LEVEL = "debug" }
# Secrets for staging are provisioned separately:
#   wrangler secret put DATABASE_URL --env staging
# Staging DB_URL points to a staging database, not production

[env.production]
name = "my-worker"
vars = { LOG_LEVEL = "warn" }
# Secrets for production provisioned via production deployment pipeline
```

For Cloudflare Pages preview deployments, disable secret inheritance for untrusted branches:

```yaml
# .github/workflows/preview.yml
- name: Deploy Preview (no production secrets)
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PREVIEW_ONLY }}
  run: npx wrangler pages deploy ./dist --project-name my-project --branch ${{ github.head_ref }}
  # Preview environment tokens are scoped to Pages preview only, not production Workers
```

Never provision `STRIPE_SECRET_KEY` (live keys) to preview environments. Use Stripe test keys in staging:

```bash
wrangler secret put STRIPE_SECRET_KEY --env staging
# (Enter sk_test_... not sk_live_...)
```

---

## Section 6 — Detecting and Remediating Committed Secrets

If a secret has been committed to git history, it must be treated as compromised and rotated immediately. History rewriting does not help if the repository has been cloned.

**Immediate response:**
1. Rotate the compromised credential with the provider (Stripe, DB, etc.) before anything else.
2. Revoke the old credential.
3. Update the new value in Cloudflare Secrets: `wrangler secret put STRIPE_SECRET_KEY`.
4. Optionally purge git history using `git filter-repo` (see `git-history-secret-removal.md`).

**Prevention — Gitleaks pre-commit hook:**

```bash
# Install gitleaks
brew install gitleaks  # macOS
# or: https://github.com/gitleaks/gitleaks/releases

# Add to .git/hooks/pre-commit (or use pre-commit framework)
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/sh
gitleaks protect --staged --redact --exit-code 1 --config .gitleaks.toml
EOF
chmod +x .git/hooks/pre-commit
```

```toml
# .gitleaks.toml
title = "gitleaks config"

[extend]
useDefault = true

[[rules]]
id = "cloudflare-api-token"
description = "Cloudflare API Token"
regex = '''(?i)cloudflare[_\-]?api[_\-]?token['":\s]+=?\s*'"'''
tags = ["cloudflare", "api-token"]

[[rules]]
id = "wrangler-var-secret"
description = "Secret-looking value in wrangler.toml [vars]"
regex = '''(?i)(password|secret|key|token)\s*=\s*["'][^$\{][^"']{8,}["']'''
paths = ["wrangler.toml", "wrangler.*.toml"]
tags = ["wrangler", "config"]

[allowlist]
paths = [
  ".gitleaks.toml",
  "tests/fixtures/**",
]
regexes = [
  "sk_test_",         # Stripe test keys are intentionally in test fixtures
]
```

Run Gitleaks in CI as a gate:

```yaml
# .github/workflows/security.yml
- name: Gitleaks Secret Scan
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    GITLEAKS_CONFIG: .gitleaks.toml
    GITLEAKS_ENABLE_COMMENTS: true  # Annotate PRs with findings
```

---

## Anti-patterns

- **Committing `wrangler.toml` with `[vars]` containing real secret values** and expecting obfuscation ("it's in a private repo") to protect them. Private repos are not attack-proof; insiders, CI tokens, and git leaks all expose them.
- **Using the Cloudflare Global API Key as the CI token.** The Global API Key cannot be scoped, cannot expire independently, and compromising it gives an attacker full account control.
- **`wrangler secret put --value $SECRET` on the command line.** The secret value appears in shell history and in `ps aux` output on the runner. Always use stdin or a file.
- **Reusing production secrets in preview/staging environments.** A vulnerability in a preview deployment (e.g., from an untrusted PR) could exfiltrate production credentials.
- **Never rotating the CI API token.** Tokens with no expiry that are never rotated accumulate risk. Set expiry and enforce rotation cadence.

---

## Gotchas

- `wrangler secret put` reads from stdin when piped. If you run it interactively, it prompts. In CI, always pipe the value: `echo "$VALUE" | wrangler secret put KEY`.
- `wrangler secret list` returns only secret *names*, not values. There is no API to retrieve a secret value after it has been set. This is intentional. Store the canonical values in a secrets manager (1Password Secrets Automation, HashiCorp Vault, AWS Secrets Manager) as your source of truth.
- Cloudflare Workers environments are scoped to a `wrangler.toml` environment stanza. A secret set for `--env production` is **not** automatically available to `--env staging` or to the top-level (default) environment. Each environment has its own isolated secret store.
- GitHub Actions does not mask secrets in artifact uploads or in `actions/upload-artifact`. Never upload log files that may contain secret values.
- Secrets provisioned via `wrangler secret put` take effect immediately on new requests; there is no deployment step required. Secrets are not included in the deployed Worker bundle — they are injected at request time by the Cloudflare runtime.

---

## Verification

```bash
# Confirm no secrets in wrangler.toml
grep -Ei '(password|secret_key|api_key|auth_token|signing_secret)\s*=' wrangler.toml && \
  echo "FAIL: secret-looking value found in wrangler.toml" && exit 1 || \
  echo "PASS: no secrets in wrangler.toml"

# Confirm all expected secrets are provisioned (names, not values)
wrangler secret list --env production | jq -r '.[].name' | sort > /tmp/actual-secrets.txt
diff <(sort <<'EOF'
DATABASE_URL
STRIPE_SECRET_KEY
JWT_SIGNING_SECRET
EOF
) /tmp/actual-secrets.txt && echo "PASS: all secrets provisioned" || echo "FAIL: secret mismatch"

# Gitleaks scan of entire repo history
gitleaks detect --source . --config .gitleaks.toml --verbose
```

---

## Related

- `git-history-secret-removal.md`
- `secrets-detection-pre-commit.md`
- `gitleaks-cloudflare-webhook.md`
- `api-key-rotation-workers-kv-secrets.md`
- `api-key-rotation-zero-downtime.md`
- `secrets-encryption-at-rest.md`

---

## Sources

- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- Wrangler CLI secret commands: https://developers.cloudflare.com/workers/wrangler/commands/#secret
- Cloudflare API Token scoping: https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
- Gitleaks: https://github.com/gitleaks/gitleaks
- GitHub Actions secret masking: https://docs.github.com/en/actions/security-guides/encrypted-secrets
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
