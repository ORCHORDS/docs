# Mobile CI/CD: Expo EAS Build Pipelines

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Builds break in CI but succeed locally. OTA updates reach
the wrong release channel. App Store submissions fail on
credentials. Environment variables present locally are
missing in EAS cloud builds.

## Context

The example project mobile app (example.com) is a React Native /
Expo project targeting iOS and Android. Builds are produced
via EAS Build (Expo Application Services) and distributed
through the App Store and Google Play. Cloudflare Workers
serve the API layer. OTA updates use expo-updates for
server-driven JS bundle delivery between native releases.

---

## 1. eas.json Profile Structure

Three profiles map to the three environments:

```jsonc
// eas.json
{
  "cli": { "version": ">= 14.0.0" },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "ios": { "simulator": true },
      "env": { "APP_ENV": "development" },
      "channel": "development"
    },
    "preview": {
      "distribution": "internal",
      "ios": { "resourceClass": "m-medium" },
      "android": { "buildType": "apk" },
      "env": { "APP_ENV": "preview" },
      "channel": "preview"
    },
    "production": {
      "autoIncrement": true,
      "ios": {
        "resourceClass": "m-medium",
        "enterpriseProvisioning": "adhoc"
      },
      "android": { "buildType": "app-bundle" },
      "env": { "APP_ENV": "production" },
      "channel": "production"
    }
  },
  "submit": {
    "production": {
      "ios": { "appleId": "ops@example.com" },
      "android": {
        "serviceAccountKeyPath": "./google-service-key.json",
        "track": "internal"
      }
    }
  }
}
```

`channel` aligns each build profile to an expo-updates
release channel so OTA updates do not bleed across envs.

---

## 2. EAS Build vs Local Build

| Dimension           | EAS Build (cloud)      | Local (expo run)       |
|---------------------|------------------------|------------------------|
| Credentials mgmt    | Managed by EAS         | Local keystore / cert  |
| Reproducibility     | Hermetic container     | Dev machine state      |
| Speed (cold)        | 8-20 min (M-medium)    | 3-8 min                |
| Caching             | Gradle / CocoaPods     | Local ~/.gradle        |
| Cost                | Build credit consumed  | Free                   |
| Native module link  | Auto via npx expo      | Manual if bare         |
| Best for            | CI, release, QA        | Fast iteration         |

Use `eas build --local` to reproduce a cloud build locally
when diagnosing a build failure that does not repro with
`expo run:ios`. The local flag uses the same build tools
but runs on your machine.

---

## 3. GitHub Actions Workflow

```yaml
# .github/workflows/eas-build.yml
name: EAS Build

on:
  push:
    branches: [main, release/*]
  workflow_dispatch:
    inputs:
      profile:
        description: 'EAS build profile'
        required: true
        default: 'preview'
        type: choice
        options: [development, preview, production]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - name: Install dependencies
        run: npm ci

      - uses: expo/expo-github-action@v8
        with:
          eas-version: latest
          token: ${{ secrets.EXPO_TOKEN }}

      - name: Build (preview)
        if: github.ref != 'refs/heads/main'
        run: eas build --platform all
                       --profile preview
                       --non-interactive

      - name: Build (production)
        if: github.ref == 'refs/heads/main'
        run: eas build --platform all
                       --profile production
                       --non-interactive
```

`--non-interactive` is required in CI; without it EAS
prompts for credential consent and hangs indefinitely.

---

## 4. Environment Variables in EAS

Never commit secrets to eas.json. Use EAS secrets:

```bash
# Set per-project secrets (scoped to all profiles)
eas secret:create --scope project \
  --name CLOUDFLARE_API_BASE \
  --value "https://api.example.com"

eas secret:create --scope project \
  --name SENTRY_DSN \
  --value "https://..."

# List existing secrets
eas secret:list

# Per-profile override in eas.json env block (non-secret)
# "env": { "LOG_LEVEL": "debug" }
```

Secrets injected by EAS are available as `process.env.*`
at build time. At runtime (JS bundle), bake values in via
`expo-constants` or a build-time babel transform. Do not
rely on `process.env` surviving in the shipped bundle
without a transform plugin.

---

## 5. OTA Updates with expo-updates

Channel routing prevents production users from receiving
preview JS bundles:

```bash
# Publish an update to the preview channel
eas update --branch preview --message "fix: modal scroll"

# Publish to production
eas update --branch production --message "fix: modal scroll"
```

`app.json` / `app.config.js` runtime version policy:

```js
export default {
  runtimeVersion: {
    policy: "sdkVersion",   // bump on SDK upgrade only
  },
  updates: {
    url: "https://u.expo.dev/<project-id>",
    checkAutomatically: "ON_LOAD",
    fallbackToCacheTimeout: 3000,
  },
};
```

Set `fallbackToCacheTimeout` to 3 000 ms. Users on slow
connections get the cached bundle immediately instead of
waiting for the update check to time out.

---

## 6. EAS Submit

```bash
# Submit the latest successful production build
eas submit --platform ios --latest
eas submit --platform android --latest

# Or reference a specific build ID
eas submit --platform ios --id <build-id>
```

iOS requires an App Store Connect API key stored as an EAS
secret (`ASC_API_KEY_ID`, `ASC_API_KEY_ISSUER_ID`, and the
key file via `eas credentials`). Android requires a Google
Play service account JSON uploaded to EAS.

---

## Anti-patterns

- Hardcoding `APP_ENV=production` in eas.json for every
  profile defeats environment isolation.
- Using `expo publish` (Classic Updates) on SDK 50+ is
  deprecated; migrate to `eas update`.
- Running `eas build` without `--non-interactive` in CI
  causes silent hangs on credential prompts.
- Storing the EXPO_TOKEN in the repository instead of a
  GitHub Actions secret exposes org-level access.
- Skipping `autoIncrement: true` on production requires
  manual version bumps before every release.

## Gotchas

- EAS build caches the `node_modules` layer. After adding a
  native module, pass `--clear-cache` once or the old
  Podfile.lock may be reused.
- `eas update` does not update native code; if you ship a
  new native module, a full build and store submission are
  required before the OTA can reference it.
- iOS Simulator builds cannot be submitted to TestFlight.
  Use `"simulator": false` for the preview profile when you
  need OTA install on a physical device.
- EAS enforces a 2 GiB artifact limit. Ensure Hermes
  bytecode compilation is enabled to keep bundle size down.

## Verification

```bash
# Confirm build succeeded and get artifact URL
eas build:list --platform all --status finished --limit 5

# Confirm update reached a channel
eas update:list --branch production --limit 10

# Check which runtime version a build targets
eas build:view <build-id> | grep runtimeVersion
```

## Related

- `react-native-hermes-performance-profiling.md`
- `ios-push-notifications-apns-workers.md`
- Expo docs: Build profiles reference

## Source URLs (verified 2026-08-17)

- https://docs.expo.dev/build/eas-json/
- https://docs.expo.dev/eas-update/getting-started/
- https://docs.expo.dev/submit/introduction/
- https://docs.expo.dev/build-reference/build-with-github-actions/
- https://docs.expo.dev/eas/environment-variables/
