# Expo EAS Build with Cloudflare Workers API Environment Secrets

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) is built with Expo and deployed through EAS Build. The React Native app communicates exclusively with Cloudflare Workers API endpoints. During the build pipeline you need to inject the correct Worker API base URL, Cloudflare Access service token, Turnstile sitekey, and other per-environment secrets (staging vs production) without committing them to source control or exposing them in the final binary beyond what is necessary.

## Context

EAS Build runs on Expo's cloud infrastructure. It has its own secret management layer (EAS Secrets) that is separate from GitHub Actions secrets, `.env` files in the repo, and Cloudflare's own `wrangler secret` mechanism. Bridging these correctly requires understanding three distinct secret surfaces:

| Surface | Where it lives | Who reads it |
|---|---|---|
| `eas secret` | EAS Build servers | Build-time: `process.env` in Metro config / `app.config.js` |
| `wrangler secret` | Cloudflare Workers runtime | Worker code: `env.SECRET_NAME` |
| `expo-constants` / `app.config.js` | Bundled JS | App runtime: `Constants.expoConfig.extra` |

The goal is to flow the correct Cloudflare Worker URL and Cloudflare Access service token credentials into the EAS build so the app calls the right endpoint, while the actual Worker's binding secrets (D1 ID, KV namespace, API tokens) remain exclusively in Cloudflare's platform and never touch the mobile build.

---

## 1. EAS Secret Setup for Per-Environment Worker URLs

```bash
# Set production Worker URL as EAS build secret
eas secret:create \
  --scope project \
  --name CLOUDFLARE_WORKER_API_URL \
  --value "https://api.example.com" \
  --environment production

eas secret:create \
  --scope project \
  --name CLOUDFLARE_WORKER_API_URL \
  --value "https://api-staging.example.com" \
  --environment preview

# Cloudflare Access service token for Worker-to-Worker or CI auth
eas secret:create \
  --scope project \
  --name CLOUDFLARE_ACCESS_CLIENT_ID \
  --value "your-access-client-id" \
  --environment production

eas secret:create \
  --scope project \
  --name CLOUDFLARE_ACCESS_CLIENT_SECRET \
  --value "your-access-client-secret" \
  --environment production

# Turnstile sitekey (public, but environment-scoped)
eas secret:create \
  --scope project \
  --name CLOUDFLARE_TURNSTILE_SITEKEY \
  --value "0x4AAAAAABxxxxxxxxxxxxxxxx" \
  --environment production

eas secret:create \
  --scope project \
  --name CLOUDFLARE_TURNSTILE_SITEKEY \
  --value "1x00000000000000000000AA" \  # always-passes test key
  --environment preview
```

---

## 2. `app.config.js`: Consuming EAS Secrets at Build Time

```js
// app.config.js  (dynamic config — replaces app.json for secret injection)
const IS_DEV     = process.env.APP_VARIANT === 'development'
const IS_PREVIEW = process.env.APP_VARIANT === 'preview'

export default {
  name: IS_DEV ? 'example project (Dev)' : IS_PREVIEW ? 'example project (Preview)' : 'example project',
  slug: 'example project',
  version: '3.5.0',
  ios: {
    bundleIdentifier: IS_DEV
      ? 'app.example project.example project.dev'
      : IS_PREVIEW
      ? 'app.example project.example project.preview'
      : 'app.example project.example project',
  },
  android: {
    package: IS_DEV
      ? 'app.example project.example project.dev'
      : IS_PREVIEW
      ? 'app.example project.example project.preview'
      : 'app.example project.example project',
  },
  extra: {
    // These are read from EAS secrets during the build, injected into
    // process.env by EAS Build, and bundled into the JS bundle.
    // Do NOT put Worker binding secrets here — only public/client values.
    workerApiUrl:   process.env.CLOUDFLARE_WORKER_API_URL ?? 'http://localhost:8787',
    turnstileSitekey: process.env.CLOUDFLARE_TURNSTILE_SITEKEY ?? '1x00000000000000000000AA',
    // Cloudflare Access client ID is safe to bundle (it's used in the request header,
    // not as a standalone credential — the secret stays server-side)
    cfAccessClientId: process.env.CLOUDFLARE_ACCESS_CLIENT_ID ?? '',
    eas: { projectId: 'your-eas-project-id' },
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
  ],
}
```

---

## 3. Reading Config Values in the App

```ts
// src/config/cloudflare.ts
import Constants from 'expo-constants'

const extra = Constants.expoConfig?.extra ?? {}

export const CF_CONFIG = {
  workerApiUrl:     String(extra.workerApiUrl     ?? 'http://localhost:8787'),
  turnstileSitekey: String(extra.turnstileSitekey ?? '1x00000000000000000000AA'),
  cfAccessClientId: String(extra.cfAccessClientId ?? ''),
} as const

// src/api/client.ts
import { CF_CONFIG } from '@/config/cloudflare'

export const apiClient = axios.create({
  baseURL: CF_CONFIG.workerApiUrl,
  headers: {
    'CF-Access-Client-Id': CF_CONFIG.cfAccessClientId,
    // CF-Access-Client-Secret must NOT be bundled in the client app;
    // use a server-side proxy Worker to attach it for M2M calls.
  },
})
```

**Important**: `CF-Access-Client-Secret` must never be bundled in the mobile binary. If your Workers are behind Cloudflare Access with service auth, only the `Client-Id` (which identifies the app but cannot authenticate alone) goes in the bundle. The `Client-Secret` stays in a proxy Worker's binding.

---

## 4. EAS Build Profile Configuration

```json
// eas.json
{
  "cli": { "version": ">= 12.0.0" },
  "build": {
    "development": {
      "extends": "preview",
      "env": { "APP_VARIANT": "development" },
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "env": { "APP_VARIANT": "preview" },
      "distribution": "internal",
      "ios": { "simulator": false },
      "channel": "preview"
    },
    "production": {
      "env": { "APP_VARIANT": "production" },
      "channel": "production",
      "autoIncrement": true
    }
  },
  "submit": {
    "production": {
      "ios": {
        "appleId": "builds@example.com",
        "ascAppId": "123456789",
        "appleTeamId": "TEAMID"
      },
      "android": {
        "serviceAccountKeyPath": "./google-play-sa.json",
        "track": "internal"
      }
    }
  }
}
```

Trigger a production build (EAS Build injects the `production` environment secrets automatically):

```bash
eas build --platform all --profile production
```

---

## 5. GitHub Actions: Passing Additional Cloudflare Secrets to EAS

When you need to pass Cloudflare-specific secrets that exist in GitHub Actions but not in EAS (e.g., a Wrangler deploy token used during post-build steps):

```yaml
# .github/workflows/build-and-deploy.yml
name: EAS Build + Worker Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm' }
      - run: npm ci

      - name: EAS Build (production)
        uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}
        # EAS Build reads its own secrets from EAS Secret store, not here.
        # GitHub Actions secrets are only for the CI step itself.

      - run: eas build --platform all --profile production --non-interactive

  deploy-worker:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Deploy Worker
        run: npx wrangler deploy workers/api-gateway/src/index.ts --name example project-api-prod
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          # Worker binding secrets are set separately via wrangler secret put
          # and do NOT travel through this pipeline
```

---

## Anti-patterns

- **Putting Worker binding secrets in EAS secrets** — Worker bindings (`DB`, `KV`, `QUEUE`) are Cloudflare-internal resource handles, not string secrets. They have no meaning in a mobile bundle; only set them via `wrangler secret put` or the Cloudflare dashboard.
- **Using a `.env` file committed to the repo** — even with `.gitignore`, `.env` files appear in EAS Build logs if echoed. Use `eas secret:create` exclusively.
- **Bundling `CF-Access-Client-Secret` in `app.config.js` extra** — this is a credential that authenticates a service to Cloudflare Access. Bundle only the `Client-Id`; route authenticated M2M calls through a proxy Worker that holds the secret in a binding.
- **Sharing one EAS project secret across preview and production** — EAS scoped secrets by environment (`--environment production`) are the correct primitive. A single shared secret forces production credentials into preview builds.
- **Reading `process.env` at runtime in the React Native JS bundle** — Metro does not support dynamic `process.env` reads at runtime; only values statically present during the Metro bundling step are inlined. Use `Constants.expoConfig.extra` instead.

---

## Gotchas

- **EAS Build environments are case-sensitive**: `--environment production` (lowercase) must match the profile name in `eas.json`. Mismatches silently fall back to no environment-specific secrets.
- **`eas secret:list` does not show secret values** — you cannot recover the value of an existing EAS secret. Rotate by deleting and recreating: `eas secret:delete --id <id>`.
- **Metro bundler caches `app.config.js`** — after changing EAS secrets and rebuilding, a stale Metro cache on a local dev machine will still serve the old values. Run `expo start --clear` or `npx expo prebuild --clean` locally.
- **Turnstile sitekeys in the bundle are public** — the sitekey is designed to be in client code. The secret key (used to verify tokens) must only ever be in a Worker binding, never in the mobile bundle.
- **`autoIncrement` in production eas.json conflicts with manual build numbers** — if you also use `fastlane` or Xcode Cloud for some builds, `autoIncrement: true` in EAS may race with your CI number; pin version management to one system.

---

## Verification

```bash
# List secrets for the project (values hidden)
eas secret:list

# Confirm the correct Worker URL is embedded after a local Metro bundle
npx expo export --platform ios 2>&1 | grep -i "worker\|cloudflare" || true

# After an EAS build, pull the artifact and inspect the JS bundle
# (for production builds the bundle is minified — search for the domain)
unzip -p ~/Downloads/build.ipa Payload/example project.app/main.jsbundle | \
  grep -o 'example project\.app[^"]*' | sort -u

# Confirm the Worker is reachable with the injected base URL
curl -s https://api.example.com/health | jq .
```

---

## Related

- `mobile-ci-cd-expo-eas-build.md` — General EAS Build patterns and profiles
- `mobile-ci-cd-github-actions.md` — GitHub Actions integration for mobile builds
- `capacitor-cloudflare-turnstile-integration.md` — Turnstile in Capacitor (sitekey injection)
- `react-native-cloudflare-turnstile-integration.md` — Turnstile in React Native
- `cloudflare-waf-false-positives-mobile-api-clients.md` — Cloudflare Access service token patterns

---

## Sources

- [EAS Secrets documentation](https://docs.expo.dev/build-reference/variables/)
- [EAS Build environment variables guide](https://docs.expo.dev/eas-update/environment-variables/)
- [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/)
- [Cloudflare Turnstile sitekey vs secret key](https://developers.cloudflare.com/turnstile/get-started/)
- [expo-constants API reference](https://docs.expo.dev/versions/latest/sdk/constants/)
- [Wrangler secret management](https://developers.cloudflare.com/workers/wrangler/commands/#secret)
