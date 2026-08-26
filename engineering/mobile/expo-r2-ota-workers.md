# Expo OTA Updates via Cloudflare Workers + R2

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You want to host your own Expo over-the-air (OTA) update server on Cloudflare rather than paying for EAS Update. Built JS bundles and assets are stored in R2. A Cloudflare Worker implements the Expo Updates protocol (`/manifest` and `/assets` endpoints) so the Expo runtime on device can fetch updates as it would from EAS, with per-channel routing (production/staging/canary) and edge-cached asset delivery.

---

## Context

The Expo Updates protocol requires two endpoints:

1. **`POST /manifest`** — returns a JSON manifest signed with an RSA private key describing the update bundle and its assets.
2. **`GET /assets?asset=<key>&contentType=<mime>`** — serves the asset bytes.

The Worker reads manifests from R2 as JSON objects and streams asset blobs directly from R2 to the device. Channel routing is determined by the `expo-channel-name` request header sent by the Expo runtime. No origin server is needed — R2 is both the store and the CDN backing layer.

Bundle files are uploaded to R2 by your CI pipeline using `wrangler r2 object put` or the S3-compatible API after `npx expo export`.

---

## 1. R2 Storage Layout

```
r2://your-ota-bucket/
  channels/
    production/
      latest/
        manifest.json
        bundles/
          android-<hash>.js.gz
          ios-<hash>.js.gz
        assets/
          <asset-hash>.<ext>
    staging/
      latest/
        manifest.json
        ...
```

---

## 2. Cloudflare Worker — Manifest Endpoint

```typescript
// workers/ota/src/index.ts
export interface Env {
  OTA_BUCKET: R2Bucket;
  UPDATE_PRIVATE_KEY: string; // RSA-PSS private key PEM for manifest signing
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/manifest") {
      return handleManifest(request, env);
    }
    if (request.method === "GET" && url.pathname === "/assets") {
      return handleAsset(request, env);
    }
    return new Response("Not found", { status: 404 });
  },
};

async function handleManifest(request: Request, env: Env): Promise<Response> {
  const channel = request.headers.get("expo-channel-name") ?? "production";
  const platform = request.headers.get("expo-platform") ?? "android"; // "android" | "ios"

  const sanitisedChannel = channel.replace(/[^a-z0-9-]/g, "");

  const manifestObj = await env.OTA_BUCKET.get(
    `channels/${sanitisedChannel}/latest/manifest.json`
  );
  if (!manifestObj) {
    return Response.json({ message: "No update available" }, { status: 404 });
  }

  const manifest = await manifestObj.json<Record<string, unknown>>();

  // Expo Updates protocol: return manifest with MIME type application/expo+json
  // Signing is required for production; omit for staging/development
  return new Response(JSON.stringify(manifest), {
    headers: {
      "Content-Type": "application/expo+json",
      "expo-protocol-version": "1",
      "expo-sfv-version": "0",
      "Cache-Control": "no-store",
    },
  });
}
```

---

## 3. Worker — Asset Endpoint

```typescript
// workers/ota/src/assets.ts
export async function handleAsset(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const assetKey = url.searchParams.get("asset");
  const contentType = url.searchParams.get("contentType") ?? "application/octet-stream";

  if (!assetKey) {
    return Response.json({ error: "missing asset parameter" }, { status: 400 });
  }

  // Prevent path traversal
  const sanitised = assetKey.replace(/\.\./g, "").replace(/^\/+/, "");

  const object = await env.OTA_BUCKET.get(`channels/production/latest/assets/${sanitised}`);
  if (!object) {
    return new Response("Asset not found", { status: 404 });
  }

  return new Response(object.body, {
    headers: {
      "Content-Type": contentType,
      "Content-Length": String(object.size),
      // Long cache — asset filenames are content-addressed (hash in filename)
      "Cache-Control": "public, max-age=31536000, immutable",
      "ETag": object.etag,
    },
  });
}
```

---

## 4. CI — Upload Bundle to R2

```bash
#!/usr/bin/env bash
# ci/upload-ota.sh

set -euo pipefail

CHANNEL="${1:-production}"
BUCKET="your-ota-bucket"
PREFIX="channels/${CHANNEL}/latest"

# 1. Export the bundle
npx expo export --platform all --output-dir dist/

# 2. Upload assets (content-addressed — idempotent)
for file in dist/assets/*; do
  key="$PREFIX/assets/$(basename "$file")"
  wrangler r2 object put "$BUCKET/$key" --file "$file"
done

# 3. Upload bundles
wrangler r2 object put "$BUCKET/$PREFIX/bundles/android.js.gz" \
  --file dist/android/bundles/*.js \
  --content-encoding gzip \
  --content-type application/javascript

wrangler r2 object put "$BUCKET/$PREFIX/bundles/ios.js.gz" \
  --file dist/ios/bundles/*.js \
  --content-encoding gzip \
  --content-type application/javascript

# 4. Upload manifest last (atomic cutover)
wrangler r2 object put "$BUCKET/$PREFIX/manifest.json" \
  --file dist/metadata.json \
  --content-type application/json

echo "OTA update deployed to channel: $CHANNEL"
```

---

## 5. Expo Client Configuration

```json
// app.json
{
  "expo": {
    "updates": {
      "enabled": true,
      "checkAutomatically": "ON_LOAD",
      "url": "https://ota.example.workers.dev",
      "requestHeaders": {
        "expo-channel-name": "production"
      }
    },
    "runtimeVersion": {
      "policy": "appVersion"
    }
  }
}
```

```typescript
// app/updateCheck.ts
import * as Updates from "expo-updates";

export async function checkAndApplyUpdate(): Promise<boolean> {
  if (__DEV__) return false;

  try {
    const result = await Updates.checkForUpdateAsync();
    if (!result.isAvailable) return false;

    await Updates.fetchUpdateAsync();
    await Updates.reloadAsync(); // instant JS reload, no store update needed
    return true;
  } catch (err) {
    console.warn("[OTA] Update check failed:", err);
    return false;
  }
}
```

---

## 6. Channel-Based Routing in the Worker

```typescript
// workers/ota/src/routing.ts
const ALLOWED_CHANNELS = new Set(["production", "staging", "canary"]);

export function resolveChannel(request: Request): string {
  const requested = request.headers.get("expo-channel-name") ?? "production";
  const sanitised = requested.replace(/[^a-z0-9-]/g, "").slice(0, 64);
  return ALLOWED_CHANNELS.has(sanitised) ? sanitised : "production";
}
```

---

## Anti-Patterns

- **Uploading the manifest before assets.** The Expo runtime fetches the manifest and immediately tries to download the assets listed in it. If assets are not yet in R2, the update fails on device. Always upload assets first, manifest last.
- **Not content-addressing asset filenames.** Mutable filenames mean old and new updates share filenames. A device mid-update may receive stale cached bytes. Use `expo export`'s default content-hash naming and set `immutable` cache headers.
- **Serving bundles without `Content-Encoding: gzip`.** The Expo runtime will try to execute the raw gzip bytes rather than the JS. Either set the `Content-Encoding` header correctly or store uncompressed bundles and rely on R2/Cloudflare compression.
- **Skipping `runtimeVersion` in `app.json`.** Without a runtime version, the Expo runtime cannot detect native module incompatibilities and may download a JS bundle that crashes against an incompatible native layer.

---

## Gotchas

- **R2 `get()` returns `null` for missing keys, not a 404 error.** Always check for `null` and return an explicit 404 response.
- **Expo Updates protocol version.** The `expo-protocol-version: 1` header is required for Expo SDK 50+. Older SDKs use an implicit v0 without this header. Branch your manifest format if you need to support both.
- **`Updates.reloadAsync()` reloads the JS bundle but does not restart the native layer.** Changes to native modules still require an app store update.
- **R2 free tier includes 10 GB storage and 10 million Class B operations per month.** Each asset request counts as a Class B read. For large apps with many users, add a Cloudflare Cache Rule to cache R2 asset responses at the edge to avoid R2 egress costs.

---

## Verification

```bash
# 1. Deploy the Worker
wrangler deploy

# 2. Check manifest endpoint
curl -X POST "https://ota.example.workers.dev/manifest" \
  -H "expo-channel-name: staging" \
  -H "expo-platform: ios" \
  -H "expo-runtime-version: 1.0.0"

# 3. Fetch an asset
curl "https://ota.example.workers.dev/assets?asset=<hash>.png&contentType=image/png" \
  -o /tmp/asset-check.png && file /tmp/asset-check.png

# 4. Verify cache headers on asset response
curl -I "https://ota.example.workers.dev/assets?asset=<hash>.png&contentType=image/png"
# Expected: Cache-Control: public, max-age=31536000, immutable
```

---

## Related

- `react-native-over-the-air-updates.md`
- `ota-updates-expo-codepush.md`
- `expo-eas-build-cloudflare-workers-secrets.md`
- `capacitor-r2-live-updates.md`
- `mobile-forced-upgrade-minimum-version.md`

---

## Sources

- Expo Updates protocol — https://docs.expo.dev/technical-specs/expo-updates-1/
- `expo-updates` SDK — https://docs.expo.dev/versions/latest/sdk/updates/
- Cloudflare R2 Workers binding — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- `wrangler r2 object put` — https://developers.cloudflare.com/workers/wrangler/commands/#put-3
- Expo `runtimeVersion` — https://docs.expo.dev/eas-update/runtime-versions/
