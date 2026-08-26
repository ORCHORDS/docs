# Apply JSON Patch as One Atomic Document Operation

**Issue:** RFC 6902 operations are sequential and later paths observe earlier mutations. A failed operation means the patch must not be treated as partially successful.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Validate media type, operation schema, JSON Pointer paths, and resource limits before application.
- Apply on an isolated candidate document and commit only if every operation succeeds.
- Authorize the resulting state and sensitive paths, not merely the initial request.
- Use `test` for explicit preconditions while retaining a resource-version concurrency control.
- Define array-index and missing-member policy exactly as the RFC.

## Verification
- Fail each operation position and assert stored state is unchanged.
- Test move into descendants, array index shifts, escaped pointers, duplicate object names at parse boundary, and stale versions.
- Compare candidate result to schema and authorization policy before commit.

## Gotchas
JSON Patch atomicity at the document layer does not provide database transaction isolation. A successful `test` can race without versioning.

## Official sources
- [RFC 6902](https://www.rfc-editor.org/rfc/rfc6902.html)
- [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901.html)
