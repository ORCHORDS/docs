# Android Key Verifier Manager trust state

**Issue:** Android Key Verifier supports out-of-band verification of end-to-end-encryption keys. A successful API call is not permanent identity proof: keys rotate, verification can be removed, and account/device context must match the conversation.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Bind verification to account, peer, device/key identifier, algorithm, and key version. Display human-comparable or scanned verification material through the system-supported flow, require explicit confirmation, and persist provenance and timestamp. Revoke trust on key replacement, account removal, or contradictory verification; never auto-transfer trust to a new key.

## Verification
Test scan/manual mismatch, stale and rotated keys, multiple devices, account switching, offline verification, cancellation, process death, restore, replayed codes, and concurrent key updates. Encryption must continue safely when verification is unavailable, while clearly showing unverified state.

## Gotchas
Verified means the compared key matched at that time; it does not establish legal identity or protect compromised endpoints.

## Sources
- Android Developers, [Key Verifier](https://developer.android.com/privacy-and-security/key-verifier)
- Android Developers, [Key Verifier Manager API](https://developer.android.com/reference/android/security/KeyStore)
