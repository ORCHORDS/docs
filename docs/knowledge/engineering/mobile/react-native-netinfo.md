# react-native-netinfo

**Issue:** Detecting network connectivity type and status changes in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apps need to react to connectivity loss, differentiate WiFi from cellular, and gate expensive operations when on metered connections.

## Pattern / Solution
```sh
npm install @react-native-community/netinfo
npx pod-install
```

```ts
import NetInfo from '@react-native-community/netinfo';

// One-time fetch
const state = await NetInfo.fetch();
console.log(state.isConnected, state.type); // 'wifi' | 'cellular' | 'none' | ...
console.log(state.details?.isConnectionExpensive); // metered connection

// Subscribe to changes
const unsubscribe = NetInfo.addEventListener((state) => {
  if (!state.isConnected) {
    showOfflineBanner();
  }
});
// cleanup
unsubscribe();

// React hook pattern
import { useNetInfo } from '@react-native-community/netinfo';

function StatusBar() {
  const netInfo = useNetInfo();
  return netInfo.isConnected ? null : <OfflineBanner />;
}
```

## Gotchas
- `isConnected: true` does not guarantee internet access — the device may be on a captive portal
- On Android emulators, `type` always reports `'unknown'` — test on real devices
- iOS requires the `NetworkExtension` entitlement to read cellular-specific details like carrier
- `NetInfo.fetch()` may return stale state; prefer the event subscription for real-time accuracy

## Related
- `mobile-network-resilience.md`
- `react-native-offline-first.md`
