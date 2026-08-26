# MIME message/partial reassembly

**Issue:** `message/partial` can fragment a large message across several emails. Reassembling by loose identifiers or without limits enables cross-message splicing, memory exhaustion, and repeated processing.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Quarantine fragments, group by exact validated ID, require consistent total numbering, cap parts/bytes/time, and reassemble only when complete. Preserve raw fragments and authenticate/correlate their transport context. Parse the reconstructed message anew under normal MIME limits and deduplicate delivery.

## Verification

Test missing/duplicate/out-of-order parts, conflicting totals, reused IDs, oversized fragments, nested partials, timeout, mixed senders, and post-reassembly parser failures.

## Gotchas

Fragment headers do not authenticate common origin. Do not execute or render partial content before complete validation.

## Sources

- RFC Editor, [RFC 2046 section 5.2.2](https://www.rfc-editor.org/rfc/rfc2046.html#section-5.2.2)
