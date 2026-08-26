# EU Instant Payments Verification-of-Payee Evidence

**Issue:** Regulation (EU) 2024/886 introduces verification of payee for euro credit transfers and requires payer-facing handling of match results before authorization.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Classify covered payment service providers, currencies, channels, and application dates with counsel.
- Submit the required payee name and account identifier through the verification service before payer authorization.
- Present match, close-match, no-match, and unavailable outcomes without silently changing beneficiary data.
- Preserve payer choice, warning, timing, request/response, displayed result, and final authorization evidence.
- Align batch and non-consumer opt-out behavior with the exact regulatory conditions.
- Monitor latency and availability without bypassing the prescribed user decision.

## Verification
- Test exact, close, no match, unavailable, timeout, changed beneficiary, batch, and accessibility paths.
- Reconstruct a disputed transfer from verification evidence and UI version.
- Confirm the transfer is not prematurely authorized.

## Gotchas
Verification of payee reduces misdirection risk but does not authenticate the underlying invoice or remove payer fraud controls.

## Official sources
- [Regulation (EU) 2024/886](https://eur-lex.europa.eu/eli/reg/2024/886/oj/eng)
