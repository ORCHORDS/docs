# Pulumi Automation API Cloudflare CI Pipeline
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Standard Pulumi CLI-based CI workflows shell out to `pulumi up` inside GitHub Actions
or a custom runner. This works for simple stacks but breaks down when you need dynamic
stack selection, programmatic output consumption, multi-stack orchestration (e.g. create
a preview stack per PR then destroy it), or embedded infrastructure provisioning inside
application code. The Pulumi Automation API lets you drive the full Pulumi lifecycle as
a TypeScript library call with no CLI dependency.

## Context

The Pulumi Automation API (`@pulumi/pulumi/automation`) provides `LocalWorkspace` and
`Stack` classes that wrap the Pulumi engine in-process. You write a Node.js/TypeScript
script that runs `stack.up()`, reads outputs, and calls `stack.destroy()` – all without
exec'ing the CLI. For Cloudflare Workers deployments this replaces bespoke bash glue
with typed, testable infrastructure code running inside the same CI job that builds the
Worker bundle.

State can be stored in Pulumi Cloud, Cloudflare R2 (via the `azblob` S3-compatible
driver with the R2 endpoint), or a local backend. Secrets use Pulumi ESC or a
passphrase-encrypted state file.

## Setting up the Automation API Project

```
infra/
  automation/
    package.json
    tsconfig.json
    src/
      deploy.ts          # entrypoint called by CI
      stacks/
        workers-stack.ts # Pulumi stack program
  dist/
    worker.js            # compiled Worker bundle (built before infra deploy)
```

```json
// infra/automation/package.json
{
  "name": "cf-automation",
  "private": true,
  "scripts": {
    "deploy": "tsx src/deploy.ts",
    "destroy": "tsx src/deploy.ts --destroy"
  },
  "dependencies": {
    "@pulumi/pulumi": "^3.120.0",
    "@pulumi/cloudflare": "^5.40.0"
  },
  "devDependencies": {
    "tsx": "^4.0.0",
    "typescript": "^5.5.0"
  }
}
```

## The Stack Program

```typescript
// infra/automation/src/stacks/workers-stack.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";
import * as fs from "fs";
import * as path from "path";

export interface WorkersStackArgs {
  accountId: string;
  workerName: string;
  bundlePath: string;
  kvNamespaceName: string;
}

export function workersProgram(args: WorkersStackArgs) {
  return async () => {
    const workerContent = fs.readFileSync(
      path.resolve(args.bundlePath),
      "utf-8"
    );

    const kvNamespace = new cloudflare.WorkersKvNamespace("kv", {
      accountId: args.accountId,
      title: args.kvNamespaceName,
    });

    const script = new cloudflare.WorkersScript("worker", {
      accountId: args.accountId,
      name: args.workerName,
      content: workerContent,
      module: true,
      kvNamespaceBindings: [
        {
          name: "KV",
          namespaceId: kvNamespace.id,
        },
      ],
    });

    return {
      workerName: script.name,
      kvNamespaceId: kvNamespace.id,
    };
  };
}
```

## The Automation Entrypoint

```typescript
// infra/automation/src/deploy.ts
import { LocalWorkspace, Stack } from "@pulumi/pulumi/automation";
import { workersProgram } from "./stacks/workers-stack";

const STACK_NAME = process.env.PULUMI_STACK ?? "dev";
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const WORKER_NAME = `my-worker-${STACK_NAME}`;
const BUNDLE_PATH = "../../dist/worker.js";

const args = {
  accountId: ACCOUNT_ID,
  workerName: WORKER_NAME,
  bundlePath: BUNDLE_PATH,
  kvNamespaceName: `my-kv-${STACK_NAME}`,
};

async function main() {
  const destroy = process.argv.includes("--destroy");

  console.log(`[automation] stack=${STACK_NAME} destroy=${destroy}`);

  // Use R2 as remote backend (S3-compatible with custom endpoint)
  const workspace = await LocalWorkspace.createOrSelectStack(
    {
      stackName: STACK_NAME,
      projectName: "cloudflare-workers",
      program: workersProgram(args),
    },
    {
      envVars: {
        PULUMI_BACKEND_URL: process.env.PULUMI_BACKEND_URL!,  // s3://bucket?endpoint=...
        PULUMI_CONFIG_PASSPHRASE: process.env.PULUMI_CONFIG_PASSPHRASE!,
        CLOUDFLARE_API_TOKEN: process.env.CLOUDFLARE_API_TOKEN!,
      },
    }
  );

  // Install required Pulumi plugins in-process
  await workspace.installPlugin("cloudflare", "v5.40.0");

  if (destroy) {
    console.log("[automation] destroying stack...");
    const result = await workspace.stack!.destroy({ onOutput: console.log });
    console.log(`[automation] destroy summary:`, result.summary);
    return;
  }

  console.log("[automation] previewing changes...");
  const preview = await workspace.stack!.preview({ onOutput: console.log });
  console.log(`[automation] change summary:`, preview.changeSummary);

  console.log("[automation] deploying...");
  const up = await workspace.stack!.up({
    onOutput: console.log,
    expectNoChanges: false,
  });

  console.log("[automation] outputs:");
  for (const [key, val] of Object.entries(up.outputs)) {
    console.log(`  ${key} = ${val.value}`);
  }

  // Surface outputs to CI environment (GitHub Actions)
  if (process.env.GITHUB_OUTPUT) {
    const fs = await import("fs");
    fs.appendFileSync(
      process.env.GITHUB_OUTPUT,
      `worker_name=${up.outputs["workerName"]?.value}\n`
    );
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

## GitHub Actions Workflow Integration

```yaml
# .github/workflows/deploy-workers.yml
name: Deploy Cloudflare Workers

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # for OIDC if used

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Build Worker bundle
        run: pnpm --filter worker build

      - name: Deploy infrastructure
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          # R2-backed Pulumi state
          PULUMI_BACKEND_URL: ${{ secrets.PULUMI_BACKEND_URL }}
          PULUMI_CONFIG_PASSPHRASE: ${{ secrets.PULUMI_CONFIG_PASSPHRASE }}
          PULUMI_STACK: ${{ github.ref == 'refs/heads/main' && 'production' || format('pr-{0}', github.event.pull_request.number) }}
        run: pnpm --filter infra-automation deploy

      - name: Destroy preview stack on PR close
        if: github.event_name == 'pull_request' && github.event.action == 'closed'
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          PULUMI_BACKEND_URL: ${{ secrets.PULUMI_BACKEND_URL }}
          PULUMI_CONFIG_PASSPHRASE: ${{ secrets.PULUMI_CONFIG_PASSPHRASE }}
          PULUMI_STACK: pr-${{ github.event.pull_request.number }}
        run: pnpm --filter infra-automation destroy
```

## R2 as Pulumi State Backend

R2 is S3-compatible and avoids Pulumi Cloud dependency for self-hosted teams:

```bash
# Create the state bucket once
wrangler r2 bucket create pulumi-state

# Set the backend URL in CI secrets (azblob driver works via S3 compat endpoint)
# Format: s3://bucket-name?endpoint=https://ACCOUNT_ID.r2.cloudflarestorage.com&region=auto
PULUMI_BACKEND_URL="s3://pulumi-state?endpoint=https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com&region=auto&disableSSL=false&s3ForcePathStyle=true"
```

Credentials for R2 must be an R2-scoped API token (not a full account token):

```hcl
# terraform/r2-state-bucket/main.tf
resource "cloudflare_r2_bucket" "pulumi_state" {
  account_id = var.account_id
  name       = "pulumi-state"
  location   = "WNAM"
}

resource "cloudflare_api_token" "pulumi_state_rw" {
  name = "pulumi-state-rw"
  policy {
    permission_groups = [
      data.cloudflare_api_token_permission_groups.all.r2["Workers R2 Storage Write"]
    ]
    resources = {
      "com.cloudflare.edge.r2.bucket.${cloudflare_r2_bucket.pulumi_state.id}" = "*"
    }
  }
}
```

## Anti-patterns

- **Calling `LocalWorkspace.create` instead of `createOrSelectStack`** – fails on the
  second run because the stack already exists.
- **Hard-coding `installPlugin` version without pinning** – causes drift when a new
  plugin version changes resource behavior unexpectedly.
- **Not capturing `onOutput` during `up()`** – CI logs show nothing until the run
  completes; streaming output is essential for debugging long deployments.
- **Using a full-account API token for the Pulumi state R2 backend** – follow
  least-privilege: scope to R2 write on the specific bucket only.

## Gotchas

- `LocalWorkspace.installPlugin` downloads the plugin binary at runtime; cache
  `~/.pulumi/plugins` between CI runs to avoid repeated downloads.
- Automation API does not inherit `PULUMI_ACCESS_TOKEN` automatically when using a
  self-managed backend; set `PULUMI_CONFIG_PASSPHRASE` explicitly.
- Stack outputs typed as `pulumi.Output<string>` come back as plain strings in the
  Automation API result; no `apply()` unwrapping is needed.
- Concurrent `stack.up()` calls on the same stack name will deadlock on the state lock.
  Use stack name namespacing (`pr-{number}`) to avoid contention.

## Verification

```bash
# Local smoke test
CLOUDFLARE_ACCOUNT_ID=xxx \
CLOUDFLARE_API_TOKEN=xxx \
PULUMI_BACKEND_URL="file://~/.pulumi/state" \
PULUMI_CONFIG_PASSPHRASE=dev \
PULUMI_STACK=dev \
pnpm --filter infra-automation deploy

# Confirm Worker deployed
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result[].id' | grep my-worker
```

## Related

- `pulumi-cloudflare-workers-infrastructure-as-code.md` – declarative Pulumi stack patterns
- `pulumi-esc-secrets-config-management.md` – ESC for secrets in Pulumi stacks
- `pulumi-cloudflare-d1-database-iac.md` – D1 resource management with Pulumi
- `github-actions-oidc-cloudflare.md` – OIDC for API token-free CI authentication
- `r2-lifecycle-archival-glacier-strategy.md` – R2 state bucket housekeeping

## Sources

- https://www.pulumi.com/docs/iac/packages-and-automation/automation-api/
- https://www.pulumi.com/docs/iac/packages-and-automation/automation-api/getting-started-automation-api-typescript/
- https://github.com/pulumi/pulumi/tree/master/sdk/nodejs/automation
- https://www.pulumi.com/docs/iac/concepts/state-and-backends/
- https://developers.cloudflare.com/r2/api/s3/api/
