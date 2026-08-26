# passkeys-2026

**Issue:** Authentication policy treats every passkey as equally suitable for every assurance level, without accounting for syncability, recovery, or authenticator controls.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A product enables passkeys and labels the result “phishing-resistant MFA,” but cannot explain whether synced credentials meet its assurance target, how recovery is protected, or when a managed hardware authenticator and step-up are required.

## Root cause

Passkeys are WebAuthn credentials, but assurance depends on the authenticator, verification ceremony, sync fabric, recovery process, and policy—not on the user-experience label. NIST SP 800-63B Rev. 4 distinguishes requirements for syncable authenticators and preserves the higher-assurance constraint that AAL3 authenticators must be non-exportable.

**Source:** [NIST SP 800-63B Rev. 4](https://pages.nist.gov/800-63-4/sp800-63b.html) and the [syncable-authenticator appendix](https://pages.nist.gov/800-63-4/sp800-63b/syncable/).

## Fix

- define the required assurance level and which transactions require step-up;
- assess syncable passkeys for encrypted key material, authenticated sync-fabric access, credential visibility, and recovery controls;
- require user verification where the risk warrants it;
- use a non-exportable authenticator for AAL3-aligned use cases;
- threat-model sign-in, privileged administration, recovery, and enrollment separately;
- collect privacy-preserving evidence of ceremony success, authenticator policy, fallback use, and step-up events.

## Verification

- RP ID, origin, challenge, and user-verification requirements are validated server-side.
- Each accepted authenticator has a documented assurance-policy basis.
- A syncable passkey alone cannot satisfy an AAL3-aligned privileged action.
- Recovery cannot silently downgrade the intended assurance level.
- A mismatched RP ID, stale challenge, or missing user verification is rejected.

## Gotchas

- A biometric unlock normally verifies the user locally; biometric data is not sent to the relying party.
- “Synced” does not mean insecure, but it changes the assurance and recovery analysis.
- Do not rely on attestation alone as proof of user identity or device management.

## Related

- `security/webauthn-passkey-flow.md`
- `security/oauth-21-2026.md`
