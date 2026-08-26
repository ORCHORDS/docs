# subscription-proration-edge-cases

**Issue:** Stripe proration basics (preview the upcoming invoice, pick a proration_behavior) are covered in stripe-proration-logic.md, but real subscriptions hit edges those docs do not prepare you for: annual-to-monthly switches that produce negative invoices, interval changes that bill immediately by default, credits and coupons stacking onto proration lines, billing dates drifting across timezones and month lengths, and trial-to-paid conversions that surprise the customer with a mid-cycle charge. Each of these produces support tickets and accounting mismatches when handled naively.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Interval switches: annual <-> monthly

1. **Interval changes bill immediately by default.** Switching monthly -> annual (or annual -> monthly) with default settings creates a new subscription item and invoices right away, which routinely shocks users who expected the change "at renewal". Decide explicitly: immediate switch with proration, or schedule the switch at period end via subscription update with `proration_behavior: 'none'` and a phase change.
2. **Annual -> monthly can produce a credit larger than the charge.** The unused remainder of the annual plan (potentially months of value) becomes a proration credit; if it exceeds the new monthly charge, the invoice goes negative. Stripe does not refund the difference automatically — it sits as customer credit balance and quietly covers future invoices.
3. **Decide the refund policy and encode it.** For downgrades with large credits, choose one: keep as credit balance (default), refund explicitly (`stripe.refunds.create` against the latest invoice payment), or forfeit (terms-of-service dependent). Whatever you pick, surface it to the customer in the UI before they confirm the switch.
4. **Never switch a plan whose price `recurring.interval` differs by editing the item in place without a preview.** Always call `invoices.retrieveUpcoming` with the new price first; the proration math for interval changes is the most surprising in the entire billing surface.

## Credits, coupons, and proration interacting

1. **Customer credit balance is applied to invoices automatically.** A credit balance from a previous overpayment or negative invoice can silently zero out an upgrade invoice the customer expected to pay. If you need the customer to feel the payment (fraud/verification reasons), check `customer.credit_balance` (or `customer.balance` on older API versions) before rendering the confirm screen.
2. **Coupons apply to the new invoice, not the proration math you previewed.** A 20%-off coupon stacked on an already-prorated invoice compounds discounts in ways the preview must include — pass the discount into your `retrieveUpcoming` call, or the customer sees one number and is charged another.
3. **Credit notes and reversals have their own proration semantics.** If a customer disputes a prorated charge and you issue a credit note, the reversal unwinds only that line item; your ledger must unwind the corresponding revenue-recognition entries per revenue-recognition-saas.md, not just net the cash.
4. **Zero-amount invoices still generate webhooks.** Proration credits that fully offset a renewal create $0 invoices; payment flows that assume amount > 0 (dunning, receipts) must handle the paid-nothing case or they will misfire.

## Billing-date drift: timezones, anchors, and month lengths

1. **Proration is computed in UTC to the second.** A "monthly" period is a fixed 30-ish day second count, not a calendar month. Customers billed on the 31st see their effective charge date slide to the 30th/28th in shorter months — harmless financially, but date-driven UI logic ("your renewal is the 31st") breaks.
2. **DST shifts move renewal instants.** A subscription anchored at 00:00 local time in a DST timezone drifts by an hour across transitions; if you snapshot "renewal date" in your DB and compare later with `current_period_end`, expect mismatches of an hour. Always treat Stripe's `current_period_end` as authoritative.
3. **Anchor-date changes trigger proration invoices.** Moving `billing_cycle_anchor` mid-life (covered in stripe-billing-anchor-dates.md for new subscriptions) on an existing subscription generates a proration invoice for the shift — batch "re-anchor everyone to the 1st" campaigns accordingly and expect an invoice per customer.
4. **Timezone-display drift causes "wrong charge" tickets.** A charge at 2026-08-01T00:30Z displays as July 31 evening in US timezones; your receipt email should render the timestamp in the customer's timezone to defuse the most common false-billing complaint.

## Trial-to-paid conversion proration

1. **Default conversion bills at trial end with no proration.** The clean case: trial ends, first full-period invoice charges. Proration only enters when you change the plan during the trial or convert early — e.g. upgrade mid-trial with immediate proration creates a partial charge for the pricier plan mid-trial, which reads as "you charged me during my free trial".
2. **Converting early should credit unused trial differently than unused paid time.** If you end a trial early on upgrade, Stripe prorates from the plan prices involved; whether the remaining trial entitlement carries over is a policy decision you must test explicitly per stripe-trial-periods.md — do not assume.
3. **Trials without a card (see free-trial-credit-card-required.md) convert to a payment-required state.** The "proration" at that point is zero — nothing owed yet — but your entitlement system must flip access the instant the first payment succeeds, or you get paid-but-locked or free-riding windows.
4. **Trial-extension for failed cards interacts with dunning.** If the card fails at conversion, Stripe's built-in retry (stripe-smart-retries.md) runs during which access continues by default; define grace behavior explicitly rather than inheriting defaults.

## Predictable alternatives to ad-hoc proration

1. **Subscription Schedules for planned phases.** For upgrade-then-bill-on-renewal flows, a subscription schedule with phases (current plan now, new plan at period end) gives you deterministic invoices without proration line items — widely recommended as the fix for "tired of handling proration".
2. **Simulate changes with the clock, not the code.** In test mode, advance `test_clock` through renewal and trial boundaries to assert invoice line items for each edge above; proration bugs surface at period rollovers, not at update time.
3. **Persist an audit trail per change.** Store who changed what, preview amount, actual invoice id, and proration_behavior used. When a customer disputes a prorated charge three months later, the audit entry is the difference between a two-minute answer and a refund.
