# affiliate-commission-tracking

**Issue:** Tracking affiliate sales and calculating commissions for external partners
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Affiliates send traffic via tagged links. Commissions are earned on qualifying purchases. Commission calculation, fraud prevention, and payout timing must all be managed.

## Pattern / Solution
Set affiliate tracking cookies with a 30-day window on click. Capture affiliate_id at checkout and store in payment metadata. On invoice.paid, calculate commission as a percentage of net revenue or flat fee. Write to a commissions table with status=pending. After the refund window, mark as payable. Pay via Stripe Connect payouts.

## Gotchas
Track post-payment refunds and reverse commissions accordingly. Cookie stuffing is a fraud vector — validate that click and conversion are on the same device. Use a dedicated affiliate platform to avoid building from scratch.

## Related
referral-credit-tracking, stripe-connect-payouts, tax-reporting-1099
