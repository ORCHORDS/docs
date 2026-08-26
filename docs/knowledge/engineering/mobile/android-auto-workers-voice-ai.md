# Android Auto Workers Voice Command with Workers AI

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Android Auto apps need to process natural-language voice commands from drivers—such as "find a gas station" or "read my last message"—without running a large language model on-device, by forwarding the recognized speech to a Cloudflare Workers AI endpoint for intent classification and response generation.

## Context
Android Auto's `CarAppService` handles UI and interaction within the vehicle head unit. Voice input arrives via the `SearchTemplate` or via the Android Auto voice action framework as a `String` of recognized text. The phone app calls a Cloudflare Workers AI endpoint (using `@cf/meta/llama-3.1-8b-instruct` or a fine-tuned classifier) to extract intent and entities from the utterance, then returns a structured response that the `CarAppService` renders as a navigation card, message list, or plain text. All heavy model inference runs in the Worker; the phone remains a thin relay.

## Workers AI Intent Endpoint

```typescript
// worker/src/voice-intent.ts
export interface Env {
  AI: Ai;
}

interface VoiceIntentRequest {
  utterance: string;
  userId: string;
  sessionId: string;
}

interface IntentResult {
  intent: string;           // e.g. "FIND_POI", "READ_MESSAGE", "NAVIGATE_HOME"
  entities: Record<string, string>; // e.g. { poiType: "gas_station", radius: "5km" }
  responseText: string;     // Human-readable reply for TTS
  confidence: number;       // 0-1
}

const SYSTEM_PROMPT = `You are a voice assistant for Android Auto. Given a driver's voice command,
extract the intent and any named entities, and generate a short, safe, non-distracting response.

Respond ONLY with valid JSON matching this schema:
{
  "intent": "<one of: FIND_POI|READ_MESSAGE|NAVIGATE_HOME|PLAY_MUSIC|MAKE_CALL|UNKNOWN>",
  "entities": { "<key>": "<value>" },
  "responseText": "<max 30 words, suitable for TTS while driving>",
  "confidence": <0.0-1.0>
}`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
      });
    }

    if (request.method !== "POST" || new URL(request.url).pathname !== "/voice-intent") {
      return new Response("Not found", { status: 404 });
    }

    const { utterance, userId, sessionId } =
      await request.json<VoiceIntentRequest>();

    if (!utterance || utterance.length > 500) {
      return new Response(
        JSON.stringify({ error: "utterance required, max 500 chars" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    let result: IntentResult;
    try {
      const aiResponse = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: `Driver said: "${utterance}"\nUser ID: ${userId}\nSession: ${sessionId}`,
          },
        ],
        max_tokens: 256,
        temperature: 0.2, // low temp for deterministic intent extraction
      });

      const rawText =
        typeof aiResponse === "string"
          ? aiResponse
          : (aiResponse as { response: string }).response;

      // Extract JSON from model output (may include preamble)
      const jsonMatch = rawText.match(/\{[\s\S]*\}/);
      if (!jsonMatch) throw new Error("No JSON in model response");
      result = JSON.parse(jsonMatch[0]) as IntentResult;
    } catch (err) {
      result = {
        intent: "UNKNOWN",
        entities: {},
        responseText: "Sorry, I didn't understand that. Please try again.",
        confidence: 0,
      };
    }

    return new Response(JSON.stringify(result), {
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      },
    });
  },
};
```

```toml
# wrangler.toml
name = "voice-intent-worker"
compatibility_date = "2026-01-01"

[ai]
binding = "AI"
```

## Android Auto CarAppService

```kotlin
// app/src/main/java/com/example/autoapp/VoiceIntentService.kt
package com.example.autoapp

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class IntentResult(
    val intent: String,
    val entities: Map<String, String>,
    val responseText: String,
    val confidence: Float
)

class VoiceIntentService(
    private val workersUrl: String,
    private val authToken: String
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    suspend fun classify(
        utterance: String,
        userId: String,
        sessionId: String
    ): IntentResult = withContext(Dispatchers.IO) {
        val payload = JSONObject().apply {
            put("utterance", utterance)
            put("userId", userId)
            put("sessionId", sessionId)
        }.toString()

        val body = payload.toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url("$workersUrl/voice-intent")
            .post(body)
            .addHeader("Authorization", "Bearer $authToken")
            .build()

        val response = client.newCall(req).execute()
        val responseBody = response.body?.string() ?: throw Exception("Empty response")

        if (!response.isSuccessful) {
            return@withContext IntentResult(
                intent = "UNKNOWN",
                entities = emptyMap(),
                responseText = "I couldn't process that request.",
                confidence = 0f
            )
        }

        val json = JSONObject(responseBody)
        val entitiesJson = json.optJSONObject("entities") ?: JSONObject()
        val entities = mutableMapOf<String, String>()
        entitiesJson.keys().forEach { key -> entities[key] = entitiesJson.getString(key) }

        IntentResult(
            intent = json.getString("intent"),
            entities = entities,
            responseText = json.getString("responseText"),
            confidence = json.getDouble("confidence").toFloat()
        )
    }
}
```

```kotlin
// app/src/main/java/com/example/autoapp/MainCarAppService.kt
package com.example.autoapp

import android.content.Intent
import androidx.car.app.CarAppService
import androidx.car.app.Screen
import androidx.car.app.Session
import androidx.car.app.model.*
import androidx.car.app.validation.HostValidator
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class MainCarAppService : CarAppService() {
    override fun createHostValidator(): HostValidator =
        HostValidator.ALLOW_ALL_HOSTS_VALIDATOR // replace with production allowlist

    override fun onCreateSession(): Session = MainSession()
}

class MainSession : Session() {
    override fun onCreateScreen(intent: Intent): Screen = VoiceScreen(carContext)
}

class VoiceScreen(carContext: androidx.car.app.CarContext) :
    Screen(carContext) {

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val intentService = VoiceIntentService(
        workersUrl = "https://voice-intent-worker.your-subdomain.workers.dev",
        authToken = <redacted-secret>
    )
    private var statusMessage = "Say a command…"
    private var lastResponse = ""

    override fun onGetTemplate(): Template {
        val actionStrip = ActionStrip.Builder()
            .addAction(
                Action.Builder()
                    .setTitle("Voice Command")
                    .setOnClickListener { promptVoiceInput() }
                    .build()
            )
            .build()

        return MessageTemplate.Builder(lastResponse.ifEmpty { statusMessage })
            .setTitle("Auto Assistant")
            .setActionStrip(actionStrip)
            .build()
    }

    private fun promptVoiceInput() {
        // In a real app, integrate with CarContext.requestPermissions + SpeechRecognizer
        // or handle via ACTION_VOICE_COMMAND intent. Here we simulate an utterance.
        val simulatedUtterance = "Find a gas station nearby"
        processUtterance(simulatedUtterance)
    }

    fun processUtterance(utterance: String) {
        statusMessage = "Processing…"
        invalidate()

        scope.launch {
            val result = try {
                intentService.classify(
                    utterance = utterance,
                    userId = "user_123",
                    sessionId = "session_${System.currentTimeMillis()}"
                )
            } catch (e: Exception) {
                IntentResult(
                    intent = "UNKNOWN",
                    entities = emptyMap(),
                    responseText = "Network error. Please try again.",
                    confidence = 0f
                )
            }

            lastResponse = result.responseText
            invalidate() // Re-render screen

            // Dispatch intent action
            when (result.intent) {
                "FIND_POI" -> handleFindPoi(result.entities)
                "NAVIGATE_HOME" -> handleNavigateHome()
                "READ_MESSAGE" -> handleReadMessage()
                else -> { /* Already shown responseText */ }
            }
        }
    }

    private fun handleFindPoi(entities: Map<String, String>) {
        val poiType = entities["poiType"] ?: "point of interest"
        // Integrate with CarContext place search or Google Maps intent
        statusMessage = "Searching for $poiType…"
        invalidate()
    }

    private fun handleNavigateHome() {
        statusMessage = "Starting navigation home…"
        invalidate()
    }

    private fun handleReadMessage() {
        statusMessage = "Reading your latest message…"
        invalidate()
    }
}
```

## AndroidManifest Declaration

```xml
<!-- AndroidManifest.xml additions -->
<service
    android:name=".MainCarAppService"
    android:exported="true"
    android:label="@string/app_name">
    <intent-filter>
        <action android:name="androidx.car.app.CarAppService" />
        <category android:name="androidx.car.app.category.IOT" />
    </intent-filter>
    <meta-data
        android:name="distractionOptimized"
        android:value="true" />
</service>

<uses-permission android:name="androidx.car.app.BIND_TEMPLATE_RENDERER" />
```

## Anti-patterns
- Blocking the Android Auto UI thread with synchronous network calls—always use coroutines with `Dispatchers.IO`
- Sending raw audio bytes to Workers AI instead of transcribed text—use the device's `SpeechRecognizer` (which runs locally on-device) to produce text before calling the Worker
- Returning long AI-generated responses as the `responseText`—Android Auto TTS is read while driving; cap responses at 25–30 words
- Trusting the `utterance` string as SQL input on the Worker without sanitization—intent extraction is LLM-based but entities should be validated before any downstream query
- Using `HostValidator.ALLOW_ALL_HOSTS_VALIDATOR` in production—replace with `HostValidator.Builder().addAllowedHost(...)` for approved Auto hosts

## Gotchas
- Android Auto apps require the `androidx.car.app` library and the `distractionOptimized` meta-data flag; missing this flag causes the app to be blocked while the car is moving
- `CarAppService` screens must be rebuilt from scratch on each `invalidate()` call—do not hold mutable UI state in the template builder; store it in the screen class and read it during `onGetTemplate`
- The Workers AI `@cf/meta/llama-3.1-8b-instruct` model has a cold-start latency of 1–3 seconds; this is acceptable for voice commands but consider caching common intents in KV (`FIND_POI:gas_station`) to short-circuit inference
- Android Auto restricts network access to apps with the `android.permission.INTERNET` permission declared and granted; verify the permission is in the manifest of the phone app (not just the Auto module)
- `BuildConfig.WORKERS_AUTH_TOKEN` must be set via a Gradle `buildConfigField` backed by a value in `local.properties` or CI secrets—never hard-code tokens in source

## Verification
1. `wrangler dev` and POST `{ "utterance": "find a coffee shop", "userId": "u1", "sessionId": "s1" }` to `/voice-intent`; assert the response contains `"intent": "FIND_POI"` and `"entities": { "poiType": "coffee_shop" }`.
2. Run the app in the Android Auto Desktop Head Unit (DHU) emulator; simulate a voice command via `processUtterance("navigate home")` and confirm the screen shows the `responseText`.
3. Block outbound network in the emulator and verify the error path returns a user-friendly message without crashing the `CarAppService`.
4. Measure round-trip latency from `processUtterance` call to `invalidate()` call; target under 2 seconds on a 4G connection.
5. Deploy the Worker with `wrangler deploy` and check `wrangler tail` logs for AI inference errors during a live test drive session.

## Related
- `cloudflare-workers-ai-mobile-inference-edge.md`
- `workers-ai-push-notification-personalization.md`
- `android-workmanager-workers-sync.md`
- `mobile-network-resilience-cloudflare-workers.md`

## Sources
- https://developers.android.com/cars/design/automotive-os/apps/car-apps/build-for-car-apps
- https://developers.cloudflare.com/workers-ai/models/
- https://developer.android.com/reference/androidx/car/app/CarAppService
