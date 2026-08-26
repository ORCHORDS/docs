# Stripe Connect controller-property governance

**Issue:** A platform creates connected accounts without understanding controller properties, leaving Stripe/platform responsibility for fees, losses, requirements, dashboard access, and collection inconsistent.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Connect controller properties describe operational responsibility and account experience. Treat them as an immutable-or-constrained onboarding architecture decision, not a cosmetic account type label.

**Source:** [Stripe Connect controller properties](https://docs.stripe.com/connect/accounts-v2/controller-properties)

## Controls

- decide liability, requirement collection, dashboard access, and fee responsibility before creation;
- store the resulting Stripe account/controller configuration;
- gate platform UI and operations from authoritative capabilities;
- review migration support before changing account architecture;
- align agreements, support, compliance, and webhook routing;
- test live/test environments separately.

## Verification

Test each supported controller configuration, missing requirements, capability loss, dashboard access, refunds/disputes, negative balance, account closure, and webhook account context.

## Gotchas

Controller choices affect legal and financial responsibility. Similar UI does not mean equivalent liability. Some properties cannot be freely changed after account creation.
