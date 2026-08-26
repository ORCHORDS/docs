# Expo EAS OTA + Cloudflare Workers API — Coordinated Release

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your mobile app ships via Expo EAS (Expo Application Services) and uses OTA (Over-the-Air) updates to push JavaScript bundle changes without going through App Store / Play Store review. Your backend runs on Cloudflare Workers. When an API contract changes — a new required field, a renamed endpoint, a removed response property — you need the backend and the OTA update to land in the right order, at the right time, for all active app versions.

Getting this wrong produces a narrow but real failure window:

- OTA update ships before the Worker deploy propagates → new JS bundle calls endpoints that don't exist yet → 404/500 for users who received the update.
- Worker deploy ships first and removes backward compat before the OTA fully propagates → old JS bundles on devices mid-update hit broken endpoints.
- A native build submitted to stores picks up a new API contract before the OTA has reached all OTA-eligible devices.

## Context

Expo OTA updates (via `eas update`) push a new JavaScript bundle to devices. Unlike a store release:
- OTA updates bypass App Store and Play Store review.
- They reach devices asynchronously — typically within minutes to hours depending on the user opening the app.
- They are governed by the `runtimeVersion` field in `app.json`: an OTA update is only delivered to devices running a binary with a matching `runtimeVersion`. Mismatched runtime versions are never served the OTA update.
- OTA updates cannot change native code (Swift, Kotlin, native modules). Only the JS layer is replaced.

This creates a fleet segmentation at the intersection of two dimensions: `runtimeVersion` (which binary is installed) and `updateGroup` / EAS Update branch (which JS bundle is live). The backend must be compatible with all active combinations.

Cloudflare Workers propagate globally within approximately 30 seconds of `wrangler deploy`. EAS OTA updates propagate to devices over minutes to hours. The asymmetry means Workers changes always arrive before the OTA fleet has fully updated.

## Step 1 — Map runtimeVersion to API compatibility surface

Treat `runtimeVersion` as your backward-compatibility contract boundary, not app version string.

```json
// app.json
{
  "expo": {
    "name": "Orchords",
    "runtimeVersion": {
      "policy": "sdkVersion"
    },
    "updates": {
      "url": "https://u.expo.dev/YOUR_EAS_PROJECT_ID"
    }
  }
}
```

With `"policy": "sdkVersion"`, the runtimeVersion is tied to the Expo SDK version in the native binary. When you bump the SDK (requiring a new native build), the runtimeVersion increments and old OTA updates are no longer served to new installs. Map each runtimeVersion to the minimum Workers API version it requires:

```
runtimeVersion=53  →  requires Workers API v2 (fieldName: "userId")
runtimeVersion=52  →  requires Workers API v1 (fieldName: "user_id") — still in store
```

## Step 2 — Version-gate Workers API responses

The Worker reads the app's runtime version from a request header set by the Expo SDK:

```typescript
// workers/api/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const runtimeVersion = request.headers.get("Expo-Runtime-Version");
    const updateId = request.headers.get("Expo-Update-Id");

    const useV2Api = isRuntimeVersionAtLeast(runtimeVersion, "53");

    if (request.url.includes("/api/user/me")) {
      const user = await getUser(request, env);

      if (useV2Api) {
        return Response.json({ userId: user.id, email: user.email });
      } else {
        // Legacy shape still required for runtimeVersion <= 52
        return Response.json({ user_id: user.id, email: user.email });
      }
    }

    return new Response("Not Found", { status: 404 });
  },
};

function isRuntimeVersionAtLeast(header: string | null, min: string): boolean {
  if (!header) return false;
  const headerNum = parseInt(header.replace(/\D/g, ""), 10);
  const minNum = parseInt(min.replace(/\D/g, ""), 10);
  return headerNum >= minNum;
}
```

The `Expo-Runtime-Version` header is sent automatically by `expo-updates` on every request originating from within the Expo app when you use the Expo SDK's `fetch` wrapper or pass the header explicitly from your API client layer.

## Step 3 — Coordinated deploy pipeline

### Backend deploy first (expand phase)

```yaml
# .github/workflows/coordinated-release.yml
name: Coordinated API + OTA Release

on:
  workflow_dispatch:
    inputs:
      ota_branch:
        description: "EAS Update branch to publish OTA to"
        required: true
        default: "production"
      ota_message:
        description: "Update message"
        required: true

jobs:
  deploy-worker:
    runs-on: ubuntu-latest
    environment: production
    outputs:
      deploy_id: ${{ steps.deploy.outputs.deploy_id }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci

      - name: Deploy Cloudflare Worker
        id: deploy
        working-directory: workers/api
        run: |
          npx wrangler deploy --env production 2>&1 | tee deploy.log
          DEPLOY_ID=$(grep -oP "(?<=Version ID: )[a-f0-9-]+" deploy.log || echo "unknown")
          echo "deploy_id=$DEPLOY_ID" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Wait for global propagation
        run: |
          # Poll until all sampled edge PoPs return the new version
          for i in $(seq 1 12); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
              -H "Expo-Runtime-Version: 53" \
              "https://api.orchords.workers.dev/api/health")
            VERSION=$(curl -s -H "Expo-Runtime-Version: 53" \
              "https://api.orchords.workers.dev/api/health" | jq -r '.apiVersion')
            echo "Attempt $i: HTTP $STATUS, apiVersion=$VERSION"
            [ "$VERSION" = "v2" ] && exit 0
            sleep 5
          done
          echo "Worker propagation timeout" && exit 1

  publish-ota:
    runs-on: ubuntu-latest
    needs: deploy-worker     # OTA ships only after Worker is confirmed live
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci

      - name: Setup Expo
        uses: expo/expo-github-action@v8
        with:
          expo-version: latest
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Publish EAS Update (OTA)
        run: |
          eas update \
            --branch "${{ github.event.inputs.ota_branch }}" \
            --message "${{ github.event.inputs.ota_message }}" \
            --non-interactive
        working-directory: mobile

      - name: Record OTA publish
        run: |
          echo "OTA published after Worker deploy ${{ needs.deploy-worker.outputs.deploy_id }}"
          echo "Branch: ${{ github.event.inputs.ota_branch }}"
          echo "Time: $(date -u)"
```

### Contract-breaking changes: two-PR strategy

For breaking changes that cannot be version-gated (e.g., removing an endpoint entirely):

- **PR #<number>**: Worker supports both old and new contracts simultaneously. Merge and deploy. Confirm old runtimeVersion devices still work.
- **PR #<number> (OTA)**: Publish OTA update that moves devices to the new contract. Monitor OTA adoption via EAS dashboard (typically 90%+ within 24 hours for active users).
- **PR #<number>**: Worker removes old contract, scoped by a `runtimeVersion` gate that only old (now unreachable via OTA) runtimeVersions would hit. Schedule for after the oldest supported runtimeVersion has been deprecated.

## Step 4 — Rollback coordination

OTA rollbacks via `eas update:republish` are fast but imperfect:

```bash
# List recent updates on the production branch
eas update:list --branch production

# Re-publish a previous update (effectively an OTA rollback)
eas update:republish \
  --branch production \
  --group <previous-update-group-id>
```

The Worker rollback is independent:

```bash
# Roll back the Worker to the previous version
npx wrangler rollback --env production
# or via Worker Versions:
npx wrangler versions rollback --name orchords-api --env production
```

Rollback order for a bad OTA + Worker combo:
1. Rollback the Worker first (instant, sub-30s propagation).
2. Republish the previous OTA update immediately after.
3. The window between steps 1 and 2 is safe because the old Worker code is backward compatible with both the old and new JS bundle (that was the expand phase guarantee).

## Step 5 — Monitoring OTA propagation vs. API error rate

Set up a Cloudflare Worker analytics query to track the proportion of requests from each runtimeVersion over the 24 hours following an OTA release:

```typescript
// workers/analytics/src/index.ts — query Analytics Engine
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Requires Analytics Engine binding
    const query = `
      SELECT
        blob3 AS runtime_version,
        SUM(_sample_interval) AS request_count
      FROM api_requests
      WHERE timestamp > NOW() - INTERVAL '24' HOUR
      GROUP BY runtime_version
      ORDER BY request_count DESC
    `;
    const result = await env.ANALYTICS.query(query);
    return Response.json(result);
  },
};
```

Log `runtimeVersion` to Analytics Engine in the API Worker:

```typescript
// In your API Worker's fetch handler
env.ANALYTICS.writeDataPoint({
  blobs: [request.method, request.url, runtimeVersion ?? "unknown"],
  doubles: [1],
  indexes: [runtimeVersion ?? "unknown"],
});
```

When the proportion of old runtimeVersion requests falls below 1% of traffic (typically 48-72 hours post-OTA), it is safe to remove the legacy compatibility code from the Worker.

## Anti-patterns

- **Shipping OTA before Worker deploy**: Even a 30-second window can be significant at high traffic. The Worker must always deploy first.
- **Assuming OTA "instantly" replaces all app instances**: Devices update the JS bundle on next app launch after the update is available. Background-launched sessions may run stale bundles for hours.
- **Using app semver string for API compatibility gating**: The version string in `Constants.expoConfig.version` is user-facing and not reliable for API contract routing. Use `runtimeVersion` (transmitted via `Expo-Runtime-Version` header) instead.
- **Removing legacy Worker endpoints the same week as OTA**: Give at least one runtimeVersion cycle (the full store review + OTA propagation window) before removing deprecated endpoints. For a global app, plan for 2-4 weeks minimum.
- **Forgetting that EAS `--branch` maps to an audience**: If you use multiple EAS branches for staged OTA rollout (e.g., `internal`, `staging`, `production`), the Worker must be compatible with all active branches simultaneously — they all hit the same Worker.

## Gotchas

- Expo SDK `expo-updates` sends `Expo-Runtime-Version` in the header only when the app is running in production mode with `expo-updates` configured. In Expo Go or development builds, the header may be absent — code defensively with a fallback.
- `eas update:republish` re-publishes a previous group to the branch but does not undo the group from existing devices that already downloaded it. Devices cache the latest bundle they received; a republish only affects devices that haven't yet downloaded the bad bundle.
- Native builds submitted to the store carry a specific `runtimeVersion` embedded in the binary. If you use `"policy": "fingerprint"`, the runtimeVersion changes whenever native dependencies change, which can be hard to track. Consider an explicit numeric `runtimeVersion` for tighter control.
- Cloudflare Workers do not currently support reading the `Expo-Runtime-Version` header in Cloudflare Access policies — header-based routing must be done in Worker code, not Access rules.
- EAS Update adoption metrics (available in the EAS dashboard) show download counts, not successful launch counts. A device that downloaded the update but crashed immediately still counts as "received".

## Verification

```bash
# Confirm Worker is serving the new API version to runtimeVersion 53
curl -s \
  -H "Expo-Runtime-Version: 53" \
  "https://api.orchords.workers.dev/api/health" | jq .

# Confirm Worker still serves legacy shape to runtimeVersion 52
curl -s \
  -H "Expo-Runtime-Version: 52" \
  "https://api.orchords.workers.dev/api/user/me" \
  -H "Authorization: Bearer $TEST_TOKEN" | jq 'has("user_id")'

# Check OTA update publication status
eas update:list --branch production --limit 5

# Monitor OTA adoption (EAS CLI)
eas update:view <update-group-id>
```

## Related

- `mobile-app-store-staged-rollout.md`
- `workers-service-bindings-deployment-ordering.md`
- `feature-flag-deploy-coupling.md`
- `api-versioning-2026.md`
- `event-schema-compat-deploys.md`
- `rollback-strategies-workers-pages.md`
- `worker-versioning-gradual-rollout.md`

## Sources

- Expo EAS Update documentation: https://docs.expo.dev/eas-update/introduction/
- EAS Update runtime versions: https://docs.expo.dev/eas-update/runtime-versions/
- `eas update` CLI reference: https://docs.expo.dev/eas-update/eas-update-with-local-build/
- Cloudflare Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
