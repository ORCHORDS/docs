# Android Instant App Workers Auth Handoff

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
A potential user of example project / example.com taps a shared wam link (`https://example.com/wam/abc123`)
on a device where the full app is not installed. Android Instant Apps serves a streamlined feature
module that previews example project and prompts for install. The problem: the instant app module must still
establish an anonymous identity token so the Worker can count the view, and when the user later
installs the full app, that identity must carry over seamlessly without forcing a fresh sign-up.

## Context
Android Instant Apps run in a sandboxed process with restricted persistent storage. The anonymous
identity handoff uses an `InstantApps.getInstantAppCookie` / `setInstantAppCookie` byte payload
(max 16 KB) to transfer the anon token from the instant module to the full app. The Cloudflare
Worker issues a short-lived JWT on first view, stores the mapping in Workers KV, and later
validates the same token during full-app first launch to restore session continuity without user
friction.

## Architecture — Token Flow Overview

```
User taps link
      │
      ▼
Android resolves Instant App module
      │
      ▼
Instant module → POST /auth/anon-token (Worker)
                        │ issues JWT, stores in KV
                        ▼
              token saved in InstantAppCookie
                        │
      ▼ (user installs)
Full app reads InstantAppCookie
      │
      ▼
Full app → POST /auth/claim-cookie-token (Worker)
                        │ validates JWT, creates full session
                        ▼
              KV entry promoted to full anon session
```

## Workers Side — Anon Token Issuance
The Worker generates a HMAC-signed JWT with a 48-hour TTL and stores the raw payload in KV under
the token's `jti` so it can be revoked or promoted later.

```typescript
// worker/src/auth-anon-token.ts
import { Env } from './types';
import { signJwt, verifyJwt } from './jwt';

export async function handleAnonToken(request: Request, env: Env): Promise<Response> {
  const deviceId = request.headers.get('X-Device-Id') ?? crypto.randomUUID();
  const jti = crypto.randomUUID();
  const issuedAt = Math.floor(Date.now() / 1000);
  const expiresAt = issuedAt + 48 * 3600;

  const payload = { sub: `anon:${deviceId}`, jti, iat: issuedAt, exp: expiresAt };
  const token = await signJwt(payload, env.JWT_SECRET);

  // Store in KV with the same TTL so we can validate it on claim
  await env.AUTH_KV.put(
    `anon_token:${jti}`,
    JSON.stringify({ deviceId, issuedAt }),
    { expirationTtl: 48 * 3600 },
  );

  return Response.json({ token, expiresAt });
}

export async function handleClaimCookieToken(request: Request, env: Env): Promise<Response> {
  const { cookieToken } = (await request.json()) as { cookieToken: string };

  let payload: { sub: string; jti: string; exp: number };
  try {
    payload = await verifyJwt(cookieToken, env.JWT_SECRET);
  } catch {
    return new Response('Invalid token', { status: 401 });
  }

  if (Math.floor(Date.now() / 1000) > payload.exp) {
    return new Response('Token expired', { status: 401 });
  }

  const stored = await env.AUTH_KV.get(`anon_token:${payload.jti}`, 'json') as {
    deviceId: string;
    issuedAt: number;
  } | null;

  if (!stored) return new Response('Token already claimed or expired', { status: 409 });

  // Promote to full anon session
  const sessionId = crypto.randomUUID();
  await env.AUTH_KV.put(
    `session:${sessionId}`,
    JSON.stringify({ anonId: payload.sub, deviceId: stored.deviceId, promotedAt: Date.now() }),
    { expirationTtl: 30 * 24 * 3600 },
  );

  // Consume the one-time cookie token
  await env.AUTH_KV.delete(`anon_token:${payload.jti}`);

  return Response.json({ sessionId, anonId: payload.sub });
}
```

## Instant App Module Side — Token Request and Cookie Write
The Instant App module is a standard Android feature module. On launch it calls the Worker for
an anon token and writes it into the `InstantAppCookie` byte array for later retrieval by the
full app.

```kotlin
// instant/src/main/java/app/example project/instant/AnonTokenManager.kt
import android.content.Context
import com.google.android.gms.instantapps.InstantApps
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import javax.net.ssl.HttpsURLConnection

object AnonTokenManager {

    private const val WORKER_URL = "https://api.example.com/auth/anon-token"

    suspend fun fetchAndStoreCookieToken(context: Context): String =
        withContext(Dispatchers.IO) {
            val existingCookie = InstantApps.getInstantAppCookie(context)
            if (existingCookie.isNotEmpty()) {
                // Token already stored from a previous session in this module
                return@withContext String(existingCookie, Charsets.UTF_8)
                    .let { JSONObject(it).getString("token") }
            }

            val conn = URL(WORKER_URL).openConnection() as HttpsURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("X-Device-Id", android.provider.Settings.Secure
                .getString(context.contentResolver, android.provider.Settings.Secure.ANDROID_ID))
            conn.doOutput = false
            conn.connect()

            val responseBody = conn.inputStream.bufferedReader().readText()
            conn.disconnect()

            val json = JSONObject(responseBody)
            val token = json.getString("token")

            // Write into InstantAppCookie (max 16 KB, survives until full app install)
            val cookiePayload = JSONObject().apply {
                put("token", token)
                put("storedAt", System.currentTimeMillis())
            }.toString().toByteArray(Charsets.UTF_8)

            InstantApps.setInstantAppCookie(context, cookiePayload)
            token
        }
}
```

## Full App Side — Cookie Token Claim on First Launch
When the full app launches for the first time after install, it reads the cookie, sends it to
the Worker's claim endpoint, and stores the resulting session ID in `EncryptedSharedPreferences`.

```kotlin
// app/src/main/java/app/example project/SessionManager.kt
import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.android.gms.instantapps.InstantApps
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.URL
import javax.net.ssl.HttpsURLConnection

class SessionManager(private val context: Context) {

    private val prefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context, "example project_session", masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    fun hasSession(): Boolean = prefs.contains("session_id")

    suspend fun claimInstantAppTokenIfPresent(): Boolean = withContext(Dispatchers.IO) {
        val cookieBytes = InstantApps.getInstantAppCookie(context)
        if (cookieBytes.isEmpty()) return@withContext false

        val cookieJson = JSONObject(String(cookieBytes, Charsets.UTF_8))
        val token = cookieJson.optString("token", "") .takeIf { it.isNotEmpty() }
            ?: return@withContext false

        val conn = URL("https://api.example.com/auth/claim-cookie-token")
            .openConnection() as HttpsURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.outputStream.use { it.write(JSONObject().put("cookieToken", token).toString().toByteArray()) }

        if (conn.responseCode != 200) {
            conn.disconnect()
            return@withContext false
        }

        val res = JSONObject(conn.inputStream.bufferedReader().readText())
        conn.disconnect()

        prefs.edit()
            .putString("session_id", res.getString("sessionId"))
            .putString("anon_id", res.getString("anonId"))
            .apply()

        // Clear the cookie now that it's consumed
        InstantApps.setInstantAppCookie(context, ByteArray(0))
        true
    }
}
```

## Anti-patterns
- Using `SharedPreferences` (unencrypted) for the session ID — use `EncryptedSharedPreferences` on
  Android to protect the session token at rest.
- Storing the full JWT in the `InstantAppCookie` and re-validating it in the full app without the
  Worker — the Worker is the single authority; the full app must call the claim endpoint.
- Forgetting to clear the cookie after claiming — leaving the token in the cookie means any
  subsequent fresh install would re-attempt a claim on an already-deleted KV entry and return 409.
- Using the same `jti` for multiple cookie writes — each module launch that fetches a new token
  gets a new `jti`; do not cache the token in memory across process restarts.

## Gotchas
- `InstantApps.getInstantAppCookie` returns an empty `ByteArray` (not null) when no cookie is set;
  check `.isEmpty()`, not null-safety.
- The cookie is cleared by the OS when the full app is installed and its first launch is completed;
  read it before any `Activity.onResume` delay.
- `InstantApps.setInstantAppCookie` has a 16 KB limit; store only the compact JWT string plus a
  timestamp, not the full decoded payload.
- Workers KV `get` with `'json'` type returns `null` for missing or expired keys — always null-
  check before accessing fields.
- Instant App modules must declare the `<dist:module dist:instant="true">` manifest attribute and
  be uploaded to Play as part of the App Bundle.

## Verification
1. Sideload the Instant App module via `adb shell pm install-existing --instant <package>`.
2. Open a wam deep link — confirm the Worker issues a token (`wrangler kv key list --prefix=anon_token:`).
3. Install the full APK and launch — `SessionManager.claimInstantAppTokenIfPresent()` should
   return `true` and the KV entry for `anon_token:<jti>` should be deleted.
4. A second launch should return `false` (no cookie) and `prefs.getString("session_id")` should
   be populated.

## Related
- `/documentation/docs/policies/mobile/deep-linking-universal-app-links.md`
- `/documentation/docs/policies/mobile/mobile-auth-oauth-pkce.md`
- `/documentation/docs/policies/mobile/android-credential-manager-passkey-migration.md`
- `/documentation/docs/policies/mobile/ios-app-clip-workers-auth-flow.md`

## Sources
- https://developer.android.com/topic/google-play-instant
- https://developers.google.com/android/reference/com/google/android/gms/instantapps/InstantApps
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
