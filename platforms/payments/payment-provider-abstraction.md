# payment-provider-abstraction

**Issue:** Building a provider-agnostic payment layer to switch processors without full rewrites
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Coupling business logic directly to Stripe SDK methods makes switching providers expensive. Tax handling, webhook verification, and refund flows all differ between providers.

## Pattern / Solution
Define an IPaymentProvider interface with methods: createCustomer, createSubscription, cancelSubscription, createCheckout, handleWebhook, issueRefund. Implement concrete adapters per provider. Keep domain events separate from provider events.

## Gotchas
Lowest-common-denominator abstraction loses provider-specific features. Use the adapter pattern but expose escape hatches for provider-specific calls. Test each adapter against sandbox environments.

## Related
stripe-setup-workers, paddle-integration, lemonsqueezy-integration
