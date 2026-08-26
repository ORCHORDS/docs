# security.txt RFC 9116 publication lifecycle

**Issue:** Researchers cannot find a current private reporting channel, or an expired security.txt points to an abandoned mailbox.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Publish `/.well-known/security.txt` over HTTPS following RFC 9116. Include current Contact and Expires; add Policy, Encryption, Acknowledgments, Hiring, and Canonical where appropriate. Monitor mailbox delivery and on-call ownership. Keep expiry short enough to force review. Sign only when key lifecycle is operational.

## Verification

Fetch from external networks; validate content type, redirects, canonical URL, expiry, PGP signature if used, and response ownership. Send a harmless test report and measure acknowledgement.

## Gotchas

security.txt is discovery, not an authorization to test. It must not expose internal contacts or secrets. A valid file does not replace coordinated-disclosure procedures.

## Sources

- [RFC 9116](https://www.rfc-editor.org/info/rfc9116/)
