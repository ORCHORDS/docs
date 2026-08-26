# RFC 9204 QPACK Blocked-Stream Budget

**Issue:** QPACK dynamic-table references can improve compression but block HTTP/3 streams until insertions arrive, consuming memory and interacting with flow control.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Advertise bounded dynamic-table capacity and blocked-stream limits.
- Use acknowledged entries or literals for latency-sensitive fields when reordering risk is unacceptable.
- Reserve flow-control credit for QPACK encoder and decoder streams to avoid deadlock.
- Bound unacknowledged references and unsent instruction memory.

## Verification

- Reorder encoder instructions and field sections under loss.
- Exceed blocked-stream limits and confirm connection-error handling.
- Test zero-capacity and zero-blocked-stream configurations.

## Gotchas

- More compression can increase blocking risk.
- Blocked-stream count is only a proxy for actual memory.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9204.html
