# Stripe Connect embedded-component access control

**Issue:** A platform renders Stripe Connect embedded components without constraining account context or features, exposing operations beyond the platform user's role.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Connect embedded components run in Stripe-hosted UI but the platform still controls which connected account and component features a user may access. Create account sessions server-side only after domain authorization.

**Source:** [Stripe Connect embedded components](https://docs.stripe.com/connect/get-started-connect-embedded-components)

## Controls

- authorize platform user, tenant, and connected-account relationship before session creation;
- enable only required components/features;
- keep client secrets short-lived, client-side only where documented, and out of logs;
- regenerate after account/role changes;
- enforce financial operations through server/webhook reconciliation;
- audit component access and sensitive configuration changes.

## Verification

Test wrong tenant/account, expired/replayed secret, role downgrade, concurrent tabs, disabled capability, account closure, webhook delay, and CSP/network failure. UI visibility must match backend authorization.

## Gotchas

Stripe-hosted UI is not a substitute for platform authorization. A client secret must not be persisted as an API credential. Component completion is not final settlement state.
