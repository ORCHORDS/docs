# Antidumping and Countervailing Duty Control

## Scope

Antidumping (AD) and countervailing duty (CVD) orders raise the landed cost of specific goods from specific countries and producers long before any duty is finally assessed. This article covers the operating discipline a trading or importing organization needs when order scope, producer and exporter pairing, case numbers, deposit rates, and liquidation outcomes sit inside its commercial flow: which facts must be established per shipment, how deposits are calculated and reconciled, and what evidence survives a Customs audit or an administrative review.

Out of scope are the economics of dumping margins, petition strategy, and litigation before trade authorities. Those belong to counsel. The scope here ends at the commercial record: the durable case file, the controls around it, and the correction path when a shipment turns out to be covered when it was assumed not to be.

A single import can attract several stacked orders — an AD order and a CVD order may both apply to the same product, each with its own case number, deposit rate, and review history. Treating "antidumping" as one undifferentiated tax block is the most common failure this control prevents.

## Workflow or implementation guidance

1. **Determine order coverage before booking.** Match the product against the scope language of each potentially applicable order, not against the product's tariff heading. Scope is defined by the authority's order text, which describes physical characteristics and uses in ordinary commerce; the harmonized code is only a screening aid. Record the specific order, case number, and scope rationale in the purchase or sales record at booking time.
2. **Pair producer and exporter correctly.** Deposit rates differ by producer and exporter combination. A rate quoted for one producer does not travel with the goods when they are routed through a different exporter or reseller. Capture the actual manufacturer identity — not the trading company on the invoice — and match it to the rate table in force on the entry date.
3. **Apply the rate in force on the date of entry.** Rates move after administrative reviews. The deposit owed is determined by the rate effective at entry summary filing, not the rate when the order was placed. Freeze the applicable rate table version alongside each entry so a later recalculation can be reproduced.
4. **Calculate, deposit, and record.** Compute expected deposits at booking for cash planning; compute actual deposits at entry from entered value and the applicable rates. Store both, with their inputs, under the case number.
5. **Track liquidation.** Deposits are provisional. Final liability crystallizes when entries liquidate, which can occur years after entry and at rates different from the deposited ones. Keep entries open in the ledger until liquidation notice arrives, and reconcile the final assessment against deposits paid, booking accruals, and any retroactive exposure.
6. **Route changes through reassessment.** New factory, redesign, new country of manufacture, new middleman, or a scope ruling request — each reopens step 1. The case record should show why coverage was re-examined and with what result.

## Controls

- **Order-scope gate at booking.** No purchase order is accepted for goods in AD/CVD-sensitive categories without a recorded scope determination (covered, not covered, or pending ruling) linked to the order.
- **Rate-table versioning.** The deposit-rate tables used for each entry are snapshotted, dated, and retained; recalculations cite the snapshot rather than a live source.
- **Producer identity corroboration.** Manufacturer identity from the supplier is cross-checked against shipping documents and, where feasible, physical or facility evidence. Reseller invoices are never sufficient alone.
- **Separation of booking and entry calculation.** The person who books the sale does not solely determine the duty treatment; a second role verifies producer-exporter pairing and rate application for every entry.
- **Open-entry ledger with aging.** Unliquidated entries are visible in a ledger aged by entry date, with review-estimate postings when review outcomes are announced, so retroactive liability is never a surprise.
- **Exception log with owner and expiry.** Any shipment released on an assumption (for example, scope "not covered" pending a ruling) carries a named approver, rationale, and expiry date after which it must be resolved.

## Validation evidence

Validation asks whether the duty record can be defended later, not whether documents merely exist:

- Trace a sample of entries from purchase order to liquidation: does each show a booking-time scope determination, an entry-time rate snapshot, a producer identification, and a liquidation reconciliation?
- Recompute deposits from source values (entered value × applicable rate) for a sample and compare against amounts deposited; differences indicate rate-table drift or manual override.
- Reconcile the open-entry ledger against the authority's public liquidation notices; entries liquidated at higher rates than deposited must show accrual postings dated before the liquidation notice, not after.
- Review the exception log for entries past expiry and scope determinations that relied on a supplier's assertion alone.

The evidence file per case should retain: order texts and scope language relied on, rate-table snapshots, entry summaries, deposit proofs, liquidation notices, reconciliations, and any scope-ruling correspondence. A reviewer must be able to reconstruct the rate applied to any entry and why that rate was believed applicable on the entry date.

## Failure modes and correction

- **Scope surprise.** A shipment assumed outside an order is later found inside it. Response: freeze further releases of the affected product-party combination, quantify deposit shortfall from entry date, file or amend through the official procedure, and re-run the scope gate for all open orders of the same family.
- **Wrong producer pairing.** Deposits were paid at the wrong rate because a reseller was treated as the producer. Response: correct subsequent entries immediately, estimate retroactive exposure for unliquidated entries, and require facility-level manufacturer evidence going forward.
- **Review shock.** An administrative review resets rates sharply upward and applies to unliquidated entries. Response: post the exposure to the ledger on the preliminary result, notify affected commercial owners, and re-price open quotations that assume the old rate.
- **Stale determination reuse.** Coverage decided once is silently reused for years. Response: age-scan the scope-determination register; determinations older than the order's review cycle or predating a scope clarification are re-performed, not grandfathered.
- **Evidence loss at liquidation.** Records needed to defend deposited rates are purged under ordinary retention before entries liquidate. Response: extend retention for AD/CVD case files to cover the statutory liquidation plus protest window, and tag such files at entry.

In every failure path, the original mis-deposited or mis-scoped record stays intact; corrections file through the official channel, and the case file links original and corrected states.

## Limitations

Rates, scope, and producer-specific outcomes are set by trade authorities and change through reviews and rulings; no operational control can freeze them. This article is operational governance for the commercial record, not legal advice on any transaction, and it does not substitute for counsel where coverage or exposure is disputed. Other regimes — Section 301, safeguards, absolute quotas — interact with AD/CVD and are outside this article's boundary.

## Canonical sources

- U.S. International Trade Administration, Antidumping and Countervailing Duty operations: https://access.trade.gov/
- U.S. International Trade Administration, Antidumping and countervailing duties overview: https://www.trade.gov/us-antidumping-and-countervailing-duties
