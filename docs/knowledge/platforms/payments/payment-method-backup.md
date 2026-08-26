# payment-method-backup

**Issue:** Storing multiple payment methods per customer to retry failed payments on alternate cards
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A single stored payment method creates a single point of failure. Customers with a backup card can recover from a decline without manual intervention.

## Pattern / Solution
Allow customers to add multiple payment methods in the customer portal. Store a priority order. On invoice.payment_failed, if the default method failed, iterate through backup methods and attempt payment via POST /v1/invoices/{id}/pay with payment_method parameter. Update default on success.

## Gotchas
Stripe subscriptions have a single default_payment_method. Manual payment attempts via /pay do not trigger Smart Retries. Log each attempt separately. Notify the customer which card succeeded or if all backups failed.

## Related
account-updater-service, card-expiry-handling, stripe-failed-payment-retry, stripe-dunning-management
