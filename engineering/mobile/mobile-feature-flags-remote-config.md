# mobile-feature-flags-remote-config

**Issue:** Implementing feature flags and remote configuration in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Feature flags enable gradual rollouts, A/B testing, and kill switches for buggy features without an app store release. Remote config allows changing app behavior (strings, thresholds, URLs) without a code deploy.

## Pattern / Solution
**Firebase Remote Config:**
```ts
import remoteConfig from '@react-native-firebase/remote-config';

async function initRemoteConfig() {
  await remoteConfig().setDefaults({
    enable_new_checkout: false,
    max_upload_size_mb: 10,
    api_base_url: 'https://api.example.com',
  });

  await remoteConfig().setConfigSettings({
    minimumFetchIntervalMillis: __DEV__ ? 0 : 3600000, // 1 hour in prod
  });

  await remoteConfig().fetchAndActivate();
}

// Read values
const isNewCheckout = remoteConfig().getBoolean('enable_new_checkout');
const maxUpload = remoteConfig().getNumber('max_upload_size_mb');
```

**Custom lightweight flag service:**
```ts
interface FeatureFlags {
  newCheckout: boolean;
  darkMode: boolean;
}

async function fetchFlags(userId: string): Promise<FeatureFlags> {
  const res = await fetch(`https://flags.example.com/v1/flags?userId=${userId}`);
  return res.json();
}

// Context provider
const FlagsContext = createContext<FeatureFlags>(defaultFlags);
export const useFlag = (key: keyof FeatureFlags) => useContext(FlagsContext)[key];
```

**Gradual rollout by user cohort:**
```ts
function isInRollout(userId: string, percentage: number): boolean {
  const hash = murmur32(userId) % 100;
  return hash < percentage;
}

const showNewFeature = isInRollout(currentUser.id, 20); // 20% rollout
```

**Kill switch pattern:**
```ts
const isKilled = remoteConfig().getBoolean('kill_switch_payment');
if (isKilled) {
  return <MaintenanceBanner message={remoteConfig().getString('kill_switch_payment_msg')} />;
}
```

## Gotchas
- Always define defaults; if the network fetch fails, the app uses defaults — missing defaults cause undefined behavior
- Remote config is cached; `fetchAndActivate()` returns `true` if new values were activated
- Do not put secrets in remote config — it is accessible to all clients
- Flag evaluation must be synchronous for render — fetch and cache before the app renders
- Coordinate flag cleanup: remove dead flags from both code and the remote config backend

## Related
- `react-native-over-the-air-updates.md`
- `mobile-analytics-patterns.md`
- `mobile-crash-reporting.md`
