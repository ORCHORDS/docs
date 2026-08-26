# Automating Cloudflare Access Service Token Rotation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Access service tokens (client ID + client secret) used by machine-to-machine services must be rotated periodically. Manual rotation causes downtime if the old token is revoked before the consumer is updated.

## Context

The rotation sequence must be:
1. Create new token
2. Deliver new credentials to the consuming service (Workers Secret via API)
3. Verify the new token works end-to-end
4. Revoke the old token
5. Write the audit record

A GitHub Actions workflow running on OIDC handles steps 1-5 monthly. All events are logged to a D1 table for compliance.

Prerequisites:
- Cloudflare API token with `Access: Service Tokens:Edit` permission
- Target Worker already deployed (the consumer)
- D1 database for audit logs
- GitHub OIDC configured for Cloudflare

---

## D1 Audit Schema

```sql
CREATE TABLE IF NOT EXISTS token_rotations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  service      TEXT NOT NULL,
  old_token_id TEXT NOT NULL,
  new_token_id TEXT NOT NULL,
  rotated_at   TEXT NOT NULL DEFAULT (datetime('now')),
  rotated_by   TEXT NOT NULL,
  verified     INTEGER NOT NULL DEFAULT 0   -- 0=false, 1=true
);

CREATE INDEX idx_token_rotations_service ON token_rotations(service, rotated_at);
```

---

## GitHub Actions Rotation Workflow

```yaml
# .github/workflows/rotate-access-tokens.yml
name: Rotate Cloudflare Access Service Tokens

on:
  schedule:
    - cron: '0 4 1 * *'   # 04:00 UTC, first of every month
  workflow_dispatch:
    inputs:
      service:
        description: 'Service name to rotate'
        required: true
        type: string

permissions:
  id-token: write
  contents: read

jobs:
  rotate:
    name: Rotate token for ${{ inputs.service || 'all' }}
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: actions/checkout@v4

      - name: Exchange OIDC token for Cloudflare API token
        id: cf-auth
        uses: cloudflare/cloudflare-github-action@v1
        with:
          audience: 'https://cloudflare.com'

      - name: Rotate service token
        id: rotate
        env:
          CF_API_TOKEN:  ${{ steps.cf-auth.outputs.api-token }}
          CF_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          SERVICE_NAME:  ${{ inputs.service || 'api-internal' }}
          OLD_TOKEN_ID:  ${{ vars.ACCESS_TOKEN_ID }}
          WORKER_SCRIPT: ${{ vars.CONSUMER_WORKER_SCRIPT }}
          D1_DB_ID:      ${{ vars.D1_AUDIT_DB_ID }}
        run: |
          set -euo pipefail

          # 1. Create new Access service token
          NEW_TOKEN=$(curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/service_tokens" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"${SERVICE_NAME}-$(date +%Y%m)\"}"
          )

          NEW_TOKEN_ID=$(echo "$NEW_TOKEN"     | jq -r '.result.id')
          NEW_CLIENT_ID=$(echo "$NEW_TOKEN"    | jq -r '.result.client_id')
          NEW_CLIENT_SECRET=$(echo "$NEW_TOKEN" | jq -r '.result.client_secret')

          echo "new_token_id=${NEW_TOKEN_ID}"         >> $GITHUB_OUTPUT
          echo "new_client_id=${NEW_CLIENT_ID}"       >> $GITHUB_OUTPUT
          # Never echo the secret; pass via env to next steps
          echo "NEW_CLIENT_SECRET=${NEW_CLIENT_SECRET}" >> $GITHUB_ENV

          # 2. Update the consumer Worker secret with new credentials
          echo -n "${NEW_CLIENT_ID}" | \
            wrangler secret put ACCESS_CLIENT_ID --name "${WORKER_SCRIPT}"
          echo -n "${NEW_CLIENT_SECRET}" | \
            wrangler secret put ACCESS_CLIENT_SECRET --name "${WORKER_SCRIPT}"

          # 3. Verify new token works
          HTTP_STATUS=$(curl -so /dev/null -w '%{http_code}' \
            -H "CF-Access-Client-Id: ${NEW_CLIENT_ID}" \
            -H "CF-Access-Client-Secret: ${NEW_CLIENT_SECRET}" \
            "${{ vars.SERVICE_HEALTH_URL }}")

          if [[ "$HTTP_STATUS" != "200" ]]; then
            echo "Verification failed (HTTP ${HTTP_STATUS}), aborting — old token unchanged"
            exit 1
          fi
          echo "verified=true" >> $GITHUB_OUTPUT

          # 4. Revoke old token
          curl -sf -X DELETE \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/service_tokens/${OLD_TOKEN_ID}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}"

          # 5. Write audit record to D1
          curl -sf -X POST \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{ \"sql\": \"INSERT INTO token_rotations(service,old_token_id,new_token_id,rotated_by,verified) VALUES(?,?,?,?,1)\", \
                  \"params\": [\"${SERVICE_NAME}\",\"${OLD_TOKEN_ID}\",\"${NEW_TOKEN_ID}\",\"github-actions\"] }"

      - name: Update old token ID secret in GitHub
        uses: actions/github-script@v7
        with:
          script: |
            const { Octokit } = require('@octokit/rest');
            // Update the repository variable so next rotation knows the current token ID
            await github.rest.actions.updateRepoVariable({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              name:  'ACCESS_TOKEN_ID',
              value: '${{ steps.rotate.outputs.new_token_id }}',
            });
```

---

## Worker: Consuming the Rotated Credentials

```typescript
// src/index.ts — consumer Worker reads secrets at runtime
export interface Env {
  ACCESS_CLIENT_ID:     string;
  ACCESS_CLIENT_SECRET: string;
  UPSTREAM_URL:         string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = new Request(env.UPSTREAM_URL + new URL(request.url).pathname, request);
    upstream.headers.set('CF-Access-Client-Id',     env.ACCESS_CLIENT_ID);
    upstream.headers.set('CF-Access-Client-Secret', env.ACCESS_CLIENT_SECRET);
    return fetch(upstream);
  },
};
```

---

## Verification

```bash
# Query audit log for last 5 rotations
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DB_ID}/query" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT service, old_token_id, new_token_id, rotated_at, verified FROM token_rotations ORDER BY rotated_at DESC LIMIT 5"}'

# Confirm Worker has new secret (secret value is masked, but name confirms presence)
wrangler secret list --name api-consumer
```

---

## Anti-patterns

- **Revoking the old token before verifying the new one**: always verify first. If the health check fails, skip revocation and page the on-call engineer.
- **Storing `client_secret` in GitHub Secrets or logs**: the secret is returned only once at creation time. Write it immediately to Worker Secrets via `wrangler` and never log it.
- **Using the same `name` for the new token**: Cloudflare allows duplicate names, which makes audit logs ambiguous. Append `YYYYMM` to the name.
- **Not updating `ACCESS_TOKEN_ID` repo variable**: the next rotation run needs to know which token to revoke.

## Gotchas

- `client_secret` is returned only at token creation (`POST`). It cannot be retrieved again from the API. If the Worker secret update fails mid-workflow, you must re-create the token.
- Access service tokens have a configurable expiry. Set `duration` to `"8760h"` (1 year) if you rotate monthly, to avoid the token expiring between rotations.
- OIDC → Cloudflare API token must include `Access: Service Tokens:Edit` scope explicitly; the generic `All accounts` token does not include it by default.

## Related

- `terraform-workers-secret-rotation-automation.md`
- `cloudflare-access-policy-management.md`
- `cloudflare-workers-zero-downtime-migration-strategy.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- https://developers.cloudflare.com/api/operations/access-service-tokens-create-a-service-token
- https://developers.cloudflare.com/workers/configuration/secrets/
