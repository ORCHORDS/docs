# multi-currency-rounding-fees

**Issue:** Selling in multiple currencies fails in the details adjacent to conversion: per-currency minor-unit rules (zero-decimal JPY, three-decimal KWD, and Stripe's ISK/UGX/HUF special cases), FX and cross-border fees that silently change what the customer pays or what you net, localized prices that drift from your base price as rates move, and rounding residue that accumulates in your ledger when line items, invoices, refunds, and payouts each round differently. multi-currency-handling.md and price-rounding-rules.md cover the basics (store integers, presentment vs settlement, rate caching); this article covers the fee mechanics, localization policy, and reconciliation residue those files do not.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Minor-unit correctness per currency

1. **Zero-decimal currencies take whole-unit amounts.** Stripe's zero-decimal list (JPY, KRW, VND, CLP, KRW, and peers like BIF, DJF, GNF, LAK, PYG, VUV, XAF, XOF, XPF) requires `amount=500` for 500 JPY — the "multiply by 100" habit from USD produces 100x overcharges. Encapsulate per-currency minor-unit conversion in one function; never inline `* 100`.
2. **Stripe's backward-compat exceptions bite.** ISK and UGX are zero-decimal in reality but the API represents them as two-decimal values with `.00` only (charge 5 ISK as `amount=500`); HUF and TWD accept two-decimal charges but manual payouts must be divisible by 100, so a payout of HUF 10.45 is impossible — you can pay out only 10. Encode the exception table next to your minor-unit function.
3. **UGX demonstrates Stripe's own rounding-residue pattern.** When prorations, coupons, or taxes produce fractional UGX amounts, Stripe automatically rounds to a multiple of 100 and credits/debits the difference to the customer balance. That is the canonical model for your own edge handling: round to the representable unit, park the residue somewhere explicit (customer balance), never vanish it.
4. **Three-decimal currencies need precision checks.** ISO 4217 defines BHD, JOD, KWD, OMR with 1/1000 minor units. Verify your PSP, ledger, and display stack all support the required decimal places before pricing in them — a stack that assumes two decimals will silently corrupt them.
5. **Charge minimums differ per currency.** Stripe enforces per-currency minimums (0.50 USD/EUR, 50 JPY, 50 KRW, 175 HUF, 10 MXN, 0.30 GBP...). Small converted amounts (micropayments, prorated upgrades, minimum top-ups) can fall below the minimum after FX and be rejected — clamp prices per market, not per base currency.

## FX fee mechanics and disclosure

1. **Know who pays the conversion.** Standard Stripe US pricing adds +1.5% for cross-border transactions and +1% when currency conversion is required, on top of the 2.9%+30¢ base. If the charge currency differs from your settlement currency, Stripe converts and you net less than the face amount; if you charge in the customer's non-wallet currency, their bank may also charge them an FX fee.
2. **Adaptive Pricing moves the FX cost to the customer.** Stripe Adaptive Pricing (localize-prices/adaptive-pricing) auto-presents local-currency prices in 150+ countries with a 2-4% conversion fee baked into the exchange rate, while you still settle in your home currency; as of late 2025 it supports subscriptions, with Stripe reporting ~4.7% conversion lift. That lift is bought with a higher customer-visible price — A/B it against plain USD pricing before committing.
3. **Disclose the total in the customer's currency at confirmation.** Regulators (and card-network dispute rules) treat hidden FX markups as dispute fuel. Show the exact debited amount and currency before payment, and if the rate is not locked (client-side conversion from a cached rate per forex-rate-caching.md), label it as an estimate and bound the drift.
4. **Reconcile fees separately from FX.** Your ledger should record face amount, FX rate applied, conversion fee, and processing fee as distinct entries. Collapsing them into one "fees" number makes FX-fee audits and PSP-cost optimization impossible later.

## Price localization vs pegging

1. **Pegging: base price x rate, rounded.** Simple and always consistent with your margin, but produces ugly prices (37.42 BRL) that drift daily with FX, forcing price churn in your catalog and invoices that never match the published price.
2. **Localization: fixed charm prices per market.** Define per-currency price points (29.99 USD, 449.000 COP-style local endings) and re-review them on a schedule (monthly/quarterly) or when FX moves beyond a band (e.g. 5%). Stable prices, better conversion, but your realized margin varies with the rate — track effective base-currency revenue per market.
3. **Set a re-pegging trigger, not just a schedule.** Combine both: fixed localized prices plus automatic review thresholds. When a currency breaches the band, decide to re-price or accept margin change — never let a crashing currency ride for a quarter because "we review monthly".
4. **Subscriptions pin the localized currency at creation.** Per multi-currency-handling.md, Stripe subscription currency locks at creation — localized subscribers keep their price through FX moves, so your exposure compounds across cohorts. Model cohort FX exposure before enabling multi-currency subscriptions.

## Reconciliation rounding residue

1. **Line-item rounding vs total rounding diverges.** If you round each line (item, tax, shipping) to the currency's minor unit and sum, the total differs from rounding the raw sum — auditors care which convention you use, and Stripe's invoice totals follow its own rules. Pick one convention (round-per-line-then-sum is the common tax answer), document it, and make your invoice generator match your ledger.
2. **Partial refunds need a rounding policy.** Refunding 33.33% of 100.00 across three iterations cannot be exact in cents; define whether remainders go to the last refund, are truncated, or are credited, and keep the sum of refunds bounded by the original charge — refunding more than captured is a PSP error at best and a fraud signal at worst (see partial-refund-handling.md).
3. **Payout divisibility creates stranded residue.** HUF/TWD payouts must be divisible by 100; residual balances (like HUF 0.45) can never be paid out in that currency. Sweep residues into a rounding account on a schedule instead of letting them linger and break bank-statement matching.
4. **FX-converted settlements never tie out exactly.** The settled base-currency amount is rate x face x (1 - fees), each step rounding independently; your reconciliation should tolerate a small per-transaction tolerance band and aggregate the true remainder into an explicit FX rounding P&L account rather than forcing fake matches per payment-reconciliation.md.
5. **Residue is only harmless when it is visible.** Whatever bucket absorbs rounding (customer balance, FX rounding account, payout residue), report its balance and aging monthly. Untracked residue is how, a year later, you discover a rounding bug that has been skimming or overcharging customers by one minor unit per transaction.
