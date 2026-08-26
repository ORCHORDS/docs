# Capacitor Live Updates: Deploying JS Bundles to Mobile via Cloudflare R2

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You ship a Capacitor app and need to push JavaScript / web-asset updates to users without going through the App Store or Play Store review cycle. Existing commercial solutions (Appflow, CodePush) are either expensive or locked to a specific framework. You already run your backend on Cloudflare Workers and have R2 for object storage — you want a self-hosted OTA pipeline that costs pennies at scale.

---

## Context

Capacitor wraps a web app in a native WebView. The bundle living in the `public/` directory can be swapped at runtime — the native shell does not change, so no binary review is required. The update lifecycle is:

1. CI builds a new web bundle and uploads it to Cloudflare R2.
2. A Cloudflare Worker exposes a version manifest endpoint.
3. On app launch the Capacitor app fetches the manifest, compares it with the locally installed version stored in `@capacitor/preferences`, and downloads a delta or full bundle.
4. The downloaded bundle is extracted into the app's private file system path.
5. On the next WebView reload the new bundle is served from disk.

This pattern is framework-agnostic (React, Vue, Angular all work) and requires only the `@capacitor/filesystem` and `@capacitor/preferences` plugins plus a Worker + R2 bucket.

---

## 1. R2 Bucket and Worker Setup

Create a bucket and bind it to a Worker. Use a separate bucket for production vs. staging.

```toml
# wrangler.toml
name = "live-updates"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[r2_buckets]]
binding = "BUNDLES"
bucket_name = "app-live-bundles"

[vars]
CURRENT_CHANNEL = "production"
```

The Worker handles two routes:

```typescript
// src/index.ts
export interface Env {
  BUNDLES: R2Bucket;
  CURRENT_CHANNEL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/manifest") {
      return handleManifest(request, env);
    }

    if (url.pathname.startsWith("/bundle/")) {
      return handleBundleDownload(request, env, url);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function handleManifest(
  request: Request,
  env: Env
): Promise<Response> {
  const channel = new URL(request.url).searchParams.get("channel")
    ?? env.CURRENT_CHANNEL;

  const manifestKey = `${channel}/manifest.json`;
  const obj = await env.BUNDLES.get(manifestKey);
  if (!obj) {
    return new Response("No manifest found", { status: 404 });
  }

  const manifest = await obj.json<BundleManifest>();

  return Response.json(manifest, {
    headers: {
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

async function handleBundleDownload(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  // e.g. /bundle/production/1.2.3/bundle.zip
  const key = url.pathname.replace("/bundle/", "");
  const obj = await env.BUNDLES.get(key);
  if (!obj) {
    return new Response("Bundle not found", { status: 404 });
  }

  return new Response(obj.body, {
    headers: {
      "Content-Type": "application/zip",
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
      "ETag": obj.etag,
    },
  });
}

interface BundleManifest {
  version: string;
  channel: string;
  checksum: string;           // sha256 hex of the zip
  url: string;                // absolute URL to the zip
  minNativeVersion: string;   // semver: reject if native < this
  rolloutPercent: number;     // 0–100 staged rollout
  releaseNotes: string;
}
```

---

## 2. CI Upload Script

After `npm run build` produces `dist/`, zip it and upload to R2 via the Wrangler R2 API or AWS SDK (R2 is S3-compatible).

```typescript
// scripts/upload-bundle.ts
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { createHash } from "crypto";
import { createReadStream, readFileSync } from "fs";
import { resolve } from "path";
import { execSync } from "child_process";

const VERSION = process.env.BUNDLE_VERSION!;          // e.g. "2026.08.22-1"
const CHANNEL = process.env.CHANNEL ?? "production";  // staging | production

const client = new S3Client({
  region: "auto",
  endpoint: `https://${process.env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

async function main() {
  // 1. Zip the dist directory
  const zipPath = resolve(`bundle-${VERSION}.zip`);
  execSync(`zip -r ${zipPath} dist/`);

  const zipBuffer = readFileSync(zipPath);
  const checksum = createHash("sha256").update(zipBuffer).digest("hex");

  // 2. Upload the zip
  const bundleKey = `${CHANNEL}/${VERSION}/bundle.zip`;
  await client.send(
    new PutObjectCommand({
      Bucket: "app-live-bundles",
      Key: bundleKey,
      Body: zipBuffer,
      ContentType: "application/zip",
    })
  );

  // 3. Upload the manifest
  const manifest = {
    version: VERSION,
    channel: CHANNEL,
    checksum,
    url: `https://live-updates.example.workers.dev/bundle/${bundleKey}`,
    minNativeVersion: "1.0.0",
    rolloutPercent: CHANNEL === "production" ? 20 : 100,
    releaseNotes: process.env.RELEASE_NOTES ?? "",
  };

  await client.send(
    new PutObjectCommand({
      Bucket: "app-live-bundles",
      Key: `${CHANNEL}/manifest.json`,
      Body: JSON.stringify(manifest),
      ContentType: "application/json",
    })
  );

  console.log(`Uploaded bundle ${VERSION} to channel ${CHANNEL}`);
}

main();
```

---

## 3. Capacitor Update Client

Install the required plugins:

```bash
npm install @capacitor/filesystem @capacitor/preferences
npx cap sync
```

```typescript
// src/lib/live-update.ts
import { Filesystem, Directory, Encoding } from "@capacitor/filesystem";
import { Preferences } from "@capacitor/preferences";
import { createHash } from "crypto";        // polyfilled in the WebView

const MANIFEST_URL = "https://live-updates.example.workers.dev/manifest";
const PREFS_KEY_VERSION = "liveUpdate:installedVersion";
const PREFS_KEY_PATH   = "liveUpdate:bundlePath";

export interface UpdateResult {
  updated: boolean;
  version?: string;
  error?: string;
}

export async function checkAndApplyUpdate(
  currentNativeVersion: string
): Promise<UpdateResult> {
  try {
    const channel = __DEV__ ? "staging" : "production";
    const res = await fetch(`${MANIFEST_URL}?channel=${channel}`, {
      cache: "no-store",
    });
    if (!res.ok) return { updated: false };

    const manifest = await res.json();

    // Staged rollout gate
    if (manifest.rolloutPercent < 100) {
      const roll = Math.floor(Math.random() * 100);
      if (roll >= manifest.rolloutPercent) return { updated: false };
    }

    const { value: installed } = await Preferences.get({
      key: PREFS_KEY_VERSION,
    });
    if (installed === manifest.version) return { updated: false };

    // Native version gate
    if (!semverGte(currentNativeVersion, manifest.minNativeVersion)) {
      return { updated: false, error: "Native version too old" };
    }

    // Download
    const bundleRes = await fetch(manifest.url);
    const arrayBuffer = await bundleRes.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);

    // Checksum verification
    const hash = await subtleSha256Hex(bytes);
    if (hash !== manifest.checksum) {
      return { updated: false, error: "Checksum mismatch" };
    }

    // Write zip to private storage
    const base64 = uint8ToBase64(bytes);
    const zipPath = `live-update-${manifest.version}.zip`;
    await Filesystem.writeFile({
      path: zipPath,
      data: base64,
      directory: Directory.Cache,
    });

    // Unzip into Documents (persists across app restarts)
    // On iOS use Cordova-plugin-zip or a native unzip bridge
    const destDir = `bundles/${manifest.version}`;
    await unzipToDirectory(zipPath, destDir);

    // Persist metadata
    await Preferences.set({ key: PREFS_KEY_VERSION, value: manifest.version });
    await Preferences.set({ key: PREFS_KEY_PATH, value: destDir });

    return { updated: true, version: manifest.version };
  } catch (err) {
    console.error("[live-update]", err);
    return { updated: false, error: String(err) };
  }
}

async function subtleSha256Hex(data: Uint8Array): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function uint8ToBase64(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary);
}

function semverGte(a: string, b: string): boolean {
  const parse = (s: string) => s.split(".").map(Number);
  const [aMaj, aMin, aPatch] = parse(a);
  const [bMaj, bMin, bPatch] = parse(b);
  if (aMaj !== bMaj) return aMaj > bMaj;
  if (aMin !== bMin) return aMin > bMin;
  return aPatch >= bPatch;
}

// stub — implement with a native Capacitor plugin or cordova-plugin-zip
async function unzipToDirectory(zip: string, dest: string): Promise<void> {
  // @ts-ignore — native bridge call
  await (window as any).CapacitorUnzip?.unzip({ source: zip, dest });
}
```

---

## 4. Initialising the Update in `App.tsx`

```typescript
// App.tsx
import { useEffect } from "react";
import { App as CapApp } from "@capacitor/app";
import { checkAndApplyUpdate } from "./lib/live-update";
import { Device } from "@capacitor/device";

export default function App() {
  useEffect(() => {
    async function bootstrap() {
      const info = await Device.getInfo();
      // Native app version comes from the binary, not the JS bundle
      const nativeVersion = (await CapApp.getInfo()).version;

      const result = await checkAndApplyUpdate(nativeVersion);
      if (result.updated) {
        // Reload WebView to activate the new bundle
        window.location.reload();
      }
    }

    bootstrap();
  }, []);

  return <YourRouterRoot />;
}
```

---

## 5. Rollback Safety

Always keep the last known-good bundle path in Preferences. On three consecutive crash signals within 5 seconds of applying an update, revert:

```typescript
// src/lib/crash-guard.ts
import { Preferences } from "@capacitor/preferences";

const KEY_CRASH_COUNT = "liveUpdate:crashCount";
const KEY_CRASH_TS    = "liveUpdate:crashTs";
const KEY_PREV_PATH   = "liveUpdate:previousPath";
const CRASH_WINDOW_MS = 5_000;

export async function recordStartup() {
  const now = Date.now();
  const { value: tsStr } = await Preferences.get({ key: KEY_CRASH_TS });
  const ts = tsStr ? Number(tsStr) : 0;

  const { value: countStr } = await Preferences.get({ key: KEY_CRASH_COUNT });
  let count = countStr ? Number(countStr) : 0;

  if (now - ts < CRASH_WINDOW_MS) {
    count++;
  } else {
    count = 1;
  }

  await Preferences.set({ key: KEY_CRASH_COUNT, value: String(count) });
  await Preferences.set({ key: KEY_CRASH_TS, value: String(now) });

  if (count >= 3) {
    await rollback();
  }
}

async function rollback() {
  const { value: prev } = await Preferences.get({ key: KEY_PREV_PATH });
  if (!prev) return;

  await Preferences.set({ key: "liveUpdate:bundlePath", value: prev });
  await Preferences.remove({ key: KEY_CRASH_COUNT });
  window.location.reload();
}
```

---

## Anti-Patterns

- **Storing secrets (API keys) inside the JS bundle.** The zip is downloadable by anyone with the signed URL. Secrets belong in the native layer or in Cloudflare Worker secrets.
- **Skipping the checksum check.** A corrupted download silently applied will crash every user.
- **Reloading synchronously on first launch.** Always defer the reload to avoid jank on the initial paint; apply after a user navigates away or backgrounding the app.
- **Not guarding with `minNativeVersion`.** Native plugins can break if the JS bundle assumes a plugin method that the installed binary does not expose.
- **Deploying 100% rollout immediately.** Start at 10–20%, monitor crash-free rates for 24 hours before widening.

---

## Gotchas

- **iOS WebView caching.** `WKWebView` aggressively caches resources. After swapping the bundle path call `window.location.href = window.location.href` rather than just `reload()` to force full re-fetch.
- **Android file:// restrictions.** Capacitor uses `capacitor://localhost` as the WebView origin. The unzipped path must be inside `getFilesDir()` and referenced via the `CapacitorHttp` scheme.
- **R2 presigned URL expiry.** If you use presigned URLs instead of a Worker proxy, they expire. Keep the Worker as a stable URL proxy and let R2 remain private.
- **Bundle size limit.** R2 has no enforced object size limit, but WebView memory on low-end Android (512 MB RAM) will OOM if you try to unzip > 100 MB in-process. Keep bundles under 30 MB by code-splitting and lazy-loading assets from R2 directly.
- **Capacitor Plugin detection.** If the unzip plugin is missing (e.g., first install before plugin sync), the update silently fails — always surface these errors to your error tracker.

---

## Verification

```bash
# 1. Upload a staging bundle
CHANNEL=staging BUNDLE_VERSION=2026.08.22-1 RELEASE_NOTES="Test" \
  npx ts-node scripts/upload-bundle.ts

# 2. Confirm the manifest is reachable
curl -s "https://live-updates.example.workers.dev/manifest?channel=staging" | jq .

# 3. Confirm the zip is downloadable and checksum matches
BUNDLE_URL=$(curl -s ".../manifest?channel=staging" | jq -r .url)
curl -sL "$BUNDLE_URL" | sha256sum

# 4. Build and run the Capacitor app against staging
CHANNEL=staging npx cap run ios
```

---

## Related

- `capacitor-native-bridge-plugin-development.md`
- `cloudflare-r2-presigned-url-mobile-clock-drift.md`
- `react-native-over-the-air-updates.md`
- `ota-updates-expo-codepush.md`
- `mobile-version-gating-workers-edge-flags.md`

---

## Sources

- Capacitor Filesystem Plugin — https://capacitorjs.com/docs/apis/filesystem
- Cloudflare R2 S3-compatible API — https://developers.cloudflare.com/r2/api/s3/
- Cloudflare Workers R2 bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/r2/
- Capacitor live update patterns — https://capacitorjs.com/docs/guides/live-reload
- Web Crypto API `subtle.digest` — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
