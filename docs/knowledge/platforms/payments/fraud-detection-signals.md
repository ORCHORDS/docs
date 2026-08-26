# fraud-detection-signals

**Issue:** Identifying fraudulent transactions using behavioral and payment signals before capture
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Card-not-present fraud is common for digital goods. Fraudsters use stolen card details. Losses occur at the point of dispute — by then the product has been delivered.

## Pattern / Solution
Evaluate risk signals before charging: Stripe Radar score, IP country vs billing country mismatch, velocity of new accounts from same IP, email domain (disposable providers), card BIN country mismatch. Use Stripe metadata to tag high-risk orders for manual review.

## Gotchas
Over-blocking legitimate customers costs revenue and trust. Calibrate thresholds using historical dispute data. Use Stripe Sigma to analyze your dispute patterns. Radar for Fraud Teams allows custom ML rules without code.

## Related
stripe-radar-fraud-rules, velocity-fraud-checks, card-testing-attack-prevention, stripe-3ds-authentication
