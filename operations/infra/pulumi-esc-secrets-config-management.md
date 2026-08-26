# Pulumi ESC: Environments, Secrets, and Configuration Management

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Teams juggle environment-specific secrets and config across Cloudflare Workers, AWS Lambda, and CI/CD
pipelines without a single source of truth, leading to drift and accidental secret exposure in plaintext YAML.

## Context
Pulumi ESC (Environments, Secrets, and Configuration) is a managed secrets and config orchestration
layer that sits on top of existing secret stores (Vault, AWS Secrets Manager, 1Password) and exposes
a unified API for consuming them in Pulumi IaC, `esc run` wrappers, and direct SDK calls.
It supports hierarchical environment composition, OIDC-based dynamic credentials, and versioned snapshots.

## Defining an ESC Environment

ESC environments are authored in YAML and stored in the Pulumi Cloud backend. A base environment
holds shared values; derived environments import and override selectively.

```yaml
# environments/base.yaml
values:
  cloudflare:
    accountId: fn::secret("cf-account-id")
    apiToken:
      fn::secret:
        <redacted-secret> ${pulumi.secret("cf-api-token-b64")}
  app:
    logLevel: info
    region: us-east-1
  aws:
    fn::open::aws-login:
      oidc:
        roleArn: arn:aws:iam::123456789012:role/pulumi-esc-deploy
        sessionName: pulumi-esc-${context.rootEnvironment.name}
        duration: 1h
```

```yaml
# environments/production.yaml
imports:
  - base

values:
  app:
    logLevel: warn        # override
  pulumiConfig:
    cloudflare:accountId: ${cloudflare.accountId}
    cloudflare:apiToken:  ${cloudflare.apiToken}
```

## Consuming ESC in Pulumi TypeScript Programs

The `@pulumi/esc-sdk` package resolves environment values at preview/up time without hard-coding
secret references. The Pulumi stack automatically inherits values set under `pulumiConfig`.

```typescript
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const config = new pulumi.Config();

// These arrive from ESC environment pulumiConfig section — no .env needed.
const accountId = config.requireSecret("cloudflare:accountId");
const apiToken  = <redacted-secret>"cloudflare:apiToken");

const provider = new cloudflare.Provider("cf", { apiToken });

const worker = new cloudflare.WorkerScript("api-worker", {
  accountId,
  name: "api-worker",
  content: pulumi.asset.FileAsset("./dist/worker.js"),
}, { provider });

export const workerId = worker.id;
```

## Running Commands with ESC-Injected Credentials

`esc run` injects environment variables into a subprocess without writing them to disk,
replacing the common pattern of `export $(cat .env)`.

```bash
# Open ESC environment and run wrangler deploy inside it
esc run example-org/example-repo -- wrangler deploy --env production

# Open environment and run arbitrary shell — useful in CI
esc run example-org/example-repo -- bash -c 'npx vitest run && wrangler deploy'
```

CI/CD integration (GitHub Actions):

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pulumi/esc-action@v1
        with:
          environment: example-org/example-repo
          # Exports ESC values as env vars for subsequent steps
      - run: wrangler deploy --env production
```

## Environment Composition and Promotion Gates

Nested imports enable a promotion model where each tier adds stricter overrides and
access controls without duplicating base config.

```yaml
# environments/staging.yaml
imports:
  - base

values:
  app:
    logLevel: debug
  cloudflare:
    workerName: api-worker-staging

---
# environments/production.yaml
imports:
  - staging     # inherits staging, then overrides

values:
  app:
    logLevel: warn
  cloudflare:
    workerName: api-worker-production
  # Narrow access: only deploy role can open this environment
  pulumiConfig:
    cloudflare:workerName: ${cloudflare.workerName}
```

Access policies are set in the Pulumi Cloud UI or via `pulumi org set-policy-group`.
Production environments should be restricted to CI service accounts and on-call engineers.

## Rotating Secrets Without Code Changes

Because Pulumi programs read secrets from ESC at runtime, rotating a secret requires
only updating the ESC environment — no code changes, no redeploys of the secret value itself.

```typescript
// scripts/rotate-cf-token.ts
import { EscClient } from "@pulumi/esc-sdk";

const client = new EscClient();

async function rotateCloudflareToken(newToken: string) {
  await client.updateEnvironment("orchords", "base", {
    values: {
      cloudflare: {
        apiToken: { "fn::secret": newToken },
      },
    },
  });
  console.log("ESC environment updated — next `pulumi up` will pick up the new token");
}

rotateCloudflareToken(process.env.NEW_CF_TOKEN!);
```

## Anti-patterns
- Storing raw secrets in `pulumiConfig` inside `Pulumi.<stack>.yaml` — use ESC instead
- Opening ESC environments in application runtime code — ESC is a build/deploy-time concern, not a live secrets backend
- Skipping environment composition and maintaining N independent environments by copy-paste
- Granting all team members `open` permission on production environments — use RBAC roles

## Gotchas
- `esc run` requires `PULUMI_ACCESS_TOKEN` or a logged-in Pulumi CLI session; add it to CI secrets
- Dynamic AWS credentials via OIDC have a max duration enforced by the IAM role's `MaxSessionDuration`
- ESC environment YAML uses `fn::secret` to encrypt a value — plain `value:` fields are stored unencrypted
- Stack `pulumiConfig` keys must match the provider config namespace exactly (e.g. `cloudflare:apiToken`)
- Versioned environment snapshots are immutable; rollback means pinning `imports` to a specific version tag

## Verification
```bash
# Preview resolved environment (secrets redacted)
esc env open example-org/example-repo --format json

# Check that a Pulumi program picks up config from ESC
pulumi preview --stack production --non-interactive 2>&1 | grep "cloudflare:apiToken"

# Validate no plaintext secrets appear in stack config file
grep -r "apiToken\|apiKey\|secret" Pulumi.production.yaml && echo "FAIL: secrets in stack config" || echo "OK"
```

## Related
- `/documentation/categories/infra/pulumi-cloudflare-workers-infrastructure-as-code.md`
- `/documentation/categories/infra/pulumi-cloudflare-provider-advanced.md`
- `/documentation/categories/infra/secrets-management-vault.md`
- `/documentation/categories/infra/workers-secrets-rotation-automation.md`

## Sources
- https://www.pulumi.com/docs/esc/
- https://www.pulumi.com/docs/esc/get-started/
- https://www.pulumi.com/docs/esc/integrations/dynamic-login-credentials/aws-login/
- https://github.com/pulumi/esc-action
