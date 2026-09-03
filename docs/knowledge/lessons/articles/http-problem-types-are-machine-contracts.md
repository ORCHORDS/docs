# HTTP Problem Types Are Machine Contracts

**Issue:** Clients are forced to branch on free-form error text, so wording changes break automation even when the underlying API behavior did not change.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

RFC 9457 gives HTTP APIs a machine-readable problem-details format. The durable contract is the problem `type`, not the prose in `detail`. A stable problem type lets clients react to a known condition without parsing human language.

## Engineering rule

- Return `application/problem+json` when problem details are the selected error representation.
- Give each reusable problem class a stable `type` URI under a controlled namespace.
- Document the type, short title, and intended HTTP status.
- Put machine-consumable fields in defined extensions instead of encoding state in prose.
- Treat changes to a published problem type's semantics as an API compatibility change.

## Verification

- Change the human-readable `detail` text and confirm clients still behave correctly.
- Confirm clients branch on `type` or defined extension fields, never substrings in `detail`.
- Verify type documentation remains resolvable and describes remediation.

## Official source

- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
