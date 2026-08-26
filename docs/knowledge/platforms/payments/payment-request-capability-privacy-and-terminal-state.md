# Payment Request capability privacy and terminal state

**Issue:** Checkout treats canMakePayment as proof that a user is enrolled, invokes show outside a direct gesture, or retries the same PaymentRequest object after abort or completion. Browsers reject the call, capability checks become a fingerprinting signal, and orders can remain pending after the sheet closes.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published with browser capability gating

## Problem and applicability

The Payment Request API coordinates browser payment UI and returns method-specific payment details. It does not process funds. Its capability query and request lifecycle are deliberately constrained for privacy and user control.

Use it as progressive enhancement over a complete checkout fallback. Keep pricing, authorization, fulfilment, and reconciliation on the server.

## Controls and implementation

1. Construct the request from server-issued cart identity and display totals that the server can re-derive. Validate currency, amount, shipping, and method data before showing UI.
2. Invoke show from the user action expected by the current browser. Keep only one interactive payment sheet active and disable duplicate checkout triggers while it is pending.
3. Use canMakePayment only as a coarse optional capability hint. Cache it briefly at most, do not call it across many method combinations, and never use it to infer identity, wealth, installed apps, or a specific enrolled instrument.
4. Handle false, rejection, rate limiting, absence, and privacy-preserving answers identically from a user-access perspective: show the ordinary payment-method fallback.
5. Model each PaymentRequest instance as single-use. After show, abort, rejection, or response completion, create a fresh instance for a new logical attempt with fresh server state.
6. On PaymentResponse, send the method response and checkout identifier to the backend under one idempotency key. Await the authoritative provider result before declaring success.
7. Call response.complete with the outcome at the appropriate point so the browser can dismiss its UI. Put a bounded timeout and cancellation path around the backend call; reconcile any ambiguous provider outcome separately.
8. Use request.abort only when the application genuinely invalidates the attempt, and handle failure if the user agent cannot abort at that moment.
9. Redact method-specific tokens from logs and analytics. Record lifecycle state and sanitized provider identifiers instead.

## Verification

Test unsupported API, canMakePayment true/false/rejection/rate limit, show without activation, two simultaneous requests, user cancellation, abort before and during interaction, shipping updates, invalid details, backend timeout, provider success/decline, complete success/fail/unknown, and attempted object reuse.

Assert every terminal UI path maps to a recorded order-attempt state, ambiguous calls are reconciled idempotently, and capability probing never removes the accessible fallback.

## Gotchas

- canMakePayment does not mean the user has a usable credential or sufficient funds.
- Sheet acceptance is not authorization or settlement.
- Browser privacy rules can intentionally reduce the precision or frequency of capability answers.
- Method-specific payloads require their provider's independent validation.

## Official sources

- [W3C — Payment Request API](https://www.w3.org/TR/payment-request/)
- [W3C — Payment Method Identifiers](https://www.w3.org/TR/payment-method-id/)
