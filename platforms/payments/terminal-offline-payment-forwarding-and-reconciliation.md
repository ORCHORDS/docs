# Stripe Terminal offline payment forwarding and reconciliation

**Issue:** A point-of-sale application marks an offline card interaction as settled even though it has only been stored locally and will be forwarded later.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

Offline acceptance is an operational state, not proof of settlement. Stripe Terminal can store offline payments on a supported POS device and automatically forward them when connectivity returns. Only cards are supported offline; server-driven Terminal integrations do not support offline card collection.

**Sources:**

- [Stripe Terminal offline mode](https://docs.stripe.com/terminal/fleet/offline-mode)
- [Stripe Terminal integration setup](https://docs.stripe.com/terminal/payments/setup-integration)
- [Terminal payment methods](https://docs.stripe.com/terminal/payments/additional-payment-methods)

## State model

`presented → offline_accepted_locally → forwarding → provider_confirmed | provider_failed → reconciliation`

Persist a local transaction identifier, reader/location, amount, currency, operator, and state transition history. Do not fulfil irreversible goods or represent a payment as settled solely from the local acceptance state.

## Controls

- enable offline mode only for approved locations and payment methods;
- make local limits, operator fallback, receipts, and customer messaging explicit;
- observe forwarding age and unresolved local payments after connectivity returns;
- reconcile provider-confirmed events idempotently to the original order;
- handle failed forwarding with a documented recovery and customer-contact path;
- test configuration rollout: reader offline-mode changes can take up to ten minutes.

## Verification

- disconnect/reconnect testing proves one local acceptance maps to one eventual order update;
- duplicate local sends and app restarts do not create duplicate fulfilment;
- a payment that never reaches provider confirmation remains operationally visible;
- dashboards separate local acceptance, forwarding backlog, confirmation, and failure.

## Related

- `payments/stripe-payment-intents.md`
- `payments/payment-reconciliation.md`
- `payments/incremental-authorizations-and-capture-deadlines.md`
