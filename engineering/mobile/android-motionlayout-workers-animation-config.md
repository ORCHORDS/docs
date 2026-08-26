# Android MotionLayout Workers Animation Config

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

The design team needs to update MotionLayout animation parameters (durations, easing curves,
constraint keyframes) without shipping a new APK. A Cloudflare Workers endpoint serves a JSON
config that the app fetches at launch and caches in KV. Changes to animation behaviour are
deployed to Workers and take effect within the next app open.

## Context

MotionLayout reads its animations from `MotionScene` XML compiled into the APK. To make
parameters remotely configurable, the app fetches an overlay config from Workers, parses it,
and applies values programmatically via `MotionLayout.getTransition()` and
`KeyFrameSet` attribute injection at runtime. Workers KV stores the config with a short TTL so
rollouts are near-instant.

---

## 1. Workers Config Endpoint

```typescript
// worker/src/animation-config.ts
export interface AnimationConfig {
  version: number;
  transitions: TransitionConfig[];
}

export interface TransitionConfig {
  id: string; // matches MotionScene transition @id
  duration: number; // ms
  easing: string; // "linear" | "easeIn" | "easeOut" | "easeInOut" | "anticipate" | "bounce"
  staggered?: boolean;
  keyframes?: KeyframeConfig[];
}

export interface KeyframeConfig {
  framePosition: number; // 0–100
  target: string; // view ID
  scaleX?: number;
  scaleY?: number;
  alpha?: number;
  translationY?: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const cached = await env.ANIM_KV.get<AnimationConfig>(
      "animation:config",
      { type: "json" }
    );
    if (cached) {
      return Response.json(cached, {
        headers: { "Cache-Control": "public, max-age=300" },
      });
    }
    // Default config — returned when KV is empty
    const defaults: AnimationConfig = {
      version: 1,
      transitions: [
        { id: "main_expand", duration: 350, easing: "easeInOut" },
        { id: "detail_slide", duration: 280, easing: "easeOut" },
      ],
    };
    await env.ANIM_KV.put("animation:config", JSON.stringify(defaults), {
      expirationTtl: 3600,
    });
    return Response.json(defaults, {
      headers: { "Cache-Control": "public, max-age=300" },
    });
  },
};
```

---

## 2. Android HTTP Fetch (Kotlin Coroutines)

```kotlin
// AnimationConfigRepository.kt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.net.URL

@Serializable
data class AnimationConfig(
    val version: Int,
    val transitions: List<TransitionConfig>,
)

@Serializable
data class TransitionConfig(
    val id: String,
    val duration: Int,
    val easing: String,
    val staggered: Boolean = false,
    val keyframes: List<KeyframeConfig> = emptyList(),
)

@Serializable
data class KeyframeConfig(
    val framePosition: Int,
    val target: String,
    val scaleX: Float? = null,
    val scaleY: Float? = null,
    val alpha: Float? = null,
    val translationY: Float? = null,
)

class AnimationConfigRepository(
    private val workersBaseUrl: String,
    private val cache: AnimationConfigCache,
) {
    private val json = Json { ignoreUnknownKeys = true }

    suspend fun fetchConfig(): AnimationConfig = withContext(Dispatchers.IO) {
        val local = cache.load()
        if (local != null && !cache.isStale()) return@withContext local
        runCatching {
            val raw = URL("$workersBaseUrl/api/animation-config").readText()
            val config = json.decodeFromString<AnimationConfig>(raw)
            cache.save(config)
            config
        }.getOrDefault(local ?: AnimationConfig(version = 1, transitions = emptyList()))
    }
}
```

---

## 3. Applying Config to MotionLayout at Runtime

```kotlin
// AnimationConfigApplier.kt
import androidx.constraintlayout.motion.widget.MotionLayout
import androidx.constraintlayout.motion.widget.MotionScene

class AnimationConfigApplier(private val motionLayout: MotionLayout) {

    fun apply(config: AnimationConfig) {
        val scene = motionLayout.scene ?: return
        config.transitions.forEach { tc ->
            val transitionId = motionLayout.context.resources.getIdentifier(
                tc.id, "id", motionLayout.context.packageName
            )
            if (transitionId == 0) return@forEach
            // Set duration
            motionLayout.getTransition(transitionId)?.duration = tc.duration
            // Set interpolator
            motionLayout.getTransition(transitionId)?.interpolatorRes =
                easingToInterpolator(tc.easing)
        }
        motionLayout.rebuildScene()
    }

    private fun easingToInterpolator(easing: String): Int {
        return when (easing) {
            "linear" -> android.R.interpolator.linear
            "easeIn" -> android.R.interpolator.accelerate_quad
            "easeOut" -> android.R.interpolator.decelerate_quad
            "easeInOut" -> android.R.interpolator.accelerate_decelerate
            "anticipate" -> android.R.interpolator.anticipate
            "bounce" -> android.R.interpolator.bounce
            else -> android.R.interpolator.accelerate_decelerate
        }
    }
}
```

---

## 4. ViewModel Wiring

```kotlin
// AnimationViewModel.kt
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class AnimationViewModel(
    private val repo: AnimationConfigRepository,
) : ViewModel() {

    private val _config = MutableStateFlow<AnimationConfig?>(null)
    val config: StateFlow<AnimationConfig?> = _config

    init {
        viewModelScope.launch {
            _config.value = repo.fetchConfig()
        }
    }
}

// In Fragment / Activity:
// lifecycleScope.launch {
//     viewModel.config.filterNotNull().collect { config ->
//         applier.apply(config)
//     }
// }
```

---

## 5. Workers Admin Endpoint to Update Config

```typescript
// worker/src/admin-update.ts
export async function handleAdminUpdate(req: Request, env: Env): Promise<Response> {
  const authHeader = req.headers.get("Authorization");
  if (authHeader !== `Bearer ${env.ADMIN_SECRET}`) {
    return new Response("Unauthorized", { status: 401 });
  }
  const newConfig = await req.json<AnimationConfig>();
  newConfig.version = Date.now(); // monotonic version via timestamp
  await env.ANIM_KV.put("animation:config", JSON.stringify(newConfig), {
    expirationTtl: 86400,
  });
  // Purge Cloudflare cache for the public endpoint
  await fetch("https://api.cloudflare.com/client/v4/zones/" + env.ZONE_ID + "/purge_cache", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ files: [`${env.WORKERS_URL}/api/animation-config`] }),
  });
  return Response.json({ ok: true, version: newConfig.version });
}
```

---

## Anti-patterns

- **Blocking the main thread on config fetch** — always fetch on a coroutine dispatcher;
  MotionLayout must only be touched on the main thread after the coroutine completes.
- **Re-creating the entire MotionScene** — `rebuildScene()` is lighter than replacing the
  whole XML; avoid inflating a new MotionScene from scratch on every config refresh.
- **Hardcoding view IDs as strings** — use `resources.getIdentifier` with a fallback to 0
  and skip gracefully; missing IDs after ProGuard minification will crash silently.
- **Using Wall-clock time as cache TTL in KV** — set `expirationTtl` (relative) not
  `expiration` (absolute epoch) to avoid stale configs when the KV write is delayed.

## Gotchas

- **`getTransition()` returns null** — if the MotionScene XML does not declare a transition
  with the given ID, the call returns null; guard every access.
- **`rebuildScene()` resets in-progress animations** — call `apply()` before the user triggers
  an animation, not during; use a `lifecycleScope.launch` in `onStart` rather than mid-gesture.
- **KV eventual consistency** — a config write may not be visible in all regions for up to
  60 seconds; use Workers KV's `consistency` tier or Durable Objects for instant propagation.
- **ProGuard and serialization** — add keep rules for all `@Serializable` data classes if
  using R8 with kotlinx-serialization; otherwise field names are mangled and JSON parsing fails.

## Verification

```bash
# Push a new animation config
curl -X POST https://api.example.com/api/admin/animation-config \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"version":0,"transitions":[{"id":"main_expand","duration":500,"easing":"bounce"}]}'

# Verify KV write
wrangler kv key get animation:config --namespace-id $ANIM_KV_ID

# Confirm public endpoint returns new duration
curl -s https://api.example.com/api/animation-config | jq '.transitions[0].duration'
```

## Related

- `android-jetpack-compose.md`
- `android-material-design-3.md`
- `mobile-feature-flags-remote-config.md`
- `mobile-version-gating-workers-edge-flags.md`

## Sources

- https://developer.android.com/develop/ui/views/animations/motionlayout
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developer.android.com/reference/androidx/constraintlayout/motion/widget/MotionLayout
- https://developers.cloudflare.com/cache/how-to/purge-cache/
