# nowpayments-mass-payout-authorization-and-expiry

**Issue:** A NOWPayments payout batch is created or retried without a durable approval boundary, recipient controls, or expiry-aware handling of the provider authorization step.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Outbound payouts are materially different from inbound payments: they move funds to recipient-controlled addresses. Provider two-factor authorization and address/IP controls are helpful, but the merchant must still enforce recipient authorization, idempotency, segregation of duties, and a recovery process for expired or rejected approval.

**Source:** [NOWPayments — custody and mass payouts](https://nowpayments.zendesk.com/hc/en-us/articles/18313666110493-Custody-and-Mass-Payouts) and [integration guide](https://nowpayments.zendesk.com/hc/en-us/articles/21341613323421-NOWPayments-Integration-Guide).

## Fix

- create a server-side payout batch with immutable recipients, amounts, asset/network, and business authorization;
- use a stable idempotency key per batch and reject changes after approval;
- require least-privilege approval with an independent reviewer for material payouts;
- handle authorization expiry as a new explicit state requiring renewed approval, never an automatic retry;
- use recipient allowlists where appropriate and verify changes through a separate controlled process;
- reconcile provider payout outcomes to the local ledger and preserve non-sensitive audit evidence.

## Verification

- A duplicate batch request cannot create duplicate payouts — BUT only if the provider itself honors the idempotency key. If the provider doesn't support idempotency on batch payouts, persist an explicit unknown-outcome state after submission and require a provider-side history lookup that resolves the first submission before any retry. A stable local key alone is insufficient when the worker loses the response before persisting the provider batch ID.
- Changing a recipient or amount after approval is rejected.
- An expired authorization is not silently re-submitted.
- A disallowed recipient cannot pass the payout workflow.
- Provider and local payout states reconcile to one terminal outcome.

## Related

- `payments/nowpayments-callback-payment-intent-integrity.md`
- `patterns/idempotency-keys.md`
