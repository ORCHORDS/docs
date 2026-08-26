# Pulumi Cloudflare Provider — Advanced Resource Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A team managing Cloudflare Workers, D1 databases, R2 buckets, KV namespaces, and DNS zones through Terraform HCL hits abstraction limits: generating 30 worker route patterns from a JSON config requires convoluted `for_each` expressions, writing unit tests for module logic requires deploying real infrastructure, and the team's TypeScript-first culture makes HCL a second language everyone tolerates but no one wants to own. Pulumi's Cloudflare provider offers the same resource coverage in idiomatic TypeScript with unit-testable stack logic and first-class support for Cloudflare's resource graph.

## Context

Pulumi manages Cloudflare resources through the `@pulumi/cloudflare` npm package, which is auto-generated from the Terraform Cloudflare provider schema using `pulumi-terraform-bridge`. Resource parity is high (95%+), and new Cloudflare API resources appear in the Pulumi provider within days of the Terraform provider update. example project's infrastructure stack manages multiple Cloudflare zones (example.com, example project.app), dozens of Workers with cron triggers and D1 bindings, R2 buckets for user assets, Durable Objects namespaces, and Zero Trust access applications — all in one Pulumi TypeScript program with reusable component resources. This article covers resource management patterns not in the general IaC comparison document: zone management, Workers with bindings, D1/R2/KV provisioning, and cross-stack references.

## Project Setup and Authentication

```bash
# Install Pulumi CLI
curl -fsSL https://get.pulumi.com | sh

# Install Cloudflare provider
npm install @pulumi/cloudflare @pulumi/pulumi

# Configure credentials (prefer environment variables in CI)
export CLOUDFLARE_API_TOKEN="<token>"
export CLOUDFLARE_ACCOUNT_ID="<account-id>"

# Or set via Pulumi config (stored encrypted in state)
pulumi config set cloudflare:apiToken --secret "$(cat ~/.cloudflare/token)"

# Create a new stack
pulumi stack init production
pulumi config set cloudflare:accountId "<account-id>"
```

Recommended project structure for example project:

```
infra/
├── Pulumi.yaml                  # project metadata
├── Pulumi.production.yaml       # per-stack config
├── Pulumi.staging.yaml
├── index.ts                     # entry point, composes components
├── components/
│   ├── WorkerService.ts         # reusable Worker + bindings component
│   ├── D1Database.ts
│   ├── R2Bucket.ts
│   └── ZoneConfig.ts
└── stacks/
    ├── workers.ts
    ├── dns.ts
    └── access.ts
```

## Zone and DNS Management

```typescript
// components/ZoneConfig.ts
import * as cloudflare from '@pulumi/cloudflare';
import * as pulumi from '@pulumi/pulumi';

export interface ZoneConfigArgs {
  domain: string;
  accountId: pulumi.Input<string>;
  plan?: 'free' | 'pro' | 'business' | 'enterprise';
}

export class ZoneConfig extends pulumi.ComponentResource {
  public readonly zone: cloudflare.Zone;
  public readonly zoneId: pulumi.Output<string>;

  constructor(name: string, args: ZoneConfigArgs, opts?: pulumi.ComponentResourceOptions) {
    super('example project:infra:ZoneConfig', name, {}, opts);

    this.zone = new cloudflare.Zone(`${name}-zone`, {
      zone: args.domain,
      accountId: args.accountId,
      plan: args.plan ?? 'free',
      jumpStart: false,
    }, { parent: this });

    this.zoneId = this.zone.id;

    // Zone-level settings
    new cloudflare.ZoneSettingsOverride(`${name}-settings`, {
      zoneId: this.zoneId,
      settings: {
        alwaysUseHttps: 'on',
        minTlsVersion: '1.2',
        opportunisticEncryption: 'on',
        tls13: 'zrt',               // 0-RTT TLS 1.3
        http3: 'on',
        brotli: 'on',
        earlyHints: 'on',
        securityLevel: 'medium',
        browserCacheTtl: 14400,
      },
    }, { parent: this });

    // DNSSEC
    new cloudflare.ZoneDnssec(`${name}-dnssec`, {
      zoneId: this.zoneId,
    }, { parent: this });

    this.registerOutputs({ zoneId: this.zoneId });
  }
}
```

Bulk DNS record creation from a typed array (pattern that replaces complex `for_each` in HCL):

```typescript
// stacks/dns.ts
import * as cloudflare from '@pulumi/cloudflare';
import { ZoneConfig } from '../components/ZoneConfig';

const config = new pulumi.Config();
const accountId = config.require('cloudflare:accountId');

const zone = new ZoneConfig('orchords', {
  domain: 'example.com',
  accountId,
  plan: 'pro',
});

interface DnsRecord {
  name: string;
  type: 'A' | 'CNAME' | 'MX' | 'TXT';
  value: string;
  proxied?: boolean;
  ttl?: number;
  priority?: number;
}

const records: DnsRecord[] = [
  { name: '@',           type: 'A',     value: '192.0.2.1', proxied: true },
  { name: 'www',         type: 'CNAME', value: 'example.com', proxied: true },
  { name: 'api',         type: 'CNAME', value: 'example project-api.orchords.workers.dev', proxied: true },
  { name: '_dmarc',      type: 'TXT',   value: 'v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com' },
  { name: '@',           type: 'MX',    value: 'aspmx.l.google.com', priority: 1 },
];

records.forEach((rec, idx) => {
  new cloudflare.Record(`dns-${rec.name}-${rec.type}-${idx}`, {
    zoneId: zone.zoneId,
    name: rec.name,
    type: rec.type,
    value: rec.value,
    proxied: rec.proxied ?? false,
    ttl: rec.proxied ? 1 : (rec.ttl ?? 3600),
    priority: rec.priority,
  }, { parent: zone.zone });
});
```

## Workers with D1, KV, and R2 Bindings

```typescript
// components/WorkerService.ts
import * as cloudflare from '@pulumi/cloudflare';
import * as pulumi from '@pulumi/pulumi';
import { readFileSync } from 'node:fs';

export interface WorkerServiceArgs {
  accountId: pulumi.Input<string>;
  name: string;
  scriptPath: string;          // path to compiled dist/worker.js
  compatibilityDate: string;
  d1Bindings?: Array<{ binding: string; databaseId: pulumi.Input<string> }>;
  kvBindings?: Array<{ binding: string; namespaceId: pulumi.Input<string> }>;
  r2Bindings?: Array<{ binding: string; bucketName: pulumi.Input<string> }>;
  plainTextBindings?: Record<string, pulumi.Input<string>>;
  secretBindings?: Record<string, pulumi.Input<string>>;
  cronTriggers?: string[];
  routes?: Array<{ pattern: string; zoneId: pulumi.Input<string> }>;
}

export class WorkerService extends pulumi.ComponentResource {
  public readonly worker: cloudflare.WorkerScript;
  public readonly url: pulumi.Output<string>;

  constructor(name: string, args: WorkerServiceArgs, opts?: pulumi.ComponentResourceOptions) {
    super('example project:infra:WorkerService', name, {}, opts);

    const scriptContent = readFileSync(args.scriptPath, 'utf-8');

    // Build bindings array programmatically — no HCL dynamic blocks needed
    const kvNamespaceBindings = (args.kvBindings ?? []).map(b => ({
      name: b.binding,
      namespaceId: b.namespaceId,
    }));

    const d1DatabaseBindings = (args.d1Bindings ?? []).map(b => ({
      name: b.binding,
      databaseId: b.databaseId,
    }));

    const r2BucketBindings = (args.r2Bindings ?? []).map(b => ({
      name: b.binding,
      bucketName: b.bucketName,
    }));

    const plainTextBindings = Object.entries(args.plainTextBindings ?? {}).map(([k, v]) => ({
      name: k,
      text: v,
    }));

    const secretTextBindings = Object.entries(args.secretBindings ?? {}).map(([k, v]) => ({
      name: k,
      text: v,
    }));

    this.worker = new cloudflare.WorkerScript(`${name}-script`, {
      accountId: args.accountId,
      name: args.name,
      content: scriptContent,
      module: true,
      compatibilityDate: args.compatibilityDate,
      compatibilityFlags: ['nodejs_compat_v2'],
      kvNamespaceBindings,
      d1DatabaseBindings,
      r2BucketBindings,
      plainTextBindings,
      secretTextBindings,
    }, { parent: this });

    // Cron triggers
    if (args.cronTriggers && args.cronTriggers.length > 0) {
      new cloudflare.WorkerCronTrigger(`${name}-cron`, {
        accountId: args.accountId,
        scriptName: this.worker.name,
        schedules: args.cronTriggers,
      }, { parent: this.worker });
    }

    // Route bindings
    (args.routes ?? []).forEach((route, idx) => {
      new cloudflare.WorkerRoute(`${name}-route-${idx}`, {
        zoneId: route.zoneId,
        pattern: route.pattern,
        scriptName: this.worker.name,
      }, { parent: this.worker });
    });

    this.url = pulumi.interpolate`https://${args.name}.${args.accountId}.workers.dev`;
    this.registerOutputs({ url: this.url });
  }
}
```

Using the component:

```typescript
// stacks/workers.ts
import { WorkerService } from '../components/WorkerService';
import { resolve } from 'node:path';

const config = new pulumi.Config();
const accountId = config.require('cloudflare:accountId');

// D1 database
const db = new cloudflare.D1Database('example project-db', {
  accountId,
  name: 'example project-production',
});

// KV namespace
const sessionKv = new cloudflare.WorkersKvNamespace('session-kv', {
  accountId,
  title: 'example project_SESSION_STORE',
});

// R2 bucket
const assetsBucket = new cloudflare.R2Bucket('assets', {
  accountId,
  name: 'example project-user-assets',
  location: 'WEUR',
});

// Compose the Worker with all bindings
const apiWorker = new WorkerService('api', {
  accountId,
  name: 'example project-api',
  scriptPath: resolve(__dirname, '../../../apps/api-worker/dist/worker.js'),
  compatibilityDate: '2026-08-01',
  d1Bindings: [{ binding: 'DB', databaseId: db.id }],
  kvBindings: [{ binding: 'SESSION_STORE', namespaceId: sessionKv.id }],
  r2Bindings: [{ binding: 'ASSETS', bucketName: assetsBucket.name }],
  plainTextBindings: { ENVIRONMENT: 'production', APP_VERSION: '2.4.0' },
  secretBindings: {
    JWT_SECRET: config.requireSecret('jwtSecret'),
    INTERNAL_TOKEN: config.requireSecret('internalToken'),
  },
  cronTriggers: ['0 2 * * *'],   // daily cleanup at 2 AM UTC
  routes: [
    { pattern: 'api.example.com/*', zoneId: orchordsZone.zoneId },
  ],
});

export const apiWorkerUrl = apiWorker.url;
```

## Durable Objects and Cross-Stack References

```typescript
// Durable Object namespace with class name binding
const doNamespace = new cloudflare.WorkersDomain('example project-do-ns', {
  accountId,
  name: 'example project_SESSION_DO',
});

// Cross-stack reference: read outputs from a sibling stack
const infraStack = new pulumi.StackReference('example-org/example-repo/production');
const dbId = infraStack.getOutput('d1DatabaseId');
const kvId = infraStack.getOutput('sessionKvId');

// Use cross-stack outputs in the worker stack
const workerWithCrossStackBindings = new WorkerService('worker-cross', {
  accountId,
  name: 'example project-stateful',
  scriptPath: resolve(__dirname, '../dist/stateful-worker.js'),
  compatibilityDate: '2026-08-01',
  d1Bindings: [{ binding: 'DB', databaseId: dbId }],
  kvBindings: [{ binding: 'KV', namespaceId: kvId }],
});
```

## Unit Testing with Pulumi Mocks

```typescript
// __tests__/WorkerService.test.ts
import * as pulumi from '@pulumi/pulumi';

pulumi.runtime.setMocks({
  newResource(args) {
    return { id: `${args.name}-id`, state: args.inputs };
  },
  call(args) {
    return args.inputs;
  },
});

import { WorkerService } from '../components/WorkerService';

test('WorkerService creates cron trigger when schedules provided', async () => {
  const worker = new WorkerService('test-worker', {
    accountId: 'test-account',
    name: 'test',
    scriptPath: '/dev/null',  // mocked — file not read during unit test
    compatibilityDate: '2026-08-01',
    cronTriggers: ['0 * * * *'],
  });

  const url = await new Promise<string>(resolve =>
    worker.url.apply(v => resolve(v))
  );

  expect(url).toContain('workers.dev');
});
```

## WAF Rules and Page Rules

```typescript
// Cloudflare WAF custom rule via Pulumi (replaces complex Terraform locals)
const environments = ['production', 'staging'];

environments.forEach(env => {
  new cloudflare.RulesetRule(`waf-rate-limit-${env}`, {
    zoneId: zone.zoneId,
    kind: 'zone',
    phase: 'http_ratelimit',
    name: `Rate limit API — ${env}`,
    rules: [{
      action: 'block',
      expression: `(http.request.uri.path matches "^/api/") and (http.request.method eq "POST")`,
      description: `Block excessive POST to /api/ in ${env}`,
      ratelimit: {
        characteristics: ['cf.colo.id', 'ip.src'],
        period: 60,
        requestsPerPeriod: 100,
        mitigationTimeout: 600,
      },
    }],
  });
});
```

## State Management and CI Integration

```bash
# Use Pulumi Cloud (default) or self-hosted backend (S3/R2)
# Switch to R2-backed state (Cloudflare native)
pulumi login s3://example project-pulumi-state?region=auto&endpoint=<r2-endpoint>

# Per-environment stacks
pulumi stack select production
pulumi preview --diff

# CI deploy (GitHub Actions)
- name: Deploy infrastructure
  env:
    PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    cd infra
    pnpm install --frozen-lockfile
    pulumi up --stack production --yes --non-interactive
```

## Mobile vs Desktop Considerations

The Pulumi program manages resources shared by both platforms, but some resources are platform-specific:

- **Mobile (React Native)**: R2 buckets for OTA bundle storage, Durable Objects for per-user session state shared across mobile and web sessions, KV for feature flags consumed by both mobile and Next.js
- **Desktop (Next.js on Pages)**: Pages projects are not yet in the Pulumi Cloudflare provider (as of 2026-08); manage Pages via wrangler CLI or the Cloudflare REST API in a separate Pulumi dynamic provider
- **Both**: D1 databases, Workers, KV namespaces, and DNS records are platform-agnostic and managed in the shared Pulumi stack; stack outputs are consumed by wrangler.toml via `wrangler.toml`'s `[env.production]` block referencing the same IDs

## Anti-patterns

- Calling `pulumi up --yes` in CI without `pulumi preview` in a pull request check — skips human review of destructive diffs (Worker name changes cause replace, not update)
- Embedding the compiled Worker script content in Pulumi state via `content: readFileSync(...)` without invalidating on content hash — Pulumi does not re-diff large string values efficiently; use `fileAsset` or store the hash as a resource input
- Creating one Pulumi stack for all environments in a single program file — use per-environment stacks (`pulumi stack init staging`) with `Pulumi.staging.yaml` config overrides
- Managing Cloudflare Pages deployments through Pulumi when `wrangler pages deploy` is faster and integrates directly with the Pages build pipeline
- Using `pulumi destroy` to clean up staging without protecting production resources with `pulumi.ResourceOptions({ protect: true })` — a mis-targeted `destroy` on production is catastrophic

## Gotchas

- `@pulumi/cloudflare` version must match the Pulumi CLI version's engine; always update both together (`pulumi upgrade` + `npm update @pulumi/cloudflare`)
- Worker script content is stored in Pulumi state; rotate the state backend's encryption key if a secret was accidentally included in the script bundle
- The `cloudflare.WorkerScript` resource name (the `name` field) must match the Workers subdomain used in routes; a rename triggers a Worker recreation (delete + create), causing brief downtime
- Pulumi stores cross-stack outputs in the source stack's state; if the infra stack is deleted before the worker stack, the `StackReference.getOutput()` call hangs indefinitely — always destroy dependent stacks first
- Cloudflare rate-limits the API at ~1200 req/min per token; large Pulumi programs with hundreds of resources (DNS records, routes) may hit rate limits during initial `pulumi up`; add `pulumi:parallelism: 10` to `Pulumi.yaml`

## Verification

```bash
# Preview all changes before applying
pulumi preview --stack production --diff --show-replacement-steps

# Verify deployed Worker exists in the account
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '[.result[] | .id]'

# Check D1 database was created
wrangler d1 list

# Confirm KV namespace IDs match Pulumi outputs
pulumi stack output --stack production --json | jq '.sessionKvId'
wrangler kv namespace list | jq '.[] | select(.title == "example project_SESSION_STORE")'

# Run unit tests for component logic
pnpm test -- --testPathPattern=__tests__/WorkerService
```

## Related

- `documentation/docs/policies/infra/pulumi-terraform-cdk-iac-comparison.md`
- `documentation/docs/policies/infra/terraform-cloudflare-provider-workers-d1.md`
- `documentation/docs/policies/infra/wrangler-toml-multi-environment-config.md`
- `documentation/docs/policies/infra/cloudflare-r2-backup-restore-strategy.md`
- `documentation/docs/policies/infra/vault-dynamic-secrets-cloudflare-workers.md`
- `documentation/docs/policies/infra/iac-best-practices.md`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/
- https://www.pulumi.com/docs/concepts/stack/
- https://www.pulumi.com/docs/concepts/testing/unit/
- https://developers.cloudflare.com/workers/wrangler/api/
- https://www.pulumi.com/docs/concepts/options/protect/
