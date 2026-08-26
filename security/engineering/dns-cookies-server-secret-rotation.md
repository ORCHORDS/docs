# Deploy DNS Cookies with Interoperable Server-Secret Rotation

**Issue:** DNS Cookies provide limited off-path spoofing and amplification resistance, but inconsistent server-cookie derivation or abrupt secret rotation can break clients across an anycast fleet.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Implement DNS Cookies according to RFC 7873 as updated by RFC 9018, including the standardized interoperable server-cookie construction.
- Distribute secret versions consistently across anycast nodes and rotate with an overlap window that accepts the previous secret.
- Generate client cookies using privacy-preserving inputs and avoid stable cross-network identifiers.
- Rate-limit and size-limit responses that lack a valid server cookie according to the authoritative service's threat model.
- Monitor valid, invalid, missing, and stale-cookie outcomes by node and transport.
- Keep DNSSEC and transport security controls separate; cookies do not authenticate DNS data.

## Verification

- Run clients across different anycast nodes before, during, and after secret rotation.
- Test NAT rebinding, IPv4/IPv6, malformed COOKIE options, stale cookies, and spoofed-source queries.
- Compare amplification factors for missing and validated cookies.
- Verify multiple DNS implementations produce and accept interoperable cookies for the selected method.

## Gotchas

DNS Cookies are a lightweight transaction mechanism with limited protection against off-path attackers. They do not stop on-path modification, replace DNSSEC, or justify large unauthenticated answers.

## Official sources

- [RFC 7873: Domain Name System Cookies](https://www.rfc-editor.org/rfc/rfc7873.html)
- [RFC 9018: Interoperable DNS Server Cookies](https://www.rfc-editor.org/rfc/rfc9018.html)
