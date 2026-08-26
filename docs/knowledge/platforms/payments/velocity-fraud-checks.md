# velocity-fraud-checks

**Issue:** Detecting and blocking velocity attacks where fraudsters test many cards rapidly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Attackers use automated scripts to test stolen card numbers against your checkout at high volume, resulting in many failed charges and Stripe flagging your account for excessive declines.

## Pattern / Solution
Implement server-side rate limiting per IP address (max 5 payment attempts per 10 minutes). Add CAPTCHA to checkout after 2 failures. Track failed attempts by email and device fingerprint. Block IPs with more than 10 failures in an hour. Alert on sudden spikes in decline rate.

## Gotchas
Stripe charges for failed card authentication attempts. High decline rates can trigger Stripe account reviews. Mobile users frequently share IPs via carrier NAT — use device fingerprinting, not just IP, to avoid false positives.

## Related
card-testing-attack-prevention, fraud-detection-signals, stripe-radar-fraud-rules
