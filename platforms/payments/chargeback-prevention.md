# chargeback-prevention

**Issue:** Reducing chargebacks through proactive communication, verification, and friction at key moments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Chargeback rates above 1% trigger Stripe's monitoring program and risk account termination. Most chargebacks are preventable through better communication and verification.

## Pattern / Solution
Use Stripe Radar rules to block high-risk cards. Send clear receipt emails with merchant name matching statement descriptor. Enable 3DS for transactions above a threshold. For subscriptions, send 3-day advance renewal reminders. Make cancellation easy to reduce friendly fraud.

## Gotchas
Visa's monitoring threshold is 0.9% chargeback ratio or 100 chargebacks per month. Mastercard's is 1% and 100. Even winning a dispute costs fees. Merchants in high-risk categories face lower thresholds.

## Related
chargeback-response-process, stripe-radar-fraud-rules, receipt-email-template, stripe-3ds-authentication
