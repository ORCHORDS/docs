# Over-the-Air Updates — Expo EAS Updates and CodePush

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Every bug fix, copy change, or minor feature requires a full app store
submission — a 1-3 day review cycle for iOS and hours for Android. Users
run stale versions because they disable auto-updates or ignore update
prompts. A critical JavaScript bug in production cannot be fixed without
waiting for app store review. Your React Native team cannot iterate
quickly because the release cycle is gated by app store approvals.

## Context

Over-the-air (OTA) updates push JavaScript bundle changes directly to
users' devices without app store review. For React Native and Expo
apps, OTA updates can fix bugs, update copy, change layouts, and adjust
business logic instantly. In 2026, Expo EAS Updates is the dominant OTA
solution after Microsoft App Center (which hosted CodePush) was retired
in March 2025. Expo SDK 55 (February 2026) introduced Hermes bytecode
diffing for smaller update payloads and built-in rollouts for phased
percentage-based delivery. For teams not using Expo, Bitrise CodePush
provides a managed CodePush service, and self-hosted CodePush servers
remain an option.

## OTA vs. app store release

| Aspect | OTA update | App store release |
|---|---|---|
| Scope | JavaScript bundle only | Native + JS changes |
| Review time | Instant (no review) | 1-3 days (iOS), hours (Android) |
| Rollback | Instant (revert to previous bundle) | New submission required |
| Phased rollout | Built-in (percentage-based) | App Store Connect only |
| Native code changes | Not supported | Required |
| User action | Automatic on app launch | Manual update or auto-update |

## What OTA can and cannot update

```
CAN update (JavaScript bundle):
  ✓ UI layouts and components
  ✓ Business logic
  ✓ API endpoints and configuration
  ✓ Copy, strings, translations
  ✓ Images bundled via require()
  ✓ Navigation routes

CANNOT update (native code):
  ✗ Native modules (new or modified)
  ✗ iOS/Android permissions
  ✗ App icon, splash screen
  ✗ Expo SDK version upgrade
  ✗ Native library versions
  ✗ Build configuration (Gradle, Xcode)
```

## Expo EAS Updates

### Configuration

```json
// app.json
{
  "expo": {
    "updates": {
      "url": "https://u.expo.dev/your-project-id",
      "enabled": true,
      "fallbackToCacheTimeout": 0,
      "checkAutomatically": "ON_LAUNCH"
    },
    "runtimeVersion": {
      "policy": "fingerprint"
    }
  }
}
```

### Publishing an update

```bash
# Publish to the production channel
eas update --branch production --message "Fix checkout validation"

# Publish to a preview channel
eas update --branch preview --message "New onboarding flow"

# Publish with a phased rollout (Expo SDK 55+)
eas update --branch production --message "Redesigned cart" \
  --rollout-percentage 10
```

### Runtime version strategy

```
"fingerprint" policy (recommended):
  → Automatically generates a hash of all native dependencies
  → OTA updates only delivered to compatible native builds
  → Prevents JS/native version mismatch crashes

"appVersion" policy:
  → Uses app version (1.0.0) as runtime version
  → Manual management required
  → Risk of delivering incompatible updates

"nativeVersion" policy:
  → Uses native build version
  → Intermediate option between fingerprint and appVersion
```

### Checking for updates in-app

```tsx
import * as Updates from 'expo-updates';

async function checkForUpdate() {
  const update = await Updates.checkForUpdateAsync();
  if (update.isAvailable) {
    await Updates.fetchUpdateAsync();
    await Updates.reloadAsync();
  }
}
```

## Phased rollouts (Expo SDK 55+)

```
Stage 1:  10% of users  → Monitor crash rate, ANR rate
Stage 2:  25% of users  → Monitor key business metrics
Stage 3:  50% of users  → Verify performance at scale
Stage 4: 100% of users  → Full rollout

Rollback: instant — revert to previous bundle for all users
```

## CodePush alternatives (2026)

| Platform | Status | Features |
|---|---|---|
| **Expo EAS Updates** | Active (recommended) | Hermes diffing, rollouts, fingerprint versioning |
| **Bitrise CodePush** | Active | Managed CodePush, React Native support |
| **Revopush** | Active | Self-hosted, Expo + RN support |
| **Self-hosted CodePush** | Community | Open-source server, full control |
| **Microsoft CodePush** | Retired (March 2025) | App Center shutdown |

## Anti-patterns

- **OTA for native code changes** — attempting to push native module
  changes via OTA. This crashes the app because the JavaScript bundle
  references native APIs that do not exist in the installed build.
  Use runtime version fingerprinting to prevent incompatible updates.
- **No rollout strategy** — pushing OTA updates to 100% of users
  immediately. A bad update crashes every user's app simultaneously.
  Use phased rollouts (10% → 25% → 50% → 100%) with crash monitoring.
- **Ignoring update size** — shipping multi-megabyte OTA updates
  that fail on slow connections. Use Hermes bytecode diffing (Expo
  SDK 55+) to minimize update payload size.
- **No fallback on update failure** — if an OTA update fails to
  download or apply, the app should fall back to the embedded bundle,
  not crash. Configure `fallbackToCacheTimeout` appropriately.

## Gotchas

- **Apple and Google guidelines** — both platforms allow OTA updates
  for JavaScript bundles but prohibit changing the app's primary
  purpose or adding features that bypass review. Violating this
  risks app store removal.
- **Runtime version mismatch** — if the OTA bundle expects a native
  API that the installed native build does not have, the app crashes.
  The `fingerprint` runtime version policy prevents this automatically.
- **Update timing** — checking for updates on app launch adds latency
  to the startup experience. Use `checkAutomatically: "ON_LAUNCH"`
  with `fallbackToCacheTimeout: 0` to show the cached version
  immediately and apply updates on the next launch.
- **Offline users** — users who are offline when an update is
  published receive it the next time they launch with connectivity.
  Critical fixes may take days to reach 100% of users.

## Verification

- OTA updates are published via CI/CD (not manual CLI commands).
- Runtime version fingerprinting prevents JS/native mismatches.
- Phased rollouts are used for all production OTA updates.
- Crash rate is monitored after each OTA rollout stage.
- Rollback procedure is tested and documented.
- Update payload size is optimized with Hermes bytecode diffing.

## Related

- `documentation/categories/mobile/deep-linking-universal-app-links.md`
- `documentation/categories/deploy/progressive-canary-deployment-rollback.md`
- `documentation/categories/mobile/react-native-expo-architecture.md`

## Source URLs (verified 2026-08-16)

- Expo EAS Updates CodePush Alternative — https://appcircle.io/codepush-alternatives/expo-eas-updates
- CodePush in React Native and OTA Updates — https://medium.com/@bhuvin25/codepush-in-react-native-and-ota-updates-with-expo-a-complete-guide-8f20b55e22fd
- Bitrise CodePush: Managed OTA Updates — https://bitrise.io/platform/codepush
- React Native Code Push 2026 Alternatives — https://catdoes.com/blog/react-native-code-push
