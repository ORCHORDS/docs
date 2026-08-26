# oauth-dpop-sender-constrained-token-validation

**Issue:** A stolen OAuth bearer token can be replayed by a different client.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Bearer tokens confer access to whoever possesses them. Demonstrating Proof-of-Possession (DPoP) binds a token to a client-held key, but only when the authorization server and resource server validate the proof, token confirmation binding, target URI/method, freshness, nonce requirements, and replay protection.

**Source:** [RFC 9449 — OAuth 2.0 Demonstrating Proof-of-Possession](https://datatracker.ietf.org/doc/rfc9449/).

## Fix

- validate the DPoP proof signature and public-key thumbprint;
- require the expected HTTP method and normalized target URI;
- enforce issued-at freshness and a bounded replay cache for proof identifiers;
- validate nonce challenges where required;
- verify the access token confirmation claim binds to the proof key;
- fail closed with stable public errors and protected diagnostics.

## Verification

- A valid proof succeeds only with the bound token and intended method/URI.
- Replaying the same proof is rejected.
- A proof from another key, stale timestamp, or wrong target is rejected.
- A token without the expected binding cannot use the sender-constrained route.

## Related

- `security/oauth-21-2026.md`
- the token revocation guidance in the OAuth sections
