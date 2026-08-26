# Android Restore Credentials Account Reprovisioning

**Issue:** After device setup or app-data restoration, users must sign in manually and background services resume against stale local state; a restore key can also be confused with a user-managed passkey.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use Credential Manager Restore Credentials as a server-verified reprovisioning ceremony. Generate a restore key only after an authenticated session, distinguish it from user-managed passkeys in backend records, and support only the single account that the Android feature permits per app. On the new device, request the restore credential at first launch and, when app backup is enabled, from `BackupAgent.onRestoreFinished()`.

Send the public-key response to the relying-party server and run the same cryptographic verification boundary used for passkey assertions while applying restore-specific risk, audit, and revocation policy. Re-register device-bound services such as push tokens after success; credentials do not restore those registrations automatically.

## Verification

Test cloud backup, device-to-device transfer, backup disabled, unavailable end-to-end encryption, multiple app accounts, work/personal profiles, no restore key, revoked server record, replay, restored app data arriving before the key, and first launch without network. Confirm restoration cannot link the wrong account and push delivery resumes only after a fresh token is registered.

## Gotchas

Restore keys are system-managed and hidden from ordinary passkey management. Support is mobile-only and constrained across system profiles. Silent restoration should not bypass step-up policy for sensitive actions. Never log credential responses or restoration secrets.

## Sources

- [Android Developers — About Restore Credentials](https://developer.android.com/identity/sign-in/restore-credentials)
- [Android Developers — Implement Restore Credentials](https://developer.android.com/identity/sign-in/restore-credentials-implementation)
