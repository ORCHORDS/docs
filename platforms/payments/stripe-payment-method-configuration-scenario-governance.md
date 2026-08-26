# Stripe payment-method configuration scenario governance

**Issue:** A single global payment-method setting rarely fits every checkout: one-time sales, subscriptions, product restrictions, regions, and connected-account contexts can have different eligibility and risk constraints. Unreviewed configuration edits can alter customer-facing options without an application deploy.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Design approach

Use a named payment-method configuration for a stable checkout scenario and select that configuration explicitly in the supported Checkout, Payment Element, PaymentIntent, or mobile payment-sheet integration. Configurations define broader scenario policy; use transaction-level exclusions only for documented exceptions.

## Controls

- Model scenarios from business and regulatory requirements: purchase type, currency, customer location, connected account, fulfillment, and refund/capture capabilities.
- Give configurations durable, human-readable names and maintain a mapping from product flow to configuration ID outside customer-visible data.
- Require approval and test evidence before toggling a method on or off in Dashboard or API; a dashboard-only change is still production behavior.
- Test availability with representative amount, currency, country, device, and wallet states. Enabled methods are still filtered for compatibility and may be ranked dynamically.
- Do not assume a method appears because it is enabled; instrument the offered-method set and successful completion by scenario.
- Prefer a configuration change for a durable policy difference. Use per-transaction exclusions only when they cannot create an unsupported or misleading combination.
- Document wallet behavior separately: some wallets cannot be excluded through the generic per-transaction exclusion parameter.

## Release checklist

1. Name the scenario, owner, expected payment methods, and eligibility constraints.
2. Validate the exact integration passes the intended configuration.
3. Test customer-visible availability and a successful payment/refund path.
4. Monitor conversion, authorization failures, and method mix after rollout.
5. Keep a fast reversal plan that restores the last known-good configuration.

## Sources

- [Stripe — Payment method configurations](https://docs.stripe.com/payments/payment-method-configurations)
- [Stripe — Dynamic payment methods](https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods)

## Tags

`payments` `stripe` `checkout` `payment-methods` `governance`
