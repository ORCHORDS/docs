# Stripe Payment-Method Domain Registration Governance

**Issue:** Wallet and accelerated payment methods can fail or appear on unintended hosts when production, preview, tenant, and embedded checkout domains are registered inconsistently.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Inventory every top-level and embedded host that renders Stripe payment-method UI. Register only approved HTTPS domains through Stripe's payment-method-domain workflow/API and separate test from live-mode registration. Treat domain addition as a reviewed deployment change with owner, environment, certificate readiness, and removal date for previews.

Normalize hostnames and reject arbitrary tenant/customer input. Wildcard assumptions are unsafe: register the exact hosts required by the current Stripe method. Keep DNS, TLS, CSP, frame-ancestor policy, Connect account context, and Stripe account ownership aligned. Remove retired preview/custom domains promptly.

At runtime, degrade gracefully when a wallet is unavailable and retain a supported alternate payment path. Domain registration affects eligibility/presentation, not payment authorization.

## Verification

Test apex/subdomain, www redirect, preview host, custom tenant domain, embedded iframe/top-level combinations, test/live modes, expired certificate, wrong Stripe account, DNS cutover, method unavailable, and deregistration. Use browser/payment-method diagnostics without exposing keys.

## Gotchas

A domain that loads Stripe.js is not necessarily registered for every method. Registration can be account/context specific. Do not automate registration for unverified user-controlled domains.

## Sources

- [Stripe payment method domains](https://docs.stripe.com/payments/payment-methods/pmd-registration)
- [Stripe Payment Method Domains API](https://docs.stripe.com/api/payment_method_domains)
- [Stripe payment methods](https://docs.stripe.com/payments/payment-methods)
