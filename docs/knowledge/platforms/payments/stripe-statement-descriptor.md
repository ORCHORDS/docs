# stripe-statement-descriptor

**Issue:** Configuring statement descriptors so customers recognize charges on their bank statements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unrecognized charges are the primary cause of friendly-fraud chargebacks. The statement descriptor is the merchant name that appears on the customer's bank or credit card statement.

## Pattern / Solution
Set the account-level statement_descriptor in Stripe Dashboard settings (max 22 chars, no special characters except spaces and hyphens). For individual charges, use the statement_descriptor_suffix on the PaymentIntent to append a product or order reference. For card charges this appears as 'ACME* ANNUAL PLAN'. Keep it recognizable — use your brand name, not a legal entity name.

## Gotchas
Statement descriptor changes take effect immediately but existing charges are not retroactively updated. Different card networks display descriptors differently — test across Visa, Mastercard, and Amex. The suffix adds to the base descriptor; the combined length must not exceed 22 characters. Dynamic descriptors are not supported for ACH or bank transfer payments.

## Related
receipt-email-template, chargeback-prevention, stripe-payment-intents
