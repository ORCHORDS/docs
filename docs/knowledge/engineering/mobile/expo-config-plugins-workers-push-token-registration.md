# Expo Config Plugins: Cloudflare Workers Push Token Registration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project uses Expo-managed workflow with EAS Build. Anonymous users should receive push notifications (reaction alerts, moderation actions) without creating an account. The push token must be registered with a Cloudflare Worker that stores it in D1 alongside the `anonId`.

Problems that bring you here:
- The native `UNUserNotificationCenter` entitlement and `NSUserTrackingUsageDescription` are missing from the final `.ipa`/`.apk` because the managed workflow doesn't add them automatically
- The Expo `Notifications.getExpoPushTokenAsync()` call silently returns `undefined` on a production build because the `experienceId` doesn't match the EAS project
- The push token registration Worker call fails because the anonymous JWT hasn't been issued yet at the moment the token is obtained (race condition on first launch)
- Android `google-services.json` for FCM is not embedded in the app because the config plugin ran before the file was placed
- The token is re-registered on every cold start, causing duplicate D1 rows

---

## Context

Stack: Expo SDK 52, EAS Build, TypeScript, `expo-notifications`, Cloudflare Workers + D1.

Push flow:
1. App starts, anonymous JWT is issued (or loaded from keychain)
2. Request notification permission
3. Get Expo push token (wraps APNs token on iOS, FCM token on Android)
4. `POST /push/register` to Cloudflare Worker with `{ anonId, expoPushToken, platform }`
5. Worker upserts to D1 `push_tokens` table (unique on `anon_id + platform`)
6. Cloudflare Queues consumer sends notifications via Expo Push API

---

## Writing the Config Plugin

Config plugins modify the native project during `expo prebuild` or EAS Build. For push notifications in the managed workflow, you need:
- iOS: `aps-environment` entitlement (`development` / `production`)
- Android: the correct `google-services.json` placement

```typescript
// plugins/withWaspPushNotifications.ts
import {
  ConfigPlugin,
  withEntitlementsPlist,
  withAndroidManifest,
  withDangerousMod,
  IOSConfig,
  AndroidConfig,
} from 'expo/config-plugins';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Sets up push notification entitlements on iOS and ensures
 * google-services.json is copied for Android FCM.
 */
const withWaspPushNotifications: ConfigPlugin<{
  googleServicesJsonPath?: string;
  apsEnvironment?: 'development' | 'production';
}> = (config, { googleServicesJsonPath, apsEnvironment = 'production' } = {}) => {

  // iOS: add aps-environment entitlement
  config = withEntitlementsPlist(config, (mod) => {
    mod.modResults['aps-environment'] = apsEnvironment;
    return mod;
  });

  // Android: copy google-services.json if provided
  if (googleServicesJsonPath) {
    config = withDangerousMod(config, [
      'android',
      async (mod) => {
        const src = path.resolve(googleServicesJsonPath);
        const dest = path.join(mod.modRequest.projectRoot, 'android', 'app', 'google-services.json');
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, dest);
        } else {
          console.warn(`[withWaspPushNotifications] google-services.json not found at: ${src}`);
        }
        return mod;
      },
    ]);
  }

  // Android: ensure FCM permission in AndroidManifest
  config = withAndroidManifest(config, (mod) => {
    const manifest = mod.modResults.manifest;
    const usesPermissions = manifest['uses-permission'] ?? [];
    const permName = 'android.permission.POST_NOTIFICATIONS';
    const alreadyHas = usesPermissions.some(
      (p: { $: { 'android:name': string } }) => p.$['android:name'] === permName
    );
    if (!alreadyHas) {
      usesPermissions.push({ $: { 'android:name': permName } });
      manifest['uses-permission'] = usesPermissions;
    }
    return mod;
  });

  return config;
};

export default withWaspPushNotifications;
```

Register it in `app.config.ts`:

```typescript
// app.config.ts
import { ExpoConfig } from 'expo/config';

const config: ExpoConfig = {
  name: 'example project',
  slug: 'example project-app',
  version: '1.0.0',
  plugins: [
    [
      './plugins/withWaspPushNotifications',
      {
        googleServicesJsonPath: './secrets/google-services.json',
        apsEnvironment: process.env.EAS_BUILD_PROFILE === 'production' ? 'production' : 'development',
      },
    ],
    'expo-notifications',
  ],
  ios: {
    bundleIdentifier: 'com.example project.app',
    entitlements: {
      // aps-environment is set by the plugin; do not hardcode here
    },
  },
  android: {
    package: 'com.example project.app',
    googleServicesFile: './android/app/google-services.json', // Expo reads this at build
  },
};

export default config;
```

---

## Cloudflare Worker: Push Token Registration

```typescript
// workers/src/push/register.ts
import { D1Database } from '@cloudflare/workers-types';

interface Env { DB: D1Database; }

interface RegisterBody {
  anonId: string;
  expoPushToken: string;
  platform: 'ios' | 'android';
}

export async function handlePushRegister(request: Request, env: Env): Promise<Response> {
  // Verify JWT from Authorization header (reuse your existing JWT middleware)
  const anonId = request.headers.get('X-Anon-Id'); // set by JWT middleware
  if (!anonId) {
    return new Response(JSON.stringify({ error: 'unauthorized' }), { status: 401 });
  }

  const body = await request.json<RegisterBody>();

  if (!body.expoPushToken || !body.platform) {
    return new Response(JSON.stringify({ error: 'missing_fields' }), { status: 400 });
  }

  // Validate Expo push token format
  if (!/^ExponentPushToken\[[\w-]+\]$/.test(body.expoPushToken)) {
    return new Response(JSON.stringify({ error: 'invalid_token_format' }), { status: 400 });
  }

  // Upsert: update token if platform row already exists for this anonId
  await env.DB.prepare(
    `INSERT INTO push_tokens (anon_id, expo_push_token, platform, registered_at)
     VALUES (?1, ?2, ?3, unixepoch())
     ON CONFLICT (anon_id, platform)
     DO UPDATE SET expo_push_token = excluded.expo_push_token,
                   registered_at   = unixepoch()`
  )
    .bind(anonId, body.expoPushToken, body.platform)
    .run();

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS push_tokens (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  anon_id       TEXT NOT NULL,
  expo_push_token TEXT NOT NULL,
  platform      TEXT NOT NULL CHECK(platform IN ('ios', 'android')),
  registered_at INTEGER NOT NULL,
  UNIQUE(anon_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_push_tokens_anon ON push_tokens(anon_id);
```

---

## React Native: Token Acquisition and Registration Hook

The critical ordering: wait for the anonymous JWT before registering the push token.

```typescript
// src/hooks/usePushTokenRegistration.ts
import { useEffect } from 'react';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { apiClient } from '../auth/apiClient';

// Configure how notifications appear while the app is in the foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export function usePushTokenRegistration() {
  const anonId = useAuthStore((s) => s.anonId);
  const accessToken = <redacted-secret> => s.accessToken);

  useEffect(() => {
    // Do not attempt registration until we have an anonymous session
    if (!anonId || !accessToken) return;

    let cancelled = false;

    async function register() {
      // 1. Request permission (no-op if already granted)
      const { status } = await Notifications.requestPermissionsAsync({
        ios: {
          allowAlert: true,
          allowSound: false, // example project is a silent-notification app by design
          allowBadge: false,
        },
      });

      if (status !== 'granted') return; // user declined — don't retry aggressively

      // 2. Get Expo push token
      let tokenData: Notifications.ExpoPushToken;
      try {
        tokenData = await Notifications.getExpoPushTokenAsync({
          projectId: process.env.EXPO_PUBLIC_EAS_PROJECT_ID, // from .env
        });
      } catch (e) {
        console.warn('[push] Failed to get Expo push token:', e);
        return;
      }

      if (cancelled) return;

      // 3. Register with Worker
      try {
        await apiClient.post('/push/register', {
          anonId,
          expoPushToken: tokenData.data,
          platform: Platform.OS as 'ios' | 'android',
        });
      } catch (e) {
        console.warn('[push] Token registration failed:', e);
        // Non-fatal: the user won't get push notifications but the app still works
      }
    }

    register();
    return () => { cancelled = true; };
  }, [anonId, accessToken]); // Re-run if anonId changes (new anonymous session)
}
```

Use it at the app root:

```typescript
// App.tsx
import { usePushTokenRegistration } from './src/hooks/usePushTokenRegistration';

export default function App() {
  usePushTokenRegistration();
  // ... rest of app
}
```

---

## EAS Build Configuration

```json
// eas.json
{
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "env": {
        "EXPO_PUBLIC_EAS_PROJECT_ID": "your-eas-project-uuid",
        "EAS_BUILD_PROFILE": "development"
      }
    },
    "production": {
      "distribution": "store",
      "env": {
        "EXPO_PUBLIC_EAS_PROJECT_ID": "your-eas-project-uuid",
        "EAS_BUILD_PROFILE": "production"
      },
      "ios": {
        "credentialsSource": "remote"
      },
      "android": {
        "credentialsSource": "remote"
      }
    }
  }
}
```

The `EXPO_PUBLIC_` prefix makes the variable available at runtime via `process.env`. The `EAS_BUILD_PROFILE` variable drives the `apsEnvironment` selection in the config plugin.

---

## Preventing Duplicate Token Rows

The D1 `UNIQUE(anon_id, platform)` constraint and `ON CONFLICT DO UPDATE` handle the idempotency on the server side. On the client, avoid re-registering on every cold start with a local cache:

```typescript
// src/hooks/usePushTokenRegistration.ts (addition)
import AsyncStorage from '@react-native-async-storage/async-storage';

const TOKEN_CACHE_KEY = '@example project/registeredPushToken';

async function register() {
  // ...obtain tokenData as before...

  // Check if this exact token is already registered
  const cached = await AsyncStorage.getItem(TOKEN_CACHE_KEY);
  if (cached === tokenData.data) {
    return; // already registered, skip Worker call
  }

  await apiClient.post('/push/register', {
    anonId,
    expoPushToken: tokenData.data,
    platform: Platform.OS as 'ios' | 'android',
  });

  // Cache the registered token locally
  await AsyncStorage.setItem(TOKEN_CACHE_KEY, tokenData.data);
}
```

The Worker's upsert is the authoritative source; the local cache just prevents unnecessary network calls.

---

## Anti-patterns

- **Hardcoding `apsEnvironment: 'production'` for all build profiles**: Development builds need `aps-environment = development` or APNs will reject the token registration. Use `EAS_BUILD_PROFILE` to switch.
- **Calling `getExpoPushTokenAsync` before the anonymous JWT is ready**: The registration Worker requires a valid JWT. If you call this before the auth flow completes, you either hit a 401 or silently drop the token.
- **Putting `google-services.json` in the repository root**: EAS Build clones your repo; the file must be committed or passed via EAS Secrets. Prefer EAS Secrets for the JSON content and write it to disk in a `withDangerousMod`.
- **Not handling the case where `status !== 'granted'`**: On iOS, once denied, `requestPermissionsAsync` always returns `denied` — never show a prompt again without deep-linking to Settings. Respect this and don't spam the user.
- **Using `Notifications.getDevicePushTokenAsync()` instead of `getExpoPushTokenAsync`**: The raw device token (APNs/FCM) can't be used with the Expo Push API. Use `getExpoPushTokenAsync` with your `projectId` to get an Expo token.

---

## Gotchas

- **`projectId` mismatch**: If `projectId` doesn't match the EAS project tied to your credentials, `getExpoPushTokenAsync` returns a token for the wrong project and Expo's push service rejects it. Always pass `projectId` explicitly; don't rely on the default.
- **iOS Simulator limitations**: APNs is not available on simulators. `getExpoPushTokenAsync` throws on simulators. Wrap in a try/catch and gate with `!__DEV__ || Platform.OS === 'android'` for local testing.
- **FCM v1 API**: As of 2024, Firebase dropped the legacy FCM API. Expo SDK 50+ uses FCM v1. Ensure your Firebase project has the FCM API v1 enabled and that you've uploaded the FCM v1 service account JSON to EAS.
- **EAS Build cache and config plugins**: Config plugins run during `expo prebuild`. In EAS Build, if the plugin file changes but the build cache key doesn't, the old prebuild output may be used. Use `--clear-cache` on EAS CLI when changing plugin code.
- **`withDangerousMod` runs async**: `withDangerousMod` callbacks can be async, but they must return the `mod` object (not the file write result). Always `await` the file operation but return `mod`.

---

## Verification

```bash
# 1. Check entitlements after prebuild
npx expo prebuild --platform ios --clean
cat ios/example project/example project.entitlements | grep aps-environment
# Should show: <string>production</string> (or development)

# 2. Verify google-services.json placed for Android
ls android/app/google-services.json

# 3. Test token registration end-to-end on a physical device
# Launch app → observe console: "[push] registered" or token in D1
npx wrangler d1 execute example project-db --command "SELECT * FROM push_tokens LIMIT 5"

# 4. Verify idempotency: kill + relaunch app twice
# D1 row count for the same anon_id+platform should remain 1
npx wrangler d1 execute example project-db \
  --command "SELECT anon_id, platform, COUNT(*) FROM push_tokens GROUP BY anon_id, platform HAVING COUNT(*) > 1"
# Should return 0 rows

# 5. Test permission denial path
# Revoke notification permission in iOS Settings > example project
# Relaunch: confirm no crash, no retry loop in logs
```

---

## Related

- `expo-notifications-workers-scheduled-push-d1.md`
- `expo-eas-build-cloudflare-workers-secrets.md`
- `mobile-push-delivery-reliability.md`
- `mobile-push-notifications-cloudflare-queues.md`
- `ios-push-notifications-apns-workers.md`
- `android-firebase-messaging.md`
- `workers-ai-push-notification-personalization.md`

---

## Sources

- Expo Config Plugins docs: https://docs.expo.dev/config-plugins/introduction/
- expo-notifications API: https://docs.expo.dev/versions/latest/sdk/notifications/
- EAS Build environment variables: https://docs.expo.dev/build-reference/variables/
- Firebase FCM v1 migration: https://firebase.google.com/docs/cloud-messaging/migrate-v1
- Cloudflare D1 UPSERT syntax: https://developers.cloudflare.com/d1/platform/client-api/#databaseprepare
- Expo `getExpoPushTokenAsync` projectId requirement: https://docs.expo.dev/push-notifications/push-notifications-setup/
