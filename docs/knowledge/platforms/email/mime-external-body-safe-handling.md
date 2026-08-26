# MIME external-body safe handling

**Issue:** A `message/external-body` part is a reference to content that is not carried in the message. Automatically resolving it turns untrusted email into a network or local-resource request chosen by the sender. RFC 2046 also gives the format unusual nested-header, access-type, expiration, and transfer-encoding rules, so treating it like an ordinary attachment creates security and interoperability failures.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls

1. Disable automatic retrieval by default. Require an explicit user action after displaying the scheme, host, object name, expiry, and resulting data type.
2. Reject or quarantine access types outside a documented allowlist. Never implement `local-file`, TFTP, FTP, or mail-server retrieval merely because a parser recognizes the token.
3. Apply SSRF defenses to any network-backed resolver: deny loopback, link-local, private, metadata, and organization-internal ranges; resolve DNS again at connection time; limit redirects; and bind the connected address to the validated result.
4. Run retrieval in an isolated service with no ambient credentials, local filesystem access, cookies, or corporate proxy authority. Limit bytes, redirects, wall time, decompressed size, and media type.
5. Treat the sender-supplied Content-ID, expiration, size, permission, and inner media headers as claims, not authorization or integrity proof.

## Implementation contract

Parse the outer MIME entity without fetching. RFC 2046 requires `access-type`; the encapsulated headers must include Content-ID, and the external-body entity itself uses 7bit transfer encoding. Preserve outer and inner fields separately before applying the RFC merge rules. Normalize the access type case-insensitively but retain its original value for audit.

Represent resolution as an explicit state machine: unreviewed, blocked, approved, fetching, verified, failed, expired. Bind approval to the exact normalized reference and message identity; a changed redirect target or DNS answer requires revalidation. Store fetched bytes as a new untrusted artifact with its own scanner verdict and content hash, never as if they arrived authenticated inside the email.

## Verification

- Feed missing access-type, missing inner Content-ID, prohibited 8bit/binary encoding, malformed nested headers, and expired references; each must fail closed without network activity.
- Exercise DNS rebinding, redirects to private addresses, oversized/chunked responses, decompression bombs, slow responses, and type confusion.
- Confirm previewing or indexing a mailbox makes zero resolver calls.
- Confirm approvals cannot be replayed for another message or a mutated reference and that audit records include message ID, normalized destination, connected IP, limits, hash, and verdict.

## Gotchas

A signed email authenticates the reference text, not the remotely retrieved bytes. Remote content can change after signing, expire, observe the recipient, or return user-specific data. `multipart/alternative` may offer several external access methods; selecting a “preferred” part must not bypass the same policy. Legacy access types are standards-defined, not automatically safe or appropriate for modern clients.

## Sources

- RFC Editor, [RFC 2046 — MIME media types, section 5.2.3](https://www.rfc-editor.org/rfc/rfc2046.html#section-5.2.3)
- RFC Editor, [RFC 4289 — MIME registration procedures](https://www.rfc-editor.org/rfc/rfc4289.html)
