# DKIM body-length tag unsigned-tail risk

**Issue:** A DKIM signature with the optional `l=` body-length tag authenticates only a prefix. Content appended after that byte count is not covered even though signature verification can report success.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Omit `l=` for ordinary outbound mail and sign the complete canonicalized body. At verification and security-analysis boundaries, distinguish a cryptographically valid prefix from a fully covered message.

## Controls

- Configure organizational signers to avoid body-length limits by default.
- Sign security-relevant Content-Type and other required headers.
- Surface whether bytes exist beyond the signed length in forensic results.
- Treat unsigned trailing MIME or HTML content as suspicious.
- Do not “fix” mailing-list modification by weakening all outbound signatures.
- Test canonicalization at the actual post-transport bytes expected by verifiers.
- Keep DMARC alignment and other authentication results separate from content-safety decisions.
- Preserve raw evidence under controlled retention when investigating.

## Verification

Send plain text, HTML, multipart, empty-body, canonicalization-edge, footer-appended, MIME-boundary-altered, and deliberately unsigned-tail fixtures through the real pipeline. Verify full-body signing has no `l=` and policy distinguishes covered versus appended bytes.

## Gotchas

A DKIM PASS does not mean every body byte was signed when `l=` is present. A zero value signs none of the body. Mailing-list interoperability pressure does not remove the security risk.

## Sources

- [RFC 6376 DKIM body-length limits](https://www.rfc-editor.org/rfc/rfc6376.html#section-5.3.1)
- [RFC 6377 DKIM and mailing lists](https://www.rfc-editor.org/rfc/rfc6377.html)
