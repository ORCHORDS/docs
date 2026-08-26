# KV Namespace Deleted in Wrong Environment — Production Loss Postmortem

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An infrastructure engineer running routine cleanup of stale development resources deleted a
KV namespace named `WAM_FEATURE_FLAGS` from what they believed to be the staging Cloudflare
account. The namespace was in fact bound to the production example project (example.com) Worker. Within
seconds of deletion, every request that read a feature flag value received `undefined` instead of
the expected flag state, causing the code paths that guarded new and experimental features to
default to their "flag off" fallback. Several features that had been fully rolled out — including
the new export pipeline and collaborative session joining — silently reverted to their pre-GA
disabled states for all users.

There were no hard errors, no 500s, and no alert fired. The degradation was discovered 23 minutes
later when a product manager noticed in a Slack channel that collaborative session counts had
dropped to zero on the real-time dashboard.

## Context

Cloudflare Workers KV is a globally distributed key-value store. KV namespaces are Cloudflare
account resources identified by a UUID. A Worker binds to a namespace via `wrangler.toml`, and
the binding is resolved at request time. If the bound namespace is deleted from the account, the
`env.NAMESPACE.get()` call does not throw — it returns `null` silently, because from the
Worker's perspective the namespace binding is still present in the script metadata; the
underlying namespace simply has no keys.

example project used a KV namespace as its primary feature flag store. Flag keys were written by an
admin dashboard and read at request time in the Worker. The production namespace and the staging
namespace had similar names (`WAM_FEATURE_FLAGS` vs. `WAM_FEATURE_FLAGS_STAGING`) and were both
visible in the same Cloudflare account because the team used a single account with environment
prefixes rather than separate accounts per environment.

## Timeline

**14:10 UTC** — Engineer opens the Cloudflare dashboard to delete stale staging KV namespaces.
Filters by name substring "WAM_FEATURE_FLAGS". Two results appear.

**14:11 UTC** — Engineer deletes the first result, which lists 6 keys. This is the production
namespace. The staging namespace (the intended target) has 6 keys; the production namespace also
has 6 keys (one flag per feature). The name similarity and identical key count cause the engineer
to select the wrong row.

**14:11:30 UTC** — Namespace deletion completes. All 6 feature flag values are gone.

**14:12 UTC** — Production Workers begin returning `null` for all `env.FEATURE_FLAGS.get()` calls.
Feature flag guards default to `false` (flags-off) for all features.

**14:34 UTC** — Product manager notices the collaborative session count chart at zero.

**14:36 UTC** — On-call engineer is pinged. Checks recent deploys — none.

**14:41 UTC** — Engineer checks KV namespace list; `WAM_FEATURE_FLAGS` is missing. Incident
declared.

**14:43 UTC** — New namespace created with the same name via `wrangler kv namespace create`.
New namespace UUID is different; Worker script must be redeployed to bind to the new UUID.

**14:46 UTC** — Emergency Worker redeploy with updated `wrangler.toml` binding.

**14:49 UTC** — Feature flags repopulated from the runbook's documented default values.
Production traffic restored. Total outage: 38 minutes.

## Root Cause Analysis

Three factors combined:

**1. Single Cloudflare account with environment prefix naming.** Staging and production resources
lived in the same account, making destructive operations on production resources possible during
routine staging cleanup.

**2. KV namespace deletion via the dashboard offers no confirmation of bound Workers.** The
dashboard does not show which Workers are currently bound to a namespace before deletion. There
is no "namespace is in use" guard.

**3. Silent null return on missing namespace.** When the underlying namespace is deleted, `env.KV.get()` returns `null` rather than throwing an error. This means feature flags silently
revert to their code-level defaults with no observable error signal:

```typescript
// feature-flags.ts — vulnerable pattern
export async function getFlag(env: Env, flag: string): Promise<boolean> {
  const value = await env.FEATURE_FLAGS.get(flag);
  // If namespace is deleted, value is null here — no error thrown
  return value === 'true';   // null === 'true' → false — silent regression
}
```

The corrected pattern adds an explicit null check with observability:

```typescript
// feature-flags.ts — hardened pattern
export async function getFlag(
  env: Env,
  ctx: ExecutionContext,
  flag: string,
  defaultValue: boolean = false
): Promise<boolean> {
  let value: string | null;
  try {
    value = await env.FEATURE_FLAGS.get(flag);
  } catch (err) {
    // Namespace binding error — should never happen but guard anyway
    console.error(`[feature-flags] KV get error for ${flag}:`, err);
    return defaultValue;
  }

  if (value === null) {
    // Namespace exists but key is absent — or namespace was deleted
    // Emit a metric so silent nulls are visible in Analytics Engine
    ctx.waitUntil(
      env.METRICS.writeDataPoint({
        blobs: [flag, 'kv_null'],
        doubles: [1],
        indexes: ['feature_flag_null_reads'],
      })
    );
    return defaultValue;
  }

  return value === 'true';
}
```

**4. No IaC source of truth.** The KV namespace UUID was hardcoded in `wrangler.toml`. There
was no Terraform or IaC record linking namespace UUID to environment, so the UUID visible in
`wrangler.toml` was not cross-referenced during the deletion.

## Impact Analysis

- 38-minute full degradation of six production features (export pipeline, collaborative join,
  advanced search, AI-assisted tagging, bulk download, webhook delivery).
- ~8 200 active sessions affected; all features defaulted to disabled state silently.
- No data loss; all flag values were recovered from runbook documentation.
- Zero HTTP errors surfaced to monitoring — degradation was entirely silent from an error-rate
  perspective.
- Post-incident review revealed the same silent-null risk existed for three other KV namespaces.

## Remediation

### Separate Cloudflare accounts per environment

Migrate staging resources to a separate Cloudflare account to eliminate cross-environment
resource pollution:

```bash
# Create a dedicated staging account (via Cloudflare dashboard or Terraform)
# Update wrangler.toml to use account_id per environment:

# wrangler.toml
account_id = "prod-account-uuid"

# wrangler.staging.toml
account_id = "staging-account-uuid"
```

Deploy targeting:

```bash
# Production deploy
wrangler deploy

# Staging deploy
wrangler deploy --config wrangler.staging.toml
```

### IaC-managed KV namespaces via Terraform

```hcl
# terraform/kv-namespaces.tf
resource "cloudflare_workers_kv_namespace" "feature_flags_prod" {
  account_id = var.cf_account_id_prod
  title      = "WAM_FEATURE_FLAGS"
}

resource "cloudflare_workers_kv_namespace" "feature_flags_staging" {
  account_id = var.cf_account_id_staging
  title      = "WAM_FEATURE_FLAGS_STAGING"
}

output "feature_flags_prod_id" {
  value = cloudflare_workers_kv_namespace.feature_flags_prod.id
}
```

With IaC managing namespace lifecycle, ad-hoc dashboard deletions of Terraform-managed
resources will cause a Terraform drift alarm on the next `terraform plan`.

### KV namespace health check in the Worker

Add a startup health check that asserts all critical KV namespaces are reachable and returns
a known sentinel key:

```typescript
// health.ts
const SENTINEL_KEY = '__health_check__';
const SENTINEL_VALUE = 'ok';

export async function assertKVHealthy(env: Env): Promise<void> {
  const value = await env.FEATURE_FLAGS.get(SENTINEL_KEY);
  if (value !== SENTINEL_VALUE) {
    throw new Error(
      `KV namespace WAM_FEATURE_FLAGS health check failed: ` +
      `expected "${SENTINEL_VALUE}", got "${value}". Namespace may be missing or misconfigured.`
    );
  }
}
```

Write the sentinel key as part of the deployment pipeline:

```bash
# deploy.sh — write sentinel after wrangler deploy
wrangler deploy
wrangler kv key put --binding=FEATURE_FLAGS "__health_check__" "ok" --env production
```

## Prevention

- **Use separate Cloudflare accounts for production and staging.** This is the single highest-
  impact control for preventing cross-environment destructive operations.
- **Manage all KV namespaces via IaC (Terraform/Pulumi).** Resource deletion through IaC
  requires a pull request, peer review, and plan approval — not a single dashboard click.
- **Write a sentinel key to every KV namespace** and assert it in the Worker's health-check
  endpoint so namespace deletion causes an immediate, observable 500 on the health route.
- **Add an `env.KV.get()` null-rate metric** to detect silent feature flag degradation before
  users notice.
- **Document KV namespace UUIDs in a source-controlled runbook** with their bound Workers and
  environment, so deletion candidates can be verified by cross-reference.

## Anti-patterns

- Using a single Cloudflare account for all environments with only name prefixes to differentiate.
- Deleting cloud resources from the UI dashboard during routine cleanup without a checklist.
- Treating `env.KV.get()` returning `null` as a "key not found" when it may indicate a deleted
  namespace — the two cases are indistinguishable at the call site without additional telemetry.
- Hardcoding KV namespace UUIDs in `wrangler.toml` without an IaC record as the authoritative
  source.
- Defaulting feature flags to `false` at the code level without alerting when flags are expected
  to be `true` (fully-rolled-out features become invisible regressions).

## Gotchas

- `env.KV.get()` returns `null` for both a missing key and a deleted namespace. There is no way
  to distinguish these two cases from within the Worker without a dedicated sentinel key.
- Deleting a KV namespace from the Cloudflare dashboard is instantaneous and irreversible. There
  is no recycle bin, soft-delete, or recovery mechanism.
- A KV namespace can be deleted even when one or more Workers are bound to it. Cloudflare does
  not prevent deletion of in-use namespaces.
- After namespace deletion and recreation, the new namespace has a different UUID. The Worker
  must be redeployed with the updated UUID in `wrangler.toml` before it can write to the new
  namespace — reads will silently return `null` until redeploy.
- `wrangler kv namespace list` shows UUIDs but not which Workers are bound to each namespace,
  making it difficult to audit namespace-Worker relationships without cross-referencing
  `wrangler.toml` files manually.

## Verification

```bash
# 1. Confirm namespace exists and sentinel is present
wrangler kv key get --binding=FEATURE_FLAGS "__health_check__" --env production
# Expected output: "ok"

# 2. Confirm Worker health endpoint asserts KV health
curl https://example.com/health
# Expected: 200 {"status": "ok", "kv": "ok"}

# 3. Confirm feature flag null-read metric is not firing
wrangler tail --format=json \
  | jq 'select(.logs[].message | contains("kv_null"))'
# Expected: no output

# 4. Verify IaC state matches live namespace UUID
terraform plan -target=cloudflare_workers_kv_namespace.feature_flags_prod
# Expected: "No changes."
```

## Related

- `kv-write-rate-limit-exceeded-postmortem.md`
- `kv-cold-start-mobile-latency-spike-postmortem.md`
- `feature-flag-lifecycle-management.md`
- `staging-prod-parity-lies-config-drift-data-volume.md`

## Sources

- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare KV namespace management API: https://developers.cloudflare.com/api/operations/workers-kv-namespace-list-namespaces
- Cloudflare Terraform provider — KV namespace: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/workers_kv_namespace
