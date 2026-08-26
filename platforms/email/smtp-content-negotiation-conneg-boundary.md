# SMTP CONNEG content-negotiation boundary

**Issue:** A sender assumes a recipient can render a specialized media format, or treats SMTP content negotiation as license to transform signed content invisibly.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined for specialized deployments; support is limited

RFC 4141 defines SMTP/ESMTP content negotiation using recipient capabilities. Use it only when advertised and preserve per-recipient outcomes, original content, signatures, and downgrade policy.

**Source:** [RFC 4141: SMTP and MIME Extensions for Content Conversion](https://www.rfc-editor.org/rfc/rfc4141)

## Controls

- negotiate only after capability advertisement;
- bind capability results to the exact recipient and transaction;
- allowlist transformations with explicit fidelity/security policy;
- retain the original or a recoverable source;
- avoid modifying encrypted or signed bodies unless the contract permits it;
- fall back or fail per recipient rather than weakening all recipients.

## Verification

Test unsupported peers, mixed recipient capabilities, no acceptable format, conversion failure, size expansion, signed/encrypted MIME, retries, and DSNs. Validate converted MIME structure and accessibility.

## Gotchas

Negotiation is not proof a human can perceive the content. Gateway behavior and support are uncommon. Conversion can invalidate signatures, lose semantics, or expose content.
