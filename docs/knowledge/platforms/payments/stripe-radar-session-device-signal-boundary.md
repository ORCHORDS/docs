# Stripe Radar Session device-signal boundary

**Issue:** A checkout creates or reuses Radar Sessions incorrectly, weakening device-signal association or turning a fraud signal into a tracking identifier.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe Radar Sessions collect browser/device signals for eligible fraud evaluation. Create them in the intended client flow, bind the resulting identifier to the correct server-side payment operation, and treat it as one risk input.

**Source:** [Stripe Radar Sessions API](https://docs.stripe.com/api/radar/session)

## Controls

- create a fresh session at the documented point in checkout;
- transmit its identifier to the server over the authenticated operation;
- prevent cross-customer/cart reuse;
- keep secret keys server-side and follow Stripe.js collection requirements;
- minimize retention and disclose processing appropriately;
- keep authorization and business rules independent of the signal.

## Verification

Test abandoned/restarted checkout, duplicate submit, multiple tabs, account switch, blocked scripts, unsupported client, delayed payment, and webhook reconciliation. Confirm one user's session cannot attach to another payment.

## Gotchas

A Radar Session does not approve or authenticate a payment. Availability depends on integration/product settings. Excessive reuse reduces contextual integrity and may increase privacy risk.
