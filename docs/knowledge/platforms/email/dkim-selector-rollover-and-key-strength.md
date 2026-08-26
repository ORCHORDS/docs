# DKIM Selector Rollover and Key Strength

**Issue:** Replacing a DKIM key in place can make in-flight mail unverifiable, while weak or leaked keys let attackers forge authenticated mail.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Generate a new private key and a new selector; never overwrite the active selector. Publish the new TXT record, wait for authoritative DNS and resolver visibility, then switch signers to the new selector. Keep the old public key published for at least the maximum message transit/queue time plus DNS caching margin, then revoke or remove it under a recorded change.

Use rsa-sha256, never rsa-sha1. RFC 8301 requires at least 1024-bit RSA signing keys and recommends at least 2048 bits; choose a size compatible with DNS publication and receivers. Restrict private-key access to the signer identity, keep it out of source/logs/backups not designed for secrets, and inventory selector owner, creation, activation, and retirement.

## Verification

Before cutover, query every authoritative server and independent recursive resolvers, reconstruct split TXT strings, and validate sample signatures. During overlap, sign test mail with old and new selectors and verify through representative receivers. Exercise rollback, DNS failure, signer restart, clock skew, and delayed mail. Monitor DKIM pass rate by selector.

## Gotchas

DNS TTL is not the only cache lifetime and queued mail can outlive a normal TTL. Removing the old record immediately breaks verification. DKIM authenticates a signing domain and content integrity; it does not prove message safety.

## Sources

- [RFC 6376: DKIM Signatures](https://www.rfc-editor.org/rfc/rfc6376.html)
- [RFC 8301: DKIM cryptographic update](https://www.rfc-editor.org/rfc/rfc8301.html)
