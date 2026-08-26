# Android Adaptive Icons Workers R2 Asset Serve

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com lets anonymous users choose a custom avatar layer for their adaptive icon
within the app launcher shortcut. Icon assets (foreground layers, background fills, monochrome
variants) must be served consistently across device pixel densities, OEM launchers, and dark/light
wallpaper modes without bundling dozens of PNGs into the APK and inflating download size.

## Context
Android's adaptive icon system requires a foreground layer (usually a 108 dp transparent PNG) and
a background layer, plus an optional monochrome layer for Android 13+ themed icons. By storing
canonical source PNGs in Cloudflare R2 and serving density-correct variants through a Cloudflare
Worker that transforms via `cf.image`, the APK only ships one tiny placeholder; the runtime icon
badge is fetched and cached locally on first use. The Worker respects `dppx` query params to serve
the right `mdpi`/`hdpi`/`xhdpi`/`xxhdpi`/`xxxhdpi` size.

## Architecture — R2 Storage Layout
Assets are stored in R2 under a structured key space so the Worker can resolve them from a
`userId` (or theme slug for community packs) plus density suffix.

```
r2://example project-assets/
  adaptive-icons/
    themes/
      default/
        foreground.png       <- 432×432 source
        background.png       <- 432×432 source
        monochrome.png       <- 432×432 source
      neon/
        foreground.png
        background.png
        monochrome.png
    users/
      {anonId}/
        foreground.png       <- optional user-uploaded layer
```

## Workers Side — Icon Serve Endpoint
The Worker receives `GET /icon/{themeSlug}/{layer}?dppx=3` and returns the appropriately scaled
PNG. Image Transform is applied at the CDN edge so the Worker itself does no pixel manipulation.

```typescript
// worker/src/adaptive-icon.ts
import { Env } from './types';

const DENSITY_MAP: Record<string, number> = {
  '1': 48,   // mdpi
  '1.5': 72, // hdpi
  '2': 96,   // xhdpi
  '3': 144,  // xxhdpi
  '4': 192,  // xxxhdpi
};

const ALLOWED_LAYERS = new Set(['foreground', 'background', 'monochrome']);

export async function handleAdaptiveIcon(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const parts = url.pathname.split('/').filter(Boolean); // ['icon', themeSlug, layer]

  if (parts.length < 3) return new Response('Bad Request', { status: 400 });

  const [, themeSlug, layer] = parts;
  if (!ALLOWED_LAYERS.has(layer)) return new Response('Not Found', { status: 404 });

  const dppx = url.searchParams.get('dppx') ?? '2';
  const sizePx = DENSITY_MAP[dppx] ?? 96;

  // Resolve anonId from header for user-specific overrides
  const anonId = request.headers.get('X-Anon-Id');
  let r2Key = `adaptive-icons/themes/${themeSlug}/${layer}.png`;

  if (anonId && layer === 'foreground') {
    const userKey = `adaptive-icons/path/to/foreground.png`;
    const userObj = await env.ASSETS.head(userKey);
    if (userObj) r2Key = userKey;
  }

  const obj = await env.ASSETS.get(r2Key);
  if (!obj) return new Response('Not Found', { status: 404 });

  // Use Cloudflare Image Resizing via fetch re-dispatch
  const imageRequest = new Request(
    `https://example project-assets.example.com/${r2Key}?width=${sizePx}&height=${sizePx}&fit=contain&format=png`,
    { cf: { image: { width: sizePx, height: sizePx, fit: 'contain', format: 'png' } } } as RequestInit,
  );

  // For Workers that serve R2 directly without Images binding, stream the raw object
  // and let Cache API handle CDN-layer resizing via transform rules instead.
  const cacheKey = new Request(url.toString(), request);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const body = await obj.arrayBuffer();
  const response = new Response(body, {
    headers: {
      'Content-Type': 'image/png',
      'Cache-Control': 'public, max-age=86400, stale-while-revalidate=3600',
      'Vary': 'Accept',
      'X-Theme': themeSlug,
      'X-Density': dppx,
    },
  });

  // Store in edge cache
  await cache.put(cacheKey, response.clone());
  return response;
}
```

## Android Side — Fetching and Applying the Dynamic Icon Layer
The Android app fetches the foreground layer at app start (or after theme change) and writes it to
the internal files directory. A custom `AdaptiveIconDrawable` wraps the downloaded bitmap alongside
a static XML background so the launcher sees a fully conformant adaptive icon.

```kotlin
// IconLayerFetcher.kt
import android.content.Context
import android.graphics.BitmapFactory
import androidx.core.graphics.drawable.toBitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.URL

object IconLayerFetcher {

    private const val BASE_URL = "https://api.example.com/icon"

    suspend fun fetchForeground(
        context: Context,
        themeSlug: String,
        anonId: String,
        dppx: Int,
    ): File = withContext(Dispatchers.IO) {
        val dest = File(context.filesDir, "icon_fg_${themeSlug}_${dppx}x.png")

        if (dest.exists() && System.currentTimeMillis() - dest.lastModified() < 86_400_000L) {
            return@withContext dest
        }

        val url = URL("$BASE_URL/$themeSlug/foreground?dppx=$dppx")
        val conn = url.openConnection()
        conn.setRequestProperty("X-Anon-Id", anonId)
        conn.connect()

        dest.outputStream().use { out ->
            conn.getInputStream().use { it.copyTo(out) }
        }

        dest
    }
}
```

```kotlin
// DynamicAdaptiveIcon.kt
import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.drawable.AdaptiveIconDrawable
import android.graphics.drawable.BitmapDrawable
import androidx.core.content.ContextCompat
import java.io.File

fun buildAdaptiveIconDrawable(context: Context, foregroundFile: File): AdaptiveIconDrawable {
    val bitmap = BitmapFactory.decodeFile(foregroundFile.absolutePath)
    val foreground = BitmapDrawable(context.resources, bitmap)
    val background = ContextCompat.getDrawable(context, R.drawable.ic_adaptive_bg)!!

    return AdaptiveIconDrawable(background, foreground)
}
```

## Themed / Monochrome Layer Handling (Android 13+)
For Android 13+ themed icons, the app fetches the `monochrome` layer separately and applies it via
the `ShortcutInfoCompat.Builder` when pinning app shortcuts.

```kotlin
// ShortcutHelper.kt
import android.content.Context
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

fun pinProfileShortcut(context: Context, anonId: String, themeSlug: String) {
    CoroutineScope(Dispatchers.IO).launch {
        val density = context.resources.displayMetrics.density.toInt().coerceIn(1, 4)
        val fgFile = IconLayerFetcher.fetchForeground(context, themeSlug, anonId, density)
        val drawable = buildAdaptiveIconDrawable(context, fgFile)
        val icon = IconCompat.createWithAdaptiveBitmap(drawable.toBitmap(192, 192))

        val shortcut = ShortcutInfoCompat.Builder(context, "profile_$anonId")
            .setShortLabel("My Wams")
            .setIcon(icon)
            .setIntent(android.content.Intent("android.intent.action.VIEW").apply {
                data = android.net.Uri.parse("example project://profile/$anonId")
            })
            .build()

        ShortcutManagerCompat.pushDynamicShortcut(context, shortcut)
    }
}
```

## Anti-patterns
- Bundling all density variants in `res/mipmap-*` — this inflates APK size for artwork that changes
  per user; delegate to R2 + Worker instead.
- Skipping the `anonId` header on the foreground request — the Worker falls back to the default
  theme layer silently, which is correct behaviour but confusing during debugging.
- Caching the file indefinitely on device — `themeSlug` could be updated by a server-side push;
  check `lastModified` against a 24 h TTL.
- Using `ImageView` with a remote URL for adaptive icons — adaptive icons require `AdaptiveIconDrawable`,
  not a plain bitmap loaded into a view.

## Gotchas
- Cloudflare Image Resizing requires a paid plan and the `cf.image` object in fetch options only
  works when the Worker is proxying a publicly routable URL, not an R2 stream; either use an Images
  Transform Rule in the dashboard or the `/cdn-cgi/image/` URL variant.
- The `monochrome` layer on Android 13 must be a single-channel (greyscale-rendered) PNG; OEMs
  tint it with the system wallpaper accent colour — test on Pixel and Samsung launchers.
- `ShortcutManagerCompat.pushDynamicShortcut` is rate-limited by the system; do not call it on
  every app launch.
- R2 `head()` calls count against Class A operation limits; cache the existence check in Workers KV
  with a short TTL if user-override adoption is high.

## Verification
1. Upload a test foreground PNG to R2: `wrangler r2 object put example project-assets/adaptive-icons/themes/neon/foreground.png --file=./neon_fg.png`.
2. Hit `curl "https://api.example.com/icon/neon/foreground?dppx=3" -H "X-Anon-Id: test123" -o out.png` and inspect dimensions (`file out.png` should show 144×144 or source size if transform rules are not yet active).
3. Run the Android app on a Pixel device, change theme to `neon`, and long-press the app icon to verify the foreground updates within the launcher.
4. Check R2 access logs in Cloudflare dashboard to confirm cache hits on subsequent requests.

## Related
- `/documentation/categories/mobile/android-workmanager-workers-sync.md`
- `/documentation/categories/mobile/react-native-workers-image-cache-r2-cdn.md`
- `/documentation/categories/mobile/flutter-workers-image-transform-cdn.md`

## Sources
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/images/transform-images/
- https://developer.android.com/develop/ui/views/launch/icon_design_adaptive
- https://developer.android.com/reference/android/graphics/drawable/AdaptiveIconDrawable
