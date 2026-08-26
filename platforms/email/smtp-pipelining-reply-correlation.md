# SMTP PIPELINING reply correlation

**Issue:** A mail client pipelines SMTP commands but matches replies by arrival timing instead of command order, corrupting recipient outcomes and retry decisions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

RFC 2920 allows clients to send command groups without waiting for each response after the server advertises PIPELINING. The server still replies in command order; maintain an ordered command ledger and consume every expected reply before deciding transaction state.

**Source:** [RFC 2920: SMTP Service Extension for Command Pipelining](https://www.rfc-editor.org/rfc/rfc2920)

## Controls

- pipeline only after EHLO advertises the extension;
- enqueue command type, recipient identity reference, and expected reply count before writing;
- correlate replies FIFO, including multiline replies;
- apply per-recipient RCPT results independently and send DATA only under a deliberate accepted-recipient policy;
- bound batch size, buffers, command length, and timeouts.

## Verification

- scripted servers reject an early RCPT while accepting later recipients;
- multiline and delayed replies remain correctly aligned;
- connection loss mid-group yields an ambiguous outcome that is retried idempotently, not assumed failed;
- fallback without PIPELINING produces equivalent delivery decisions.

## Gotchas

- PIPELINING improves round trips, not delivery semantics.
- do not pipeline commands that RFC 2920 forbids grouping in the chosen state.
- logging raw commands can expose addresses and authentication material.
