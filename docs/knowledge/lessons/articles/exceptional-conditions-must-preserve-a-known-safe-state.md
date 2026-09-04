# Exceptional Conditions Must Preserve a Known Safe State

**Issue:** Error handling reports failures, but the application may continue with partial state, weakened authorization, incomplete transactions, or an unknown execution path after the exceptional condition occurs.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP Top 10:2025 A10 focuses on preventing, detecting, and responding safely to abnormal conditions. Security depends on what state the application enters after the failure—not merely whether an exception was logged or a generic error page was displayed.

## Engineering rule

- Define the safe outcome for missing input, insufficient privilege, dependency failure, resource exhaustion, timeout, unexpected state, and other material exceptional conditions.
- Fail closed on security decisions rather than continuing when an authorization or validation dependency is uncertain.
- Keep transactions atomic or provide explicit compensation/reconciliation when a failure occurs partway through a state change.
- Handle failures close enough to the operation to preserve invariants instead of relying only on a top-level catch-all handler.
- Return controlled public errors while retaining useful protected diagnostic context internally.
- Test recovery state after faults instead of assuming a restart restores consistency.

## Verification

- Inject representative failures into security-sensitive and transactional flows and compare actual state with the documented safe result.
- Confirm privilege/authorization failures do not fall through to successful execution.
- Verify partial writes, reservations, payments, role changes, or other multi-step operations are rolled back or reconciled as designed.

## Official source

- OWASP Top 10:2025 A10 — Mishandling of Exceptional Conditions: https://owasp.org/Top10/2025/A10_2025-Mishandling_of_Exceptional_Conditions/
