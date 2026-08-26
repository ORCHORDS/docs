# Android Jetpack Glance Widget with Cloudflare Workers Data Refresh

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A home-screen or lock-screen widget built with Jetpack Glance needs to show data that lives
behind a Cloudflare Workers API (e.g. a live score, queue depth, sensor reading). The widget
must refresh on a schedule, survive process death, and not drain the battery by making
unbounded network calls.

## Context

Jetpack Glance replaces the old `RemoteViews`-based AppWidget API with a Compose-style DSL.
State is stored in a `GlanceStateDefinition` backed by `DataStore`, and refreshes are driven
by `WorkManager` periodic tasks or system `AppWidgetManager` updates. The widget process is
separate from the main app process, so network calls must be scoped carefully.

Cloudflare Workers is the natural backend: a Worker at the edge can aggregate, cache, and
sign the payload so the widget receives a compact, ready-to-render JSON blob in a single
round-trip.

Stack: Kotlin, Jetpack Glance 1.1+, WorkManager 2.9+, `kotlinx.serialization`, OkHttp /
`ktor-client-android`.

## Defining the Widget State

```kotlin
// WidgetState.kt
import kotlinx.serialization.Serializable

@Serializable
data class DashboardWidgetState(
    val value: String = "–",
    val label: String = "",
    val updatedAt: Long = 0L,
    val isError: Boolean = false,
)

// GlanceStateDefinition using DataStore<Preferences>
object DashboardWidgetStateDefinition :
    GlanceStateDefinition<DashboardWidgetState> {

    private val Context.dataStore by preferencesDataStore("dashboard_widget")

    override suspend fun getDataStore(
        context: Context,
        fileKey: String,
    ): DataStore<DashboardWidgetState> =
        context.dataStore.map { prefs ->
            DashboardWidgetState(
                value   = prefs[stringPreferencesKey("value")] ?: "–",
                label   = prefs[stringPreferencesKey("label")] ?: "",
                updatedAt = prefs[longPreferencesKey("updatedAt")] ?: 0L,
                isError = prefs[booleanPreferencesKey("isError")] ?: false,
            )
        } as DataStore<DashboardWidgetState>   // simplified; use serialized DataStore in prod

    override fun getLocation(context: Context, fileKey: String): File =
        File(context.filesDir, "dashboard_widget_$fileKey.pb")
}
```

## Building the Glance Composable

```kotlin
// DashboardWidget.kt
class DashboardWidget : GlanceAppWidget() {

    override val stateDefinition = DashboardWidgetStateDefinition

    @Composable
    override fun Content() {
        val state = currentState<DashboardWidgetState>()
        val ctx   = LocalContext.current

        GlanceTheme {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(GlanceTheme.colors.widgetBackground)
                    .padding(16.dp),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    if (state.isError) {
                        Text(
                            "⚠ Could not refresh",
                            style = TextStyle(
                                color = ColorProvider(Color.Red),
                                fontSize = 12.sp,
                            ),
                        )
                    } else {
                        Text(
                            state.value,
                            style = TextStyle(fontSize = 36.sp, fontWeight = FontWeight.Bold),
                        )
                        Spacer(GlanceModifier.height(4.dp))
                        Text(
                            state.label,
                            style = TextStyle(fontSize = 12.sp),
                        )
                    }
                    Spacer(GlanceModifier.height(8.dp))
                    Button(
                        text = "Refresh",
                        onClick = actionRunCallback<RefreshActionCallback>(),
                    )
                }
            }
        }
    }
}

class RefreshActionCallback : ActionCallback {
    override suspend fun onAction(
        context: Context,
        glanceId: GlanceId,
        parameters: ActionParameters,
    ) {
        WidgetRefreshWorker.enqueueImmediate(context)
    }
}
```

## WorkManager Refresh Worker

```kotlin
// WidgetRefreshWorker.kt
class WidgetRefreshWorker(
    ctx: Context,
    params: WorkerParameters,
) : CoroutineWorker(ctx, params) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    override suspend fun doWork(): Result {
        return try {
            val json = fetchFromWorker()
            val state = Json.decodeFromString<DashboardWidgetState>(json)
            updateAllWidgets(applicationContext, state)
            Result.success()
        } catch (e: Exception) {
            val errorState = DashboardWidgetState(isError = true, updatedAt = System.currentTimeMillis())
            updateAllWidgets(applicationContext, errorState)
            if (runAttemptCount < 3) Result.retry() else Result.failure()
        }
    }

    private suspend fun fetchFromWorker(): String = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url("https://api.example.com/widget-data")
            .header("Authorization", "Bearer ${BuildConfig.WIDGET_API_TOKEN}")
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}")
            resp.body!!.string()
        }
    }

    private suspend fun updateAllWidgets(ctx: Context, state: DashboardWidgetState) {
        GlanceAppWidgetManager(ctx)
            .getGlanceIds(DashboardWidget::class.java)
            .forEach { id ->
                updateAppWidgetState(ctx, DashboardWidgetStateDefinition, id) { state }
                DashboardWidget().update(ctx, id)
            }
    }

    companion object {
        private const val WORK_NAME = "widget_periodic_refresh"

        fun enqueueImmediate(ctx: Context) {
            WorkManager.getInstance(ctx).enqueue(
                OneTimeWorkRequestBuilder<WidgetRefreshWorker>()
                    .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                    .build()
            )
        }

        fun schedulePeriodicRefresh(ctx: Context) {
            val request = PeriodicWorkRequestBuilder<WidgetRefreshWorker>(
                repeatInterval = 15, repeatIntervalTimeUnit = TimeUnit.MINUTES,
            )
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()

            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
```

## Cloudflare Workers Backend

```typescript
// worker.ts  –  returns a compact JSON payload for the widget
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const auth = request.headers.get("Authorization") ?? ""
    if (auth !== `Bearer ${env.WIDGET_API_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 })
    }

    // Cache at the edge for 60 s to absorb burst refreshes across many devices
    const cacheKey = new Request("https://internal/widget-data", request)
    const cached   = await caches.default.match(cacheKey)
    if (cached) return cached

    const row = await env.DB.prepare(
      "SELECT value, label FROM dashboard_metrics ORDER BY recorded_at DESC LIMIT 1"
    ).first<{ value: string; label: string }>()

    const payload = JSON.stringify({
      value:     row?.value     ?? "–",
      label:     row?.label     ?? "",
      updatedAt: Date.now(),
      isError:   false,
    })

    const response = new Response(payload, {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "s-maxage=60, stale-while-revalidate=30",
      },
    })

    await caches.default.put(cacheKey, response.clone())
    return response
  },
}
```

## Anti-patterns

- **Waking on every `onUpdate`** — `AppWidgetProvider.onUpdate` is called by the system on an
  unpredictable schedule; delegate actual network work to WorkManager so the system can batch
  and throttle the calls.
- **Storing secrets in widget XML metadata** — any key in `res/xml/widget_info.xml` is world-
  readable. Use `BuildConfig` fields injected via `signingConfig` or a local.properties pipeline.
- **Large payloads through DataStore** — DataStore for Preferences has a practical size limit.
  Keep the widget state under 4 KB; push image URLs rather than inline base64.
- **Direct OkHttp on the main thread** — always dispatch to `Dispatchers.IO`; Glance composables
  run on a coroutine dispatcher but `doWork` is already on a background thread.

## Gotchas

- Glance updates are asynchronous. Call `widget.update(ctx, id)` _after_ `updateAppWidgetState`
  completes, or the Composable reads the old state.
- On Android 12+ the system throttles `AppWidgetManager.requestPinAppWidget` and periodic
  updates to a minimum of 15 minutes; WorkManager's `PeriodicWorkRequest` respects the same
  floor.
- The widget process may be running in a trimmed-memory state. Avoid referencing `Application`
  singletons (e.g. Hilt component) directly from the widget; create a lightweight local
  `OkHttpClient` in the Worker instead.
- `setExpedited` requires `FOREGROUND_SERVICE` permission on Android 12–13 when the app is
  in the background; declare `<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />`
  and handle `ForegroundServiceStartNotAllowedException` for older OS versions.

## Verification

```bash
# Force a widget update via ADB broadcast
adb shell am broadcast \
  -a android.appwidget.action.APPWIDGET_UPDATE \
  -n com.example.app/.DashboardWidgetProvider

# Inspect WorkManager job queue
adb shell dumpsys jobscheduler | grep WidgetRefresh

# Watch DataStore proto file for state changes
adb shell run-as com.example.app \
  cat /data/data/com.example.app/files/dashboard_widget_1.pb | xxd | head
```

## Related

- `android-workmanager-workers-sync.md`
- `android-jetpack-compose-workers-api-state.md`
- `ios-widgetkit-workers-background-refresh.md`
- `mobile-battery-optimization.md`

## Sources

- Jetpack Glance 1.1 release notes — developer.android.com/jetpack/androidx/releases/glance
- WorkManager periodic constraints — developer.android.com/topic/libraries/architecture/workmanager/how-to/define-work
- Cloudflare Workers Cache API — developers.cloudflare.com/workers/runtime-apis/cache
