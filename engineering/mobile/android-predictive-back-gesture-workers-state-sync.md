# Android Predictive Back Gesture with Cloudflare Workers State Sync

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Android app (API 35+) adopts the predictive back gesture but the back-navigation animation reveals stale data in the destination screen. The user swipes back, sees an animated preview of the previous screen, and the data shown in that preview is seconds or minutes old. You need the Workers backend to push a lightweight state snapshot so the destination screen is warm before the user commits to the swipe.

---

## Context

Android's predictive back gesture (stable on API 35, opt-in from API 33) fires `OnBackPressedCallback` events during the swipe gesture itself — before the user lifts their finger. The window: `onBackStarted` → user decides → `onBackProgressed` → `onBackInvoked` or `onBackCancelled`. This gives you 100–400 ms to warm up the destination screen.

Cloudflare Workers paired with KV or Durable Objects can serve a thin "preview snapshot" endpoint that returns the minimal state needed to render the destination screen above the fold. The Worker response must arrive inside the animation window (~200 ms budget from swipe start on a fast connection).

```toml
# wrangler.toml
name = "state-sync-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[kv_namespaces]]
binding = "SNAPSHOTS"
id = "YOUR_KV_NAMESPACE_ID"
```

---

## 1. Worker: Snapshot Endpoint

```typescript
// src/index.ts
export interface Env {
  SNAPSHOTS: KVNamespace;
}

interface ScreenSnapshot {
  screenId: string;
  userId: string;
  payload: Record<string, unknown>;
  generatedAt: number;
  ttl: number; // seconds
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname.startsWith("/snapshot/")) {
      const screenId = url.pathname.replace("/snapshot/", "");
      const userId = request.headers.get("x-user-id");
      if (!userId || !screenId) {
        return new Response("Bad request", { status: 400 });
      }

      const key = `snap:${userId}:${screenId}`;
      const snapshot = await env.SNAPSHOTS.get<ScreenSnapshot>(key, "json");

      if (!snapshot) {
        return new Response(JSON.stringify({ empty: true }), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        });
      }

      return new Response(JSON.stringify(snapshot), {
        headers: {
          "content-type": "application/json",
          "cache-control": `private, max-age=${snapshot.ttl}`,
        },
      });
    }

    if (request.method === "PUT" && url.pathname.startsWith("/snapshot/")) {
      const screenId = url.pathname.replace("/snapshot/", "");
      const userId = request.headers.get("x-user-id");
      if (!userId || !screenId) {
        return new Response("Bad request", { status: 400 });
      }

      const body = await request.json<{ payload: Record<string, unknown>; ttl?: number }>();
      const snapshot: ScreenSnapshot = {
        screenId,
        userId,
        payload: body.payload,
        generatedAt: Date.now(),
        ttl: body.ttl ?? 60,
      };

      const key = `snap:${userId}:${screenId}`;
      await env.SNAPSHOTS.put(key, JSON.stringify(snapshot), {
        expirationTtl: snapshot.ttl,
      });

      return new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## 2. Android: Registering the Predictive Back Callback

```kotlin
// PredictiveBackHandler.kt (Kotlin, called from your Fragment/Activity)
import androidx.activity.BackEventCompat
import androidx.activity.OnBackPressedCallback
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class PredictiveBackHandler(
    private val scope: CoroutineScope,
    private val snapshotRepository: SnapshotRepository,
    private val destinationScreenId: String,
    private val onNavigateBack: () -> Unit,
) : OnBackPressedCallback(true) {

    private var prefetchJob: kotlinx.coroutines.Job? = null

    override fun handleOnBackStarted(backEvent: BackEventCompat) {
        // Fire prefetch immediately — budget is ~200 ms
        prefetchJob = scope.launch(Dispatchers.IO) {
            snapshotRepository.prefetch(destinationScreenId)
        }
    }

    override fun handleOnBackProgressed(backEvent: BackEventCompat) {
        // No-op; animation progress is handled by the system
    }

    override fun handleOnBackInvoked() {
        prefetchJob?.cancel()
        onNavigateBack()
    }

    override fun handleOnBackCancelled() {
        prefetchJob?.cancel()
    }
}
```

---

## 3. Kotlin: Snapshot Repository

```kotlin
// SnapshotRepository.kt
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers

data class ScreenSnapshot(
    val screenId: String,
    val payload: Map<String, Any>,
    val generatedAt: Long,
)

class SnapshotRepository(
    private val httpClient: okhttp3.OkHttpClient,
    private val baseUrl: String,
    private val userId: String,
) {
    // In-memory cache keyed by screenId
    private val cache = java.util.concurrent.ConcurrentHashMap<String, ScreenSnapshot>()

    suspend fun prefetch(screenId: String): ScreenSnapshot? = withContext(Dispatchers.IO) {
        try {
            val request = okhttp3.Request.Builder()
                .url("$baseUrl/snapshot/$screenId")
                .header("x-user-id", userId)
                .build()

            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) return@withContext null

            val json = org.json.JSONObject(response.body!!.string())
            if (json.optBoolean("empty")) return@withContext null

            val snapshot = ScreenSnapshot(
                screenId = screenId,
                payload = json.getJSONObject("payload").toMap(),
                generatedAt = json.getLong("generatedAt"),
            )
            cache[screenId] = snapshot
            snapshot
        } catch (_: Exception) {
            null
        }
    }

    fun getCached(screenId: String): ScreenSnapshot? = cache[screenId]

    suspend fun publish(screenId: String, payload: Map<String, Any>) = withContext(Dispatchers.IO) {
        val body = okhttp3.RequestBody.create(
            okhttp3.MediaType.parse("application/json"),
            org.json.JSONObject(mapOf("payload" to payload, "ttl" to 60)).toString(),
        )
        val request = okhttp3.Request.Builder()
            .url("$baseUrl/snapshot/$screenId")
            .header("x-user-id", userId)
            .put(body)
            .build()
        httpClient.newCall(request).execute()
    }
}

private fun org.json.JSONObject.toMap(): Map<String, Any> =
    keys().asSequence().associateWith { get(it) }
```

---

## 4. Publishing a Snapshot on Screen Load

Call `publish()` when a screen finishes loading its data so the snapshot is warm when the user navigates forward:

```kotlin
// Inside your ViewModel
viewModelScope.launch {
    val data = repository.loadScreenData()
    _uiState.value = data

    // Write warm snapshot for parent screen so back-gesture preview is fresh
    snapshotRepository.publish(
        screenId = "parent_screen",
        payload = mapOf(
            "headerTitle" to data.parentTitle,
            "itemCount" to data.parentItemCount,
            "lastUpdated" to System.currentTimeMillis(),
        ),
    )
}
```

---

## Anti-Patterns

- **Fetching full screen data during the swipe** — the predictive back animation window is too short for a full data load. Only fetch a thumbnail snapshot.
- **Blocking `handleOnBackStarted` on the main thread** — always dispatch the prefetch to `Dispatchers.IO`.
- **Storing large blobs in KV** — KV values are capped at 25 MB but large payloads defeat the low-latency goal. Keep snapshots under 4 KB.
- **Not cancelling `prefetchJob` on `handleOnBackCancelled`** — leaving dangling coroutines wastes bandwidth when the user aborts the swipe.

---

## Gotchas

- Predictive back is gated by `android:enableOnBackInvokedCallback="true"` in `AndroidManifest.xml`. Without this flag, no predictive back events fire.
- KV has eventual consistency; a snapshot written < 100 ms ago may not be visible at a different edge node. Use a short `cache-control: private, max-age=…` header so the client can reuse its own prior fetch without re-hitting KV.
- Cloudflare's nearest PoP from an Android device varies by carrier. In regions where latency to the Worker exceeds 300 ms (rural, emerging markets), fall back to a locally cached snapshot rather than blocking the animation.

---

## Verification

1. Enable predictive back: `adb shell am broadcast -a android.intent.action.BOOT_COMPLETED` then confirm `onBackStarted` fires in Logcat.
2. Add a `System.currentTimeMillis()` timestamp to the snapshot payload and log it in the destination VM — confirm it matches a recent Workers write.
3. Use `wrangler tail` to confirm the `/snapshot/` GET fires within 200 ms of swipe start.
4. Test with Android Network Profiler set to "3G (slow)" to verify graceful fallback to cached snapshot.

---

## Related

- `android-predictive-back-gesture.md`
- `android-workmanager-workers-sync.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md`

---

## Sources

- Android back navigation guide: https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture
- Cloudflare KV docs: https://developers.cloudflare.com/kv/
- `OnBackPressedCallback` API: https://developer.android.com/reference/androidx/activity/OnBackPressedCallback
