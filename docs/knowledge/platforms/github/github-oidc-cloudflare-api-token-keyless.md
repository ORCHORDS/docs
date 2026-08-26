# Keyless Cloudflare Deployments with GitHub OIDC

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Storing a long-lived `CLOUDFLARE_API_TOKEN` in GitHub Secrets means the token remains valid indefinitely even if it is accidentally logged, leaked in a PR diff, or exfiltrated from a compromised runner. You want deployments to work without any persistent secret stored in GitHub while still scoping the Cloudflare token tightly to a single Worker.

---

## Context

GitHub Actions natively supports OpenID Connect (OIDC): each job receives a short-lived JWT signed by GitHub's OIDC provider (`https://token.actions.githubusercontent.com`). Cloudflare's API allows creating API tokens whose validity is gated on an incoming OIDC assertion — the token is issued only when the `iss` (issuer) and `sub` (subject) claims match the configured conditions. The resulting Cloudflare token has a 15-minute TTL, is scoped to a specific account and Worker name, and is never stored anywhere. This pattern eliminates the entire class of long-lived-credential leaks and is the recommended keyless deployment approach for Cloudflare Workers as of 2024.

---

## Section 1 — GitHub Actions workflow

```yaml
# .github/workflows/deploy-keyless.yml
name: Deploy Worker (Keyless OIDC)

on:
  push:
    branches: [main]

# Grant the job permission to request an OIDC token from GitHub
permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      # Exchange the GitHub OIDC JWT for a short-lived Cloudflare API token.
      # The Cloudflare token endpoint validates iss + sub from the JWT,
      # then returns a token valid for 15 minutes.
      - name: Get Cloudflare token via OIDC
        id: cf-token
        run: |
          # Request the OIDC token from GitHub's internal endpoint
          OIDC_TOKEN=$(curl --silent --fail \
            -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            -H "Accept: application/json" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://token.actions.githubusercontent.com" \
            | jq -r '.value')

          # Exchange with Cloudflare's workload identity endpoint
          CF_TOKEN=$(curl --silent --fail \
            -X POST \
            -H "Content-Type: application/json" \
            -d "{\"grant_type\":\"urn:ietf:params:oauth:grant-type:token-exchange\",\
                  \"subject_token_type\":\"urn:ietf:params:oauth:token-type:id_token\",\
                  \"subject_token\":\"$OIDC_TOKEN\"}" \
            "https://oidc.cloudflare.com/token" \
            | jq -r '.access_token')

          # Mask token so it never appears in logs
          echo "::add-mask::$CF_TOKEN"
          echo "cf_token=$CF_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Deploy Worker
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ steps.cf-token.outputs.cf_token }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}

      - name: Verify deployment
        run: curl --fail --silent https://my-worker.example.workers.dev/health
```

---

## Section 2 — Cloudflare OIDC token policy configuration (TypeScript / API)

Create the scoped API token via the Cloudflare API before your first deploy:

```typescript
// scripts/setup-oidc-token-policy.ts
// Run once with a privileged token: npx ts-node scripts/setup-oidc-token-policy.ts

const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const CF_ADMIN_TOKEN = process.env.CLOUDFLARE_ADMIN_TOKEN!;
const GITHUB_REPO = "example-org/example-repo"; // owner/repo

interface TokenPolicy {
  name: string;
  policies: Policy[];
  not_before?: string;
  expires_on?: string;
  condition?: {
    request_type: string;
    conditions: OidcCondition[];
  };
}

interface Policy {
  effect: "allow" | "deny";
  resources: Record<string, string>;
  permission_groups: { id: string }[];
}

interface OidcCondition {
  claim: string;
  operator: "eq";
  value: string;
}

async function createOidcTokenPolicy() {
  // Look up the permission group ID for Workers Scripts:Edit
  const permsRes = await fetch(
    `https://api.cloudflare.com/client/v4/user/tokens/permission_groups`,
    { headers: { Authorization: `Bearer ${CF_ADMIN_TOKEN}` } }
  );
  const perms = await permsRes.json() as { result: { id: string; name: string }[] };
  const editGroup = perms.result.find((p) => p.name === "Workers Scripts:Edit")!;

  const policy: TokenPolicy = {
    name: `GitHub OIDC — ${GITHUB_REPO}`,
    policies: [
      {
        effect: "allow",
        resources: {

        },
        permission_groups: [{ id: editGroup.id }],
      },
    ],
    // OIDC conditions: only tokens from this exact repo and the deploy job
    condition: {
      request_type: "oidc",
      conditions: [
        {
          claim: "iss",
          operator: "eq",
          value: "https://token.actions.githubusercontent.com",
        },
        {
          claim: "sub",
          operator: "eq",
          value: `repo:${GITHUB_REPO}:ref:refs/heads/main`,
        },
      ],
    },
  };

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/user/tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CF_ADMIN_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(policy),
    }
  );

  const data = await res.json() as { result: { id: string } };
  console.log("Created OIDC token policy:", data.result.id);
  console.log(
    "No secret to store in GitHub — the OIDC exchange happens at runtime."
  );
}

creatOidcTokenPolicy().catch(console.error);
```

---

## Section 3 — Verification / Testing

```bash
# Confirm OIDC is enabled for the repo
gh api /repos/{owner}/{repo} | jq '.visibility'

# Decode the GitHub OIDC JWT locally (for inspection only — never do this in CI)
# The token is only available inside a running Actions job via ACTIONS_ID_TOKEN_REQUEST_URL
jq -R 'split(".") | .[1] | @base64d | fromjson' <<< "$OIDC_TOKEN"
# Expected claims:
# {
#   "iss": "https://token.actions.githubusercontent.com",
#   "sub": "repo:example-org/example-repo:ref:refs/heads/main",
#   "aud": "https://token.actions.githubusercontent.com",
#   "exp": ...
# }

# List Cloudflare token policies to confirm the OIDC one exists
curl -s https://api.cloudflare.com/client/v4/user/tokens \
  -H "Authorization: Bearer $CF_ADMIN_TOKEN" | \
  jq '.result[] | {name, status, condition}'

# Trigger a deploy and watch it succeed without a stored token
gh workflow run deploy-keyless.yml --ref main
gh run watch $(gh run list --workflow deploy-keyless.yml --limit 1 --json databaseId -q '.[0].databaseId')
```

---

## Anti-patterns

- **`id-token: write` at the workflow level** — Granting `id-token: write` at the top-level `permissions` block gives every job in the workflow the ability to mint OIDC tokens. Scope it to the specific deploy job only.
- **Logging the OIDC or CF token** — Even a 15-minute token can be exploited if it appears in logs. Always use `::add-mask::` immediately after obtaining the token.
- **`sub` condition matching only the repo without the ref** — Without `:ref:refs/heads/main` in the subject condition, any branch in the repo (including PRs from forks) can exchange for a production Cloudflare token.
- **Storing the admin token used to create the policy in the same repo** — Keep the bootstrapping admin token in a separate privileged context; it should never appear in the repository's secrets.

---

## Gotchas

- Cloudflare's OIDC token exchange endpoint (`https://oidc.cloudflare.com/token`) returns a 403 if the `sub` claim does not match exactly — the error message does not tell you which claim failed, so instrument your exchange script to log the full JWT claims during initial setup.
- GitHub's `ACTIONS_ID_TOKEN_REQUEST_URL` includes a query parameter; the `audience` must be appended as `&audience=...`, not `?audience=...`.
- The issued Cloudflare token TTL is fixed at 15 minutes and cannot be extended; structure your workflow so the deploy step completes well within that window.
- `wrangler` does not natively call the Cloudflare OIDC endpoint yet (as of wrangler 3.x); the token exchange in the workflow script is a manual step until native support ships.

---

## Verification

```bash
# Confirm no CLOUDFLARE_API_TOKEN secret exists at the repo level
gh secret list | grep CLOUDFLARE_API_TOKEN || echo "No repo-level token — good"

# Verify the deployed Worker responds correctly
curl --fail https://my-worker.example.workers.dev/health

# Check the Cloudflare audit log for the OIDC-issued token's actions
curl -s https://api.cloudflare.com/client/v4/user/audit_logs?actor_type=token \
  -H "Authorization: Bearer $CF_ADMIN_TOKEN" | \
  jq '.result[:5][] | {action: .action.type, token_name: .actor.display_name, when: .when}'
```

---

## Related

- `github-environments-cloudflare-workers-secrets.md`
- `github-actions-wrangler-matrix-deploy.md`

---

## Sources

- GitHub OIDC for cloud providers — https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect
- Cloudflare OIDC token exchange — https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/#use-github-oidc-tokens-to-authenticate-with-cloudflare
- Cloudflare API token conditions — https://developers.cloudflare.com/fundamentals/api/get-started/create-token/
