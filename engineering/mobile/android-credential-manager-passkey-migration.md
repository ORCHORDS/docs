# Android Credential Manager passkey migration

**Issue:** An Android application adds passkeys through a provider-specific or legacy sign-in path, producing inconsistent account linking, recovery, and fallback behavior.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

Use Android Credential Manager as the application integration boundary for credentials and passkeys. Treat passkey enrollment and sign-in as server-verified WebAuthn ceremonies, not as a local biometric success signal.

**Source:** [AndroidX Credential Manager releases](https://developer.android.com/jetpack/androidx/releases/credentials)

## Migration controls

- support existing account sign-in alongside passkeys until migration metrics and recovery paths are proven;
- bind registration and assertion challenges to the server session, user, origin/RP ID, and short expiry;
- verify the credential response server-side before linking it to an account;
- provide an explicit account-recovery path that does not silently downgrade account security;
- distinguish device credential/provider availability from authentication failure;
- record privacy-minimized funnel outcomes: offered, selected, succeeded, cancelled, unavailable, and server-rejected.

## Verification

- registration cannot link a passkey to the wrong signed-in account;
- assertion for a different RP/origin or expired challenge is rejected server-side;
- a user with no compatible credential provider receives a usable fallback;
- credential removal, device change, and recovery preserve account access without bypassing verification;
- automated coverage uses platform/provider test doubles while production still verifies server behavior.

## Gotchas

- Credential Manager APIs and providers evolve; pin supported library versions and review release notes before upgrades.
- A biometric prompt confirms local user verification, not your backend authorization.
- Do not log credential responses, challenges, or user-identifying attestation data.
- Passkeys are not a reason to delete password/recovery controls without an account-lifecycle decision.

## Related

- `mobile/biometric-auth.md`
- `security/passkeys-2026.md`
- the WebAuthn guidance in security/
