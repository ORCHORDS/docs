# android-keystore-biometrics

**Issue:** Using Android Keystore with biometric authentication to protect cryptographic keys
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Android Keystore stores cryptographic keys in hardware-backed secure storage. Combining Keystore keys with BiometricPrompt ensures that private keys are only unlocked after biometric verification.

## Pattern / Solution
**Generate biometric-bound key:**
```kotlin
private fun generateBiometricKey(keyName: String) {
    val keyGenerator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
    keyGenerator.init(
        KeyGenParameterSpec.Builder(keyName,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_CBC)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_PKCS7)
            .setUserAuthenticationRequired(true)
            .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
            .setInvalidatedByBiometricEnrollment(true) // invalidate on new biometric
            .build()
    )
    keyGenerator.generateKey()
}
```

**BiometricPrompt with Crypto object:**
```kotlin
val keyName = "my_biometric_key"
generateBiometricKey(keyName)

val keystore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
val secretKey = keystore.getKey(keyName, null) as SecretKey
val cipher = Cipher.getInstance("AES/CBC/PKCS7Padding").apply {
    init(Cipher.ENCRYPT_MODE, secretKey)
}

val cryptoObject = BiometricPrompt.CryptoObject(cipher)
val executor = ContextCompat.getMainExecutor(this)
val biometricPrompt = BiometricPrompt(this, executor, object : BiometricPrompt.AuthenticationCallback() {
    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
        val encryptedData = result.cryptoObject?.cipher?.doFinal(plaintext)
        // Store encryptedData
    }
})

val promptInfo = BiometricPrompt.PromptInfo.Builder()
    .setTitle("Biometric Authentication")
    .setSubtitle("Authenticate to encrypt data")
    .setNegativeButtonText("Cancel")
    .build()

biometricPrompt.authenticate(promptInfo, cryptoObject)
```

## Gotchas
- `setInvalidatedByBiometricEnrollment(true)` means adding a new fingerprint/face invalidates the key — handle `KeyPermanentlyInvalidatedException` gracefully by regenerating
- `setUserAuthenticationRequired` without `setUserAuthenticationParameters` uses deprecated API on Android 11+
- Keys requiring auth can't be used in background services — authentication is always interactive
- `StrongBox` (hardware security module) is present on Pixel 3+ and some Samsung devices; check with `setIsStrongBoxBacked(true)` and catch `StrongBoxUnavailableException`
- BiometricManager must confirm `BIOMETRIC_STRONG` support before using crypto-based biometric prompt

## Related
- `react-native-biometric-auth.md`
- `react-native-secure-storage.md`
- `ios-keychain-storage.md`
- `android-play-store-submission.md`
