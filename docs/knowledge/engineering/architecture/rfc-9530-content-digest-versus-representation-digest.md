# RFC 9530 Content-Digest Versus Repr-Digest

**Issue:** HTTP integrity checks fail when implementations hash encoded message content while peers expect the selected representation data, or continue using obsolete Digest fields.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `Content-Digest` for conveyed message content and `Repr-Digest` for representation data; document which transformation boundary each protects.
- Use the structured-field syntax and supported algorithm registry rather than the obsolete `Digest` and `Want-Digest` fields.
- Honor `Want-Content-Digest` and `Want-Repr-Digest` preferences only for algorithms the endpoint safely supports.
- Verify digests before acting on content and define behavior for missing, unsupported, malformed, or mismatching values.
- Combine digest fields with TLS or authenticated signatures when protection against malicious substitution is required.

## Verification

- Change content encoding while holding representation constant and verify the two digest meanings remain distinct.
- Test valid, malformed, duplicated, unsupported, downgraded, removed, and substituted digest fields.
- Exercise intermediaries that transform content and confirm policy detects unexpected modifications.

## Gotchas

- Confirm the cited feature or standard edition remains current before relying on it.
- Keep secrets, personal data, and restricted evidence out of examples and logs.
- Reassess after scope, implementation, or policy changes.

## Sources

- https://www.rfc-editor.org/rfc/rfc9530.html
