# ach-vs-card-cost-economics

**Issue:** US merchants accepting both cards and ACH Direct Debit routinely price the choice wrong: they treat ACH as "the cheap one" without modeling fixed fees, settlement delay, return risk, and the dispute asymmetry (ACH disputes are final and uncontestable, and a dispute kills the mandate). Conversely, high-ticket B2B flows that stay on cards burn 2-3% in interchange where ACH would cost pennies on the dollar. This note works the actual economics and the operational guardrails that decide when each rail wins.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Cost structure: percentage-plus-fixed vs capped-flat

1. **Cards.** Typical online card pricing is around 2.9% + $0.30 per transaction (higher for premium cards, international, and AMEX; lower for negotiated interchange-plus at volume). Cost scales linearly with ticket size.
2. **ACH Direct Debit.** Stripe prices ACH at 0.8% capped at $5.00 per transaction; many PSPs and banks offer flat-fee ACH ($0.25-$1.50 per item) or per-batch pricing on direct ODFI relationships. Above the cap threshold (~$625 on Stripe's 0.8%-cap), ACH cost is constant — that is the whole story of ACH economics.
3. **The crossover math.** At $100: card ~$3.20 vs ACH ~$0.80. At $625: card ~$18.43 vs ACH ~$5.00 (cap). At $2,000: card ~$58.30 vs ACH ~$5.00. The bigger the ticket, the more irrational card-only pricing becomes — but note ACH failure fees exist: a failed ACH debit typically incurs a fee (e.g., Stripe charges an ACH failure fee), and return rates directly erode the saving.
4. **Effective cost includes returns.** A single $5 capped fee is great until a 2-5% return rate (R01 insufficient funds, R08 stopped payment) adds failure fees plus ops handling; underwrite ACH by customer segment, not as a default for everyone.

## Settlement timing and cash-flow implications

1. **ACH is a delayed-notification method.** Standard settlement to your PSP balance is up to 4 business days (T+4) with a 21:00 US/Eastern cutoff; an eligible faster option is T+2 (14:00 US/Eastern cutoff) — this is the confirmation horizon your order-fulfillment and revenue-recognition logic must assume, versus card auth confirmed in seconds (Stripe ACH documentation).
2. **Provisional access is not finality.** Funds can be pulled back after they appear: customers generally have 60 calendar days from the debit on personal accounts to dispute through their bank (business accounts effectively ~2 business days), and in-rail-window disputes are final — there is no representment (Stripe).
3. **Post-success failure events exist.** Rarely a bank returns a debit after the PaymentIntent reports succeeded; the PSP then creates a dispute object (insufficient_funds, incorrect_account_details, bank_cannot_process) and debits your balance back plus a failure fee. Your ledger must handle "succeeded then reversed" as a normal state, not an exception.
4. **Payout scheduling compounds delay.** The T+2/T+4 figure is to your PSP balance; the money reaches your bank on your payout schedule after that. B2B cash-flow planning should model T+5 to T+8 end-to-end.

## Returns, disputes, and the mandate machinery

1. **Disputes are final.** ACH disputes within the network window cannot be contested; the only path is resolving directly with the customer. Radar-style tools help screen, but the design assumption must be: if it disputes, the money is gone.
2. **A dispute invalidates the mandate.** After a disputed ACH payment, the saved bank account cannot be reused until you resolve with the customer and collect a new mandate; repeated disputes get the bank account blocked network-wide under Nacha rules (Stripe surfaces this via payment_method.automatically_updated).
3. **Nacha mandate compliance is mandatory.** You must present authorization language (business name, one-time vs recurring terms, revocation procedure), deliver a copy to the customer (Stripe emails it automatically if billing email is set), and keep proof of acceptance — banks can demand it in authorization inquiries.
4. **Verification gates the rail.** Bank accounts must be verified (instant via Financial Connections-style flows, or 1-2 day microdeposits with a 10-day verification window). Unverified accounts are where fraud and returns concentrate.
5. **Retry rules are narrow.** Stripe's direct-debit retry will retry an NSF failure at most 2 times within 40 days; custom retry logic beyond that risks Nacha non-compliance and bank blocks.

## When each rail wins

1. **ACH wins: high-ticket B2B invoices, rent, tuition, charitable large gifts, recurring SaaS above ~$300-500/month, and any flow where the customer will tolerate a multi-day confirmation for lower fees.**
2. **Cards win: sub-$100 e-commerce (fee gap small, conversion friction high), digital goods with instant fulfillment (ACH return risk on instantly consumed goods is brutal), international customers, and anywhere chargeback-based buyer protection drives conversion.**
3. **Hybrid flows are the norm.** Offer ACH at the invoice/billing surface (where the customer is paying a known amount to a known payee) and cards at impulse surfaces; measure realized fee saving net of returns, not headline rates.
4. **Instant bank payments change the math.** Link-style instant bank payments in the US give card-like confirmation with bank-debit-level pricing and bank-initiated-return guarantees — for flows needing speed without card cost, evaluate them before accepting ACH's T+4 tradeoff (Stripe).
5. **Revisit quarterly.** Interchange, ACH caps, and same-day-ACH fee schedules move; the crossover ticket where ACH beats cards shifts with your negotiated rates, so keep the comparison as a parameterized model, not tribal knowledge.
