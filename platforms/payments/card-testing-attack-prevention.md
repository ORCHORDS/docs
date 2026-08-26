# card-testing-attack-prevention

**Issue:** Stopping automated card testing attacks that probe your checkout with stolen card numbers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Card testing attacks use bots to submit hundreds of small transactions to determine which stolen card numbers are valid. This results in chargebacks, elevated decline rates, and potential Stripe account termination.

## Pattern / Solution
Never allow zero-dollar authorization charges. Implement CAPTCHA on checkout. Add exponential backoff after payment failures. Use Stripe Radar to block cards from high-risk BIN ranges. Monitor for sudden spikes in payment attempts.

## Gotchas
Some fraudsters use human farms to bypass CAPTCHA. Monitor the failed_charge_volume metric in Stripe Sigma. If attacked, temporarily add a mandatory 3DS challenge for all transactions. Report sustained attacks to Stripe support.

## Related
velocity-fraud-checks, fraud-detection-signals, stripe-radar-fraud-rules, stripe-3ds-authentication
