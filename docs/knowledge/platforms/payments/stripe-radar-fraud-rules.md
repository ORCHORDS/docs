# stripe-radar-fraud-rules

**Issue:** Configuring Stripe Radar rules to block fraudulent payments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Stripe Radar uses ML to score each payment. Custom rules let you block, review, or allow payments based on risk signals, customer metadata, or velocity.

## Pattern / Solution
Dashboard > Radar > Rules. Example rules in Stripe's rule language:

```
# Block if risk score is very high
Block if :risk_score: > 85

# Block payments from specific countries
Block if :card_country: = 'XX'

# Review if new card and high amount
Review if :is_new_card: = true and :amount_in_usd: > 500

# Block specific BINs associated with fraud
Block if :card_bin: in ('123456', '234567')

# Allow trusted customers
Allow if :metadata:trusted_customer: = 'true'
```

Set metadata on PaymentIntent: `metadata: { trusted_customer: 'true' }`.

## Gotchas
- Rules are evaluated in order; put `Allow` rules before `Block` rules for the same condition
- Radar for Fraud Teams unlocks custom rules; the free tier only has Stripe-managed rules
- Blocking a card does not refund the customer — handle separately
- Test with Stripe's test card numbers in test mode before deploying rules to production

## Related
- `stripe-3ds-authentication.md`
- `fraud-detection-signals.md`
- `card-testing-attack-prevention.md`
