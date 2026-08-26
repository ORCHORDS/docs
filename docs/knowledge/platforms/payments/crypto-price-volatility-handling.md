# crypto-price-volatility-handling

**Issue:** When a customer pays with a volatile cryptocurrency, the amount owed is quoted in fiat but settled in an asset whose price moves every block. Between quote display, transaction broadcast, and network confirmation (minutes to an hour depending on chain and fee market), the value received can drift below what the customer agreed to pay, or the customer can overpay materially. Unlike card payments, there is no issuer to reverse a short settlement: the engineering system must bound the exposure itself with price locks, expiry windows, tolerance bands, and explicit policies for underpayment and overpayment. The 2025 regulatory arrival of payment stablecoins in the US (the GENIUS Act, enacted July 18, 2025) changes the calculus by making fully-reserved, 1:1 fiat-backed stablecoin rails a first-class alternative for merchants whose real problem is volatility rather than crypto itself.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Price lock windows

1. **Quote with an explicit expiry.** Every crypto invoice must carry a generated-at timestamp, the source price feed (aggregated spot, not a single exchange), and a validity window (typically 10-20 minutes for BTC/LTC, shorter is possible on fast chains). After expiry, the invoice is void and requires a fresh quote; accepting a payment against an expired quote is how you absorb the volatility loss silently.
2. **Persist the locked rate and the invoice amount independently.** Store the fiat order amount, the quoted crypto amount, the rate, the price feed snapshot, and the expiry as separate fields on the payment intent. Reconciliation and dispute handling depend on being able to prove what was quoted, not just what arrived.
3. **Rate-source integrity.** Use an aggregated feed or your processor's rate endpoint, record which source produced the quote, and alert when your processor's confirmation-time valuation diverges from your quote source by more than a configured threshold; divergence usually means one feed is stale or manipulated.

## Underpayment and overpayment

1. **Define tolerance bands in advance.** Underpayment below a small tolerance (for example, sub-cent equivalent or a fixed bps of the invoice) is usually accepted and the difference written off as conversion cost; below-quote-but-within-band is a business policy decision that must be coded, not improvised. Overpayment above tolerance should trigger a refund workflow for the surplus, denominated in the paid asset.
2. **Build a top-up flow for underpayment.** When the received amount is under tolerance, hold the payment in a partial state and present the remaining amount due as a new micro-invoice referencing the same order. Auto-refunding and re-invoicing the full amount is simpler but costs two network fees and another volatility window.
3. **Never reuse deposit addresses across orders.** Address reuse breaks amount-based matching entirely: two customers paying the same address cannot be distinguished except by amount, and privacy-minded users may overpay deliberately to de-anonymize. One order, one address, enforced by the address management service.

## Stablecoin rails as the volatility answer

1. **Prefer regulated stablecoins for volatility-sensitive commerce.** The GENIUS Act (enacted July 18, 2025) establishes a US federal framework for payment stablecoins: issuance restricted to permitted issuers, reserves fully backed and denominated in the same fiat currency, with implementing rules proposed in early 2026. A USDC/USDT/PYUSD-denominated invoice has no meaningful quote-to-settlement drift, eliminating the entire price-lock machinery for those payment methods.
2. **Keep the volatility machinery for BTC-style rails anyway.** Volatile-asset payment support carries product demand (crypto-native users, markets with poor card penetration), so the lock window, tolerance, and reconciliation logic remain required; structure the code so stablecoin flows are the degenerate case of a zero-volatility asset rather than a separate pipeline.
3. **Track issuer risk as a new failure mode.** Stablecoins remove price volatility but add issuer/depeg and regulatory risk. Monitor peg deviation, cap exposure per issuer, and settle to fiat on an automated schedule rather than accumulating stablecoin balances.

## Confirmation and finality risk

1. **Delay fulfillment to probabilistic finality thresholds.** Credit the order only after N confirmations appropriate to the chain and amount (more confirmations for larger amounts), because chain reorganizations can unconfirm a broadcast transaction. Your payment state machine needs an unconfirmed, confirmed, and reorged/reverted set of states.
2. **Handle stuck and replaced transactions.** Fee-market spikes leave transactions unconfirmed for hours. Support RBF/CPFP acceleration policies, decide at what age an unconfirmed invoice expires, and define whether a late-arriving payment (after expiry, full amount) is auto-refunded or honored at a re-quoted rate.
3. **Beware of sweeping races.** Only sweep (consolidate) received funds after confirmation thresholds; sweeping unconfirmed deposits to a hot wallet then facing a reorg leaves you chasing your own money.

## Ledger and reconciliation

1. **Post volatility variance explicitly.** When the fiat value at confirmation differs from the quoted fiat amount (within tolerance or on stablecoin peg drift), post the difference to a dedicated FX/volatility variance account in the double-entry ledger rather than adjusting gross revenue, so finance can see aggregate drift exposure.
2. **Reconcile on-chain truth daily.** Chain-scanning confirmations, processor reports, and your ledger will disagree at the edges (memo-less payments, dust, refunds in flight). A daily three-way reconciliation job is the only defense against silent balance drift.
3. **Record network fees as separate line items.** Miner fees paid on sweeps and refunds are an operating cost of the rail; commingling them with payment amounts corrupts both reconciliation and revenue reporting.
