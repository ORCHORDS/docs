# real-time-payments-fraud-window

**Issue:** The compressed investigation window on real-time payment rails (FedNow, RTP Network, SEPA Instant, UPI, PIX) lets fraudulent payments settle before fraud teams can intervene
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
You integrated FedNow or The Clearing House RTP network to offer instant payouts or instant funding. Within
the first month you see a pattern: a "customer" signs up, links a debit card or bank account, tops up their
balance, and immediately requests an instant withdrawal to a different account — all within 90 seconds.
By the time your fraud analyst opens the dashboard, the funds have settled irrevocably.

The defining property of real-time payment rails is **7x24x365 settlement in seconds**, which is great for
UX and terrible for the post-hoc fraud model that traditional card payments allow. With cards you have an
authorization hold, then a capture hours later, then a 120-day chargeback window. With RTP, the moment the
payment is sent it is final — there is no hold and no recall. ACAMS and the AFP both flag real-time payments
fraud as the fastest-growing category in 2026 because the window to intervene has collapsed from days to
seconds.

This bites any product that offers: instant payouts (creator platforms, gig economy, trading apps), instant
wallet top-ups followed by transfers, peer-to-peer payments, or instant refunds.

## Pattern / Solution
Shift fraud defense to **pre-transaction, synchronous** controls. You cannot investigate after the fact;
you must decide before the rails accept the payment.

1. **Risk score before payout, block in software.** Run a synchronous risk check at payout-request time
   that incorporates account age, velocity (deposits in vs. withdrawals out), device fingerprint,
   linkage to other accounts, and behavioral signals. If the score exceeds threshold, decline the
   payout in your API — never send it to the rail and hope. Default action for high-risk is hold-for-review,
   not send-then-investigate.
2. **Hold-and-clear pattern for new accounts.** For accounts under N days old or with no withdrawal
   history, route instant payouts through a short hold (minutes to hours) during which a model re-scores
   with any newly-arrived signals. Surface the hold to the user as "security review," not "fraud check."
3. **Balance the funds-flow ratio.** Track `withdrawals / deposits` per account. A healthy account funds
   spending on-platform; a fraud account funnels money straight out. Flag accounts where >X% of deposited
   funds are withdrawn to external instruments within 24 hours, especially if the deposit itself was via
   a reversible method (card, ACH that can be returned).
4. **Block first-payout to a newly added instrument.** Don't allow the first withdrawal to go to a bank
   account or card that was added within the last 24-48 hours. Require the instrument to age before it
   can receive an instant payout; allow slower rails (ACH) for new instruments.
5. **Network-level controls.** FedNow and RTP both support request-for-payment (RfP) flows and, increasingly,
   opt-in fraud filters at the receiving institution. Use Confirmation of Payee / name-match where the
   rail supports it. Some rails now support a "stop-payment" instruction within a tiny window — know your
   specific rail's recall capability and assume it's near-zero.
6. **Loss budgeting, not just prevention.** Accept that some real-time fraud will settle. Model expected
   loss rate per rail, reserve against it, and feed confirmed-fraud cases back into the risk model weekly.
   The goal is a low, predictable loss rate, not zero.

## Gotchas
- **"We'll recall it" is fiction on RTP.** Unlike cards, there is no consumer chargeback right on most
  real-time rails. Once sent and accepted, the funds belong to the receiver. The receiving bank may
  voluntarily freeze a fraudulent account if you act within minutes, but it is not guaranteed and not
  automatic. Treat every send as final.
- **Funded-by-reversible-method is the killer combo.** A fraudster deposits via card (chargebackable in
  120 days) or ACH (returnable for unauthorized), then withdraws via RTP (irreversible). You eat both the
  reversal and the payout. This asymmetry is the entire business model for many fraud rings. Hold RTP
  withdrawals until the funding source's reversal window closes, or accept the risk explicitly.
- **Velocity must be measured across rails, not per-method.** A fraudster will test card top-up, ACH
  top-up, and P2P inbound in the same hour. If your velocity check runs per payment method it misses the
  cross-rail burst. Centralize the velocity counter at the account/wallet level.
- **Off-hours are when fraud spikes.** RTP settles 24/7 but your fraud team does not work 24/7. Fraud
  rings know this and hit on weekends and holidays. Your synchronous pre-send model is the only defense
  at 2am Sunday — staff cannot be the control.
- **Don't confuse RTP with ACH same-day.** Same-day ACH still settles in batch windows and supports
  returns. FedNow/RTP settle in seconds with no return code for "I didn't mean to." The two need different
  controls and different user-facing language.
- **PIX (Brazil), UPI (India), SEPA Instant (EU), FedNow/RTP (US) all differ.** Each rail has its own
  recall mechanism, fraud signal availability, and regulatory regime. Do not port your US RTP controls
  to PIX assuming parity; read the rail's documentation and local regulation before launch.
- **First-party fraud loves instant rails.** A legitimate-looking user disputes a perfectly delivered
  instant payout ("I didn't authorize this") hoping the bank reverses it. Because there is no goods-
  delivery proof on a push payment, your defense is account behavioral baselining, not shipment tracking.

## Related
velocity-fraud-checks, fraud-detection-signals, authorized-push-payment-fraud-bec,
ai-ml-fraud-risk-scoring, wallet-balance-patterns, payment-audit-logging
