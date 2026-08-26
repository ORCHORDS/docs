# Pulumi for Cloudflare Workers Infrastructure as Code

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team writes TypeScript everywhere and wants to define Cloudflare Workers infrastructure in the same language — no HCL context-switching. You want type-safe resource definitions, reusable component abstractions, and programmatic deployments via the Pulumi Automation API for custom deployment pipelines.

## Context

Pulumi's `@pulumi/cloudflare` package wraps the Cloudflare Terraform provider, exposing it as a typed TypeScript (or Python/Go) SDK. Each Pulumi stack maps to an environment. The Automation API allows embedding Pulumi inside a Node.js program — useful for multi-tenant deployments where each tenant gets isolated resources.

Pulumi state can be stored in Pulumi Cloud (free tier available) or self-hosted on S3/GCS/Azure Blob.

## Solution

```typescript
// index.ts — main Pulumi program
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();
const accountId = config.require("accountId");
const zoneId = config.require("zoneId");
const environment = pulumi.getStack(); // "dev" | "staging" | "production"

// ── KV Namespaces ───────────────────────────────────────────────
const sessionsKv = new cloudflare.WorkersKvNamespace("sessions", {
  accountId,
  title: `sessions-${environment}`,
});

const configKv = new cloudflare.WorkersKvNamespace("config", {
  accountId,
  title: `config-${environment}`,
});

// ── D1 Database ─────────────────────────────────────────────────
const appDb = new cloudflare.D1Database("app-db", {
  accountId,
  name: `app-db-${environment}`,
});

// ── R2 Buckets ──────────────────────────────────────────────────
const assetsBucket = new cloudflare.R2Bucket("assets", {
  accountId,
  name: `assets-${environment}`,
  location: "EEUR",
});

const uploadsBucket = new cloudflare.R2Bucket("uploads", {
  accountId,
  name: `uploads-${environment}`,
  location: "EEUR",
});

// ── Worker Script ────────────────────────────────────────────────
import * as fs from "fs";

const workerContent = fs.readFileSync("dist/worker.js", "utf-8");

const apiWorker = new cloudflare.WorkerScript("api", {
  accountId,
  name: `api-${environment}`,
  content: workerContent,
  module: true,
  kvNamespaceBindings: [
    {
      name: "SESSIONS",
      namespaceId: sessionsKv.id,
    },
    {
      name: "CONFIG",
      namespaceId: configKv.id,
    },
  ],
  d1DatabaseBindings: [
    {
      name: "DB",
      databaseId: appDb.id,
    },
  ],
  r2BucketBindings: [
    {
      name: "ASSETS",
      bucketName: assetsBucket.name,
    },
  ],
  plainTextBindings: [
    {
      name: "ENVIRONMENT",
      text: environment,
    },
  ],
  secretTextBindings: [
    {
      name: "JWT_SECRET",
      text: config.requireSecret("jwtSecret"),
    },
  ],
});

// ── Worker Route ─────────────────────────────────────────────────
const routePattern =
  environment === "production"
    ? "api.example.com/*"
    : `api-${environment}.example.com/*`;

const apiRoute = new cloudflare.WorkerRoute("api-route", {
  zoneId,
  pattern: routePattern,
  scriptName: apiWorker.name,
});

// ── Stack Outputs ─────────────────────────────────────────────────
export const kvSessionsId = sessionsKv.id;
export const kvConfigId = configKv.id;
export const d1DatabaseId = appDb.id;
export const r2AssetsBucket = assetsBucket.name;
export const r2UploadsBucket = uploadsBucket.name;
export const workerRoute = routePattern;
```

```typescript
// components/WorkerService.ts — reusable component abstraction
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

export interface WorkerServiceArgs {
  accountId: pulumi.Input<string>;
  environment: string;
  workerContent: string;
  kvNamespaces?: Array<{ bindingName: string; namespace: cloudflare.WorkersKvNamespace }>;
  d1Databases?: Array<{ bindingName: string; database: cloudflare.D1Database }>;
  r2Buckets?: Array<{ bindingName: string; bucket: cloudflare.R2Bucket }>;
  secrets?: Array<{ name: string; value: pulumi.Output<string> }>;
  plainText?: Array<{ name: string; value: string }>;
}

export class WorkerService extends pulumi.ComponentResource {
  public readonly workerName: pulumi.Output<string>;

  constructor(
    name: string,
    args: WorkerServiceArgs,
    opts?: pulumi.ComponentResourceOptions
  ) {
    super("orchords:cloudflare:WorkerService", name, {}, opts);

    const script = new cloudflare.WorkerScript(
      name,
      {
        accountId: args.accountId,
        name: `${name}-${args.environment}`,
        content: args.workerContent,
        module: true,
        kvNamespaceBindings: (args.kvNamespaces ?? []).map((kv) => ({
          name: kv.bindingName,
          namespaceId: kv.namespace.id,
        })),
        d1DatabaseBindings: (args.d1Databases ?? []).map((db) => ({
          name: db.bindingName,
          databaseId: db.database.id,
        })),
        r2BucketBindings: (args.r2Buckets ?? []).map((r2) => ({
          name: r2.bindingName,
          bucketName: r2.bucket.name,
        })),
        secretTextBindings: (args.secrets ?? []).map((s) => ({
          name: s.name,
          text: s.value,
        })),
        plainTextBindings: (args.plainText ?? []).map((p) => ({
          name: p.name,
          text: p.value,
        })),
      },
      { parent: this }
    );

    this.workerName = script.name;
    this.registerOutputs({ workerName: this.workerName });
  }
}
```

```typescript
// automation/deploy.ts — Pulumi Automation API for programmatic deploys
import { LocalWorkspace, Stack } from "@pulumi/pulumi/automation";
import * as path from "path";

async function deployTenant(tenantId: string, accountId: string): Promise<void> {
  const stackName = `tenant-${tenantId}`;
  const workDir = path.join(__dirname, "..");

  const stack = await LocalWorkspace.createOrSelectStack({
    stackName,
    workDir,
    projectName: "orchords-workers",
  });

  // Set per-tenant config
  await stack.setConfig("accountId", { value: accountId });
  await stack.setConfig("zoneId", { value: process.env.ZONE_ID! });
  await stack.setConfig("jwtSecret", {
    value: process.env[`JWT_SECRET_${tenantId.toUpperCase()}`]!,
    secret: true,
  });

  console.log(`Deploying stack: ${stackName}`);

  const upResult = await stack.up({ onOutput: console.log });

  console.log(`Deployment complete. Summary:`, upResult.summary);
  console.log(`KV Sessions ID:`, upResult.outputs["kvSessionsId"]?.value);
  console.log(`D1 Database ID:`, upResult.outputs["d1DatabaseId"]?.value);
}

// Preview-only (no changes applied)
async function previewStack(environment: string): Promise<void> {
  const stack = await LocalWorkspace.selectStack({
    stackName: environment,
    workDir: path.join(__dirname, ".."),
    projectName: "orchords-workers",
  });

  const preview = await stack.preview({ onOutput: console.log });
  console.log(`Preview changeSummary:`, preview.changeSummary);
}

deployTenant(process.env.TENANT_ID!, process.env.CF_ACCOUNT_ID!);
```

```yaml
# Pulumi.yaml — project definition
name: orchords-workers
runtime: nodejs
description: Cloudflare Workers infrastructure for example.com

# Pulumi.production.yaml — stack config (committed, no secrets)
config:
  cloudflare:apiToken:
    secure: AAABAxxxxxxx  # encrypted by Pulumi
  orchords-workers:accountId: "abc123def456"
  orchords-workers:zoneId: "zonexxxxxxxx"
```

## Implementation Details

**Package installation:**
```bash
npm install @pulumi/pulumi @pulumi/cloudflare
pulumi login  # or pulumi login --local for file-based state
```

**Environment-specific stacks:**
```bash
pulumi stack init dev
pulumi stack init staging
pulumi stack init production

# Select and deploy
pulumi stack select production
pulumi up --yes
```

**Stack outputs consumed by other systems:**
```bash
# Read a stack output from CI
KV_ID=$(pulumi stack output kvSessionsId --stack production)
echo "KV namespace: $KV_ID"
```

**Cross-stack references** — share outputs between Pulumi programs:
```typescript
const infraStack = new pulumi.StackReference("example-org/example-repo/production");
const kvId = infraStack.getOutput("kvSessionsId");
```

## Anti-patterns

- **Committing `Pulumi.<stack>.yaml` with plaintext secrets** — always use `pulumi config set --secret` so values are encrypted in the config file.
- **Reading `fs.readFileSync` at program evaluation time without a build step** — ensure `dist/worker.js` exists before `pulumi up`. Add a pre-up build hook or run `npm run build && pulumi up`.
- **Sharing one stack across environments** — use separate stacks; stack names encode the environment, enabling independent `pulumi up` and `pulumi destroy`.
- **Using Automation API without error handling** — wrap `stack.up()` in try/catch; unhandled errors leave stacks in a locked state requiring `pulumi cancel`.
- **Ignoring `pulumi preview` in CI** — always preview on PR, apply only on merge to main.

## Gotchas

- `@pulumi/cloudflare` versions track the Terraform provider; check the [changelog](https://github.com/pulumi/pulumi-cloudflare/releases) before upgrading — breaking resource renames occur between major versions.
- Pulumi serializes resource creation; parallel resource creation requires explicit `pulumi.all([...]).apply(...)` patterns.
- The Automation API locks the stack during `up`/`destroy` — concurrent deployments of the same stack will fail. Use a queue or mutex in multi-tenant scenarios.
- `config.requireSecret()` returns a `pulumi.Output<string>` even in preview — never try to `.get()` it synchronously; use `.apply()` instead.
- Stack outputs are stored in plaintext in state by default — mark sensitive outputs with `{ secret: true }` to encrypt them.

## Verification

```bash
# List stacks and their last update
pulumi stack ls

# See all resources in the production stack
pulumi stack --stack production --show-urns

# Refresh state against live Cloudflare resources
pulumi refresh --stack production

# Verify no drift
pulumi preview --stack production --expect-no-changes

# Check stack outputs
pulumi stack output --stack production --json
```

## Related

- `documentation/docs/policies/infra/workers-terraform-cloudflare-provider.md`
- `documentation/docs/policies/infra/workers-wrangler-environments-matrix.md`
- `documentation/docs/policies/infra/workers-multi-account-deployment.md`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/
- https://www.pulumi.com/docs/iac/packages-and-automation/automation-api/
- https://github.com/pulumi/pulumi-cloudflare
- https://developers.cloudflare.com/workers/
