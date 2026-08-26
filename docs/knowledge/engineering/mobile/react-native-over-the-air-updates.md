# react-native-over-the-air-updates

**Issue:** Deploying JavaScript bundle updates to users without going through the app store
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
OTA updates let you push bug fixes and feature changes to the JS bundle without a full app store release. Expo Updates (EAS Update) is the standard mechanism. Misuse can violate app store policies.

## Pattern / Solution
**Setup with Expo:**
```bash
npx expo install expo-updates
eas update:configure
```

```json
// app.json
{
  "expo": {
    "updates": {
      "url": "https://u.expo.dev/<project-id>",
      "enabled": true,
      "fallbackToCacheTimeout": 0,
      "checkAutomatically": "ON_LOAD"
    },
    "runtimeVersion": { "policy": "appVersion" }
  }
}
```

**Publish an update:**
```bash
eas update --branch production --message "Fix login crash"
```

**Manual update check in-app:**
```ts
import * as Updates from 'expo-updates';

async function checkForUpdate() {
  if (__DEV__) return;
  try {
    const update = await Updates.checkForUpdateAsync();
    if (update.isAvailable) {
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync(); // restart app with new bundle
    }
  } catch (e) {
    console.error('Update check failed:', e);
  }
}
```

**Branch strategy:**
- `production` branch → shipped app versions
- `staging` branch → internal TestFlight/beta builds
- `development` branch → dev client builds

## Gotchas
- OTA updates can only change JS and assets, NOT native code — any native module change requires an app store release
- Apple's guidelines prohibit OTA updates that change core app functionality; bug fixes and minor improvements are fine
- `runtimeVersion` must match between the update and the installed native shell — mismatches are silently ignored
- `fallbackToCacheTimeout: 0` means the app launches immediately from cache and checks in the background; set a timeout if you need the update before launch
- Always test updates with `eas update --branch staging` before promoting to production
- Rollback by publishing an older bundle to the branch or pinning with `eas update:rollback`

## Related
- `react-native-expo-setup.md`
- `mobile-feature-flags-remote-config.md`
- `mobile-crash-reporting.md`
