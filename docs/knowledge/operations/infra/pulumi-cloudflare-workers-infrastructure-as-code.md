# Pulumi Cloudflare Workers Infrastructure as Code

- Date: 2026-08-22
- Author: example.com
- Status: production

## Managing Cloudflare Workers Resources with Pulumi

Terraform has long been the default IaC choice for Cloudflare resources, but Pulumi's `@pulumi/cloudflare` provider offers a compelling alternative when your team is already in TypeScript and wants actual programming language constructs—loops, conditionals, abstractions—instead of HCL templating. The provider wraps the same Cloudflare API surface, so feature parity is near-complete, and the state model follows Pulumi's standard backends (S3, Azure Blob, GCS, or Pulumi Cloud).

The key difference from the Terraform Cloudflare provider is that resource definitions live inside ordinary TypeScript modules. You can extract a `createWorkerWithD1` helper, import it across stacks, and unit-test it with Pulumi's mocking SDK—none of which is idiomatic in HCL without heavy use of modules. For organisations that already run Pulumi for AWS or GCP resources, consolidating Cloudflare into the same pipeline removes a separate `tofu`/`terraform` workflow.

Pulumi state is per-stack. A `staging` stack and a `prod` stack each hold independent state files, so a misconfigured `pulumi up` in staging cannot touch prod. Config values (secrets encrypted with a KMS key or Pulumi Cloud ESC) are stack-scoped, making the staging/prod split clean without workspace juggling.

## Context

- Pulumi CLI ≥ 3.110, Node 20+
- `@pulumi/cloudflare` ≥ 5.x (wraps Cloudflare provider v4)
- Cloudflare account with Workers Paid plan for D1 production limits
- State stored in S3 (example) with a separate DynamoDB lock table

## Stack Initialisation and Config

```bash
pulumi stack init staging --secrets-provider="awskms://alias/pulumi-secrets"
pulumi config set cloudflare:apiToken --secret   # never commit
pulumi config set cloudflare:accountId cf-acct-xxxxx
pulumi config set workerEnv staging
```

```typescript
// Pulumi.staging.yaml is committed; secrets are ciphertext only
// pulumi/index.ts — top-level entrypoint
import * as pulumi from "@pulumi/pulumi";
import { createWorkerStack } from "./stacks/worker";

const cfg = new pulumi.Config();
const env = cfg.require("workerEnv"); // "staging" | "prod"

export const { workerUrl, d1DatabaseId, kvNamespaceId } =
  createWorkerStack(env);
```

## Workers, D1, KV, R2, and Queues Resources

```typescript
// pulumi/stacks/worker.ts
import * as cf from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";
import * as fs from "fs";

export function createWorkerStack(env: string) {
  const accountId = new pulumi.Config("cloudflare").require("accountId");
  const isProd = env === "prod";

  // --- D1 database ---
  const db = new cf.D1Database(`api-db-${env}`, {
    accountId,
    name: `api-db-${env}`,
  });

  // --- KV namespace ---
  const kv = new cf.WorkersKvNamespace(`cache-${env}`, {
    accountId,
    title: `cache-${env}`,
  });

  // --- R2 bucket ---
  const bucket = new cf.R2Bucket(`assets-${env}`, {
    accountId,
    name: `assets-${env}`,
    location: "WEUR",
  });

  // --- Queue ---
  const queue = new cf.Queue(`jobs-${env}`, {
    accountId,
    name: `jobs-${env}`,
  });

  // --- Worker script ---
  const script = new cf.WorkerScript(`api-worker-${env}`, {
    accountId,
    name: `api-worker-${env}`,
    content: fs.readFileSync("../dist/worker.js", "utf-8"),
    d1DatabaseBindings: [
      { name: "DB", databaseId: db.id },
    ],
    kvNamespaceBindings: [
      { name: "CACHE", namespaceId: kv.id },
    ],
    r2BucketBindings: [
      { name: "ASSETS", bucketName: bucket.name },
    ],
    queueBindings: [
      { binding: "JOBS", queue: queue.name },
    ],
    plainTextBindings: [
      { name: "ENV", text: env },
    ],
    logpush: isProd,
  });

  // --- Custom domain / route ---
  const subdomain = isProd ? "api" : `api-${env}`;
  const route = new cf.WorkerRoute(`api-route-${env}`, {
    zoneId: new pulumi.Config("cloudflare").require("zoneId"),
    pattern: `${subdomain}.example.com/*`,
    scriptName: script.name,
  });

  return {
    workerUrl: pulumi.interpolate`https://${subdomain}.example.com`,
    d1DatabaseId: db.id,
    kvNamespaceId: kv.id,
  };
}
```

## Stack Separation for Staging and Prod

```typescript
// pulumi/stacks/pipeline.ts — cross-stack references
import * as pulumi from "@pulumi/pulumi";

// Read outputs from the shared-infra stack (VPC, DNS zone, etc.)
const sharedInfra = new pulumi.StackReference(
  `acme/shared-infra/${pulumi.getStack()}`
);
const zoneId = sharedInfra.requireOutput("cloudflareZoneId");

// Environments get their own StackReference so prod never reads
// staging outputs by accident.
export { zoneId };
```

```bash
# Deploy staging first, then promote to prod
pulumi up --stack staging --yes
pulumi up --stack prod    --yes
```

## Comparing Pulumi vs Terraform Cloudflare Provider

| Capability | Pulumi `@pulumi/cloudflare` | Terraform `cloudflare/cloudflare` |
|---|---|---|
| Language | TypeScript, Python, Go, C# | HCL / CDK for Terraform |
| State backend | S3, GCS, Pulumi Cloud | S3, GCS, Terraform Cloud |
| Resource coverage | ~95 % parity | Reference implementation |
| Unit testing | Pulumi mock SDK, `jest` | `terratest`, `check` |
| Import existing | `pulumi import` | `terraform import` |
| Drift detection | `pulumi refresh` | `terraform plan` |
| Secret handling | ESC / `--secrets-provider` | Vault provider, `sensitive()` |

Terraform's provider ships same-day with Cloudflare API changes because Cloudflare maintains it. Pulumi's provider is auto-generated from the Terraform provider via the bridging tool, so there is typically a 1–7 day lag for brand-new resources.

## Anti-patterns

- Sharing a single Pulumi stack for staging and prod—use `pulumi.getStack()` to branch, not config flags in a monolithic stack.
- Embedding the Worker bundle as a base64 literal in `index.ts`—keep build artifacts outside the Pulumi project and reference the compiled path.
- Storing `cloudflare:apiToken` in plaintext config—always use `--secret` and a KMS secrets provider.
- Using `dependsOn` everywhere instead of natural output references; Pulumi infers dependencies from output chains automatically.

## Gotchas

- `cf.WorkerScript` replaces the entire script on each `pulumi up`, including bindings. If a D1 migration is in progress, the old binding is live until the new script is deployed atomically.
- D1 database names must be globally unique within an account—prefix with env explicitly.
- Pulumi's bridged provider may not expose the latest `compatibility_flags`; use `customTimeouts` or an `Overlay` resource to pass raw API bodies.
- `pulumi destroy` on a prod stack deletes D1 databases. Enable state locking and require MFA for prod stack operations via Pulumi Cloud RBAC.

## Verification

```bash
# Preview without applying
pulumi preview --stack staging --diff

# Confirm D1 database exists after deploy
wrangler d1 list

# Confirm Worker is deployed
wrangler whoami && curl -sf https://api-staging.example.com/health
```

## Related

- `/documentation/docs/policies/infra/terraform-cloudflare-provider-workers-d1.md`
- `/documentation/docs/policies/infra/pulumi-cloudflare-provider-advanced.md`
- `/documentation/docs/policies/infra/wrangler-toml-multi-environment-config.md`
- `/documentation/docs/policies/infra/cloudflare-zero-trust-staging-prod-isolation.md`
- `/documentation/docs/policies/infra/iac-best-practices.md`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/
- https://developers.cloudflare.com/workers/
- https://www.pulumi.com/docs/concepts/stack/
- https://github.com/pulumi/pulumi-cloudflare
