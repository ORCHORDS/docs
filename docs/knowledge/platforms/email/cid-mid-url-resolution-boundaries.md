# CID and MID URL resolution boundaries

**Issue:** HTML email commonly embeds a `cid:` URL that refers to a MIME body part, while `mid:` can identify a message or a body part within a message. RFC 2392 defines precise identifier encoding and selection behavior. Treating these identifiers as ordinary web URLs, matching them loosely, or resolving them across tenants can leak message content, display the wrong alternative, and create script or cache-confusion paths.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls

1. Resolve `cid:` within the current message context by default. Do not query a global body-part store solely by Content-ID.
2. For the long `mid:message-id/content-id` form, require authorization to the named message before resolving its part. Scope caches by tenant, mailbox, message, and selected MIME alternative.
3. Percent-decode exactly once according to the URL syntax, then compare the resulting addr-spec to the parsed Message-ID or Content-ID value without angle brackets. Reject malformed escapes and control characters.
4. Apply the containing MIME entity's selection rules. Duplicate Content-IDs can occur within `multipart/alternative`; do not pick the first global match.
5. Serve resolved bodies through a constrained attachment origin with declared/verified media type, nosniff policy, content-security restrictions, size limits, and active-content blocking.

## Implementation

Parse MIME and build a per-message index from canonical identifier to all candidate parts plus their ancestry. Resolution receives the referring part and selected alternative context, not just a string key. A bare `cid:` lookup must remain within that message. A `mid:` lookup first resolves the message under mailbox authorization, then selects a body part using the MIME tree.

Keep URL decoding separate from header parsing. Header angle brackets are syntax and are not part of the URL addr-spec. Percent encoding is required for characters that are not allowed in a URL, including the slash used as the long-form separator. Do not lowercase an entire identifier: domain comparison may be normalized where appropriate, but local-part semantics and stored identifiers should remain exact.

## Verification

- Test encoded reserved characters, malformed and double encoding, mixed-case domains, missing angle brackets, duplicate identifiers, and the long MID form.
- Construct `multipart/alternative` parts with the same Content-ID and prove the chosen representation follows the selected alternative.
- Attempt cross-mailbox and cross-tenant resolution with a known identifier; return no existence signal.
- Verify SVG, HTML, and mislabeled executable bodies cannot gain an active same-origin rendering context.
- Confirm cache keys include authorization and message context and are purged with the message.

## Gotchas

Content-ID is intended to be globally unique, but RFC 2392 explicitly accommodates duplicates in limited multipart contexts. Uniqueness is not authorization. A `cid:` reference also does not fetch the public web, so routing it through a generic URL client expands the attack surface unnecessarily. Rewriting HTML must preserve the mapping without exposing internal storage identifiers.

## Sources

- RFC Editor, [RFC 2392 — Content-ID and Message-ID URLs](https://www.rfc-editor.org/rfc/rfc2392.html)
- RFC Editor, [RFC 2046 — MIME media types](https://www.rfc-editor.org/rfc/rfc2046.html)
