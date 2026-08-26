# credits-system-implementation

**Issue:** Building a promotional credits system that applies to future invoices or charges
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Credits are granted for referrals, promotions, or service credits. They must reduce future charges correctly, expire at defined dates, and be visible to the customer.

## Pattern / Solution
Use Stripe Customer Balance for simple credit application — add a balance adjustment and it applies automatically to the next invoice. For complex expiring credits, maintain a credits table with amount, expiry, and source. At invoice creation, compute applicable credits, apply as a Stripe coupon or balance adjustment, mark credits as consumed.

## Gotchas
Stripe Customer Balance does not support expiry dates — implement expiry in your own system. Credits applied as coupons show differently on invoices than balance adjustments. Test that credits do not allow free charges beyond their value.

## Related
wallet-balance-patterns, stripe-coupon-discount, referral-credit-tracking, stripe-invoice-customization
