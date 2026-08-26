# nowpayments-minimum-amount-and-quote-preflight

**Issue:** A checkout creates a NOWPayments payment before verifying that the requested asset pair and amount meet the current minimum.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Minimum payment amounts are dynamic and pair-specific. A price that was payable earlier can become too small after network conditions or the payment pair changes. Creating an unusable payment first produces failed deposits and support cases rather than a clear pre-check.

**Source:** [NOWPayments — minimum payment amount](https://nowpayments.zendesk.com/hc/en-us/articles/27407237685917-Minimum-payment-amount).

## Fix

- obtain the current minimum for the exact pay/outcome pair before creating a payment or invoice;
- calculate using decimal-safe units and the provider’s required precision;
- bind the quoted pair, amount, rate mode, and preflight timestamp to the payment intent;
- refresh short-lived preflight data rather than treating a cached minimum as permanent;
- present a clear alternative asset or amount before the customer transfers funds;
- treat a deposit below the minimum as an exception, never as successful payment.

## Verification

- A request below the current minimum is rejected before provider payment creation.
- A valid pair at the documented precision creates successfully.
- A changed minimum after quote expiry requires a refreshed confirmation.
- Tests cover fixed and floating rate modes when used.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/nowpayments-exception-reconciliation-and-refunds.md`
