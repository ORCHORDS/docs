# ios-keychain-storage

**Issue:** Storing secrets securely in the iOS Keychain
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The iOS Keychain provides hardware-backed encrypted storage for passwords, tokens, and cryptographic keys. Misunderstanding accessibility attributes and keychain groups leads to data loss or security gaps.

## Pattern / Solution
**Swift Keychain wrapper:**
```swift
import Security

struct KeychainHelper {
    static func save(_ data: Data, service: String, account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    static func read(service: String, account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        SecItemCopyMatching(query as CFDictionary, &result)
        return result as? Data
    }
}
```

**Accessibility options — choose carefully:**
| Constant | Accessible when |
|---|---|
| `kSecAttrAccessibleWhenUnlocked` | Device unlocked (backed up to iCloud) |
| `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` | Device unlocked, no iCloud backup |
| `kSecAttrAccessibleAfterFirstUnlock` | After first unlock post-boot (suitable for background) |
| `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` | Requires device passcode, no backup |

**Keychain groups (share between apps):**
```xml
<!-- MyApp.entitlements -->
<key>keychain-access-groups</key>
<array>
    <string>$(AppIdentifierPrefix)com.example.shared</string>
</array>
```

## Gotchas
- Keychain items persist after app uninstall on iOS — delete items on first launch to avoid stale credentials from a previous install
- `kSecAttrAccessibleAlways` is deprecated and will fail App Review; never use it
- Items created without `kSecAttrAccessGroup` are only accessible by the creating app
- Simulator Keychain is shared across all apps — don't rely on isolation during testing
- Large values (> ~64 KB) should store a key reference, not the value itself; store blobs in encrypted files

## Related
- `react-native-secure-storage.md`
- `react-native-biometric-auth.md`
- `android-keystore-biometrics.md`
- `mobile-jwt-storage-pitfalls.md`
