# referral-credit-tracking

**Issue:** Tracking referral relationships and distributing credits when referees convert to paid
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Referral programs require linking referrer to referee at signup, tracking conversion events, and applying credits only after the referee makes a qualifying payment — not on signup alone.

## Pattern / Solution
Generate unique referral codes per user. On signup with a referral code, store referrer_id on the new user's record. On referee's first successful payment, trigger credit grant to referrer. Use Stripe Customer Balance to apply credit to next invoice. Set minimum qualifying payment thresholds.

## Gotchas
Prevent self-referral with account matching on email domain and IP. Apply credits only after the referee's first charge clears, not after trial. Cap credits per referrer per month to limit fraud.

## Related
credits-system-implementation, affiliate-commission-tracking, freemium-to-paid-conversion
