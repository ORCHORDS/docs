# gift-card-implementation

**Issue:** Building a gift card system with unique codes that apply value to purchases
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Gift cards require unique code generation, redemption at checkout, partial usage tracking, and expiry handling. Fraud (selling stolen gift cards) is a significant risk.

## Pattern / Solution
Generate codes using CSPRNG encoded as alphanumeric strings. Store in DB with fields: code_hash (indexed), original_value, remaining_value, redeemed_by, expires_at. At checkout, verify code, apply remaining value as discount, deduct from remaining_value in a transaction.

## Gotchas
Never store raw codes — store a hash. Rate-limit redemption attempts to prevent brute-force. Implement velocity checks: flag accounts redeeming more than 5 gift cards per day. Gift card fraud is common — require 3DS for gift card purchases.

## Related
credits-system-implementation, stripe-coupon-discount, card-testing-attack-prevention
