# Serving AR 3D Assets via Cloudflare Workers and R2 for Android ARCore

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Android ARCore apps that load `.glb` or `.gltf` model files at runtime suffer from high
first-load latency because the binary assets are often hundreds of megabytes and served from
a single-region origin. By routing asset requests through Cloudflare Workers backed by R2
storage, teams reduce p95 load times significantly and gain per-asset cache control without
re-submitting to the Play Store.

## Context

ARCore's `ModelRenderable.Builder` and the Sceneform-successor `SceneView` library both
accept `Uri` inputs, meaning the model URL can point to any HTTPS endpoint. Cloudflare R2
stores the `.glb` files; a Worker handles signed URL generation, `Range` request pass-through
for partial downloads, and `Cache-Control` headers tuned for immutable versioned assets.
The Android client authenticates with a short-lived JWT from your auth Worker before
requesting each asset URL, keeping R2 credentials off-device entirely.

## Workers R2 Asset Endpoint

```typescript
// workers/src/ar-assets.ts
export interface Env {
  AR_ASSETS: R2Bucket;
  AR_ASSET_CACHE: KVNamespace;
  AUTH_SECRET: string;
}

const ALLOWED_EXTENSIONS = new Set(['.glb', '.gltf', '.bin', '.png', '.jpg', '.webp']);

function assetKey(path: string): string {
  // Strip leading slash and sanitise
  return path.replace(/^\/+/, '').replace(/\.\./g, '');
}

async function verifyJWT(token: string, secret: string): Promise<boolean> {
  const [header, payload, sig] = token.split('.');
  if (!header || !payload || !sig) return false;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify']
  );
  const data = new TextEncoder().encode(`${header}.${payload}`);
  const signature = Uint8Array.from(atob(sig.replace(/-/g, '+').replace(/_/g, '/')), c =>
    c.charCodeAt(0)
  );
  const valid = await crypto.subtle.verify('HMAC', key, signature, data);
  if (!valid) return false;
  const claims = JSON.parse(atob(payload));
  return claims.exp > Math.floor(Date.now() / 1000);
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Validate extension
    const ext = url.pathname.substring(url.pathname.lastIndexOf('.'));
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      return new Response('Unsupported asset type', { status: 415 });
    }

    // Verify bearer JWT
    const auth = req.headers.get('Authorization') ?? '';
    const token = auth.replace(/^Bearer\s+/i, '');
    if (!(await verifyJWT(token, env.AUTH_SECRET))) {
      return new Response('Unauthorized', { status: 401 });
    }

    const key = assetKey(url.pathname);

    // Range support for large GLB files
    const rangeHeader = req.headers.get('Range') ?? undefined;
    const object = rangeHeader
      ? await env.AR_ASSETS.get(key, { range: req.headers })
      : await env.AR_ASSETS.get(key);

    if (!object) {
      return new Response('Asset not found', { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('Cache-Control', 'public, max-age=31536000, immutable');
    headers.set('Accept-Ranges', 'bytes');
    headers.set('Access-Control-Allow-Origin', '*');

    const status = rangeHeader ? 206 : 200;
    return new Response(object.body, { status, headers });
  },
};
```

## Android ARCore Asset Loader

```kotlin
// app/src/main/java/com/example/ar/ArAssetLoader.kt
package com.example.ar

import android.content.Context
import io.github.sceneview.ar.ArSceneView
import io.github.sceneview.node.ModelNode
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File

class ArAssetLoader(
    private val context: Context,
    private val workerBaseUrl: String,
    private val tokenProvider: suspend () -> String
) {
    private val client = OkHttpClient.Builder()
        .cache(okhttp3.Cache(File(context.cacheDir, "ar_assets"), 200L * 1024 * 1024))
        .build()

    suspend fun loadModel(sceneView: ArSceneView, assetPath: String): ModelNode =
        withContext(Dispatchers.IO) {
            val token = tokenProvider()
            val url = "$workerBaseUrl/assets/$assetPath"

            val request = Request.Builder()
                .url(url)
                .header("Authorization", "Bearer $token")
                .build()

            val cacheFile = File(context.cacheDir, "ar_assets/${assetPath.hashCode()}.glb")

            if (!cacheFile.exists()) {
                val response = client.newCall(request).execute()
                if (!response.isSuccessful) {
                    throw RuntimeException("Asset fetch failed: ${response.code}")
                }
                cacheFile.parentFile?.mkdirs()
                response.body?.byteStream()?.use { input ->
                    cacheFile.outputStream().use { output -> input.copyTo(output) }
                }
            }

            withContext(Dispatchers.Main) {
                ModelNode(
                    modelInstance = sceneView.modelLoader.createModelInstance(
                        fileLocation = cacheFile.absolutePath
                    )
                )
            }
        }
}
```

## Cache-Control Strategy for Versioned 3D Assets

```typescript
// workers/src/ar-asset-manifest.ts
// Serves a manifest mapping logical names to versioned R2 keys
export interface AssetManifest {
  version: string;
  assets: Record<string, string>; // logical name -> versioned R2 key
}

export async function serveManifest(env: { AR_ASSET_CACHE: KVNamespace }): Promise<Response> {
  const cached = await env.AR_ASSET_CACHE.get<AssetManifest>('manifest', 'json');
  if (cached) {
    return Response.json(cached, {
      headers: {
        'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
        'Content-Type': 'application/json',
      },
    });
  }

  // KV miss — rebuild manifest from R2 listing (expensive, cached for 60s)
  return Response.json({ error: 'manifest not found' }, { status: 503 });
}

// Upload script (run locally / in CI)
// wrangler kv key put --binding AR_ASSET_CACHE manifest '{"version":"2026-08-23","assets":{"robot":"models/robot-v4.glb"}}'
```

## Anti-patterns

- Embedding R2 public bucket URLs directly in the APK — if you rotate or restrict the bucket,
  all shipped app versions break with no way to patch without a full app update.
- Downloading entire GLB files before rendering — use `Range` requests and ARCore's streaming
  loaders where available to show partial models while the rest downloads.
- Using a single immutable `Cache-Control` header on the manifest file — the manifest changes
  frequently; only the versioned asset keys deserve `immutable`.

## Gotchas

- R2 `get()` with `range: req.headers` returns an `R2ObjectBody` whose `.size` reflects the
  full object size, not the range size; always read `Content-Range` from the written headers
  to send back the correct `Content-Length`.
- OkHttp's disk cache and ARCore's own file cache can conflict — store AR assets in a
  separate subdirectory and manage eviction manually based on available disk space.

## Verification

```bash
# Upload a test GLB to R2
npx wrangler r2 object put ar-assets/models/cube-v1.glb --file ./assets/cube.glb

# Start Workers dev server
npx wrangler dev --port 8787

# Request with a valid JWT (generate one for testing)
TOKEN=$(node -e "
  const crypto = require('crypto');
  const h = Buffer.from(JSON.stringify({alg:'HS256',typ:'JWT'})).toString('base64url');
  const p = Buffer.from(JSON.stringify({sub:'test',exp:Math.floor(Date.now()/1000)+3600})).toString('base64url');
  const sig = crypto.createHmac('sha256','dev-secret').update(h+'.'+p).digest('base64url');
  console.log(h+'.'+p+'.'+sig);
")
curl -si -H "Authorization: Bearer $TOKEN" \
  http://localhost:8787/assets/models/cube-v1.glb \
  | head -20

# Verify range support
curl -si -H "Authorization: Bearer $TOKEN" \
  -H "Range: bytes=0-1023" \
  http://localhost:8787/assets/models/cube-v1.glb \
  | grep -i 'content-range'
```

## Related

- `mobile/android-app-bundle.md`
- `mobile/mobile-app-size-optimization.md`
- `mobile/cloudflare-r2-presigned-url-mobile-clock-drift.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/workers/runtime-apis/request/#the-cf-property
- https://github.com/SceneView/sceneview-android
