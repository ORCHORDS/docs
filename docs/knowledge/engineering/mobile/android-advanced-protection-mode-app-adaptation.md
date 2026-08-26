# Android Advanced Protection Mode app adaptation

**Issue:** Apps serving at-risk users can continue risky workflows after the user enables Android Advanced Protection unless they subscribe to and safely apply the platform signal.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Declare `android.permission.QUERY_ADVANCED_PROTECTION_MODE` only when the product has documented behavior that changes under the mode.
- On API level 36+, obtain `AdvancedProtectionManager`, query `isAdvancedProtectionEnabled()` during initialization, and register a callback on an explicitly chosen executor.
- Make changes monotonic and conservative: strengthen app-controlled mitigations without claiming the signal proves identity, device integrity, or authorization.
- Unregister callbacks at the appropriate lifecycle boundary; re-query on fresh process startup because callbacks disappear when the process terminates.
- Define offline/default behavior and ensure unsupported OS versions continue with the normal security baseline.

## Verification

1. Test mode disabled, enabled before launch, toggled while running, process death, and restart.
2. Assert the initial callback/query race cannot temporarily weaken policy; apply transitions idempotently.
3. Test API-level guards so older devices never load unavailable classes.
4. Verify callback work runs on the intended executor and cannot block the main thread.
5. Exercise every adapted feature for accessibility and recovery, since the mode intentionally prioritizes security and may reduce functionality.

## Gotchas

Advanced Protection is a user-selected mode, not an attestation token. Do not upload or use its status for unrelated profiling. Registration produces change notifications but terminated apps cannot receive them, making the startup query essential. Platform restrictions and app-specific mitigations are separate; an app must not promise controls it does not implement.

## Sources

- [Android Developers: Advanced Protection Mode](https://developer.android.com/privacy-and-security/advanced-protection-mode)
- [Android API: AdvancedProtectionManager](https://developer.android.com/reference/android/security/advancedprotection/AdvancedProtectionManager)
