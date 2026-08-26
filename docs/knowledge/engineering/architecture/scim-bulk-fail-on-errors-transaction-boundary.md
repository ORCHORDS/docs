# SCIM Bulk failOnErrors Transaction Boundary

**Issue:** SCIM bulk provisioning is not defined as an all-or-nothing transaction. Assuming atomic behavior can leave identity state partially applied after errors.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Treat every BulkRequest operation as independently reportable and correlate responses with bulkId or operation order.
- Honor failOnErrors as a processing-stop threshold, not a rollback promise.
- Design create/update/delete operations for safe retry and reconcile final resource state after partial completion.
- Cap operations and payload size and authorize every target operation independently.

## Verification

- Inject failures before and after the failOnErrors threshold and verify already-completed operations remain visible.
- Test bulkId references, duplicate retries, reordered responses, and per-operation authorization failures.
- Run reconciliation after network interruption with an unknown completion point.

## Gotchas

- HTTP success for the bulk envelope does not mean every operation succeeded.
- Do not expose one operation’s sensitive error detail to an unauthorized bulk caller.

## Official sources

- https://www.rfc-editor.org/rfc/rfc7644.html#section-3.7
