# GitHub Actions Workers Secret Rotation Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

API keys and service credentials used by Cloudflare Workers expire or must be rotated on a schedule for compliance (SOC 2, PCI-DSS). Doing this manually is error-prone and creates outage windows. You need a workflow that generates a new secret, writes it to Cloudflare Workers Secrets and GitHub Actions Secrets simultaneously, then verifies the Worker is healthy before invalidating the old credential.

## Context

Cloudflare Workers Secrets are encrypted at rest and injected into the Worker runtime as environment variables. GitHub Actions Secrets hold the same values for use in CI. The two stores must stay in sync — a rotation that updates only one side breaks either the live Worker or CI pipelines that run tests against the same API. Wrangler CLI can write secrets non-interactively via `wrangler secret put --stdin`. GitHub's REST API (`PUT /repos/{owner}/{repo}/actions/secrets/{name}`) can update Actions Secrets after encrypting the value with the repo's public key using `libsodium`.

---

## 1. Scheduled Rotation Workflow

```yaml
# .github/workflows/rotate-secrets.yml
name: Rotate Worker Secrets

on:
  schedule:
    - cron: '0 3 1 * *'   # 03:00 UTC on the 1st of every month
  workflow_dispatch:
    inputs:
      secret_name:
        description: 'Secret to rotate (e.g. STRIPE_API_KEY)'
        required: true
        type: string

permissions:
  contents: read

jobs:
  rotate:
    runs-on: ubuntu-latest
    environment: production          # requires manual approval gate
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      GH_TOKEN: ${{ secrets.BOT_PAT }}   # fine-grained PAT: secrets:write on this repo
      WORKER_NAME: my-api-worker
```

## 2. Generate a New Credential

```yaml
    steps:
      - uses: actions/checkout@v4

      - name: Generate new API key
        id: gen
        run: |
          # Replace this block with your provider's key-generation API call.
          # Example: rotate a generic shared secret with openssl.
          NEW_SECRET=$(openssl rand -hex 32)
          echo "new_secret=$NEW_SECRET" >> "$GITHUB_OUTPUT"
          # Never echo the value into unmasked logs.
          echo "::add-mask::$NEW_SECRET"

      - name: Call provider rotation API (example: custom HMAC key)
        id: provider
        env:
          ADMIN_TOKEN: ${{ secrets.ADMIN_API_TOKEN }}
        run: |
          # Stripe example (adapt for your provider):
          # NEW_KEY=$(curl -sf -X POST https://api.stripe.com/v1/restricted_keys \
          #   -u "$ADMIN_TOKEN:" \
          #   -d "name=workers-$(date +%Y%m)" \
          #   | jq -r '.secret')
          # echo "new_secret=$NEW_KEY" >> "$GITHUB_OUTPUT"
          # echo "::add-mask::$NEW_KEY"
          echo "Placeholder: replace with real provider call"
```

## 3. Write the New Secret to Cloudflare Workers

```yaml
      - uses: actions/setup-node@v4
        with: { node-version: '22' }

      - run: npm install -g wrangler@latest

      - name: Push secret to Cloudflare Worker
        run: |
          printf '%s' "${{ steps.gen.outputs.new_secret }}" \
            | wrangler secret put "${{ github.event.inputs.secret_name || 'API_SECRET' }}" \
              --name "$WORKER_NAME"
```

## 4. Write the New Secret to GitHub Actions Secrets

```typescript
// scripts/update-gh-secret.ts
// Run with: npx tsx scripts/update-gh-secret.ts <SECRET_NAME> <VALUE>
import { execSync } from 'child_process';
import * as sodium from 'libsodium-wrappers';

const [, , secretName, secretValue] = process.argv;
const owner = process.env.GITHUB_REPOSITORY_OWNER!;
const repo  = process.env.GITHUB_REPOSITORY!.split('/')[1];
const token = process.env.GH_TOKEN!;

await sodium.ready;

async function getPublicKey() {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/secrets/public-key`,
    { headers: { Authorization: `Bearer ${token}`, 'X-GitHub-Api-Version': '2022-11-28' } },
  );
  return res.json() as Promise<{ key_id: string; key: string }>;
}

async function putSecret(keyId: string, encryptedValue: string) {
  await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/secrets/${secretName}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({ encrypted_value: encryptedValue, key_id: keyId }),
    },
  );
}

const { key_id, key } = await getPublicKey();
const keyBytes    = sodium.from_base64(key, sodium.base64_variants.ORIGINAL);
const secretBytes = sodium.from_string(secretValue);
const encrypted   = sodium.crypto_box_seal(secretBytes, keyBytes);
await putSecret(key_id, sodium.to_base64(encrypted, sodium.base64_variants.ORIGINAL));
console.log(`Updated GitHub Actions secret: ${secretName}`);
```

```yaml
      - name: Push secret to GitHub Actions
        run: |
          npx tsx scripts/update-gh-secret.ts \
            "${{ github.event.inputs.secret_name || 'API_SECRET' }}" \
            "${{ steps.gen.outputs.new_secret }}"
```

## 5. Verify Worker Health and Revoke Old Credential

```yaml
      - name: Wait for Worker deployment to pick up new secret
        run: sleep 15

      - name: Smoke test with new secret
        run: |
          STATUS=$(curl -sf -o /dev/null -w '%{http_code}' \
            -H "X-Api-Key: ${{ steps.gen.outputs.new_secret }}" \
            "https://$WORKER_NAME.workers.dev/health")
          if [ "$STATUS" != "200" ]; then
            echo "Smoke test failed (HTTP $STATUS) — NOT revoking old credential"
            exit 1
          fi
          echo "Smoke test passed — proceeding to revoke old credential"

      - name: Revoke old credential at provider
        if: success()
        env:
          ADMIN_TOKEN: ${{ secrets.ADMIN_API_TOKEN }}
          OLD_KEY_ID: ${{ secrets.OLD_KEY_ID }}
        run: |
          # Provider-specific revocation call goes here.
          # curl -sf -X DELETE "https://api.example.com/keys/$OLD_KEY_ID" ...
          echo "Old credential revoked"

      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v2
        with:
          webhook: ${{ secrets.SLACK_WEBHOOK_URL }}
          webhook-type: incoming-webhook
          payload: '{"text":"Secret rotation FAILED for ${{ env.WORKER_NAME }} — old credential still active. Check run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"}'
```

---

## Anti-patterns

- Rotating Cloudflare Workers Secrets without updating GitHub Actions Secrets — integration test jobs will start failing with 401s immediately after the Worker restart.
- Revoking the old credential before verifying the new one works — causes an outage window if the Worker failed to restart with the new secret.
- Storing the new secret value in `GITHUB_OUTPUT` without masking it — output variables are written to a file on disk and visible in workflow logs unless `::add-mask::` is used.
- Using a personal PAT with broad `repo` scope for the rotation bot — use a fine-grained PAT scoped to `secrets: write` on the single repository.

## Gotchas

- Cloudflare Workers do not hot-reload secrets; a new deployment (or a manual redeploy) is required for secret changes to take effect. `wrangler secret put` triggers a redeployment automatically.
- The `libsodium-wrappers` package requires `await sodium.ready` before any crypto call — forgetting this causes silent failures on the `crypto_box_seal` call.
- GitHub environment secrets (`/environments/{env}/secrets`) use a different API path and a separate public key endpoint from repository secrets — check which scope your secrets are stored under.
- Scheduled `workflow_dispatch` triggers only fire if the workflow file exists on the default branch.

## Verification

```bash
# Confirm secret is set in Cloudflare (lists secret names only, not values)
wrangler secret list --name my-api-worker

# Confirm secret is set in GitHub
gh secret list --repo owner/repo
```

The rotation workflow should appear in the Environments `production` required workflows list so that the approval gate is enforced even on scheduled runs.

## Related

- `github-actions-secrets-management.md`
- `github-actions-environment-secrets-vs-repo-secrets-workers.md`
- `github-apps-private-key-rotation-ci.md`
- `github-actions-oidc-cloudflare-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://docs.github.com/en/rest/actions/secrets
- https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- https://libsodium.gitbook.io/doc/public-key_cryptography/sealed_boxes
