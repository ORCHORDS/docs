# Android Compose Navigation Workers Dynamic Deep-Link Routing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Marketing and growth teams need to reroute deep links (e.g. `/promo/summer` →
`ProductDetailScreen`) without publishing a new APK. Static `<intent-filter>` entries are
baked into the manifest at build time. A Cloudflare Worker resolves the logical link to a
typed Compose Navigation destination at runtime, enabling server-controlled routing, A/B
redirect tests, and auth-gated screen redirects — all without an app update.

## Context

Jetpack Compose Navigation 2.7+ supports `navDeepLink { uriPattern = "..." }` and
`NavController.navigate(Uri)`. A Worker endpoint maps path segments to a `ResolvedRoute`
JSON object that the app deserialises and navigates to. The Worker reads overrides from KV so
marketing can publish a redirect in seconds. The Android side uses a lightweight
`DeepLinkActivity` trampoline that calls the Worker before handing control to `MainActivity`.

---

## 1. Workers Route-Resolution Endpoint

```typescript
// worker/src/deep-link-router.ts
export interface ResolvedRoute {
  destination: string;           // Compose route template, e.g. "product/{id}"
  params: Record<string, string>;
  redirect?: string;             // off-app URL (browser redirect)
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const path = url.pathname.replace('/route', '') || '/';  // e.g. "/promo/summer"

    // KV override wins over fallback logic
    const override = await env.ROUTE_KV.get<ResolvedRoute>(`route:${path}`, 'json');
    if (override) return Response.json(override);

    // Fallback: parse common path patterns
    const [, section, id] = path.split('/');
    if (section === 'product' && id) {
      return Response.json({ destination: 'product/{id}', params: { id } } satisfies ResolvedRoute);
    }
    if (section === 'promo' && id) {
      return Response.json({ destination: 'promotions/{slug}', params: { slug: id } } satisfies ResolvedRoute);
    }
    return Response.json({ destination: 'home', params: {} } satisfies ResolvedRoute);
  },
} satisfies ExportedHandler<Env>;
```

---

## 2. Hilt-Injectable Route Resolver

```kotlin
// domain/WorkersRouteResolver.kt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import javax.inject.Inject

@Serializable
data class ResolvedRoute(
    val destination: String,
    val params: Map<String, String>,
    val redirect: String? = null,
)

class WorkersRouteResolver @Inject constructor(
    private val httpClient: OkHttpClient,
    @WorkerBaseUrl private val baseUrl: String,
) {
    suspend fun resolve(path: String): ResolvedRoute = withContext(Dispatchers.IO) {
        val req = Request.Builder().url("$baseUrl/route$path").get().build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string() ?: error("Empty route response")
            Json.decodeFromString(body)
        }
    }
}
```

---

## 3. DeepLinkActivity Trampoline

```kotlin
// ui/DeepLinkActivity.kt
@AndroidEntryPoint
class DeepLinkActivity : ComponentActivity() {

    @Inject lateinit var resolver: WorkersRouteResolver

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val incomingPath = intent.data?.path ?: run { finish(); return }

        lifecycleScope.launch {
            val route = try {
                resolver.resolve(incomingPath)
            } catch (e: Exception) {
                // Fall through to home on network failure
                ResolvedRoute(destination = "home", params = emptyMap())
            }

            if (route.redirect != null) {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(route.redirect)))
                finish()
                return@launch
            }

            // Build app:// URI that matches Compose NavGraph uriPattern
            val appUri = Uri.parse(
                "app://${route.destination.replace("{", "").replace("}", "")}" +
                route.params.values.joinToString("/", prefix = if (route.params.isNotEmpty()) "/" else "")
            )
            startActivity(
                Intent(this@DeepLinkActivity, MainActivity::class.java).apply {
                    data = appUri
                    flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                }
            )
            finish()
        }
    }
}
```

---

## 4. Compose NavGraph with Deep-Link Entries

```kotlin
// ui/NavGraph.kt
@Composable
fun AppNavGraph(navController: NavHostController) {
    NavHost(navController = navController, startDestination = "home") {

        composable("home") { HomeScreen() }

        composable(
            route = "product/{id}",
            deepLinks = listOf(navDeepLink { uriPattern = "app://product/{id}" })
        ) { back ->
            ProductDetailScreen(productId = back.arguments?.getString("id") ?: return@composable)
        }

        composable(
            route = "promotions/{slug}",
            deepLinks = listOf(navDeepLink { uriPattern = "app://promotions/{slug}" })
        ) { back ->
            PromotionScreen(slug = back.arguments?.getString("slug") ?: return@composable)
        }
    }
}
```

---

## 5. KV Override Push from CI or Admin Dashboard

```typescript
// scripts/publish-route-override.ts
const CF_API = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}`;

async function setRouteOverride(path: string, route: ResolvedRoute, ttlSeconds = 604800) {
  await fetch(`${CF_API}/values/route:${encodeURIComponent(path)}?expiration_ttl=${ttlSeconds}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${CF_API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(route),
  });
}

// Example: redirect /promo/summer → product detail
await setRouteOverride('/promo/summer', {
  destination: 'product/{id}',
  params: { id: 'prod-789' },
});
```

---

## Anti-patterns

- Putting the final navigation target in the manifest `<intent-filter>` — build-time only; defeats the purpose of server-driven routing.
- Navigating directly to the final screen inside `DeepLinkActivity` — the back stack will be empty; always trampoline through `MainActivity`.
- Caching route responses for long TTLs on the device — promo redirects must be fresh; set `Cache-Control: no-store` on the Worker for KV-override routes.
- Trusting raw incoming URI path segments without sanitisation — the Worker must validate segments against an allow-list before KV lookup.

## Gotchas

- `FLAG_ACTIVITY_CLEAR_TOP` requires `MainActivity` to already be in the back stack; use `FLAG_ACTIVITY_NEW_TASK` for cold-start deep links.
- Compose Navigation `uriPattern` matching is exact — `app://product/123` does NOT match `app://product/123/`; strip trailing slashes in the Worker.
- KV `get` returns `null` for missing keys, not a 404; the Kotlin resolver must handle `null`/empty body gracefully.
- The Workers resolution round-trip adds ~80–150 ms; show a `CircularProgressIndicator` in `DeepLinkActivity` to avoid a blank flash.

## Verification

```bash
# Publish a test override
wrangler kv key put --binding=ROUTE_KV "route:/promo/summer" \
  '{"destination":"product/{id}","params":{"id":"prod-789"}}'

# Confirm the Worker resolves it
curl https://router.example.com/route/promo/summer | jq .

# Trigger the deep link on a connected device
adb shell am start -W -a android.intent.action.VIEW \
  -d "https://example.com/promo/summer" com.example.app
```

## Related

- `android-app-links-dynamic-rules-verification.md`
- `android-deep-linking-intents.md`
- `android-jetpack-compose-workers-api-state.md`
- `cloudflare-workers-deep-link-redirect.md`

## Sources

- https://developer.android.com/jetpack/compose/navigation/deep-links
- https://developers.cloudflare.com/kv/
- https://developer.android.com/training/app-links
- https://developer.android.com/reference/androidx/navigation/compose/package-summary
