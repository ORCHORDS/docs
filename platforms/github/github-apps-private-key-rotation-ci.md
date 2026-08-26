# GitHub App Private Key Rotation in CI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
GitHub App private keys do not expire automatically; when a key is compromised or reaches your security policy's maximum age, you need a zero-downtime rotation workflow that generates a new key, distributes it to dependent secret stores, and revokes the old key — all from CI.

## Context
GitHub Apps authenticate with a PEM-encoded RSA private key to mint installation access tokens. Rotating the key requires creating a new key via the GitHub API, propagating the new PEM to every consumer (GitHub Actions secrets, AWS Secrets Manager, HashiCorp Vault), verifying the new key works, then revoking the old one. Orchestrating this sequence in GitHub Actions prevents key sprawl and gives you an auditable rotation trail in the Actions log.

## Key Rotation Workflow

```yaml
# .github/workflows/rotate-app-key.yml
name: Rotate GitHub App Private Key

on:
  workflow_dispatch:
    inputs:
      app_id:
        description: 'GitHub App numeric ID'
        required: true
        type: string
      dry_run:
        description: 'Dry-run only — generate and verify but do not revoke old key'
        required: false
        default: 'false'
        type: choice
        options: ['true', 'false']

permissions:
  contents: read
  id-token: write     # for AWS OIDC / Vault auth

concurrency:
  group: key-rotation-${{ inputs.app_id }}
  cancel-in-progress: false   # rotation must never be interrupted mid-flight
```

## Generating the New Key

```yaml
jobs:
  rotate:
    runs-on: ubuntu-24.04
    environment: key-rotation
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate with a bootstrap PAT that has app management scope
        env:
          GH_TOKEN: ${{ secrets.APP_MANAGER_PAT }}
        run: echo "GH_TOKEN=${GH_TOKEN}" >> "$GITHUB_ENV"

      - name: Create new private key
        id: new-key
        env:
          APP_ID: ${{ inputs.app_id }}
        run: |
          RESPONSE=$(gh api \
            -X POST \
            /apps/${APP_ID}/keys \
            --jq '{key_id: .id, pem: .pem}')
          KEY_ID=$(echo "$RESPONSE" | jq -r '.key_id')
          PEM=$(echo "$RESPONSE" | jq -r '.pem')
          echo "key_id=${KEY_ID}" >> "$GITHUB_OUTPUT"
          # Do NOT echo the PEM to the log
          printf '%s' "${PEM}" > /tmp/new_key.pem
          echo "pem_path=/tmp/new_key.pem" >> "$GITHUB_OUTPUT"
```

## Verifying the New Key

Before revoking the old key, verify the new PEM can mint an installation token:

```typescript
// scripts/verify-app-key.ts
import { createSign } from 'node:crypto';
import { readFileSync } from 'node:fs';

const appId = process.env.APP_ID!;
const installationId = process.env.INSTALLATION_ID!;
const pemPath = process.env.PEM_PATH!;
const pem = readFileSync(pemPath, 'utf8');

const now = Math.floor(Date.now() / 1000);
const payload = Buffer.from(
  JSON.stringify({ iat: now - 60, exp: now + 600, iss: appId }),
).toString('base64url');

const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
const unsigned = `${header}.${payload}`;
const signer = createSign('RSA-SHA256');
signer.update(unsigned);
const sig = signer.sign(pem, 'base64url');
const jwt = `${unsigned}.${sig}`;

const res = await fetch(
  `https://api.github.com/app/installations/${installationId}/access_tokens`,
  {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${jwt}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  },
);

if (!res.ok) {
  console.error(await res.text());
  process.exit(1);
}
console.log('New key verified — installation token minted successfully.');
```

```yaml
      - name: Verify new key mints installation token
        env:
          APP_ID: ${{ inputs.app_id }}
          INSTALLATION_ID: ${{ vars.APP_INSTALLATION_ID }}
          PEM_PATH: /tmp/new_key.pem
        run: pnpm tsx scripts/verify-app-key.ts
```

## Distributing the New Key to Secret Stores

```yaml
      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_ROTATION_ROLE_ARN }}
          aws-region: us-east-1

      - name: Update AWS Secrets Manager
        env:
          SECRET_ARN: ${{ vars.APP_PEM_SECRET_ARN }}
        run: |
          aws secretsmanager put-secret-value \
            --secret-id "${SECRET_ARN}" \
            --secret-string "$(cat /tmp/new_key.pem)"

      - name: Update GitHub Actions org secret
        env:
          GH_TOKEN: ${{ secrets.APP_MANAGER_PAT }}
          ORG: ${{ github.repository_owner }}
          SECRET_NAME: APP_PRIVATE_KEY
        run: |
          gh secret set "${SECRET_NAME}" \
            --org "${ORG}" \
            --visibility all \
            --body "$(cat /tmp/new_key.pem)"
```

## Revoking the Old Key

```yaml
      - name: List old key IDs
        id: old-keys
        env:
          APP_ID: ${{ inputs.app_id }}
          NEW_KEY_ID: ${{ steps.new-key.outputs.key_id }}
        run: |
          OLD=$(gh api /apps/${APP_ID}/keys \
            --jq "[.[] | select(.id != ($NEW_KEY_ID | tonumber)) | .id]")
          echo "ids=${OLD}" >> "$GITHUB_OUTPUT"

      - name: Revoke old keys
        if: inputs.dry_run == 'false'
        env:
          APP_ID: ${{ inputs.app_id }}
          OLD_KEY_IDS: ${{ steps.old-keys.outputs.ids }}
        run: |
          for KEY_ID in $(echo "${OLD_KEY_IDS}" | jq -r '.[]'); do
            echo "Revoking key ${KEY_ID}"
            gh api -X DELETE /apps/${APP_ID}/keys/${KEY_ID}
          done

      - name: Cleanup PEM from runner
        if: always()
        run: shred -u /tmp/new_key.pem || rm -f /tmp/new_key.pem
```

## Scheduling Proactive Rotation

```yaml
# .github/workflows/scheduled-key-rotation.yml
on:
  schedule:
    - cron: '0 3 1 */3 *'   # first of every third month at 03:00 UTC
  workflow_dispatch: {}

jobs:
  trigger-rotation:
    uses: ./.github/workflows/rotate-app-key.yml
    with:
      app_id: ${{ vars.PRIMARY_APP_ID }}
      dry_run: 'false'
    secrets: inherit
```

## Anti-patterns
- Echoing the PEM to `$GITHUB_OUTPUT` or `GITHUB_ENV` — both are captured in the Actions log; write the PEM only to an ephemeral file under `/tmp/`.
- Revoking the old key before verifying the new one works — always verify first.
- Using a PAT with `admin:org` scope as the bootstrap credential — scope it to `admin:org_hook` and the specific app management permissions only.
- Storing the bootstrap PAT in the same secret store as the app PEM — compromise of one should not immediately compromise the other.
- Running rotation inside a matrix or parallel job that can be cancelled mid-flight — use `concurrency: cancel-in-progress: false`.

## Gotchas
- GitHub Apps can have at most 10 active private keys simultaneously; the revocation step must run even in failure paths or you will exhaust the key limit.
- `gh api /apps/{app_id}/keys` requires the `Authorization: Bearer <JWT>` header signed with an existing valid key, not the new one — use a bootstrap PAT instead.
- The `shred` command is not available on macOS runners; use `rm -P` on macOS or `rm -f` as a cross-platform fallback.
- AWS Secrets Manager `put-secret-value` does not delete old versions; set a `DeletionPolicy` rotation window or the secret history grows unboundedly.

## Verification
1. Trigger `rotate-app-key.yml` with `dry_run: true` and confirm the new key is generated and verified without revoking old keys.
2. Trigger again with `dry_run: false` and confirm the old key IDs are listed and revoked.
3. In the GitHub App settings UI, verify only one active key remains.
4. Confirm the updated org secret is accessible from a downstream workflow by running a test job that mints an installation token.

## Related
- `github-apps-installation-tokens.md`
- `github-apps-vs-pat.md`
- `github-actions-secrets-management.md`
- `github-fine-grained-personal-access-tokens.md`

## Sources
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps
- https://docs.github.com/en/rest/apps/apps#create-a-github-app-from-a-manifest
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions
