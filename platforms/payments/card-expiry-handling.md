# card-expiry-handling

**Issue:** Proactively handling expiring cards to prevent subscription payment failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cards expire at end of month — subscriptions billed after that date fail. Customers often do not notice until access is cut off, leading to churned subscriptions that could have been saved.

## Pattern / Solution
Query Stripe for subscriptions where the default_payment_method card exp_year/exp_month is within 60 days. Send expiry warning emails at 60, 30, and 7 days with a link to update the payment method. Use Stripe customer portal for self-serve updates.

## Gotchas
Account Updater may update the card before expiry — avoid duplicate emails by checking if the card is already updated. Stripe Sigma can query for expiring cards with SQL. Some issuers extend cards automatically.

## Related
account-updater-service, payment-method-backup, stripe-dunning-management, dunning-email-sequences
