# Android Keystore StrongBox-Backed Key Generation

StrongBox (introduced Android 9 / API 28 on dedicated hardware) executes key material and crypto operations inside a discrete secure processor, isolated from the TEE that backs default Android Keystore keys. Using it correctly means requesting it conditionally, handling `StrongBoxUnavailableException`, and never assuming the same key exists across devices or reinstalls. This article covers generation, fallback strategy, and attestation-verified deployment.

## Scope

Covered: `KeyGenParameterSpec.Builder` with `setIsStrongBoxBacked(true)`, the `STRONGBOX`/`TEE` backing distinction, `StrongBoxUnavailableException` fallback flows, key attestation extension parsing to prove backing, user-authentication-bound StrongBox keys, and `setInvalidatedByBiometricEnrollment` interactions. Not covered: general biometric-prompt UX or the WebAuthn/credential flows that may consume such keys - this is the key-generation and lifecycle layer.

## Workflow or implementation guidance

**Capability detection before generation.** StrongBox presence is not a pure API-level check: it requires API 28+ *and* dedicated hardware (`PackageManager.FEATURE_STRONGBOX_KESTSTORE` - note the constant is `FEATURE_STRONGBOX_KEYSTORE`; query `packageManager.hasSystemFeature`). Notably, API 30 clarified with `FEATURE_STRONGBOX_KEYSTORE` declared flags. Check both `Build.VERSION.SDK_INT >= 28` and the feature flag; a device can be API 33 and still lack the secure element (most mid-range devices).

**Generate with an explicit fallback chain.**

1. Attempt StrongBox generation inside `try` when the feature check passed: `setIsStrongBoxBacked(true)` on the `KeyGenParameterSpec.Builder`, alongside the standard parameters - `PURPOSE_SIGN or PURPOSE_VERIFY` for EC keys (`KEY_ALGORITHM_EC` with `setDigests(DIGEST_SHA256)`), or `PURPOSE_ENCRYPT/DECRYPT` for AES with `setBlockModes(BLOCK_MODE_GCM)` and `setEncryptionPaddings(ENCRYPTION_PADDING_NONE)`.
2. Catch `StrongBoxUnavailableException` (and the general `ProviderException` wrapping it on some OEM builds) and retry the identical generation *without* the StrongBox flag, marking the resulting key's backing as TEE in app state.
3. Do not retry StrongBox in a loop: some devices report the feature then fail per-key when the secure element has no slots left or is in an error state; one fallback, logged, is correct.

**Bind user authentication deliberately.** `setUserAuthenticationRequired(true)` plus `setUserAuthenticationParameters(timeout, authTypes)` (API 30+) or the legacy `setUserAuthenticationValidityDurationSeconds`. StrongBox keys support `setInvalidatedByBiometricEnrollment(true)`: a new biometric enrollment invalidates the key via `KeyPermanentlyInvalidatedException` on next use, which is exactly what you want for high-value keys - surface a re-enrollment flow, do not swallow the exception.

**Prove the backing with attestation.** After generation, request an attestation certificate chain (the `AttestationApplicationId` and root from `Keymaster`/`KeyMint`): generate with `setAttestationChallenge(byteArray)` and read `keyStore.getCertificateChain(alias)`. Parse the Android Keystore attestation extension (OID 1.3.6.1.4.1.11129.2.1.17) and verify: the challenge matches, the chain roots at a Google-issued attestation root, and the security level / keymaster tags indicate the secure element. Server-side verification is mandatory for trust decisions - a client-side "I checked my own attestation" is decorative. Keymint attestation on newer devices reports the security level explicitly (StrongBox = `TrustedEnvironment`/secure element per the extension's `RootOfTrust` and security-level fields).

**Usage and lifecycle.** Sign via `Signature.getInstance("SHA256withECDSA")` initialized with the `PrivateKey` from `keyStore.getEntry(alias, null)`; perform crypto in the Keystore provider so the raw key never leaves the secure element - there is no export path, by design. Key deletion is `keyStore.deleteEntry(alias)`; reinstalls and device resets destroy StrongBox keys permanently, so any encrypted payload under a StrongBox key needs a cloud-recovery or re-derivation path designed in.

## Controls

- Gate every StrongBox call behind `hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)`; treat feature-present-but-generation-failing devices as a normal fleet segment (log the OEM/model for tracking).
- Persist key metadata (alias, creation timestamp, backing level) in app storage or server-side, never the key itself; verify attestation server-side and record the verified backing level per installation.
- Set `setAttestationChallenge` to a server-issued nonce per generation so replayed attestation chains are detectable.
- Use `setUserAuthenticationRequired(true)` with `setInvalidatedByBiometricEnrollment(true)` for keys protecting user secrets; catch `KeyPermanentlyInvalidatedException` at use-time and route to re-provisioning.
- Keep one alias scheme (`<userId>-signing-v1`) and version it; migrating keys means generating v2 and re-wrapping data, not mutating v1.
- In tests, inject a Keystore abstraction; Robolectric does not emulate StrongBox or TEE, so attestation-path tests belong on hardware.

## Validation evidence

On a StrongBox-equipped device (certain Pixel models ship the secure element; verify with `adb shell dumpsys trust` or your attestation parse), generate a key, parse the attestation chain, and confirm the extension's security level denotes the secure element with your challenge present. Then test the matrix: (1) feature-flag absent device - assert fallback to TEE-backed key succeeds and metadata records backing=TEE; (2) lock the key behind auth, fail biometric, assert `UserNotAuthenticatedException`; (3) enroll a new biometric, assert next use throws `KeyPermanentlyInvalidatedException` when configured; (4) uninstall/reinstall, assert the key is gone and recovery path engages. Evidence basis: parameter semantics come from the `KeyGenParameterSpec` reference; the exception contract from `StrongBoxUnavailableException`; attestation extension structure from the Android Keystore attestation documentation.

## Failure modes and correction

- `StrongBoxUnavailableException` despite feature flag present: secure element busy, out of key slots, or OEM firmware fault. Correct behavior is single fallback to non-StrongBox generation with telemetry; do not crash or retry-loop.
- `KeyStoreException: -66` style low-level failures on generation: slot exhaustion on the secure element; use fewer, longer-lived aliases rather than per-operation keys.
- Attestation chain fails server verification with wrong root: test keys (verified boot red state) or an emulator produce non-Google-rooted chains; verify only on production-booted hardware for trust decisions.
- Key works then throws `KeyPermanentlyInvalidatedException`: expected after biometric re-enrollment or lock-screen credential change when bound - run the re-provisioning UX; catching-and-continuing silently corrupts the security model.
- Random `SignatureException` under concurrent use: Keystore operations on one key are not arbitrarily parallel across the secure element; serialize operations per alias with a mutex in the repository layer.
- OEM reports StrongBox but attestation says TEE: trust the attestation, not the feature flag; record actual backing from the parsed chain.

## Limitations

StrongBox availability is sparse across the Android fleet - designing as if it is universal inverts the fallback. Secure-element operation throughput is lower than TEE; high-frequency crypto under StrongBox keys adds measurable latency. Attestation verification requires Google's attestation root certificates and correct extension parsing; Google rotates roots over time. This article does not cover Identity Credential APIs or remote key provisioning (IRK), which interact with the same hardware but have separate contracts.

## Canonical sources

- Android Developers - `KeyGenParameterSpec` reference (`setIsStrongBoxBacked`, auth binding parameters): https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec (verified HTTP 200)
- Android Developers - `StrongBoxUnavailableException` reference (fallback trigger contract): https://developer.android.com/reference/android/security/keystore/StrongBoxUnavailableException (verified HTTP 200)
- Android Developers - "Android Keystore system" (attestation and hardware-backed key overview): https://developer.android.com/training/articles/keystore (verified HTTP 200)
