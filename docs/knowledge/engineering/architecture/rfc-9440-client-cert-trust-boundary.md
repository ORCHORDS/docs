# Make RFC 9440 Client-Cert a Proxy Trust Boundary

**Issue:** Backends behind TLS termination cannot directly observe the client handshake. Accepting a client-supplied certificate header enables identity spoofing.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Accept Client-Cert fields only from an authenticated, authorized TLS-terminating reverse proxy.
- Strip or overwrite every inbound Client-Cert and Client-Cert-Chain field, including when client authentication was not negotiated.
- Validate the client certificate at the terminator and bind backend authorization to the trusted hop.
- Parse the RFC Structured Field byte sequence and cap header/chain size.
- Make certificate-dependent responses uncacheable or correctly selective as RFC 9440 requires.

## Verification
- Inject duplicate and forged headers from public and internal paths.
- Test unauthenticated TLS, invalid chains, proxy bypass, cache reuse, and rotation.
- Confirm all alternative ingress paths enforce the same sanitization.

## Gotchas
The header conveys the certificate presented at the originating client-to-proxy connection, not proof of every downstream hop. RFC 9440 is informational and deployment trust remains local policy.

## Official sources
- [RFC 9440](https://www.rfc-editor.org/rfc/rfc9440.html)
