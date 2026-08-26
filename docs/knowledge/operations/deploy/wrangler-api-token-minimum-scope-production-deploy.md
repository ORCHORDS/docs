# Wrangler API Token Minimum Scope for Production Deploys

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

CI pipelines that deploy Cloudflare Workers or Pages use a `CLOUDFLARE_API_TOKEN` with
Account-level Edit or even Global API Key credentials. Over-privileged tokens increase the
blast radius of a leaked secret and violate the principle of least privilege. The goal is to
determine the exact minimum set of permission scopes a Wrangler deploy token needs and to
validate those scopes programmatically before every production deploy.

---

## Context

Wrangler authenticates via the `CLOUDFLARE_API_TOKEN` environment variable (or
`--api-token` flag). The Cloudflare API uses a fine-grained token system where each token
carries one or more permission groups scoped to an Account, Zone, or User resource.

Common over-permissions seen in the wild:
- `Zone:Edit` when only `Worker Routes:Edit` is needed
- `Account Settings:Read` granted globally when only one account is targeted
- `Workers Scripts:Edit` with no zone binding restriction

For a standard `wrangler deploy` targeting a Workers script bound to a custom domain via a
Worker Route, the minimum required scopes are:

| Cloudflare Resource        | Permission Level |
|---------------------------|-----------------|
| Workers Scripts            | Edit            |
| Workers Routes             | Edit            |
| Workers KV Storage         | Edit (if KV bindings present) |
| D1                         | Edit (if D1 bindings present) |
| Cloudflare Pages           | Edit (Pages deploys only)    |
| Account Settings           | Read            |
| User Details               | Read            |

---

## Creating a Minimum-Scope Token via Cloudflare Dashboard

1. Navigate to **My Profile → API Tokens → Create Token**.
2. Use **Create Custom Token**.
3. Add permission rows using the table above — scope each to the specific account or zone.
4. Set IP restriction to your CI provider's egress IP range when available.
5. Set token TTL to 90 days maximum; rotate via CI secret before expiry.

---

## Validating Token Scopes in CI Before Deploy

Add a pre-deploy step that calls the `/user/tokens/verify` endpoint and inspects the
returned permission list.

```yaml
# .github/workflows/deploy-workers.yml
name: Deploy Workers

on:
  push:
    branches: [main]

jobs:
  validate-token:
    runs-on: ubuntu-latest
    steps:
      - name: Verify API token scopes
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          RESPONSE=$(curl -s -X GET \
            "https://api.cloudflare.com/client/v4/user/tokens/verify" \
            -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
            -H "Content-Type: application/json")

          STATUS=$(echo "$RESPONSE" | jq -r '.result.status')
          if [ "$STATUS" != "active" ]; then
            echo "ERROR: Token is not active. Status: $STATUS"
            exit 1
          fi
          echo "Token is active."

      - name: Check required permission groups
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          PERMS=$(curl -s -X GET \
            "https://api.cloudflare.com/client/v4/user/tokens/verify" \
            -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | \
            jq -r '.result.policies[].permission_groups[].name')

          REQUIRED=("Workers Scripts" "Workers Routes" "Account Settings")
          for perm in "${REQUIRED[@]}"; do
            if ! echo "$PERMS" | grep -q "$perm"; then
              echo "ERROR: Missing required permission: $perm"
              exit 1
            fi
          done
          echo "All required permissions verified."

  deploy:
    needs: validate-token
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: deploy --env production
```

---

## TypeScript Token Scope Validator Utility

Use this as a pre-deploy script (`scripts/verify-token.ts`) run via `tsx` in CI.

```typescript
// scripts/verify-token.ts
import { execSync } from "node:child_process";

interface TokenVerifyResult {
  result: {
    id: string;
    status: "active" | "disabled" | "expired";
    policies: Array<{
      id: string;
      effect: "allow" | "deny";
      resources: Record<string, string>;
      permission_groups: Array<{ id: string; name: string }>;
    }>;
  };
  success: boolean;
  errors: Array<{ code: number; message: string }>;
}

const REQUIRED_PERMISSIONS = [
  "Workers Scripts:Edit",
  "Account Settings:Read",
  "User Details:Read",
];

async function verifyTokenScopes(): Promise<void> {
  const token = process.env.CLOUDFLARE_API_TOKEN;
  if (!token) {
    throw new Error("CLOUDFLARE_API_TOKEN environment variable is not set");
  }

  const response = await fetch(
    "https://api.cloudflare.com/client/v4/user/tokens/verify",
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );

  const data = (await response.json()) as TokenVerifyResult;

  if (!data.success || data.result.status !== "active") {
    const errorMessages = data.errors.map((e) => e.message).join(", ");
    throw new Error(`Token verification failed: ${errorMessages || data.result.status}`);
  }

  const grantedPermissions = data.result.policies
    .flatMap((p) => p.permission_groups.map((pg) => pg.name))
    .join("\n");

  const missing: string[] = [];
  for (const required of REQUIRED_PERMISSIONS) {
    const permName = required.split(":")[0];
    if (!grantedPermissions.includes(permName)) {
      missing.push(required);
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `Token is missing required permissions:\n${missing.map((m) => `  - ${m}`).join("\n")}`
    );
  }

  console.log("✔  Token is active and has required permissions.");
  console.log(`   Token ID: ${data.result.id}`);
}

verifyTokenScopes().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
```

Invoke in `package.json`:

```json
{
  "scripts": {
    "verify-token": "tsx scripts/verify-token.ts",
    "predeploy": "npm run verify-token"
  }
}
```

---

## Wrangler Config: Locking Down Account and Zone

Bind the token to a specific account in `wrangler.toml` / `wrangler.json` to prevent
accidental cross-account deploys.

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-06-01"
account_id = "abc123def456"   # hard-code the target account

[env.production]
name = "my-worker-production"
routes = [
  { pattern = "api.example.com/*", zone_name = "example.com" }
]
```

When Wrangler reads a hard-coded `account_id`, it will refuse to deploy to any other account
even if the token technically has permissions elsewhere.

---

## GitHub Actions OIDC Approach (Token-less)

For teams on Cloudflare's OIDC integration, replace long-lived tokens entirely.

```yaml
# .github/workflows/deploy-oidc.yml
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to Cloudflare via OIDC
        uses: cloudflare/wrangler-action@v3
        with:
          # No apiToken needed — OIDC exchange happens automatically
          command: deploy --env production
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
```

OIDC tokens are short-lived (15 minutes) and scoped to a single workflow run, eliminating
long-lived token leakage risk entirely.

---

## Rotating Tokens Before Expiry

```bash
# List tokens approaching expiry (pseudo-script using CF API)
curl -s "https://api.cloudflare.com/client/v4/user/tokens" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | \
  jq '.result[] | select(.expires_on != null) |
    {id, name, expires_on, days_left: (((.expires_on | fromdateiso8601) - now) / 86400 | floor)}'
```

Automate rotation with a GitHub Actions scheduled workflow that calls the Cloudflare API to
create a replacement token, updates the repository secret via the GitHub API, then deletes
the old token.

---

## Anti-patterns

- **Global API Key** — has full account access and cannot be scoped. Never use it in CI.
- **`Account:Edit` permission** — grants ability to modify account settings, billing, and
  member management. Workers deploys do not need it.
- **Sharing one token across multiple repos** — if one repo's secret is compromised, all
  Workers in all repos are exposed. Use per-repo tokens.
- **Not setting a TTL** — tokens without an expiry never rotate automatically.
- **Storing the token in `wrangler.toml`** — the file is committed to version control.

---

## Gotchas

- `Workers Routes:Edit` is required only when the Worker uses a zone-based route
  (`example.com/*`). Workers on `*.workers.dev` subdomains do not need it.
- The Cloudflare dashboard token editor lists permission groups differently than the API's
  `/user/tokens/verify` response field names. Cross-reference using the
  `/client/v4/user/tokens/permission_groups` endpoint to get canonical names.
- `wrangler secret put` requires an additional `Workers Secrets:Edit` permission not always
  listed in the basic deploy token template.
- When using `wrangler pages deploy`, replace `Workers Scripts:Edit` with
  `Cloudflare Pages:Edit`.
- Wrangler version ≥ 3.78 respects `CLOUDFLARE_API_TOKEN` over `CF_API_TOKEN`; older
  versions may still look for the deprecated variable name.

---

## Verification

```bash
# 1. Verify token is active and get its metadata
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq .

# 2. List all permission groups available (reference)
curl -s "https://api.cloudflare.com/client/v4/user/tokens/permission_groups" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '[.result[] | .name]'

# 3. Dry-run a deploy to confirm token is accepted
npx wrangler deploy --dry-run --env production

# 4. Confirm only expected accounts are accessible
curl -s "https://api.cloudflare.com/client/v4/accounts" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '[.result[] | {id, name}]'
```

---

## Related

- `oidc-federated-deploy-credentials.md`
- `secrets-management-wrangler-vault.md`
- `wrangler-ci-secrets-audit-pre-deploy-scan.md`
- `wrangler-bulk-secrets-deploy-automation.md`
- `workers-secrets-bulk-rotation-automation-ci.md`

---

## Sources

- Cloudflare Docs: API Tokens — https://developers.cloudflare.com/fundamentals/api/create-token/
- Cloudflare Docs: Wrangler authentication — https://developers.cloudflare.com/workers/wrangler/ci-cd/
- Cloudflare Docs: Permission groups reference — https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Cloudflare Docs: GitHub Actions OIDC — https://developers.cloudflare.com/workers/ci-cd/github-actions/
- Cloudflare Blog: Fine-grained API Tokens — https://blog.cloudflare.com/api-token-permissions/
