# Pulumi Cloudflare Pages Project Environment Variables

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Pages project needs different environment variables per deployment
environment (production vs. preview) — API keys, feature flags, service URLs — and
these values must not live in source control. Managing them through the Pages dashboard
creates configuration drift across teams and makes it impossible to audit what was set
and when. You need a Pulumi TypeScript workflow that provisions Pages projects,
injects environment variables for both `production` and `preview` environments, and
integrates with a secrets manager for sensitive values.

---

## Context

Cloudflare Pages supports environment-specific variable injection:

| Scope | Applies To |
|-------|-----------|
| `production` | Only deployments from the production branch |
| `preview` | All other branch deployments |

Variables can be **plain text** (visible in the dashboard) or **secret** (write-only,
redacted in logs). The Pulumi `cloudflare.PagesProject` resource exposes both as
`deploymentConfigs.production.envVars` / `deploymentConfigs.preview.envVars`.

Unlike Workers secrets (which are injected at runtime via the Workers runtime), Pages
environment variables are injected into the build environment at deployment time AND
are available to Pages Functions at runtime.

---

## 1. Pulumi Project Bootstrap

```typescript
// package.json (deps)
// "@pulumi/cloudflare": "^5.0.0"
// "@pulumi/pulumi": "^3.0.0"

// Pulumi.prod.yaml
// config:
//   cloudflare:apiToken:
//     secure: AAABabc...   ← encrypted by Pulumi secrets provider
```

```bash
# Stack setup
pulumi stack init prod
pulumi config set accountId <value>
pulumi config set --secret cloudflare:apiToken <token>
pulumi config set --secret stripeApiKey sk_live_...
pulumi config set --secret analyticsWriteKey abc123...
```

Using `--secret` encrypts the value in `Pulumi.prod.yaml` via the stack's secrets
provider (Pulumi Cloud, AWS KMS, or Azure Key Vault).

---

## 2. Type-safe Configuration Loader

```typescript
// src/config.ts
import * as pulumi from "@pulumi/pulumi";

export interface StackConfig {
  accountId: string;
  // Sensitive values come as pulumi.Output<string> to stay encrypted in memory
  stripeApiKeyProd: pulumi.Output<string>;
  stripeApiKeyPreview: pulumi.Output<string>;
  analyticsWriteKey: pulumi.Output<string>;
  featureFlagApiUrl: string;
  cdnBaseUrl: string;
}

export function loadConfig(): StackConfig {
  const cfg = new pulumi.Config();
  const stack = pulumi.getStack(); // "prod" | "staging" | "preview"

  return {
    accountId: cfg.require("accountId"),
    stripeApiKeyProd: cfg.requireSecret("stripeApiKeyProd"),
    stripeApiKeyPreview: cfg.requireSecret("stripeApiKeyPreview"),
    analyticsWriteKey: cfg.requireSecret("analyticsWriteKey"),
    featureFlagApiUrl: stack === "prod"
      ? "https://flags.example.com"
      : "https://flags-staging.example.com",
    cdnBaseUrl: `https://cdn-${stack}.example.com`,
  };
}
```

Using `cfg.requireSecret()` keeps values wrapped in `pulumi.Output<string>` — they
are never logged or stringified unless explicitly applied.

---

## 3. Pages Project with Dual-environment Variables

```typescript
// src/pages.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import type { StackConfig } from "./config.js";

export function createPagesProject(
  cfg: StackConfig,
): cloudflare.PagesProject {
  return new cloudflare.PagesProject("storefront", {
    accountId: cfg.accountId,
    name: "storefront",
    productionBranch: "main",

    buildConfig: {
      buildCommand: "pnpm build",
      destinationDir: "dist",
      rootDir: "/",
    },

    source: {
      type: "github",
      config: {
        owner: "example-org",
        repoName: "storefront",
        productionBranch: "main",
        prCommentsEnabled: true,
        deploymentsEnabled: true,
        previewDeploymentSetting: "custom",
        previewBranchIncludes: ["staging", "feat/*"],
        previewBranchExcludes: ["dependabot/*"],
      },
    },

    deploymentConfigs: {
      production: {
        envVars: {
          // Plain text — visible in dashboard, safe to log
          NEXT_PUBLIC_CDN_URL:     { value: cfg.cdnBaseUrl },
          NEXT_PUBLIC_FEATURE_API: { value: cfg.featureFlagApiUrl },
          NODE_ENV:                { value: "production" },
          // Secret — write-only, redacted in logs
          STRIPE_SECRET_KEY: {
            value: cfg.stripeApiKeyProd,
            type: "secret",
          },
          ANALYTICS_WRITE_KEY: {
            value: cfg.analyticsWriteKey,
            type: "secret",
          },
        },
      },
      preview: {
        envVars: {
          NEXT_PUBLIC_CDN_URL:     { value: "https://cdn-preview.example.com" },
          NEXT_PUBLIC_FEATURE_API: { value: "https://flags-staging.example.com" },
          NODE_ENV:                { value: "development" },
          STRIPE_SECRET_KEY: {
            value: cfg.stripeApiKeyPreview,
            type: "secret",
          },
          ANALYTICS_WRITE_KEY: {
            value: cfg.analyticsWriteKey,
            type: "secret",
          },
        },
      },
    },
  });
}
```

---

## 4. Pages Function Consuming Environment Variables

```typescript
// functions/api/stripe-webhook.ts
// This file is deployed as a Pages Function at /api/stripe-webhook

interface Env {
  STRIPE_SECRET_KEY: string;  // injected from Pages env vars
  NODE_ENV: string;
}

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const { request, env } = context;

  if (!env.STRIPE_SECRET_KEY) {
    return new Response("Missing Stripe key", { status: 500 });
  }

  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return new Response("Missing signature", { status: 400 });
  }

  // In production, verify the webhook signature
  if (env.NODE_ENV === "production") {
    // Verification logic here using STRIPE_SECRET_KEY
  }

  const body = await request.text();
  console.log(`Received webhook in ${env.NODE_ENV}: ${body.length} bytes`);

  return new Response("OK", { status: 200 });
};
```

Pages Functions receive environment variables via `context.env`, mirroring the Workers
runtime API. The same `Env` type pattern works for both.

---

## 5. Exporting Non-sensitive Metadata

```typescript
// index.ts
import * as pulumi from "@pulumi/pulumi";
import { loadConfig } from "./src/config.js";
import { createPagesProject } from "./src/pages.js";

const cfg = loadConfig();
const project = createPagesProject(cfg);

// Safe to export — these are not secrets
export const projectName = project.name;
export const productionUrl = pulumi.interpolate`https://${project.name}.pages.dev`;

// Explicitly mark as secret to prevent accidental logging in CI
export const stripeKeyFingerprint = cfg.stripeApiKeyProd.apply(
  (key) => `sk_live_***${key.slice(-4)}`,
);
```

---

## 6. Rotating a Secret Variable

```typescript
// src/rotate.ts — run with: pulumi up --target cloudflare:index/pagesProject:PagesProject::storefront

// 1. Update the secret in config:
//    pulumi config set --secret stripeApiKeyProd sk_live_NEW_KEY

// 2. Pulumi diff will show the changed envVar:
//    ~ envVars.STRIPE_SECRET_KEY.value: [secret] => [secret]

// 3. Apply to propagate:
//    pulumi up

// 4. Trigger a Pages deployment to pick up the new value:
//    wrangler pages deployment create --project-name storefront dist/
```

Pages deployments snapshot the environment variables at deploy time. Updating a
variable in Pulumi does **not** automatically redeploy existing deployments — you must
trigger a new deployment for the change to take effect in production.

---

## Anti-patterns

- **Storing secrets in `NEXT_PUBLIC_*` variables** — Variables prefixed `NEXT_PUBLIC_`
  are inlined into the client-side bundle at build time and visible to all users.
  Only use that prefix for truly public configuration.
- **Using the same secret value for production and preview** — Preview deployments are
  accessible to anyone with the link. Use sandbox/test API keys for preview
  environments.
- **Hardcoding environment names in application code** — Check `NODE_ENV` or a custom
  `APP_ENV` variable injected via Pages env vars. Never check the hostname at build
  time.
- **Not scoping the API token** — Pages project management requires `Account → Cloudflare
  Pages → Edit`. A token with broader permissions is unnecessary and violates least
  privilege.

---

## Gotchas

- Pulumi diffs show secret `envVars` as `[secret]` even when the value is unchanged.
  This is expected — Pulumi cannot diff encrypted values without decrypting them. Use
  `pulumi preview --show-secrets` sparingly in trusted environments.
- Removing an environment variable from `envVars` in Pulumi removes it from the Pages
  project configuration, but **does not** redeploy existing production deployments.
  Those deployments continue using the old value until a new deployment is triggered.
- `type: "secret"` makes the variable write-only. If you need to read the current
  value (e.g. for rotation validation), you must read it from the original secret store
  (Pulumi config, Vault, etc.) — the Cloudflare API will not return it.
- The `source` block is required even for projects that use direct uploads
  (`wrangler pages deploy`). Pass an empty `source` object or omit the `config` sub-block.

---

## Verification

```bash
# List env vars configured on the Pages project (secrets will show as null)
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/storefront" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result.deployment_configs.production.env_vars | to_entries[] | {key: .key, type: .value.type}'

# Confirm Pulumi stack outputs
pulumi stack output productionUrl
pulumi stack output --show-secrets stripeKeyFingerprint

# Check the latest production deployment picked up updated vars
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/pages/projects/storefront/deployments?env=production&per_page=1" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[0] | {id, created_on, environment}'
```

---

## Related

- `pulumi-cloudflare-pages-project-build-config.md`
- `pulumi-esc-secrets-config-management.md`
- `cloudflare-workers-secrets-rotation-automation.md` (see: `workers-secrets-rotation-automation.md`)
- `next-static-export-pages.md`
- `cloudflare-workers-api-token-scoping.md`

---

## Sources

- Pulumi `cloudflare.PagesProject`: https://www.pulumi.com/registry/packages/cloudflare/api-docs/pagesproject/
- Cloudflare Pages Environment Variables: https://developers.cloudflare.com/pages/configuration/environment-variables/
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Pulumi Secrets: https://www.pulumi.com/docs/concepts/secrets/
