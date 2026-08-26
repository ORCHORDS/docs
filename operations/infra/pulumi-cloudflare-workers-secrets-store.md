# Cloudflare Workers Secrets Store Pulumi Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A monorepo with 15 Workers all need the same database password, API key, or signing
secret. Using `wrangler secret put` per Worker is error-prone and causes drift: secrets
get updated in some Workers and forgotten in others. When a key rotates you must touch
every Worker. Cloudflare's centralised Secrets Store solves this — one secret, bound to
many Workers — but provisioning it consistently across environments requires Pulumi code,
not manual dashboard clicks.

## Context

Cloudflare Secrets Store (GA, 2025) is an account-level vault that stores named secrets
independently of any Worker. Workers receive secrets via bindings that reference a Store
secret by name; the Worker runtime injects the resolved value at execution time without
the value ever appearing in the Worker bundle or in Pulumi state.

Key concepts:

- **Store** — an account-scoped container; each account gets one default store, but
  additional stores can be created for isolation (per-team, per-env).
- **Secret** — a named, versioned secret within a store. Versions are immutable; rotation
  creates a new version and the binding always resolves to `latest`.
- **Binding** — a `secrets_store_secret` binding on a `WorkerScript` links the Worker's
  environment variable name to the store secret name.
- **Pulumi resource** — `cloudflare.SecretsStoreSecret` (provider ≥ 5.20).

Secrets Store secrets are **not** visible in `pulumi stack export` — they are write-only
resources. The provider stores only the secret's ID and name in state.

## 1. Provider and Stack Config

```typescript
// index.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const config = new pulumi.Config();
const cfConfig = new pulumi.Config("cloudflare");
const accountId = cfConfig.require("accountId");
const stack = pulumi.getStack(); // "staging" | "production"
```

```bash
pulumi config set cloudflare:accountId <ACCOUNT_ID>
# Secrets: stored encrypted in Pulumi ESC or backend
pulumi config set --secret db:password "s3cr3t-password"
pulumi config set --secret stripe:apiKey "sk_live_..."
```

## 2. Create or Reference the Secrets Store

```typescript
// secrets-store.ts
export const secretsStore = new cloudflare.SecretsStore(
  `workers-secrets-store-${stack}`,
  {
    accountId,
    name: `workers-${stack}`,
  }
);
```

For accounts that already have a default store, import it:

```bash
# Find the existing store ID
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/secrets_store/stores" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].id'

# Import into Pulumi
pulumi import cloudflare:index/secretsStore:SecretsStore workers-secrets-store-production \
  "<ACCOUNT_ID>/<STORE_ID>"
```

## 3. Provision Secrets in the Store

```typescript
// secrets.ts
import { secretsStore } from "./secrets-store";

const rawSecrets = config.requireSecretObject<Record<string, string>>("secrets");

// Provision one store secret per key — Pulumi treats the value as write-only
export const dbPassword = new cloudflare.SecretsStoreSecret("db-password", {
  accountId,
  storeId: secretsStore.id,
  name: `DB_PASSWORD_${stack.toUpperCase()}`,
  // value comes from encrypted Pulumi config, never written to state
  value: rawSecrets.apply((s) => s.dbPassword),
  // scopes restrict which Workers may bind this secret
  scopes: [{ type: "workers_scripts", name: `api-worker-${stack}` }],
});

export const stripeKey = new cloudflare.SecretsStoreSecret("stripe-api-key", {
  accountId,
  storeId: secretsStore.id,
  name: `STRIPE_API_KEY_${stack.toUpperCase()}`,
  value: rawSecrets.apply((s) => s.stripeKey),
  // omit scopes to allow any Worker in the account to bind
});
```

## 4. Bind Store Secrets to a Worker

```typescript
// worker.ts
import { dbPassword, stripeKey } from "./secrets";

export const apiWorker = new cloudflare.WorkerScript("api-worker", {
  accountId,
  name: `api-worker-${stack}`,
  content: pulumi.asset.FileAsset("./dist/index.js"),
  module: true,

  secretsStoreSecretBindings: [
    {
      name: "DB_PASSWORD",     // env var name inside the Worker
      secretName: dbPassword.name,
      storeId: secretsStore.id,
    },
    {
      name: "STRIPE_API_KEY",
      secretName: stripeKey.name,
      storeId: secretsStore.id,
    },
  ],
});
```

Inside the Worker the secret is accessed as a plain string:

```typescript
// src/index.ts
export interface Env {
  DB_PASSWORD: string;
  STRIPE_API_KEY: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // env.DB_PASSWORD resolves to the current store secret value at runtime
    const db = await connectDb({ password: env.DB_PASSWORD });
    return new Response("ok");
  },
};
```

## 5. Secret Rotation Without Worker Redeployment

Rotating the secret creates a new store version; Workers pick up the latest value
on the next request without redeployment:

```typescript
// rotation.ts — run via `pulumi up` after updating config
export const dbPasswordV2 = new cloudflare.SecretsStoreSecret("db-password-v2", {
  accountId,
  storeId: secretsStore.id,
  name: `DB_PASSWORD_${stack.toUpperCase()}`, // same name = new version
  value: newDbPassword,                        // new value from config
  scopes: dbPassword.scopes,
});
```

```bash
# Verify the secret was updated (value is masked in response)
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/secrets_store/stores/${STORE_ID}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {name, modified_on}'
```

## 6. Multi-Worker Shared Secret Pattern

```typescript
// shared-secrets.ts
const workerNames = [
  `api-worker-${stack}`,
  `webhook-worker-${stack}`,
  `cron-worker-${stack}`,
];

// One secret, scoped to multiple Workers
export const internalHmacKey = new cloudflare.SecretsStoreSecret(
  "internal-hmac-key",
  {
    accountId,
    storeId: secretsStore.id,
    name: "INTERNAL_HMAC_KEY",
    value: config.requireSecret("internalHmacKey"),
    scopes: workerNames.map((name) => ({
      type: "workers_scripts" as const,
      name,
    })),
  }
);
```

## Anti-patterns

- **Storing secrets in Pulumi stack outputs** — `export const mySecret = someSecret.value`
  writes the plaintext into the Pulumi backend. Always treat `SecretsStoreSecret.value`
  as write-only and never export it as a stack output.
- **One store per Worker** — stores are account-level containers. Creating dozens of
  stores adds operational overhead; use `scopes` on individual secrets to enforce
  Worker-level isolation without multiplying stores.
- **Skipping scopes on high-value secrets** — without scopes any Worker can bind a
  secret. Set explicit `scopes` on credentials with blast-radius impact (payment keys,
  CA private keys).
- **Mixing Secrets Store with per-Worker `wrangler secret put`** — the two mechanisms
  work independently but create confusion during rotation. Standardise on one approach
  per project.

## Gotchas

- `SecretsStoreSecret` is write-only: `pulumi stack export` shows the resource ID but
  not the value. You cannot use Pulumi to read back a stored secret value.
- Deleting a `SecretsStoreSecret` resource immediately removes all versions. Workers
  bound to that secret will fail with a missing binding error until redeployed with an
  updated binding.
- The `scopes[].name` field must match the Worker script name exactly, not the Worker's
  custom domain or route. Use `cloudflare.WorkerScript.name` output to avoid typos.
- Pulumi provider versions below 5.20 lack `SecretsStoreSecret`; the resource silently
  falls back to a plain `cloudflare_workers_secret` which is per-Worker.

## Verification

```bash
# List all secrets in the store
pulumi stack output secretsStoreId | xargs -I{} curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/secrets_store/stores/{}/secrets" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].name'

# Confirm Worker has the binding
wrangler deployments list --name "api-worker-production" | head -5

# Test that the Worker resolves the secret at runtime
curl -s https://api.example.com/health | jq '.dbConnected'
```

## Related

- `workers-secrets-rotation-automation.md` — automated rotation runbook
- `pulumi-esc-secrets-config-management.md` — ESC-based secret injection at deploy time
- `vault-cloudflare-workers-dynamic-secrets.md` — HashiCorp Vault as alternative secret source
- `pulumi-cloudflare-workers-infrastructure-as-code.md` — Worker provisioning patterns

## Sources

- Cloudflare Secrets Store docs: https://developers.cloudflare.com/workers/runtime-apis/bindings/secrets-store/
- Pulumi `cloudflare.SecretsStoreSecret`: https://www.pulumi.com/registry/packages/cloudflare/api-docs/secretsstoresecret/
- Secret scoping reference: https://developers.cloudflare.com/workers/configuration/secrets/#secrets-store
