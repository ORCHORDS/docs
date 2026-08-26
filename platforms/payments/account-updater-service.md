# account-updater-service

**Issue:** Automatically updating stored card details when cards are reissued or renewed by the bank
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cards expire or are reissued after fraud — stored payment methods become invalid, causing subscription failures. Manually contacting customers to update cards is inefficient.

## Pattern / Solution
Stripe's Account Updater automatically updates stored PaymentMethods when card networks share new card data with Stripe. Enable it in Dashboard settings. Monitor customer.updated webhooks where sources.data is modified. For non-Stripe vaults, use Visa Account Updater via your acquiring bank.

## Gotchas
Account Updater only works for cards stored as Stripe PaymentMethods — not raw card data. Updates are not real-time; they occur in batch weekly. Not all issuing banks participate. Always have a fallback flow for cards that cannot be updated automatically.

## Related
card-expiry-handling, payment-method-backup, stripe-failed-payment-retry
