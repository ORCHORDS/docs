# Android digital credentials verifier boundary

**Issue:** An app accepts a mobile credential presentation after platform UI succeeds but skips issuer trust, request binding, freshness, and selective-disclosure verification.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** evolving Android Credential Manager capability; verify current formats/support

Credential Manager digital credentials support holder-to-verifier presentation flows. Treat the platform result as transport: verify the requested protocol/format and cryptographic claims against the relying party's policy.

**Source:** [Android digital credentials](https://developer.android.com/identity/digital-credentials)

## Controls

- request only necessary claims with clear user context;
- bind challenge/nonce, origin, verifier identity, and expiry;
- validate issuer trust, signature, status, audience, and freshness server-side;
- minimize retention and avoid logging presentations;
- support cancellation/unavailability without weakening authorization;
- pin supported protocols/formats and review updates.

## Verification

Test replay, wrong verifier/audience, expired/revoked credential, untrusted issuer, altered disclosure, missing claim, cancellation, no provider, and cross-account binding.

## Gotchas

Wallet selection and biometric confirmation are not backend authorization. Digital-credential formats and platform APIs evolve. Selective disclosure does not eliminate correlation risk.
