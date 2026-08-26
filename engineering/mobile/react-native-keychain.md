# react-native-keychain

**Issue:** Storing sensitive credentials in the iOS Keychain and Android Keystore via React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tokens stored in AsyncStorage or MMKV are readable by any process with file access; Keychain/Keystore binds credentials to the app and optionally to biometric auth.

## Pattern / Solution
```sh
npm install react-native-keychain
npx pod-install
```

```ts
import * as Keychain from 'react-native-keychain';

// Store credentials
await Keychain.setGenericPassword('username', 'super-secret-token');

// Retrieve
const creds = await Keychain.getGenericPassword();
if (creds) {
  console.log(creds.username, creds.password);
} else {
  console.log('No credentials stored');
}

// Delete
await Keychain.resetGenericPassword();

// Biometric-protected storage
await Keychain.setGenericPassword('user', 'token', {
  accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_ANY,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});

// Retrieve with biometric prompt
const result = await Keychain.getGenericPassword({
  authenticationPrompt: { title: 'Authenticate to access your account' },
});
```

## Gotchas
- On Android the backing store is `EncryptedSharedPreferences` (API 23+) or Keystore — fallback to FB Conceal on older devices
- `WHEN_UNLOCKED_THIS_DEVICE_ONLY` means credentials are lost on backup restore — use `WHEN_UNLOCKED` if cross-device restore is needed
- Biometric-protected items require a successful biometric prompt even in tests; mock the module in Jest
- Keychain items survive app uninstall on iOS by default; use `accessGroup` to scope them

## Related
- `react-native-secure-storage.md`
- `react-native-biometric-auth.md`
- `react-native-mmkv-storage.md`
