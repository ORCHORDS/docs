# tokenization-vault-patterns

**Issue:** Storing payment method tokens securely when you need to reuse payment methods
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subscription and reuse scenarios require storing a reference to a customer's payment method. Storing raw card data is prohibited; tokens from payment processors must be stored and protected correctly.

## Pattern / Solution
Store Stripe PaymentMethod IDs and Customer IDs in your database — these are opaque references, not sensitive data themselves. Encrypt them at rest using AES-256 with a key stored in a KMS such as AWS KMS. Never store CVV under any circumstances.

## Gotchas
Stripe tokens are not cross-processor — they are useless if you switch payment processors. For processor migration, use a network tokenization provider. Do not expose PaymentMethod IDs in client-side JS or URLs.

## Related
pci-dss-scope-reduction, pci-dss-saq-a-compliance, payment-data-retention
