# SMTP enhanced status-code handling

**Issue:** A sender classifies delivery only by three-digit SMTP replies, losing structured cause information and retrying permanent failures or suppressing temporary ones.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 3463 enhanced status codes use `class.subject.detail` semantics. Preserve the original reply and enhanced code, but make retry and suppression decisions through an explicit, versioned policy because remote systems can omit or misuse codes.

**Sources:** [RFC 3463](https://www.rfc-editor.org/rfc/rfc3463) · [RFC 5248 status-code registry](https://www.rfc-editor.org/rfc/rfc5248)

## Controls

- parse an enhanced code only in the syntax/context where SMTP permits it;
- distinguish success (2), persistent transient failure (4), and permanent failure (5);
- retain subject/detail for observability without exposing recipient addresses in broad logs;
- cap retries by message age and attempt count, with jittered backoff;
- require corroborating signals before global suppression when a provider emits contradictory text or codes.

## Verification

- fixtures cover absent, malformed, contradictory, and unknown registered codes;
- a transient mailbox/system failure stays retryable while an invalid address follows suppression policy;
- DSN ingestion and live SMTP responses normalize to the same internal schema;
- dashboards can separate remote policy, mailbox, routing, and content failures.

## Gotchas

- human-readable reply text is not a stable parser contract.
- enhanced codes refine but do not replace the SMTP reply class.
- one recipient's permanent failure must not cancel valid recipients in the same transaction.
