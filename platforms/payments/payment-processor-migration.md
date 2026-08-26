# payment-processor-migration

**Issue:** Migrating from one payment processor to another (e.g., Stripe → Adyen, or PayPal → Stripe) without losing customers' saved payment methods, breaking recurring billing, or double-charging during the cutover
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
You decided to switch payment processors — for lower fees, better local methods, consolidated reporting,
or because the current provider put you on a risk hold. The instant question that stops the project cold:
"What about the 40,000 customers with saved cards, and the 12,000 active subscriptions?"

Card networks deliberately do not let you bulk-export usable card numbers from one processor's vault to
another. PANs (primary account numbers) are not portable — that would defeat the entire point of
tokenization. So a naive migration plan ("export cards, import into new processor") is dead on arrival,
and teams discover this weeks into the project, often after announcing a cutover date.

Meanwhile recurring billing has its own traps: subscriptions are stateful objects living inside the old
processor, with their own billing cycles, prorations, and retry schedules. If you just cancel old
subscriptions and create new ones on the new processor, you double-charge the customer for the overlap
period and reset their billing anchor, trial history, and dunning state.

## Pattern / Solution
Run a **dual-process cutover** over weeks, not a flag-flip in one night.

1. **Scope the migration by payment-method lifecycle, not by code path.** Three populations, each handled
   differently:
   - **Active subscriptions** — must move with billing anchor, current period, and retry state preserved.
   - **Saved (tokenized) payment methods for one-off use** — migrate on next customer-initiated action,
     not in bulk.
   - **New transactions** — route to the new processor from cutover forward.
2. **For saved cards: use the Card Account Updater / network token migration path, or re-tokenize at
   next touch.** Two legitimate options:
   - **Customer-initiated re-tokenization.** Next time the customer authenticates (login, next renewal
     email, next checkout), prompt them to re-enter or confirm their card on the new processor. Offer a
     small incentive if needed. This is the highest-integrity path and what most mature teams converge on.
   - **Account Updater alignment.** Both old and new processors receive the same network Account Updater
     feed; you cannot push PANs across, but you can use the customer's next successful charge on the old
     processor to confirm the card is live, then prompt for re-save on the new one. Do not assume you can
     "export tokens" — confirm portability with the new processor's support team in writing before
     promising a date.
3. **For subscriptions: migrate in cohorts aligned to billing cycles.** For each subscription, schedule
   the move so the new processor's first charge happens on the customer's next natural renewal date. The
   sequence per subscription: (a) read full state from old processor (anchor, plan, discounts, retry
   count, current period end); (b) recreate equivalent on new processor with identical anchor and proration
   settings; (c) cancel the old subscription to end at the same period boundary — not immediately; (d)
   verify the new subscription's first scheduled charge matches the old one's cadence.
4. **Dual-run new volume for a burn-in period.** Before moving all new traffic, route a small percentage
   (5-10%) of new transactions to the new processor in parallel with the old for 1-2 weeks. Compare
   authorization rates, decline reasons, and latency. A processor that looks fine in sandbox can have
   materially worse auth rates in your specific geography or BIN mix — find out on 5% of traffic, not 100%.
5. **Reconcile every single day during cutover.** Daily reconciliation between old-processor reports,
   new-processor reports, and your internal ledger. Any subscription that exists on both processors
   simultaneously is a double-charge; any that exists on neither is a churn event. Catch both within 24 hours.
6. **Webhooks on both processors throughout.** Keep webhook handlers for the old processor running until
   every old subscription has been migrated and confirmed. The #1 cause of "ghost" billing after migration
   is turning off old-processor webhooks while old-subscription state is still mutating (refunds, retries,
   disputes).

## Gotchas
- **Tokens are not portable across processors, full stop.** A Stripe token is meaningless to Adyen and
  vice versa. Anyone on the team who says "we'll just move the tokens" hasn't verified. Get written
  confirmation from the new processor's solutions engineer about exactly what migration tooling they
  support, and assume the answer is "customer re-enter," not "bulk import."
- **Network tokens (Visa/Mastercard token services) can be ported in some regions but require both
  processors' cooperation and a token-requestor-to-token-requestor migration flow.** This is real but
  slow (weeks to months) and not universally supported. Treat it as a possible accelerator for a subset,
  never the default plan.
- **Billing anchor drift.** If the new processor defaults to "create subscription today" you will shift
  every customer's billing date, which changes revenue recognition timing and confuses customers who
  expect a charge on the 1st and now see it on the 17th. Explicitly set `billing_cycle_anchor` (Stripe)
  or the equivalent on the new processor to match the old subscription's anchor.
- **Proration and plan differences.** Plan IDs, tax behavior, and coupon semantics differ across
  processors. A "10% off for 3 months" coupon on Stripe may not have a direct equivalent on Adyen. Map
  every active discount before migration and decide per-coupon whether to port, expire, or honor manually.
- **Tax calculation divergence.** Stripe Tax and a new processor's tax engine may compute differently
  for the same transaction, especially across VAT/GST/sales-tax boundaries. Reconcile tax amounts during
  burn-in; a tax-rate discrepancy becomes a compliance problem, not just a UX one.
- **Disputes and chargebacks don't migrate.** A chargeback opened on the old processor for a transaction
  pre-cutover still has to be fought on the old processor. Keep dispute-response tooling and access
  active for at least 120 days after the last old-processor charge.
- **Don't cancel-then-create.** The tempting script — "cancel all on old, create all on new, run once" —
  is how you get a window where a customer has no subscription and a renewal is due, or where you
  double-charge because both creations succeeded. Always overlap-at-boundary, never gap.
- **Tell customers before, not after.** A processor change often surfaces as a new descriptor on the
  customer's bank statement, which triggers "unrecognized charge" chargebacks. Pre-notify customers that
  they'll see a new descriptor starting [date], and keep the old descriptor for a billing cycle so
  recurring charges look familiar. Statement-descriptor mismatch is a top-three driver of friendly-fraud
  chargebacks during migrations.
- **3DS/SCA enrollment doesn't carry over.** A customer who has completed 3DS or Strong Customer
  Authentication exemptions on the old processor may need to re-authenticate on the new one. Expect a
  one-time uptick in friction and abandoned checkouts in the first weeks post-cutover, especially in the
  EU where SCA is enforced.

## Related
payment-provider-abstraction, tokenization-vault-patterns, stripe-subscription-lifecycle,
stripe-billing-anchor-dates, account-updater-service, card-expiry-handling,
payment-reconciliation, payment-audit-logging, stripe-statement-descriptor
