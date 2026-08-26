# Cloudflare Access Bypass List Deploy Automation

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Zero Trust Access application protects staging or internal tooling behind SSO, but CI/CD runners, uptime monitors, and health-check scrapers must reach certain paths without authentication. Manually updating the bypass (service token / IP allowlist) rules in the dashboard every time you add a new monitoring endpoint or rotate a CI service token is fragile and creates audit gaps.

---

## Context

Cloudflare Access "bypass" is implemented via Access policies with the action set to `bypass` (not `allow`). A bypass policy rule exempts matched requests from the SSO gate entirely — the request passes through without an identity check. Common bypass criteria are IP CIDR ranges (for trusted monitoring services), service tokens (for programmatic callers), and specific URI paths.

The Cloudflare API (`/accounts/{account_id}/access/apps/{app_id}/policies`) is the authoritative source for Access policy state. Codifying bypass rules in a config file and applying them via CI gives you version-controlled, auditable, idempotent bypass management.

---

## Bypass Policy Data Model

```typescript
// config/access-bypass-rules.ts

export interface BypassRule {
  /** Human-readable name for this bypass rule */
  name: string;
  /** Precedence relative to other policies on the same app; lower = evaluated first */
  precedence: number;
  /** Either "ip_ranges" or "service_token" */
  type: "ip_ranges" | "service_token";
  /** CIDR ranges (when type = ip_ranges) */
  cidrs?: string[];
  /** Service token ID (when type = service_token) */
  serviceTokenId?: string;
  /** Restrict bypass to specific paths (optional) */
  pathPatterns?: string[];
}

export interface AppBypassConfig {
  appId: string;
  appName: string;
  bypasses: BypassRule[];
}

export const BYPASS_CONFIG: AppBypassConfig[] = [
  {
    appId: process.env.CF_ACCESS_APP_ID_STAGING!,
    appName: "staging-app",
    bypasses: [
      {
        name: "CI/CD runners",
        precedence: 1,
        type: "ip_ranges",
        cidrs: ["185.199.108.0/22", "140.82.112.0/20"],  // GitHub Actions ranges
        pathPatterns: ["/health", "/api/healthcheck"],
      },
      {
        name: "Uptime robot monitor",
        precedence: 2,
        type: "ip_ranges",
        cidrs: ["216.144.248.0/24"],
        pathPatterns: ["/health"],
      },
      {
        name: "Internal deploy service token",
        precedence: 3,
        type: "service_token",
        serviceTokenId: process.env.CF_ACCESS_SERVICE_TOKEN_ID!,
      },
    ],
  },
];
```

---

## Applying Bypass Policies via API

```typescript
// scripts/deploy-access-bypass.ts
import { BYPASS_CONFIG, AppBypassConfig, BypassRule } from "../config/access-bypass-rules";

const CF_API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const CF_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;

const BASE = `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/access/apps`;

interface AccessPolicy {
  id?: string;
  name: string;
  decision: "bypass";
  precedence: number;
  include: Array<Record<string, unknown>>;
}

function buildPolicyInclude(rule: BypassRule): Array<Record<string, unknown>> {
  const include: Array<Record<string, unknown>> = [];

  if (rule.type === "ip_ranges" && rule.cidrs) {
    for (const cidr of rule.cidrs) {
      include.push({ ip: { ip: cidr } });
    }
  }

  if (rule.type === "service_token" && rule.serviceTokenId) {
    include.push({ service_token: { token_id: rule.serviceTokenId } });
  }

  return include;
}

async function cfFetch(path: string, options: RequestInit = {}): Promise<any> {
  const res = await fetch(`${BASE}/${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${CF_API_TOKEN}`,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> ?? {}),
    },
  });
  const json = await res.json() as any;
  if (!json.success) throw new Error(JSON.stringify(json.errors));
  return json.result;
}

async function listPolicies(appId: string): Promise<AccessPolicy[]> {
  return cfFetch(`${appId}/policies`);
}

async function upsertBypassPolicy(appId: string, rule: BypassRule): Promise<void> {
  const existing = await listPolicies(appId);
  const existingByName = existing.find((p) => p.name === rule.name);

  const payload: AccessPolicy = {
    name: rule.name,
    decision: "bypass",
    precedence: rule.precedence,
    include: buildPolicyInclude(rule),
  };

  if (existingByName?.id) {
    await cfFetch(`${appId}/policies/${existingByName.id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    console.log(`Updated bypass policy: ${rule.name}`);
  } else {
    await cfFetch(`${appId}/policies`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    console.log(`Created bypass policy: ${rule.name}`);
  }
}

async function removeStaleBypassPolicies(
  appId: string,
  managedNames: string[]
): Promise<void> {
  const existing = await listPolicies(appId);
  const stale = existing.filter(
    (p) => p.decision === "bypass" && !managedNames.includes(p.name)
  );

  for (const policy of stale) {
    await cfFetch(`${appId}/policies/${policy.id}`, { method: "DELETE" });
    console.log(`Removed stale bypass policy: ${policy.name}`);
  }
}

async function main(): Promise<void> {
  for (const appConfig of BYPASS_CONFIG) {
    console.log(`\nProcessing app: ${appConfig.appName} (${appConfig.appId})`);

    for (const rule of appConfig.bypasses) {
      await upsertBypassPolicy(appConfig.appId, rule);
    }

    const managedNames = appConfig.bypasses.map((r) => r.name);
    await removeStaleBypassPolicies(appConfig.appId, managedNames);
  }

  console.log("\nAccess bypass deploy complete");
}

main().catch((err) => { console.error(err); process.exit(1); });
```

---

## Service Token Rotation Deploy

When rotating a CI service token, the bypass policy must reference the new token ID before the old token is deleted:

```typescript
// scripts/rotate-service-token-bypass.ts
async function rotateServiceToken(
  appId: string,
  policyName: string,
  newTokenId: string
): Promise<void> {
  const existing = await listPolicies(appId);
  const policy = existing.find((p) => p.name === policyName);

  if (!policy?.id) {
    throw new Error(`Policy not found: ${policyName}`);
  }

  const updated = {
    ...policy,
    include: [{ service_token: { token_id: newTokenId } }],
  };

  await cfFetch(`${appId}/policies/${policy.id}`, {
    method: "PUT",
    body: JSON.stringify(updated),
  });

  console.log(`Rotated service token in bypass policy: ${policyName}`);
}
```

---

## GitHub Actions Workflow

```yaml
# .github/workflows/deploy-access-bypass.yml
name: Deploy Access Bypass Rules

on:
  push:
    branches: [main]
    paths:
      - "config/access-bypass-rules.ts"
      - "scripts/deploy-access-bypass.ts"
  workflow_dispatch:

jobs:
  deploy-bypass:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - run: npm ci

      - name: Deploy Access bypass policies
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_ACCESS_APP_ID_STAGING: ${{ secrets.CF_ACCESS_APP_ID_STAGING }}
          CF_ACCESS_SERVICE_TOKEN_ID: ${{ secrets.CF_ACCESS_SERVICE_TOKEN_ID }}
        run: npx ts-node scripts/deploy-access-bypass.ts

      - name: Smoke-test bypass path
        run: |
          STATUS=$(curl -o /dev/null -s -w "%{http_code}" https://staging.example.com/health)
          [ "$STATUS" -eq 200 ] && echo "Bypass active" || (echo "Health check failed: $STATUS"; exit 1)
```

---

## Anti-patterns

- **Bypassing entire applications instead of specific paths** — scope bypass policies to health-check paths only; a full-app bypass defeats the SSO gate.
- **Using IP bypass for dynamic CI runner IPs** — GitHub-hosted runner IPs change; use service tokens for machine callers instead.
- **Storing service token secrets in bypass config files** — only reference token IDs (non-sensitive) in config; the token client secret stays in CI secrets.
- **Not removing stale bypass policies** — accumulated bypass policies from old monitors or retired CIDRs widen the attack surface silently.
- **Setting bypass policy precedence lower than the deny policy** — if the deny policy has lower precedence (evaluated first), the bypass is never reached.

---

## Gotchas

- Cloudflare Access policy `precedence` is evaluated lowest-number-first; a bypass at precedence 1 is evaluated before an allow at precedence 2.
- The `bypass` decision in the API is distinct from `allow`; bypass means no identity is required, while allow still requires a valid session.
- Service tokens must be created in the same Zero Trust account; cross-account service tokens are not supported for bypass policies.
- Path-based bypass requires the Access application to be configured with a "path" application type, not a "self-hosted" type at a hostname level.
- API token for Access policy management requires the `Zero Trust:Edit` permission, not the generic Workers or Pages permission.

---

## Verification

```bash
# List all policies on an Access application
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/access/apps/$CF_ACCESS_APP_ID_STAGING/policies" \
  | jq '.result[] | {name, decision, precedence}'

# Verify bypass is active for the health path (should return 200 without auth)
curl -v -o /dev/null https://staging.example.com/health 2>&1 | grep "< HTTP"
```

---

## Related

- `cloudflare-access-application-deploy-automation.md`
- `oidc-federated-deploy-credentials.md`
- `workers-secrets-rotation-zero-downtime.md`
- `deploy-gate-e2e-tests-playwright-pages.md`
- `gitops-secrets-management.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/api/operations/access-policies-create-an-access-policy
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
