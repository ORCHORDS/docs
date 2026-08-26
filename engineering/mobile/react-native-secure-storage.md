# react-native-secure-storage

**Issue:** Storing sensitive data (tokens, keys) securely in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`AsyncStorage` is unencrypted and world-readable on rooted devices. Tokens, session credentials, and private keys must use OS-backed secure storage (iOS Keychain, Android Keystore).

## Pattern / Solution
**expo-secure-store (Expo / managed):**
```ts
import * as SecureStore from 'expo-secure-store';

// Write
await SecureStore.setItemAsync('auth_token', token);

// Read
const token = await SecureStore.getItemAsync('auth_token');

// Delete
await SecureStore.deleteItemAsync('auth_token');

// Options
await SecureStore.setItemAsync('key', value, {
  keychainService: 'com.example.myapp',            // iOS: custom keychain group
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  requireAuthentication: true,                     // biometric gate on read
});
```

**react-native-keychain (bare workflow):**
```ts
import * as Keychain from 'react-native-keychain';

await Keychain.setGenericPassword('username', 'password', {
  service: 'auth',
  accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_ANY,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});

const creds = await Keychain.getGenericPassword({ service: 'auth' });
// creds.password
```

**Storage tiers:**
| Sensitivity | Storage |
|-------------|---------|
| Low (UI prefs) | MMKV |
| Medium (non-secret user data) | AsyncStorage |
| High (tokens, PII) | expo-secure-store / Keychain |
| Critical (crypto keys) | SecureStore + `requireAuthentication` |

## Gotchas
- `WHEN_UNLOCKED_THIS_DEVICE_ONLY` prevents iCloud backup of the item — use this for tokens
- On Android, SecureStore falls back to SharedPreferences encrypted with a Keystore-backed key on API < 23
- Values are limited to ~2 KB in some Keychain implementations; don't store large JWTs directly — store a reference or compress
- Keychain items survive app uninstall on iOS unless you delete them on first launch (detect via a separate UserDefaults flag)
- `requireAuthentication` on Android requires `setUserAuthenticationRequired` which ties the key to the current biometric enrollment

## Related
- `react-native-biometric-auth.md`
- `mobile-jwt-storage-pitfalls.md`
- `ios-keychain-storage.md`
- `android-keystore-biometrics.md`
