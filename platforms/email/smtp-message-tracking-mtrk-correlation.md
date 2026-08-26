# SMTP MTRK message tracking and correlation

**Issue:** An operator needs to trace a transferred message but relies on recipient addresses, subject text, or log scraping across administrative domains.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; deployment support is limited

RFC 3885 defines the MTRK SMTP extension and a message-tracking service. Use it only when advertised and authorized, with opaque tracking identifiers and bounded retention. Tracking state is operational evidence, not proof that a person read a message.

**Sources:** [RFC 3885: SMTP Service Extension for Message Tracking](https://www.rfc-editor.org/rfc/rfc3885) · [RFC 3886: Message Tracking Query Protocol](https://www.rfc-editor.org/rfc/rfc3886)

## Controls

- issue MTRK parameters only after EHLO capability discovery;
- generate unguessable correlation material and separate it from internal database IDs;
- authenticate and authorize cross-domain queries as the protocol requires;
- retain only the minimum route/status data and expire it with message logs;
- rate-limit queries and redact addresses from broad observability.

## Verification

Test unsupported peers, malformed and expired identifiers, multi-recipient divergence, relays that do not preserve tracking, duplicate queries, unauthorized callers, and partial route history. Correlate results without regressing a final delivery state.

## Gotchas

Adoption is not universal. Tracking can expose communication metadata. SMTP acceptance or a tracking response is neither inbox placement nor an open/read receipt.
