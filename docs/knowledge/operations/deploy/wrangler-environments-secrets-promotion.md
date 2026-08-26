# Promoting Secrets Safely Across Wrangler Environments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You maintain `staging` and `production` Cloudflare Workers environments and need a repeatable, auditable process for promoting secrets — API keys, database passwords, OAuth tokens — from staging to production. Ad-hoc copy-paste leads to drift, stale secrets, and accidental commits of sensitive values into `wrangler.toml`.

---

## Context
Wrangler secrets are stored encrypted in Cloudflare's platform and are never exposed in plain text after upload; they appear as `"*******"` in the dashboard and API. Each environment (`staging`, `production`) holds its own independent secret store, so a secret must be explicitly set per environment. The Cloudflare API allows listing and setting secrets programmatically, enabling a CI pipeline to enforce an approval gate before production promotion. Secrets must never appear in `wrangler.toml`, `.env` files checked into git, or CI logs.

---

## Section 1 — Wrangler Configuration (environments, no secrets)

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[env.staging]
name = "my-worker-staging"
route = { pattern = "staging.example.com/*", zone_name = "example.com" }

[env.production]
name = "my-worker-production"
route = { pattern = "example.com/*", zone_name = "example.com" }

# NEVER add [secrets] or vars with sensitive values here.
# Use `wrangler secret put` or the Cloudflare API instead.
```

---

## Section 2 — Manual Secret Operations and CI Promotion Script

### Day-to-day CLI commands

```bash
# Set a secret on staging
echo "super-secret-value" | wrangler secret put DATABASE_URL --env staging

# List secrets (names only, values are never returned)
wrangler secret list --env staging
wrangler secret list --env production

# Delete a secret
wrangler secret delete OLD_API_KEY --env staging
```

### CI promotion script (staging → production)

```bash
#!/usr/bin/env bash
# promote-secrets.sh
# Copies secrets whose names exist in staging but not production.
# Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, WORKER_NAME_STAGING,
#           WORKER_NAME_PRODUCTION, and the plain-text secret values in
#           environment variables named SECRET_<NAME>.
set -euo pipefail

CF_API="https://api.cloudflare.com/client/v4"
HEADERS=(-H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" -H "Content-Type: application/json")

get_secret_names() {
  local worker_name="$1"
  curl -sf "${CF_API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${worker_name}/secrets" \
    "${HEADERS[@]}" | jq -r '.result[].name'
}

put_secret() {
  local worker_name="$1" name="$2" value="$3"
  curl -sf -X PUT \
    "${CF_API}/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${worker_name}/secrets" \
    "${HEADERS[@]}" \
    -d "{\"name\":\"${name}\",\"text\":\"${value}\",\"type\":\"secret_text\"}" \
    | jq '.success'
}

echo "Fetching staging secret names..."
STAGING_SECRETS=$(get_secret_names "${WORKER_NAME_STAGING}")
PROD_SECRETS=$(get_secret_names "${WORKER_NAME_PRODUCTION}")

echo "Staging secrets: ${STAGING_SECRETS}"
echo "Production secrets: ${PROD_SECRETS}"

for secret_name in ${STAGING_SECRETS}; do
  var_name="SECRET_${secret_name}"
  if [[ -z "${!var_name:-}" ]]; then
    echo "SKIP ${secret_name}: no value in env var ${var_name}"
    continue
  fi
  echo "Promoting ${secret_name} to production..."
  put_secret "${WORKER_NAME_PRODUCTION}" "${secret_name}" "${!var_name}"
done

echo "Secret promotion complete."
```

### Secret rotation procedure

```bash
#!/usr/bin/env bash
# rotate-secret.sh <SECRET_NAME> <NEW_VALUE> [--env staging|production]
set -euo pipefail
SECRET_NAME="${1:?secret name required}"
NEW_VALUE="${2:?new value required}"
ENV_FLAG="${3:---env production}"

# 1. Write new value to both environments atomically
echo "${NEW_VALUE}" | wrangler secret put "${SECRET_NAME}" --env staging
echo "${NEW_VALUE}" | wrangler secret put "${SECRET_NAME}" ${ENV_FLAG}

# 2. Verify the secret exists
wrangler secret list --env staging | grep "${SECRET_NAME}"
wrangler secret list --env production | grep "${SECRET_NAME}"

echo "Rotation complete. Revoke the old secret in the upstream provider."
```

---

## Section 3 — GitHub Actions CI Pipeline with Approval Gate

```yaml
# .github/workflows/promote-secrets.yml
name: Promote Secrets staging → production

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type YES to promote secrets to production'
        required: true

jobs:
  promote:
    runs-on: ubuntu-latest
    environment: production   # GitHub Environment with required reviewers
    if: ${{ github.event.inputs.confirm == 'YES' }}
    steps:
      - uses: actions/checkout@v4

      - name: Install wrangler
        run: npm install -g wrangler

      - name: Verify staging secrets list
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: wrangler secret list --env staging

      - name: Promote secrets to production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          WORKER_NAME_STAGING: my-worker-staging
          WORKER_NAME_PRODUCTION: my-worker-production
          # Plain-text values come from GitHub Actions secrets — never echoed
          SECRET_DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
          SECRET_API_KEY: ${{ secrets.PROD_API_KEY }}
        run: bash promote-secrets.sh
```

---

## Anti-patterns
- **Secrets in `wrangler.toml` `[vars]`** — `[vars]` values are plain text and committed to git; use `wrangler secret put` exclusively for sensitive data.
- **Sharing one secret store across environments** — If staging and production share the same secret, a staging compromise exposes production; always use separate, scoped secrets.
- **Logging secret values in CI** — Even a stray `echo` or `set -x` can write secrets to the CI log; mask all secret env vars in GitHub Actions and never print them.
- **Manual copy-paste promotion** — Human error introduces typos, missed secrets, and no audit trail; automate promotion via the API with an approval gate.

---

## Gotchas
- `wrangler secret list` returns only secret *names*, never values — you cannot retrieve a secret once uploaded; store originals in a vault (e.g., 1Password, AWS Secrets Manager).
- The Cloudflare API `PUT /secrets` endpoint replaces the value atomically; in-flight requests using the old value will complete before the new value takes effect.
- Worker deployments do not automatically pick up new secrets; the Worker must be redeployed (or the isolate recycled) for runtime reads to reflect the change.
- `--env` in wrangler CLI maps to the `[env.<name>]` block, not to the deployed worker name — ensure `name` inside the env block matches what the promotion script targets.

---

## Verification

```bash
# List secrets on each environment
wrangler secret list --env staging
wrangler secret list --env production

# Confirm secret is available at runtime (returns masked value via API)
curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-worker-production/secrets" \
  | jq '.result[] | {name, type}'

# Smoke test: Worker endpoint that echoes a non-sensitive derived value
curl -s https://my-worker-production.workers.dev/health | jq '.db_connected'
```

---

## Related
- `workers-deploy-on-git-tag-actions.md`
- `workers-gradual-rollout-kv-percentage.md`

---

## Sources
- Cloudflare Workers Secrets documentation — https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare API Secrets endpoint — https://developers.cloudflare.com/api/operations/worker-secrets-list-secrets
- GitHub Actions Environments — https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
