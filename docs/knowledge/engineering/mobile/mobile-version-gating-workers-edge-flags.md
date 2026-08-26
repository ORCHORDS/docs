# Mobile App Version Gating with Workers Edge Feature Flags

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) needs to block API access from deprecated app versions without waiting for an App Store / Play Store phased rollout. Specifically: when a breaking API change ships, the edge must respond to requests from app `< 3.2.0` with a structured upgrade prompt rather than a broken 500, and new features behind a flag must activate only above a version threshold — all without redeploying the mobile app.

## Context

Mobile version gating at the edge differs from generic feature flags in two ways:

1. **No client-side SDK**: the flag evaluation happens in a Cloudflare Worker reading a request header (`X-App-Version`) rather than a client library polling a flag service.
2. **Enforcement is hard-gating**: unlike a soft flag, a version below the minimum must receive a machine-readable `426 Upgrade Required` (or a custom JSON body) that the mobile client's interceptor translates into a forced-upgrade UI, not just a degraded experience.

This pattern replaces third-party services (LaunchDarkly mobile SDKs, Firebase Remote Config) for version enforcement while keeping soft feature flags in Workers KV, reducing external dependencies for the example project backend.

---

## 1. Client: Injecting the App Version Header

React Native (using Axios interceptor):

```ts
// src/api/client.ts
import axios from 'axios'
import { Platform } from 'react-native'
import DeviceInfo from 'react-native-device-info'

const api = axios.create({ baseURL: 'https://api.example.com' })

api.interceptors.request.use(async (config) => {
  const version = DeviceInfo.getVersion()  // e.g. "3.2.1"
  const build   = DeviceInfo.getBuildNumber() // e.g. "421"
  config.headers['X-App-Version'] = version
  config.headers['X-App-Build']   = build
  config.headers['X-App-Platform'] = Platform.OS // 'ios' | 'android'
  return config
})

// Intercept 426 responses globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 426) {
      const { minimumVersion, storeUrl } = err.response.data
      // Navigate to forced-upgrade screen
      navigationRef.navigate('ForceUpgrade', { minimumVersion, storeUrl })
    }
    return Promise.reject(err)
  }
)

export default api
```

---

## 2. Worker: Edge Version Gate Middleware

```ts
// workers/api-gateway/src/middleware/versionGate.ts
import { Context, Next } from 'hono'

interface VersionConfig {
  minimumVersion: string    // "3.2.0"
  minimumBuild: number      // 400
  storeUrls: { ios: string; android: string }
  flagOverrides?: Record<string, boolean>
}

function parseVersion(v: string): number[] {
  return v.split('.').map(Number)
}

function isVersionAtLeast(actual: string, minimum: string): boolean {
  const a = parseVersion(actual)
  const m = parseVersion(minimum)
  for (let i = 0; i < 3; i++) {
    if ((a[i] ?? 0) > (m[i] ?? 0)) return true
    if ((a[i] ?? 0) < (m[i] ?? 0)) return false
  }
  return true // equal
}

export async function versionGate(c: Context<{ Bindings: Env }>, next: Next) {
  const appVersion  = c.req.header('X-App-Version') ?? '0.0.0'
  const platform    = c.req.header('X-App-Platform') ?? 'unknown'

  // Read config from KV (cached at edge, ~1ms)
  const raw = await c.env.FEATURE_FLAGS_KV.get('version-config', 'json')
  const config = (raw ?? {
    minimumVersion: '1.0.0',
    minimumBuild: 0,
    storeUrls: {
      ios: 'https://apps.apple.com/app/example project/id123456789',
      android: 'https://play.google.com/store/apps/details?id=app.example project.example project',
    },
  }) as VersionConfig

  if (!isVersionAtLeast(appVersion, config.minimumVersion)) {
    return c.json(
      {
        error: 'upgrade_required',
        message: 'This version of example project is no longer supported.',
        minimumVersion: config.minimumVersion,
        currentVersion: appVersion,
        storeUrl: platform === 'ios' ? config.storeUrls.ios : config.storeUrls.android,
      },
      426
    )
  }

  // Attach parsed version to context for downstream flag checks
  c.set('appVersion', appVersion)
  c.set('appPlatform', platform)
  await next()
}
```

Register in the main router:

```ts
// workers/api-gateway/src/index.ts
import { Hono } from 'hono'
import { versionGate } from './middleware/versionGate'

const app = new Hono<{ Bindings: Env }>()
app.use('/v*', versionGate)
// ... routes
export default app
```

---

## 3. Soft Feature Flags by Version

Beyond hard-gating, individual features can be enabled only above a version threshold:

```ts
// workers/api-gateway/src/middleware/featureFlags.ts
interface Flag {
  enabled: boolean
  minimumVersion?: string   // gate behind version if present
  platforms?: string[]      // optional platform restriction
  rolloutPercent?: number   // 0-100 gradual rollout
}

export async function evaluateFlag(
  c: Context<{ Bindings: Env }>,
  flagName: string
): Promise<boolean> {
  const flags = await c.env.FEATURE_FLAGS_KV.get<Record<string, Flag>>(
    'feature-flags', 'json'
  ) ?? {}

  const flag = flags[flagName]
  if (!flag || !flag.enabled) return false

  const version  = c.get('appVersion') as string ?? '0.0.0'
  const platform = c.get('appPlatform') as string ?? 'unknown'

  if (flag.minimumVersion && !isVersionAtLeast(version, flag.minimumVersion)) return false
  if (flag.platforms && !flag.platforms.includes(platform)) return false

  if (flag.rolloutPercent !== undefined && flag.rolloutPercent < 100) {
    // Stable hash so the same user gets the same result
    const userId = c.get('userId') as string ?? c.req.header('CF-Connecting-IP') ?? ''
    const hash = await hashString(`${flagName}:${userId}`)
    const bucket = hash % 100
    if (bucket >= flag.rolloutPercent) return false
  }

  return true
}

async function hashString(s: string): Promise<number> {
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(s))
  return new DataView(buf).getUint32(0) % 100
}
```

KV value structure (edit via Wrangler or a Workers admin UI):

```json
{
  "new-checkout-flow": {
    "enabled": true,
    "minimumVersion": "3.3.0",
    "platforms": ["ios", "android"],
    "rolloutPercent": 20
  },
  "legacy-payment-modal": {
    "enabled": false
  }
}
```

---

## 4. Updating Version Config Without Redeployment

```bash
# Bump minimum version to force users below 3.4.0 to upgrade
wrangler kv key put \
  --namespace-id $FEATURE_FLAGS_KV_ID \
  "version-config" \
  '{"minimumVersion":"3.4.0","minimumBuild":450,"storeUrls":{"ios":"https://apps.apple.com/app/example project/id123456789","android":"https://play.google.com/store/apps/details?id=app.example project.example project"}}' \
  --remote

# Enable new feature flag at 50% rollout
wrangler kv key put \
  --namespace-id $FEATURE_FLAGS_KV_ID \
  "feature-flags" \
  "$(cat flags.json)" \
  --remote
```

KV propagates globally within ~60 seconds, giving a soft global rollout window without a Worker deployment.

---

## Anti-patterns

- **Trusting the version header without additional validation** — `X-App-Version` is client-supplied and trivially spoofable. Use this pattern for user-experience gating only, not security enforcement. Combine with Play Integrity / App Attest if you need cryptographic version proof.
- **Hardcoding minimum versions in Worker source** — requires a Worker deployment for every version bump. Always read from KV so the minimum can be changed in seconds.
- **Returning 403 instead of 426** — `403 Forbidden` tells clients "you are not authorized"; `426 Upgrade Required` is the correct HTTP status for protocol/version negotiation failures and is more machine-parseable.
- **Evaluating flags in the React Native layer only** — client-side flags can be bypassed by modified APKs. Enforce at the Worker level and treat client flags only as a UI hint.
- **Caching the KV value with a long TTL in the Worker** — if you cache in-memory across requests using a module-level variable, a version-bump in KV may not propagate for minutes. Use `kv.get()` per request or use a short `cacheTtl` option (Workers KV supports `cacheTtl` on `get()`).

---

## Gotchas

- **Semantic versioning edge case**: `3.10.0` must be parsed numerically, not lexicographically (`"3.10.0" < "3.9.0"` lexicographically but `3.10.0 > 3.9.0` semantically). The `parseVersion` helper above uses `Number()` splits correctly.
- **App Store rollout lag**: when you bump the minimum version, users who have not yet received the phased App Store rollout will be force-gated. Always set `minimumVersion` to a version that is fully released (100% rollout) before enforcing.
- **KV eventual consistency during cold start**: the first request to a newly deployed Worker instance incurs a KV read. During high-traffic deploys, stale KV reads (up to 60 s) mean some requests may still see the old minimum version. This is acceptable; it resolves in under a minute.
- **iOS App Review**: Apple may flag apps that display a mandatory upgrade screen during review if the reviewer's device has an older version. Use a reviewer-bypass mechanism (e.g., a hidden build-number allowlist in KV) during the review window.
- **`X-App-Build` as tiebreaker**: semantic version alone cannot disambiguate hotfix builds at the same version string. Persist and check both `X-App-Version` and `X-App-Build` for precise enforcement.

---

## Verification

```bash
# Should return 426 for an old version
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-App-Version: 2.1.0" \
  -H "X-App-Platform: ios" \
  https://api.example.com/v1/me

# Should pass for current version
curl -s -w "%{http_code}" \
  -H "X-App-Version: 3.5.0" \
  -H "X-App-Platform: android" \
  https://api.example.com/v1/me

# Inspect KV flag config
wrangler kv key get "version-config" --namespace-id $FEATURE_FLAGS_KV_ID --remote
wrangler kv key get "feature-flags" --namespace-id $FEATURE_FLAGS_KV_ID --remote
```

---

## Related

- `mobile-feature-flags-remote-config.md` — Firebase Remote Config and generic flag patterns
- `mobile-forced-upgrade-minimum-version.md` — In-app upgrade prompt UI patterns
- `mobile-staged-rollout-phased-release.md` — App Store / Play Store phased rollout mechanics
- `play-integrity-attestation.md` — Cryptographic app version + integrity proof (Android)
- `apple-app-attest-retry-and-risk-metric-preservation.md` — App Attest for iOS version integrity

---

## Sources

- [Cloudflare KV `cacheTtl` option](https://developers.cloudflare.com/kv/api/read-key-value-pairs/#cachettl-parameter)
- [RFC 7231 §6.5.15 — 426 Upgrade Required](https://datatracker.ietf.org/doc/html/rfc7231#section-6.5.15)
- [react-native-device-info](https://github.com/react-native-device-info/react-native-device-info)
- [Play Integrity API — version field](https://developer.android.com/google/play/integrity/verdicts#app-integrity)
- [Apple App Review guidelines — force upgrade](https://developer.apple.com/app-store/review/guidelines/#software-requirements)
