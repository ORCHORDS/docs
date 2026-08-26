# Workers Version Metadata Binding Deploy Tracking

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After a rapid sequence of Cloudflare Workers deploys, the team cannot determine
which Worker version is currently handling requests in a given data center or
isolate. Tail logs show errors but do not include the deployed version identifier,
making it impossible to correlate errors with a specific commit or deploy run.
For example project / example.com, this becomes critical when a gradual rollout is in
progress — anonymous post failures might be caused by v1.2.3, v1.2.4, or a
rollback to v1.2.2, and without version context in every log line the on-call
engineer wastes time bisecting the wrong deploy.

## Context

Cloudflare Workers ships a `__STATIC_CONTENT_MANIFEST` binding and, more
relevantly, a `VersionMetadata` binding (available as of the
`version_metadata` compatibility flag) that exposes the current Worker version ID
and tag at runtime. This binding is injected automatically by the Workers runtime
and does not require any deploy-time configuration beyond declaring it in
`wrangler.toml`. Version IDs are stable UUIDs that match the version shown in
`wrangler versions list` and the Cloudflare dashboard.

## Section 1 — declaring the version metadata binding

Add the `version_metadata` binding to `wrangler.toml`. The binding name is
arbitrary but `CF_VERSION_METADATA` is the convention used here.

```toml
# wrangler.toml
name = "example project-api"
compatibility_date = "2026-07-01"
main = "src/index.ts"

[version_metadata]
binding = "CF_VERSION_METADATA"
```

The binding exposes a `VersionMetadata` object at runtime with:
- `id`: the Worker version UUID (matches `wrangler versions list`)
- `tag`: the optional version tag set via `--tag` during deploy

Set a version tag during deploy to link back to the Git commit:

```bash
# Deploy with a version tag (Git SHA short ref)
GIT_SHA=$(git rev-parse --short HEAD)
npx wrangler deploy --tag "git-${GIT_SHA}"
```

## Section 2 — emitting version metadata in every response and log

Inject version metadata into request logs and response headers so every log line
is traceable to a specific deploy.

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  SESSIONS: KVNamespace;
  CF_VERSION_METADATA: WorkerVersionMetadata;
}

interface WorkerVersionMetadata {
  id: string;
  tag: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const versionId = env.CF_VERSION_METADATA.id;
    const versionTag = env.CF_VERSION_METADATA.tag;

    // Structured log line — every request carries version context
    const logPayload = {
      version_id: versionId,
      version_tag: versionTag,
      method: request.method,
      url: request.url,
      cf_ray: request.headers.get("CF-Ray"),
      timestamp: new Date().toISOString(),
    };

    try {
      const response = await handleRequest(request, env, ctx);

      // Expose version in response header for debugging (non-sensitive)
      const headers = new Headers(response.headers);
      headers.set("X-Worker-Version-Id", versionId);
      headers.set("X-Worker-Version-Tag", versionTag);

      console.log(JSON.stringify({ ...logPayload, status: response.status }));

      return new Response(response.body, {
        status: response.status,
        headers,
      });
    } catch (err) {
      console.error(
        JSON.stringify({
          ...logPayload,
          error: String(err),
          status: 500,
        })
      );
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};

async function handleRequest(
  request: Request,
  env: Env,
  _ctx: ExecutionContext
): Promise<Response> {
  // application logic
  return new Response("OK");
}
```

## Section 3 — CI deploy tracking with version IDs

After each deploy, capture the version ID via `wrangler versions list` and store
it as a deploy record in the CI run summary or an external tracking store.

```yaml
# .github/workflows/deploy.yml (version tracking additions)
- name: Deploy Worker
  id: deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    GIT_SHA=$(git rev-parse --short HEAD)
    npx wrangler deploy --tag "git-${GIT_SHA}"

- name: Capture deployed version ID
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: |
    # Fetch the latest version (most recently deployed)
    VERSION_JSON=$(npx wrangler versions list --json 2>/dev/null | head -1)
    VERSION_ID=$(echo "$VERSION_JSON" | jq -r '.[0].id // empty')
    VERSION_TAG=$(echo "$VERSION_JSON" | jq -r '.[0].annotations["workers/tag"] // empty')

    echo "## Deploy Tracking" >> "$GITHUB_STEP_SUMMARY"
    echo "| Field | Value |" >> "$GITHUB_STEP_SUMMARY"
    echo "|-------|-------|" >> "$GITHUB_STEP_SUMMARY"
    echo "| Version ID | \`${VERSION_ID}\` |" >> "$GITHUB_STEP_SUMMARY"
    echo "| Version Tag | \`${VERSION_TAG}\` |" >> "$GITHUB_STEP_SUMMARY"
    echo "| Git SHA | \`$(git rev-parse HEAD)\` |" >> "$GITHUB_STEP_SUMMARY"
    echo "| Deployed At | \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\` |" >> "$GITHUB_STEP_SUMMARY"
    echo "| Actor | \`${{ github.actor }}\` |" >> "$GITHUB_STEP_SUMMARY"

    # Export for downstream steps
    echo "VERSION_ID=${VERSION_ID}" >> "$GITHUB_ENV"
```

Store the version ID in a KV namespace for runtime version lookup without a tail:

```bash
# Post-deploy: record version → git SHA mapping in KV
npx wrangler kv key put "deploy:${VERSION_ID}" \
  "{\"git_sha\":\"$(git rev-parse HEAD)\",\"deployed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
  --namespace-id "$DEPLOY_TRACKING_KV_ID" \
  --remote
```

## Section 4 — rollback with version ID confirmation

When rolling back, use the version ID captured during the previous known-good
deploy to target the rollback precisely.

```bash
#!/usr/bin/env bash
# scripts/rollback-to-version.sh
set -euo pipefail

TARGET_VERSION_ID="${1:?Pass the target version ID}"

echo "Rolling back example project-api to version: $TARGET_VERSION_ID"

# Use wrangler rollback targeting a specific version
npx wrangler rollback "$TARGET_VERSION_ID" \
  --message "Rolling back to version $TARGET_VERSION_ID — incident response"

# Verify the rollback by checking the version ID binding from a test request
echo "Verifying rollback..."
sleep 5   # allow edge propagation

RESPONSE_VERSION=$(curl -s https://api.example.com/api/health \
  -I | grep -i x-worker-version-id | awk '{print $2}' | tr -d '\r')

if [ "$RESPONSE_VERSION" = "$TARGET_VERSION_ID" ]; then
  echo "Rollback confirmed: version ID matches target."
else
  echo "WARNING: Response version ID $RESPONSE_VERSION != target $TARGET_VERSION_ID"
  echo "Edge may still be propagating — wait 30 seconds and re-check."
fi
```

## Anti-patterns

- Logging version information from environment variables set at build time instead
  of the runtime `version_metadata` binding — build-time values do not update
  during gradual rollouts when old and new versions run simultaneously
- Using the `--tag` flag as the sole identifier for rollback — tags are
  human-readable labels, not the authoritative version UUID
- Omitting version headers from API responses — removes the fast path for
  on-call engineers to identify which version is misbehaving via a curl command
- Storing deploy tracking data only in GitHub Actions summaries — summaries expire
  and are not queryable at 3 AM during an incident

## Gotchas

- The `version_metadata` binding requires `compatibility_date` >= `"2024-01-01"`
  or the explicit `version_metadata` compatibility flag in older configs.
- `wrangler versions list --json` output format may change between wrangler
  versions — pin the wrangler version in `package.json` to stabilize the JSON
  shape.
- During a gradual rollout, `CF_VERSION_METADATA.id` will return different values
  in different requests as traffic splits between old and new versions — this is
  expected and is exactly what makes per-request version logging valuable.
- The `--tag` value on a version is set at deploy time and cannot be updated
  after deployment. Choose a meaningful tag (e.g. git SHA, semver, deploy run ID)
  before deploying.
- The `X-Worker-Version-Id` response header is visible to all clients — it exposes
  infrastructure details. Gate it behind a debug flag or restrict to internal
  health-check endpoints in production if this is a concern.

## Verification

1. Deploy the Worker with `--tag "git-$(git rev-parse --short HEAD)"`.
2. Make a request to the Worker and inspect the `X-Worker-Version-Id` response
   header — it should match the UUID from `wrangler versions list`.
3. Check `wrangler tail` output — every log line should include `version_id` in
   the JSON payload.
4. Look up the version ID in the KV deploy tracking namespace to confirm the
   git SHA mapping was written.
5. Run the rollback script targeting the previous version ID and verify the header
   changes within 30 seconds.

## Related

- `/documentation/docs/policies/deploy/wrangler-version-upload-metadata.md`
- `/documentation/docs/policies/deploy/workers-binding-version-management.md`
- `/documentation/docs/policies/deploy/worker-versioning-gradual-rollout.md`
- `/documentation/docs/policies/deploy/wrangler-versions-api-rollback-automation.md`
- `/documentation/docs/policies/deploy/deployment-audit-trail-provenance.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions-list
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
