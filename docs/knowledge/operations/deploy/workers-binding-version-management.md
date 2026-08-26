# Workers Binding Version Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

When performing a gradual rollout with Workers Versions, different versions of
a Worker run simultaneously—but they share the same binding configuration
unless explicitly managed. A change to a D1 schema, a renamed KV namespace, or
a new R2 bucket binding required by the new version will break the old version
if bindings are updated atomically with the code. Conversely, removing a
binding from `wrangler.toml` and deploying causes the old version—still
receiving a fraction of traffic—to panic with `Cannot read properties of
undefined (reading 'prepare')` when accessing the now-missing binding.

## Context

Cloudflare Workers Versions (graduated rollout) separates code deployment from
traffic promotion. Each `wrangler versions upload` creates a Version object
with a snapshot of the Worker's bindings at upload time. Traffic is then
distributed across versions using a Deployment (via `wrangler deployments
create`).

Key facts:
- Bindings are snapshotted per Version at upload time.
- Changing `wrangler.toml` bindings and uploading a new version does NOT affect
  existing Versions; each version carries its own binding configuration.
- D1, KV, R2, and Service bindings are resolved by name at upload time. If the
  underlying resource is deleted or renamed, all Versions that reference it
  break simultaneously.
- Secret bindings (Worker Secrets) are account-level and are not snapshotted;
  their current value is read at request time by all Versions. This makes
  secrets safe to rotate but means all versions see the new value immediately.

## Section 1: Binding Snapshots and Safe Additive Changes

The safest binding changes are purely additive: add a new binding in
`wrangler.toml`, upload the new version, and both old and new versions continue
to work—old versions simply don't reference the new binding variable name.

### Additive binding change (safe)

```toml
# wrangler.toml — v1 (currently deployed)
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "SESSION_CACHE"
id = "aaa111bbb222ccc333ddd444eee555ff"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "db-uuid-v1"
```

```toml
# wrangler.toml — v2 (adds new R2 bucket binding without removing SESSION_CACHE)
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[kv_namespaces]]
binding = "SESSION_CACHE"
id = "aaa111bbb222ccc333ddd444eee555ff"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "db-uuid-v1"

[[r2_buckets]]
binding = "UPLOADS"
bucket_name = "user-uploads-prod"
```

```bash
# Upload new version (does not affect live traffic yet)
wrangler versions upload --message "v2: add UPLOADS R2 binding"

# Gradually shift traffic; v1 receives 80 %, v2 receives 20 %
wrangler deployments create \
  --version-id <v2-version-id> \
  --version-percentage 20 \
  --version-id <v1-version-id> \
  --version-percentage 80
```

### Check current binding snapshot for a version

```bash
# List versions and their binding configurations
wrangler versions list --name api-gateway

# Inspect specific version bindings
wrangler versions view <version-id> --name api-gateway
```

## Section 2: Breaking Binding Changes During Gradual Rollouts

When a binding must be renamed, replaced, or removed, old versions that still
receive traffic will fail unless you sequence the change carefully.

### Procedure: rename a KV binding without downtime

**Scenario**: rename `SESSION_CACHE` → `USER_SESSIONS` in the Worker code.

**Step 1**: Add the new binding alongside the old one in `wrangler.toml`.
Update the Worker code to read from `USER_SESSIONS`, falling back to
`SESSION_CACHE` for backward compatibility.

```typescript
// src/index.ts — transitional code supporting both binding names
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Support both old and new binding name during rollout
    const cache = env.USER_SESSIONS ?? env.SESSION_CACHE;
    const session = await cache.get("session-key");
    // ...
  },
};

interface Env {
  USER_SESSIONS?: KVNamespace;  // new (v2+)
  SESSION_CACHE?: KVNamespace;  // old (v1, kept during rollout)
}
```

```toml
# wrangler.toml — transitional (both bindings present)
[[kv_namespaces]]
binding = "SESSION_CACHE"
id = "aaa111bbb222ccc333ddd444eee555ff"

[[kv_namespaces]]
binding = "USER_SESSIONS"
id = "aaa111bbb222ccc333ddd444eee555ff"   # same underlying namespace, new binding name
```

**Step 2**: Upload v2, shift 100 % of traffic to v2, confirm stable.

**Step 3**: Remove `SESSION_CACHE` binding, remove fallback code, upload v3.

```toml
# wrangler.toml — final (only USER_SESSIONS)
[[kv_namespaces]]
binding = "USER_SESSIONS"
id = "aaa111bbb222ccc333ddd444eee555ff"
```

```bash
# After 100 % traffic on v2 is stable (e.g., 24 hours):
wrangler versions upload --message "v3: remove deprecated SESSION_CACHE binding"
wrangler deployments create \
  --version-id <v3-version-id> \
  --version-percentage 100
```

### Procedure: D1 database migration with version gating

```bash
# Step 1: Apply additive schema migration to the existing D1 database
# (the old version continues to work; new columns are nullable or have defaults)
wrangler d1 migrations apply app-db --remote

# Step 2: Upload new Worker version that uses the new schema
wrangler versions upload --message "v2: use new D1 schema"

# Step 3: Gradual traffic shift
wrangler deployments create \
  --version-id <v2-version-id> --version-percentage 10 \
  --version-id <v1-version-id> --version-percentage 90

# Step 4: Monitor errors; when stable, promote to 100 %
wrangler deployments create \
  --version-id <v2-version-id> --version-percentage 100
```

## Section 3: Automation and Drift Prevention

Automate binding snapshot validation to prevent mismatches between what
`wrangler.toml` declares and what each live version actually has.

### CI check: assert binding names match expected set

```bash
#!/usr/bin/env bash
# check-binding-versions.sh — run in CI after versions upload

set -euo pipefail

WORKER="${1:?worker name required}"
EXPECTED_BINDINGS="${2:?comma-separated expected binding names}"

# Get the latest uploaded version ID
LATEST_VERSION=$(
  wrangler versions list --name "$WORKER" --json 2>/dev/null \
    | jq -r 'sort_by(.created_on) | last | .id'
)

echo "Checking bindings for version: $LATEST_VERSION"

ACTUAL_BINDINGS=$(
  wrangler versions view "$LATEST_VERSION" --name "$WORKER" --json 2>/dev/null \
    | jq -r '[.bindings[].name] | sort | join(",")'
)

IFS=',' read -ra EXPECTED <<< "$(echo "$EXPECTED_BINDINGS" | tr ',' '\n' | sort | tr '\n' ',' | sed 's/,$//')"

if [[ "$ACTUAL_BINDINGS" != "$(echo "$EXPECTED_BINDINGS" | tr ',' '\n' | sort | tr '\n' ',' | sed 's/,$//')" ]]; then
  echo "ERROR: Binding mismatch for version $LATEST_VERSION" >&2
  echo "  Expected: $EXPECTED_BINDINGS" >&2
  echo "  Actual:   $ACTUAL_BINDINGS" >&2
  exit 1
fi

echo "OK: All expected bindings present in version $LATEST_VERSION"
```

### GitHub Actions step for binding validation

```yaml
# .github/workflows/deploy.yml
- name: Upload new version
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: wrangler versions upload --message "Deploy ${{ github.sha }}"

- name: Validate binding snapshot
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    bash scripts/check-binding-versions.sh \
      api-gateway \
      "DB,SESSION_CACHE,UPLOADS,CONFIG"
```

### Rollback binding to previous version

```bash
#!/usr/bin/env bash
# rollback-version.sh — reactivate the last stable version

set -euo pipefail

WORKER="${1:?worker name required}"

# Get the version before the latest (n-1)
PREVIOUS_VERSION=$(
  wrangler versions list --name "$WORKER" --json 2>/dev/null \
    | jq -r 'sort_by(.created_on) | .[-2] | .id'
)

echo "Rolling back $WORKER to version $PREVIOUS_VERSION"

wrangler deployments create \
  --version-id "$PREVIOUS_VERSION" \
  --version-percentage 100 \
  --name "$WORKER"

echo "Rollback complete."
```

## Anti-patterns

- **Deleting the underlying KV namespace or D1 database mid-rollout**: all
  versions that hold a binding pointing to the deleted resource will throw at
  request time. The resource must persist until all versions referencing it
  have zero traffic.

- **Assuming secrets behave like bindings**: Worker Secrets are NOT
  snapshotted. Rotating a secret mid-rollout changes the value for all
  versions simultaneously. Plan secret rotations outside gradual rollout
  windows.

- **Using binding names as feature flags**: binding presence/absence is a
  deployment-time signal, not a runtime one. Use KV-backed feature flags for
  runtime behavior toggling.

- **Uploading a new version without verifying the previous version reached 100 %
  traffic**: stale version percentage math causes silent partial rollouts.
  Always verify deployment percentages before uploading the next version.

## Gotchas

- `wrangler versions upload` does not trigger a deployment—it only creates a
  Version object. A separate `wrangler deployments create` is always required
  to shift traffic.

- The `wrangler deploy` command is a shortcut that combines upload + 100 %
  deployment. It bypasses gradual rollout. Never use `wrangler deploy` when
  you intend a gradual rollout; use `wrangler versions upload` + `wrangler
  deployments create`.

- `wrangler versions list` returns versions in creation order, not traffic
  order. The currently active version for live traffic may not be the newest
  version uploaded.

- Binding changes to secrets (created via `wrangler secret put`) apply to all
  versions immediately. If the new secret format is incompatible with the old
  code, the old version will break the moment the secret is rotated.

## Verification

```bash
# List all versions and their percentage of live traffic
wrangler deployments list --name api-gateway

# Confirm current active deployment bindings match wrangler.toml
wrangler versions view $(
  wrangler deployments list --name api-gateway --json \
    | jq -r 'first | .versions[] | select(.percentage == 100) | .version_id'
) --name api-gateway

# Confirm no stale versions hold unexpected traffic
wrangler deployments list --name api-gateway --json \
  | jq '[.[] | select(.versions[].percentage > 0)] | length'
# Should be 1 (only one active deployment with > 0 % traffic versions)
```

## Related

- `worker-versioning-gradual-rollout.md`
- `env-binding-precedence.md`
- `d1-schema-migration-sequencing-wrangler-remote.md`
- `canary-workers-gradual-traffic-split.md`
- `workers-secrets-rotation-zero-downtime.md`

## Sources

- Workers Versions and Deployments: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Wrangler versions CLI: https://developers.cloudflare.com/workers/wrangler/commands/#versions
- Wrangler deployments CLI: https://developers.cloudflare.com/workers/wrangler/commands/#deployments
- Gradual rollout patterns: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
