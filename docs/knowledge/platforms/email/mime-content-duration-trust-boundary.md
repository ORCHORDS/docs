# MIME Content-Duration trust boundary

**Issue:** `Content-Duration` exposes a sender-declared duration for time-varying MIME media without decoding the attachment. RFC 3803 makes it convenient for inbox listings and voice-message interfaces, but explicitly does not make it an authoritative measurement. Using it for billing, resource allocation, upload limits, moderation, or playback bounds lets an untrusted header control security-sensitive decisions.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls

1. Parse only the RFC grammar: one to ten ASCII digits representing seconds, with no sign, decimal, whitespace suffix, or unit. Reject values above 2,147,483,647.
2. Store the declared duration separately from a duration measured by a trusted media parser. Label UI values derived from the header as estimates until media inspection completes.
3. Never use the declared value alone for quotas, transcoding reservations, billing, policy enforcement, or timeout selection. Bound processing from actual byte limits and trusted decoder metadata.
4. Apply the header to its associated MIME entity, not indiscriminately to the enclosing multipart message or every attachment.
5. Remove or recompute the field when transforming, clipping, concatenating, or transcoding media.

## Implementation

Use a strict integer parser rather than a language coercion routine that accepts exponent notation or prefixes. Preserve three fields: raw header, validated declared seconds, and measured seconds plus measurement method. If multiple Content-Duration fields occur on the same entity, treat the value as ambiguous and ignore it.

A background media-inspection job may reconcile the claim. Define product-specific tolerance only for display diagnostics; do not silently rewrite original message evidence. If decoding fails, retain “unknown” rather than trusting the claim. Keep measurement resource limits independent of the claimed duration so a tiny header cannot authorize unbounded work.

## Verification

- Accept `Content-Duration: 0`, `33`, and the RFC upper bound; reject negative, signed, decimal, exponent, unit-bearing, empty, duplicated, and over-bound values.
- Verify a declared 10-second header on a materially different media object cannot change quota, cost, or processing timeouts.
- Verify multipart messages associate each duration with the correct leaf entity.
- Verify transcode and trim paths recompute or remove stale values.
- Fuzz parsing without allocating based on the parsed number.

## Gotchas

The field measures seconds and carries no unit tag. Its presence does not prove the attachment is audio/video, decodable, complete, or safe. Authentication such as DKIM can show who signed the claim but does not make the duration exact. Client display rounding should be a presentation decision; retain integer seconds internally.

## Sources

- RFC Editor, [RFC 3803 — Content Duration MIME Header Definition](https://www.rfc-editor.org/rfc/rfc3803.html)
- RFC Editor, [RFC 2045 — MIME message body format](https://www.rfc-editor.org/rfc/rfc2045.html)
