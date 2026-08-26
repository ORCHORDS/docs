# Pulumi Cloudflare Zero Trust Access Policy Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team manages dozens of internal applications behind Cloudflare Access. New
services spin up frequently, and manually creating Access applications, policies, and
service tokens through the dashboard creates configuration drift and audit gaps. You
need a Pulumi-based IaC workflow that provisions Zero Trust Access resources
programmatically, enforces naming conventions via type-safe TypeScript, and integrates
with your existing CI/CD pipeline.

---

## Context

Cloudflare Zero Trust Access protects internal applications without a VPN. The key
resources are:

| Resource | Pulumi Class | Purpose |
|----------|-------------|---------|
| Access Application | `cloudflare.AccessApplication` | Defines the protected app + session duration |
| Access Policy | `cloudflare.AccessPolicy` | Allow / deny rules attached to an application |
| Access Group | `cloudflare.AccessGroup` | Reusable sets of identity rules |
| Service Token | `cloudflare.AccessServiceToken` | Machine-to-machine auth for Workers / CI |
| Access CA | `cloudflare.AccessCaCertificate` | Short-lived SSH certificates |

Pulumi's TypeScript SDK offers strict types for all policy rule shapes, making
policy-as-code auditable and diff-able in pull requests.

---

## 1. Pulumi Project Setup

```typescript
// package.json (relevant deps)
// "@pulumi/cloudflare": "^5.0.0",
// "@pulumi/pulumi": "^3.0.0"

// Pulumi.yaml
// name: zero-trust-access
// runtime: nodejs
// description: Cloudflare Zero Trust Access policy automation
```

```typescript
// index.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();
const accountId = config.require("accountId");
const zoneId = config.require("zoneId");
```

Store `accountId` and `zoneId` in Pulumi ESC or as stack configuration:

```bash
pulumi config set accountId <value>
pulumi config set --secret cloudflare:apiToken <token>
```

---

## 2. Reusable Access Group for Engineering Team

```typescript
// groups.ts
import * as cloudflare from "@pulumi/cloudflare";

export function createEngineeringGroup(accountId: string): cloudflare.AccessGroup {
  return new cloudflare.AccessGroup("engineering-group", {
    accountId,
    name: "Engineering Team",
    include: [
      {
        emails: [
          { email: "alice@example.com" },
          { email: "bob@example.com" },
        ],
      },
      {
        emailDomains: [{ domain: "example.com" }],
      },
    ],
    require: [
      {
        // Enforce device posture: certificate present
        devicePosture: [{ integrationUid: "POSTURE_INTEGRATION_UID" }],
      },
    ],
    exclude: [
      {
        emails: [{ email: "contractor@external.com" }],
      },
    ],
  });
}
```

Access Groups decouple identity rules from application policies. When an engineer
leaves, you update the group once and all dependent policies update on next apply.

---

## 3. Access Application with Session Control

```typescript
// apps.ts
import * as cloudflare from "@pulumi/cloudflare";

export interface AppConfig {
  name: string;
  domain: string;
  sessionDurationHours: number;
  accountId: string;
  zoneId: string;
}

export function createAccessApp(cfg: AppConfig): cloudflare.AccessApplication {
  return new cloudflare.AccessApplication(`access-app-${cfg.name}`, {
    accountId: cfg.accountId,
    zoneId: cfg.zoneId,
    name: cfg.name,
    domain: cfg.domain,
    type: "self_hosted",
    sessionDuration: `${cfg.sessionDurationHours}h`,

    // Prevent CORS pre-flight leakage to unauthorized origins
    corsHeaders: [
      {
        allowedMethods: ["GET", "POST"],
        allowedOrigins: [`https://${cfg.domain}`],
        allowCredentials: true,
        maxAge: 86400,
      },
    ],

    // Auto-redirect to IdP rather than showing a login page
    autoRedirectToIdentity: true,

    // HTTP-only, Secure, SameSite=Lax cookie settings
    httpOnlyCookieAttribute: true,
    sameSiteCookieAttribute: "lax",
  });
}
```

---

## 4. Access Policy — Allow, Require, and Bypass Tiers

```typescript
// policies.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

export function attachPolicies(
  app: cloudflare.AccessApplication,
  engineeringGroup: cloudflare.AccessGroup,
  accountId: string,
): void {
  // Bypass policy: health-check endpoint, no auth required
  new cloudflare.AccessPolicy(`bypass-healthcheck`, {
    accountId,
    applicationId: app.id,
    name: "Bypass health check path",
    precedence: 1,
    decision: "bypass",
    include: [{ everyone: {} }],
  });

  // Allow policy: members of Engineering group who passed device posture
  new cloudflare.AccessPolicy(`allow-engineering`, {
    accountId,
    applicationId: app.id,
    name: "Allow Engineering",
    precedence: 2,
    decision: "allow",
    include: [
      {
        groups: [{ id: engineeringGroup.id }],
      },
    ],
    require: [
      {
        // Require MFA — WARP client with Okta integration
        authMethod: [{ authMethod: "mfa" }],
      },
    ],
  });

  // Deny policy: catch-all at lowest precedence
  new cloudflare.AccessPolicy(`deny-all`, {
    accountId,
    applicationId: app.id,
    name: "Deny everyone else",
    precedence: 99,
    decision: "deny",
    include: [{ everyone: {} }],
  });
}
```

Policy `precedence` is evaluated lowest-number-first. Always terminate with a
catch-all deny policy to prevent accidental allow-by-default if the allow policy is
misconfigured.

---

## 5. Service Token for Workers-to-Internal-App Auth

```typescript
// service-tokens.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

export function createServiceToken(
  name: string,
  accountId: string,
): { token: cloudflare.AccessServiceToken; secret: <redacted-secret> } {
  const token = new cloudflare.AccessServiceToken(`svc-token-${name}`, {
    accountId,
    name: `${name}-ci-token`,
    // Duration: 1 year — rotate via Pulumi automation API
    duration: "8760h",
  });

  // Export client secret as a sensitive output for injection into CI
  return {
    token,
    secret: <redacted-secret> => s),
  };
}

// In index.ts:
// const { token, secret } = createServiceToken("api-worker", accountId);
// export const serviceTokenId = token.clientId;
// export const serviceTokenSecret = pulumi.secret(secret);
```

The `clientSecret` is available only at creation time. Pulumi stores it in state
encrypted with your chosen secrets provider. Rotate by running
`pulumi up` after changing `duration` or by importing a new token and destroying the
old one.

---

## 6. Attaching a Service Token Policy to an App

```typescript
// In policies.ts — add alongside allow-engineering
new cloudflare.AccessPolicy("allow-service-token", {
  accountId,
  applicationId: app.id,
  name: "Allow CI service token",
  precedence: 3,
  decision: "allow",
  include: [
    {
      serviceToken: [{ tokenId: serviceToken.id }],
    },
  ],
});
```

Service token policies let Workers or CI pipelines call protected internal APIs
without a user session. They bypass the IdP redirect, responding only to
`CF-Access-Client-Id` and `CF-Access-Client-Secret` headers.

---

## 7. TypeScript Worker Consuming a Protected Endpoint

```typescript
// src/internal-api-caller.ts
export interface Env {
  ACCESS_CLIENT_ID: string;     // bound as secret
  ACCESS_CLIENT_SECRET: string; // bound as secret
  INTERNAL_API_URL: string;     // plain text binding
}

export async function callInternalApi(
  path: string,
  env: Env,
): Promise<Response> {
  return fetch(`${env.INTERNAL_API_URL}${path}`, {
    headers: {
      "CF-Access-Client-Id": env.ACCESS_CLIENT_ID,
      "CF-Access-Client-Secret": env.ACCESS_CLIENT_SECRET,
      "Content-Type": "application/json",
    },
  });
}
```

Never hardcode `CF-Access-Client-Id`/`CF-Access-Client-Secret` in Worker source.
Inject them as Worker secrets provisioned by Terraform or Pulumi.

---

## Anti-patterns

- **Creating Access policies directly on an account without an application** — Policies
  must be attached to a specific application. Account-level policies without an app
  binding are ignored silently.
- **Single allow policy with no deny fallback** — Cloudflare evaluates policies in
  precedence order and defaults to allow if no policy matches. Always add a deny-all
  at high precedence.
- **Storing `clientSecret` in plaintext** — Use `pulumi.secret()` and a
  secrets-manager backend (Pulumi ESC, Vault). Never log or export it unencrypted.
- **Using email-based include rules without a domain constraint** — An attacker with a
  matching email from any provider could gain access if your IdP does not enforce
  domain restrictions.

---

## Gotchas

- Policy `precedence` is scoped to a single application — you can reuse the same
  integer across different applications without conflict.
- Renaming an Access Application changes the login URL. Coordinate with users before
  renaming via IaC.
- `session_duration` must use Cloudflare's duration string format (`1h`, `24h`,
  `365d`). ISO 8601 durations are not accepted.
- Service tokens cannot be used interactively (no WARP client enforcement); they bypass
  device-posture `require` rules on the same application.
- Pulumi diffs show `clientSecret` as `[secret]` — verify rotation by comparing
  `clientId` (stable) against what's deployed in CI.

---

## Verification

```bash
# List all Access applications for the account
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/access/apps" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | {id, name, domain}]'

# Confirm policy precedence order for an app
APP_ID="<app-id>"
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/access/apps/${APP_ID}/policies" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '[.result[] | {name, precedence, decision}] | sort_by(.precedence)'

# Test service token auth
curl -sv https://internal-app.example.com/health \
  -H "CF-Access-Client-Id: ${CLIENT_ID}" \
  -H "CF-Access-Client-Secret: ${CLIENT_SECRET}"

# Pulumi preview to see pending changes without applying
pulumi preview --diff
```

---

## Related

- `terraform-cloudflare-access-application-policy.md`
- `cloudflare-zero-trust-staging-prod-isolation.md`
- `cloudflare-access-self-service-app-provisioning.md`
- `vault-cloudflare-workers-dynamic-secrets.md`
- `pulumi-esc-secrets-config-management.md`

---

## Sources

- Pulumi Cloudflare Provider – AccessApplication: https://www.pulumi.com/registry/packages/cloudflare/api-docs/accessapplication/
- Cloudflare Zero Trust Access Policies docs: https://developers.cloudflare.com/cloudflare-one/policies/access/
- Cloudflare Service Tokens: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
