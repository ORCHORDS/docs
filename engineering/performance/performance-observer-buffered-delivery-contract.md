# PerformanceObserver buffered delivery contract

**Issue:** Observers installed after page initialization can miss earlier entries. Mixing `entryTypes` with `type`/`buffered`, or registering overlapping observers, produces silent gaps or duplicate telemetry.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Register one ownership path per performance entry type. Where the specification supports it, observe a single `type` with `buffered: true` to receive entries already in the buffer, then deduplicate before export.

## Controls

- Check `PerformanceObserver.supportedEntryTypes`.
- Do not combine `entryTypes` with `type` or `buffered`; the initialization modes are distinct.
- Assign stable in-process deduplication keys appropriate to each entry type.
- Bound callback work and queue telemetry outside critical interaction paths.
- Use `takeRecords()` before disconnect when final buffered entries matter.
- Cap and sample exported entries.
- Redact resource names and user-linked context.
- Treat unsupported entry types as expected capability differences.

## Verification

Install observers before and after events, use buffered and live modes, reconnect, disconnect with pending entries, create multiple observers intentionally, and test unsupported types. Assert each logical entry exports once and callback work stays within budget.

## Gotchas

`buffered` requests entries retained by the user agent; it is not unlimited history. Buffer limits and entry support vary. Observer delivery is asynchronous, so page termination still needs an appropriate telemetry transport strategy.

## Sources

- [W3C Performance Timeline](https://www.w3.org/TR/performance-timeline/)
- [MDN PerformanceObserver.observe](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceObserver/observe)
