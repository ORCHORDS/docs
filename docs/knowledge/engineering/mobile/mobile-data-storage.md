# mobile-data-storage

**Issue:** Keychain (iOS), KeyStore (Android), insecure storage patterns, Capacitor Preferences pitfalls
**Date:** 2026-08-11
**Status:** documented

## Symptom
A security researcher runs `adb backup` (Android < 12) or accesses
`/var/mobile/Containers/Data` on a jailbroken iPhone and extracts:
- JWT refresh tokens stored in `AsyncStorage`
- Age-verification status stored in `SharedPreferences`
- Creator payment account IDs in `localStorage`

All of these are plaintext and readable without any special
privileges on a compromised device.

## Root cause
**`AsyncStorage`, `localStorage`, `SharedPreferences`, and
`Capacitor Preferences` are all plaintext, unencrypted stores.**
They are protected only by the OS sandbox — which is bypassed on
jailbroken/rooted devices and via `adb backup` on older Android.

**Source:** OWASP MASVS-STORAGE:
https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-1/

**Source:** OWASP MSTG — Testing Local Data Storage:
https://mas.owasp.org/MASTG/tests/android/MASVS-STORAGE/MASTG-TEST-0001/

## Storage security levels

| Storage | iOS | Android | Use for |
|---|---|---|---|
| `Keychain` (kSecClassGenericPassword) | Encrypted, hardware-backed | — | Secrets, tokens |
| `Keystore` + encrypted file | — | Hardware-backed | Secrets, tokens |
| `SecureStore` (Expo) | Keychain | Keystore | Secrets (cross-platform) |
| `@capacitor/preferences` | UserDefaults | SharedPreferences | Non-sensitive UI state |
| `AsyncStorage` | SQLite (plaintext) | SQLite (plaintext) | Non-sensitive only |
| `localStorage` | WKWebView cache | WebView cache | Non-sensitive only |
| `Filesystem` (Capacitor) | App Documents dir | App data dir | Files; encrypt manually |

## What to store where

```
Sensitive (use Keychain / KeyStore):
  - JWT access token
  - JWT refresh token
  - Age-verification token / credential
  - Payment method tokens (Stripe PM ID)
  - Biometric-protected session key
  - Creator API keys

Non-sensitive (Preferences / AsyncStorage is OK):
  - User display name
  - UI preferences (dark mode, language)
  - Last-seen content ID
  - Cached creator IDs (not payment data)
```

## Capacitor — `@capacitor-community/secure-storage`

```bash
npm install @capacitor-community/secure-storage-plugin
npx cap sync
```

```ts
// src/storage/secureStorage.ts
import { SecureStoragePlugin } from '@capacitor-community/secure-storage-plugin';

const KEYS = {
  ACCESS_TOKEN:  '<redacted-secret>',
  REFRESH_TOKEN: 'auth.refreshToken',
  AGE_TOKEN:     'auth.ageVerified',
} as const;

export async function storeTokens(
  accessToken: string,
  refreshToken: string
): Promise<void> {
  await SecureStoragePlugin.set({ key: KEYS.ACCESS_TOKEN, value: accessToken });
  await SecureStoragePlugin.set({ key: KEYS.REFRESH_TOKEN, value: refreshToken });
}

export async function getAccessToken(): Promise<string | null> {
  try {
    const { value } = await SecureStoragePlugin.get({ key: KEYS.ACCESS_TOKEN });
    return value;
  } catch {
    return null;  // Key not found
  }
}

export async function clearTokens(): Promise<void> {
  await SecureStoragePlugin.remove({ key: KEYS.ACCESS_TOKEN });
  await SecureStoragePlugin.remove({ key: KEYS.REFRESH_TOKEN });
  await SecureStoragePlugin.remove({ key: KEYS.AGE_TOKEN });
}
```

**Under the hood:**
- iOS: `kSecClassGenericPassword` in the system Keychain, with
  `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` by default
- Android: AES-256 key in the Android KeyStore, value encrypted in
  EncryptedSharedPreferences (Jetpack Security)

## iOS Keychain — accessibility levels explained

| Attribute | When accessible | Migrates to new device |
|---|---|---|
| `kSecAttrAccessibleWhenUnlocked` | Only while screen unlocked | Yes (iCloud Keychain) |
| `kSecAttrAccessibleAfterFirstUnlock` | After first unlock (background OK) | Yes |
| `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` | Only while unlocked, no migration | No |
| `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` | After first unlock, no migration | No |
| `kSecAttrAccessibleAlways` | Always (DEPRECATED) | Yes |

**Use `ThisDeviceOnly` variants** for auth tokens — you do NOT want
them migrated to a new device. The user must re-authenticate after
restoring to a new phone.

```swift
// ios/App/App/KeychainService.swift
import Foundation
import Security

struct KeychainService {
  static func save(key: String, value: String) throws {
    let data = value.data(using: .utf8)!
    let query: [String: Any] = [
      kSecClass as String:                kSecClassGenericPassword,
      kSecAttrService as String:          "app.example project",
      kSecAttrAccount as String:          key,
      kSecValueData as String:            data,
      kSecAttrAccessible as String:       kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
    ]
    SecItemDelete(query as CFDictionary)  // Remove existing
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else {
      throw KeychainError.saveFailed(status)
    }
  }

  static func load(key: String) throws -> String? {
    let query: [String: Any] = [
      kSecClass as String:       kSecClassGenericPassword,
      kSecAttrService as String: "app.example project",
      kSecAttrAccount as String: key,
      kSecReturnData as String:  true,
      kSecMatchLimit as String:  kSecMatchLimitOne,
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = result as? Data else {
      throw KeychainError.loadFailed(status)
    }
    return String(data: data, encoding: .utf8)
  }
}

enum KeychainError: Error {
  case saveFailed(OSStatus)
  case loadFailed(OSStatus)
}
```

## Android — EncryptedSharedPreferences (Jetpack Security)

```kotlin
// android/app/src/main/java/app/example project/SecurePrefs.kt
import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SecurePrefs {
  private const val FILE_NAME = "example project_secure_prefs"

  private fun getPrefs(context: Context) = EncryptedSharedPreferences.create(
    context,
    FILE_NAME,
    MasterKey.Builder(context)
      .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
      .build(),
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
  )

  fun putString(context: Context, key: String, value: String) {
    getPrefs(context).edit().putString(key, value).apply()
  }

  fun getString(context: Context, key: String): String? =
    getPrefs(context).getString(key, null)

  fun remove(context: Context, key: String) {
    getPrefs(context).edit().remove(key).apply()
  }
}
```

The `MasterKey` is backed by the Android KeyStore and requires no
password — it is protected by the device's screen lock.

## Capacitor Preferences — when it's acceptable

```ts
// src/storage/preferences.ts
import { Preferences } from '@capacitor/preferences';

// OK to use Preferences for:
export async function saveUIState(darkMode: boolean): Promise<void> {
  await Preferences.set({ key: 'ui.darkMode', value: String(darkMode) });
}

// NOT OK:
// await Preferences.set({ key: 'auth.token', value: jwtToken });
// await Preferences.set({ key: 'age.verified', value: 'true' });
```

`@capacitor/preferences` maps to `UserDefaults` (iOS) and
`SharedPreferences` (Android). Both are plaintext. Use them only
for non-sensitive state.

## Backup exclusion — Android

Prevent sensitive files from being included in Android backups:

```xml
<!-- android/app/src/main/res/xml/backup_rules.xml -->
<?xml version="1.0" encoding="utf-8"?>
<full-backup-content>
  <!-- Exclude EncryptedSharedPreferences file -->
  <exclude domain="sharedpref" path="example project_secure_prefs.xml"/>
  <!-- Exclude all shared preferences to be safe -->
  <exclude domain="sharedpref" path="."/>
  <!-- Exclude databases (AsyncStorage) -->
  <exclude domain="database" path="."/>
</full-backup-content>
```

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<application
  android:allowBackup="false"
  android:fullBackupContent="@xml/backup_rules"
  ...>
```

On Android 12+, use `android:dataExtractionRules` instead of
`android:fullBackupContent` — but include both for compatibility.

## iOS — iCloud Keychain sync prevention

Use `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (note:
`ThisDeviceOnly`) to prevent auth tokens from syncing to iCloud
Keychain and appearing on other devices when the user restores a backup.

## Verification
- [ ] `grep -r "AsyncStorage" src/` — no token or credential keys
- [ ] `grep -r "localStorage" src/` — no sensitive data
- [ ] `grep -r "Preferences.set" src/` — all keys are non-sensitive
- [ ] Android: `adb backup -apk app.example project` and verify secrets are excluded
- [ ] iOS: check `NSURLIsExcludedFromBackupKey` on any sensitive files created by the app
- [ ] Jailbroken iOS: `ls /var/mobile/Containers/Data/Application/<uuid>/Documents/` — no plaintext tokens

## Gotchas
- **`@capacitor/preferences` is NOT secure.** Its docs don't warn you
  sufficiently. Many Capacitor starters use it for auth tokens.
- **EncryptedSharedPreferences throws on first run** if the KeyStore
  is unavailable (e.g., OS upgrade that resets hardware keys). Handle
  `java.security.KeyStoreException` and clear the prefs, then
  force re-login.
- **Keychain is shared across apps with the same `kSecAttrAccessGroup`**.
  If you have multiple example project apps (e.g., a debug variant), they share
  the same keychain namespace. Use distinct service names.
- **`allowBackup="true"` is the Android default**. Most developers
  don't know this. Always set it explicitly.
- **expo-secure-store** uses the same underlying Keychain/KeyStore
  but is Expo-specific. If you use bare Capacitor, use
  `@capacitor-community/secure-storage-plugin` instead.

## Related
- `biometric-auth.md`
- `webview-security.md`
- `jwt-best-practices.md`
- OWASP MASVS-STORAGE-1: https://mas.owasp.org/MASVS/controls/MASVS-STORAGE-1/
- Apple Keychain Services: https://developer.apple.com/documentation/security/keychain_services
- Android EncryptedSharedPreferences: https://developer.android.com/reference/androidx/security/crypto/EncryptedSharedPreferences
- Jetpack Security: https://developer.android.com/topic/security/data
- @capacitor-community/secure-storage-plugin: https://github.com/capacitor-community/secure-storage-plugin
