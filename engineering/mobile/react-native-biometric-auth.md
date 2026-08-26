# react-native-biometric-auth

**Issue:** Implementing Face ID / Touch ID / fingerprint authentication in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Biometric auth gates sensitive actions (app unlock, payment confirmation) using the device's secure enclave. The implementation must handle unavailability gracefully and integrate with secure key storage.

## Pattern / Solution
```bash
npx expo install expo-local-authentication
```

```tsx
import * as LocalAuthentication from 'expo-local-authentication';

async function authenticateWithBiometrics(): Promise<boolean> {
  const compatible = await LocalAuthentication.hasHardwareAsync();
  if (!compatible) return fallbackToPin();

  const enrolled = await LocalAuthentication.isEnrolledAsync();
  if (!enrolled) {
    Alert.alert('No biometrics enrolled', 'Please set up Face ID or fingerprint in Settings.');
    return false;
  }

  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Confirm your identity',
    fallbackLabel: 'Use PIN',
    cancelLabel: 'Cancel',
    disableDeviceFallback: false, // allow PIN fallback
  });

  return result.success;
}

// Check what's available
const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
// Returns array of: FINGERPRINT, FACIAL_RECOGNITION, IRIS
```

**Biometric-protected key (encrypt a secret):**
```ts
import * as SecureStore from 'expo-secure-store';

// Store after biometric success
await SecureStore.setItemAsync('session_token', token, {
  requireAuthentication: true, // biometric required to read back
});

// Read — triggers biometric prompt automatically
const token = await SecureStore.getItemAsync('session_token', {
  authenticationPrompt: 'Verify to continue',
});
```

## Gotchas
- iOS requires `NSFaceIDUsageDescription` in `Info.plist`; Expo adds this via the plugin but bare workflow needs it manually
- `requireAuthentication: true` in SecureStore calls the OS biometric prompt on every read — don't use for high-frequency reads
- Android biometric API changed in Android 11; `expo-local-authentication` abstracts this but older `react-native-biometrics` does not
- Enrollment can change (user adds/removes fingerprint); always re-check `isEnrolledAsync()` after app foregrounding
- Simulator returns `false` for `hasHardwareAsync()`; use a physical device for testing

## Related
- `react-native-secure-storage.md`
- `biometric-auth.md`
- `mobile-auth-oauth-pkce.md`
- `ios-keychain-storage.md`
