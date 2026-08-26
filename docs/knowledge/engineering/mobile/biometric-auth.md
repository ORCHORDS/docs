# biometric-auth-mobile

**Issue:** Face ID / Touch ID on iOS, Biometric API on Android, fallback flows, FIDO2 on mobile
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your app prompts for biometrics on every launch, but:
- The prompt shows generic OS text instead of your app name
- A user enrolled with Touch ID re-registers Face ID and the saved
  credential silently stops working
- The fallback PIN flow leaks the biometric result in localStorage
- Apple rejects the app: "Biometric usage description missing"

## Root cause
**Biometric authentication on mobile requires correct Keychain /
Keystore integration.** The biometric prompt is a gate — the actual
secret (private key or token) must be stored in hardware-backed
secure storage and only released after successful biometric auth.
Storing the result in memory or AsyncStorage defeats the purpose.

**Source:** Apple LocalAuthentication framework:
https://developer.apple.com/documentation/localauthentication

**Source:** Android BiometricPrompt API:
https://developer.android.com/training/sign-in/biometric-auth

**Source:** OWASP MASVS-AUTH:
https://mas.owasp.org/MASVS/controls/MASVS-AUTH-2/

## Capacitor — `@capacitor/biometrics` plugin (recommended)

```bash
npm install @aparajita/capacitor-biometric-auth
npx cap sync
```

```ts
// src/auth/biometric.ts
import {
  BiometricAuth,
  AuthenticateOptions,
  BiometryError,
  BiometryErrorType,
} from '@aparajita/capacitor-biometric-auth';

export async function checkBiometricAvailability(): Promise<{
  available: boolean;
  reason?: string;
}> {
  try {
    const { isAvailable, strongBiometryIsAvailable, reason } =
      await BiometricAuth.checkBiometry();

    if (!isAvailable) {
      return { available: false, reason };
    }
    return { available: true };
  } catch {
    return { available: false, reason: 'unknown' };
  }
}

export async function authenticateWithBiometric(
  reason: string
): Promise<boolean> {
  const options: AuthenticateOptions = {
    reason,
    cancelTitle: 'Cancel',
    allowDeviceCredential: false, // Do not fall back to PIN at OS level
    iosFallbackTitle: '',         // Empty string hides the fallback button
  };

  try {
    await BiometricAuth.authenticate(options);
    return true;
  } catch (error) {
    if (error instanceof BiometryError) {
      if (error.code === BiometryErrorType.userCancel ||
          error.code === BiometryErrorType.userFallback) {
        return false; // User chose not to use biometric
      }
      if (error.code === BiometryErrorType.biometryLockout) {
        // Too many failed attempts — force PIN fallback in your own UI
        await handleBiometricLockout();
        return false;
      }
    }
    return false;
  }
}
```

## iOS — `Info.plist` required keys

Apple **rejects** apps using biometrics without the usage description:

```xml
<!-- ios/App/App/Info.plist -->
<key>NSFaceIDUsageDescription</key>
<string>example project uses Face ID to securely sign you in without a password.</string>
```

Without this key, the app crashes on Face ID prompt with:
```
This app has crashed because it attempted to access privacy-sensitive data
without a usage description. The app's Info.plist must contain an
NSFaceIDUsageDescription key with a string value.
```

Touch ID does **not** require a separate key (it uses the same
LocalAuthentication framework but doesn't need a plist entry).

## iOS — Storing a secret in Keychain, gated by biometrics

The correct pattern: store a cryptographic key in the Secure Enclave,
protected by biometric auth. Use this key to encrypt/decrypt a session
token, never storing the session token directly.

```swift
// ios/App/App/BiometricKeychain.swift
import Foundation
import LocalAuthentication
import Security

enum BiometricKeychainError: Error {
  case keyCreationFailed
  case keyNotFound
  case biometricFailed
}

class BiometricKeychain {
  static let keyTag = "app.example project.biometric.sessionkey"

  /// Create or retrieve a Secure Enclave key protected by biometrics
  static func getOrCreateKey() throws -> SecKey {
    // Try to load existing key
    if let existing = loadKey() { return existing }

    // Create new key in Secure Enclave
    let access = SecAccessControlCreateWithFlags(
      kCFAllocatorDefault,
      kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
      [.privateKeyUsage, .biometryCurrentSet],  // .biometryCurrentSet invalidates on biometry change
      nil
    )!

    let attributes: [String: Any] = [
      kSecAttrKeyType as String:        kSecAttrKeyTypeECSECPrimeRandom,
      kSecAttrKeySizeInBits as String:  256,
      kSecAttrTokenID as String:        kSecAttrTokenIDSecureEnclave,
      kSecPrivateKeyAttrs as String: [
        kSecAttrIsPermanent as String:    true,
        kSecAttrApplicationTag as String: keyTag.data(using: .utf8)!,
        kSecAttrAccessControl as String:  access,
      ],
    ]

    var error: Unmanaged<CFError>?
    guard let key = SecKeyCreateRandomKey(attributes as CFDictionary, &error) else {
      throw BiometricKeychainError.keyCreationFailed
    }
    return key
  }

  private static func loadKey() -> SecKey? {
    let query: [String: Any] = [
      kSecClass as String:              kSecClassKey,
      kSecAttrKeyType as String:        kSecAttrKeyTypeECSECPrimeRandom,
      kSecAttrApplicationTag as String: keyTag.data(using: .utf8)!,
      kSecAttrTokenID as String:        kSecAttrTokenIDSecureEnclave,
      kSecReturnRef as String:          true,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    return status == errSecSuccess ? (result as! SecKey) : nil
  }
}
```

## Android — BiometricPrompt with hardware-backed KeyStore

```kotlin
// android/app/src/main/java/app/example project/BiometricHelper.kt
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

class BiometricHelper(private val activity: FragmentActivity) {

  companion object {
    private const val KEY_NAME = "example project_biometric_key"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
  }

  fun isBiometricAvailable(): Boolean {
    val manager = BiometricManager.from(activity)
    return manager.canAuthenticate(
      BiometricManager.Authenticators.BIOMETRIC_STRONG
    ) == BiometricManager.BIOMETRIC_SUCCESS
  }

  fun getOrCreateKey(): SecretKey {
    val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
    keyStore.getKey(KEY_NAME, null)?.let { return it as SecretKey }

    val keyGenerator = KeyGenerator.getInstance(
      KeyProperties.KEY_ALGORITHM_AES,
      ANDROID_KEYSTORE
    )
    keyGenerator.init(
      KeyGenParameterSpec.Builder(
        KEY_NAME,
        KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
      )
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
        .setUserAuthenticationRequired(true)
        .setUserAuthenticationParameters(
          0,                                          // 0 = require auth every use
          KeyProperties.AUTH_BIOMETRIC_STRONG
        )
        .setInvalidatedByBiometricEnrollment(true)   // Invalidate on new biometric enrol
        .build()
    )
    return keyGenerator.generateKey()
  }

  fun authenticate(
    onSuccess: (Cipher) -> Unit,
    onFailure: (String) -> Unit
  ) {
    val key = getOrCreateKey()
    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(Cipher.ENCRYPT_MODE, key)

    val executor = ContextCompat.getMainExecutor(activity)
    val prompt = BiometricPrompt(activity, executor,
      object : BiometricPrompt.AuthenticationCallback() {
        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
          result.cryptoObject?.cipher?.let { onSuccess(it) }
        }
        override fun onAuthenticationError(code: Int, msg: CharSequence) {
          onFailure("$code: $msg")
        }
        override fun onAuthenticationFailed() {
          // Individual attempt failed — do not call onFailure here; user can retry
        }
      }
    )

    prompt.authenticate(
      BiometricPrompt.PromptInfo.Builder()
        .setTitle("Sign in to example project")
        .setSubtitle("Verify your identity")
        .setNegativeButtonText("Use PIN instead")
        .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
        .build(),
      BiometricPrompt.CryptoObject(cipher)
    )
  }
}
```

## Fallback flow — PIN / password

When biometrics are unavailable or the user cancels:

```ts
// src/auth/authFlow.ts
export async function loginWithBiometricOrFallback(): Promise<string | null> {
  const { available } = await checkBiometricAvailability();

  if (available) {
    const success = await authenticateWithBiometric(
      'Sign in to verify your age and access example project.'
    );
    if (success) {
      // Retrieve stored session token using native bridge
      return NativeAuth.getSessionToken(); // decrypted from Keychain/KeyStore
    }
  }

  // Fall back to PIN — always server-side verified
  const pin = await promptUserForPin();
  return apiRequest<{ token: string }>('/auth/pin-login', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  }).then(r => r.token);
}
```

**Do not store the biometric result in AsyncStorage or localStorage.**
The native Keychain/KeyStore IS the secure storage.

## FIDO2 / WebAuthn on mobile

For apps that want phishing-resistant passkey authentication:

- **iOS 16+**: PassKeys via `ASAuthorizationPlatformPublicKeyCredentialProvider`
- **Android 9+**: Credential Manager API (`androidx.credentials`)
- Both use the device's biometric as the user verification step

Capacitor: use `@github/webauthn-json` in the WebView with the
Relying Party hosted on `example.com`. The browser handles the
platform authenticator (Face ID / fingerprint) transparently.

```ts
// In your Capacitor web layer — FIDO2 registration
import { create } from '@github/webauthn-json';

const credential = await create({
  publicKey: {
    challenge: base64urlDecode(serverChallenge),
    rp: { name: 'example project', id: 'example.com' },
    user: { id: userId, name: userEmail, displayName: userName },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7 },   // ES256
      { type: 'public-key', alg: -257 },  // RS256
    ],
    authenticatorSelection: {
      residentKey: 'required',
      userVerification: 'required',
      authenticatorAttachment: 'platform',  // device biometric only
    },
    timeout: 60000,
  },
});
```

## Verification
- [ ] `NSFaceIDUsageDescription` present in `Info.plist`
- [ ] Biometric key is invalidated when new fingerprint is enrolled (`setInvalidatedByBiometricEnrollment: true`)
- [ ] Fallback to PIN uses server-side verification, not local storage
- [ ] Simulator shows degraded state (no biometrics) — test on physical device
- [ ] Session token is NOT stored in AsyncStorage, localStorage, or SharedPreferences
- [ ] Test: enrol new fingerprint → verify old biometric session is invalidated

## Gotchas
- **`biometryAny` vs `biometryCurrentSet`**: On iOS, `biometryAny`
  allows the key to survive new biometric enrolment. `biometryCurrentSet`
  invalidates it. Use `biometryCurrentSet` for security-critical keys
  so a thief who adds their fingerprint can't reuse an existing session.
- **Android `setUserAuthenticationValidityDurationSeconds(-1)`** is
  deprecated in API 30+. Use `setUserAuthenticationParameters(0, AUTH_BIOMETRIC_STRONG)`
  to require biometric on every use.
- **Capacitor WebView biometrics**: `getUserMedia()` for camera-based
  biometrics is NOT the same as LocalAuthentication. Don't attempt to
  implement biometric auth in the WebView layer.
- **Face ID in landscape**: Supported but the prompt may render oddly.
  Test all orientations.
- **Class 1 (Convenience) vs Class 3 (Strong) biometrics on Android**:
  Only `BIOMETRIC_STRONG` is acceptable for auth gating a Keystore key.
  Class 1 (face unlock on low-end devices) cannot gate Keystore operations.

## Related
- `mobile-data-storage.md`
- `jwt-best-practices.md`
- `webview-security.md`
- Apple LocalAuthentication: https://developer.apple.com/documentation/localauthentication
- Android BiometricPrompt: https://developer.android.com/training/sign-in/biometric-auth
- OWASP MASVS-AUTH-2: https://mas.owasp.org/MASVS/controls/MASVS-AUTH-2/
- FIDO2 / WebAuthn: https://fidoalliance.org/fido2/
- @aparajita/capacitor-biometric-auth: https://github.com/aparajita/capacitor-biometric-auth
