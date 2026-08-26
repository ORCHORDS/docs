# Pulumi Cloudflare R2 Lifecycle Policy Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

R2 buckets accumulate stale objects — log exports, build artefacts, nightly
backups, user-uploaded originals — that are never explicitly deleted.  Without
lifecycle rules, storage costs grow unbounded and compliance requirements around
data retention (GDPR deletion, audit log expiry) cannot be enforced
programmatically.  Terraform already has `cloudflare_r2_bucket_lifecycle_rule`
support but teams using Pulumi for their Cloudflare stack need an equivalent
pattern with typed configuration and stack-based environment overrides.

## Context

Cloudflare R2 lifecycle rules follow an S3-compatible API.  Pulumi's Cloudflare
provider (>= 5.x) exposes `cloudflare.R2BucketLifecycle` as a first-class
resource.  Rules can target prefixes or all objects, expire current object
versions, abort incomplete multipart uploads, and delete non-current versions
(when versioning is enabled).  Lifecycle applies at the bucket level; each
bucket requires its own `R2BucketLifecycle` resource.

---

## 1. Installing the Pulumi Cloudflare Provider

```bash
# TypeScript project
npm install @pulumi/cloudflare

# Go project
go get github.com/pulumi/pulumi-cloudflare/sdk/v5
```

Minimum provider version for lifecycle support: `5.3.0`.

```typescript
// Pulumi.yaml
name: example project-r2-lifecycle
runtime: nodejs
description: R2 bucket lifecycle policies for example project platform

config:
  cloudflare:accountId:
    value: ${CLOUDFLARE_ACCOUNT_ID}
```

---

## 2. Basic Expiry Rule (TypeScript)

```typescript
// infra/r2Lifecycle.ts
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const cfg = new pulumi.Config();
const accountId = cfg.require("accountId");

// Reference an existing bucket (or create inline)
const logsBucket = new cloudflare.R2Bucket("example project-logs", {
  accountId,
  name: "example project-logs",
  location: "WEUR",
});

// Lifecycle: expire raw logs after 90 days, abort stale multiparts after 7 days
const logsLifecycle = new cloudflare.R2BucketLifecycle("example project-logs-lifecycle", {
  accountId,
  bucketName: logsBucket.name,
  rules: [
    {
      id:     "expire-raw-logs",
      enabled: true,
      prefix:  "raw/",
      expiration: {
        days: 90,
      },
    },
    {
      id:     "abort-multipart",
      enabled: true,
      prefix:  "",          // applies to all prefixes
      abortIncompleteMultipartUpload: {
        daysAfterInitiation: 7,
      },
    },
  ],
}, { dependsOn: [logsBucket] });
```

---

## 3. Multi-prefix Policy with Stack-Based Overrides

```typescript
// infra/config.ts
interface LifecyclePolicy {
  prefix:      string;
  expiryDays:  number;
  description: string;
}

const policies: Record<string, LifecyclePolicy[]> = {
  production: [
    { prefix: "builds/",   expiryDays: 30,  description: "CI build artefacts" },
    { prefix: "backups/",  expiryDays: 365, description: "Nightly DB backups" },
    { prefix: "uploads/tmp/", expiryDays: 1, description: "Temp user uploads" },
  ],
  staging: [
    { prefix: "builds/",   expiryDays: 7,   description: "CI build artefacts (staging)" },
    { prefix: "uploads/tmp/", expiryDays: 1, description: "Temp user uploads" },
  ],
};

// infra/r2Lifecycle.ts (continued)
const stack = pulumi.getStack();     // "production" | "staging"
const activePolicies = policies[stack] ?? policies["staging"];

const artefactLifecycle = new cloudflare.R2BucketLifecycle("artefacts-lifecycle", {
  accountId,
  bucketName: "example project-artefacts",
  rules: activePolicies.map((p, i) => ({
    id:      `rule-${i}-${p.prefix.replace(/\//g, "-")}`,
    enabled: true,
    prefix:  p.prefix,
    expiration: { days: p.expiryDays },
  })),
});
```

---

## 4. Versioned Bucket — Non-current Version Expiry

```typescript
// Enable versioning first (R2 bucket versioning via wrangler or API)
// Then expire non-current versions after 30 days

const versionedLifecycle = new cloudflare.R2BucketLifecycle("media-versioned-lifecycle", {
  accountId,
  bucketName: "example project-media",
  rules: [
    {
      id:      "expire-noncurrent-versions",
      enabled: true,
      prefix:  "",
      noncurrentVersionExpiration: {
        noncurrentDays: 30,
      },
    },
    {
      id:      "keep-latest-3-versions",
      enabled: true,
      prefix:  "",
      noncurrentVersionExpiration: {
        newerNoncurrentVersions: 3,  // keep 3 most recent non-current versions
        noncurrentDays: 7,
      },
    },
  ],
});
```

---

## 5. Drift Detection and Reconciliation

```bash
# Preview lifecycle state without applying
pulumi preview --stack production --diff

# Confirm applied rules via R2 API
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/r2/buckets/example project-logs/lifecycle" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '.result.rules'

# Check Pulumi state matches API
pulumi stack export --stack production | \
  jq '.deployment.resources[] | select(.type=="cloudflare:index/r2BucketLifecycle:R2BucketLifecycle")'
```

---

## 6. CI Pipeline Integration

```yaml
# .github/workflows/r2-lifecycle.yml
name: R2 Lifecycle Deploy
on:
  push:
    branches: [main]
    paths: ["infra/r2Lifecycle.ts", "infra/config.ts"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pulumi/actions@v5
        with:
          command: up
          stack-name: production
          work-dir: infra
        env:
          PULUMI_ACCESS_TOKEN:    ${{ secrets.PULUMI_ACCESS_TOKEN }}
          CLOUDFLARE_API_TOKEN:   ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID:  ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Anti-patterns

- Do not set `expiryDays: 0` — R2 rejects rules with a zero-day expiry; use
  `daysAfterInitiation: 1` for multipart and `days: 1` for object expiry.
- Do not apply a lifecycle rule with an empty prefix and `days: N` to a bucket
  that serves user media without an explicit `prefix` guard — it will silently
  delete production assets.
- Do not manage `R2BucketLifecycle` and `R2Bucket` in separate Pulumi stacks
  without an explicit `dependsOn`; the bucket must exist before the lifecycle
  resource is created.

## Gotchas

- Pulumi replaces the entire rule set on update — there is no incremental patch.
  A typo in one rule deletes all other rules during the `up`.  Always run
  `pulumi preview` before `pulumi up` on lifecycle changes.
- R2 lifecycle rules are eventually consistent; rule application can lag up to
  24 hours after configuration is accepted by the API.
- The `newerNoncurrentVersions` field requires versioning to be enabled on the
  bucket; specifying it on a non-versioned bucket returns a 400 API error.

## Verification

```bash
# Confirm lifecycle rules are active
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/r2/buckets/example project-logs/lifecycle" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" | jq '.result.rules[].id'
# Expected: "expire-raw-logs", "abort-multipart"
```

## Related

- `terraform-cloudflare-r2-cors-lifecycle.md`
- `r2-lifecycle-archival-glacier-strategy.md`
- `cloudflare-r2-backup-restore-strategy.md`
- `cloudflare-r2-presigned-urls-workers.md`
- `pulumi-cloudflare-provider-advanced.md`

## Sources

- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://www.pulumi.com/registry/packages/cloudflare/api-docs/r2bucketlifecycle/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/r2_bucket_lifecycle_rule
