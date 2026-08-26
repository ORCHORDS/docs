# TLS Exported Authenticator Context Binding

**Issue:** Exported Authenticators allow post-handshake proof of certificate possession without a new connection, but replay or context confusion can bind proof to the wrong application action.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Generate authenticators only on the intended TLS connection and validate transcript binding.
- Use unique, application-defined authenticator request context for each purpose.
- Validate certificate chain, signature scheme, identity, and authorization after cryptographic verification.
- Expire and single-use application challenges.

## Verification

- Replay on another connection and with another context.
- Swap certificate identities and signature algorithms.
- Test empty, duplicate, and oversized contexts.

## Gotchas

- Authentication does not itself grant application authorization.
- Both peers and intermediaries must support the intended TLS behavior.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9261.html
