# Marketing Reference Price Evidence

A strike-through price is a comparison claim. When a storefront shows a crossed-out figure beside the selling price, it asserts that the higher figure was, in some meaningful sense, the price at which the product was actually offered. This article governs the evidence discipline for former-price and reference-price comparisons: what counts as a genuine former price, how long the comparison remains usable, how the basis of the comparison is documented, and when a discount claim must be retired. The recurring enforcement theme is simple: the reference price must reflect reality, and the marketer must hold dated proof of that reality.

## Scope

This control covers comparative price presentations in marketing-owned surfaces: strike-through and former-price displays, "was/now" claims, percentage-off claims computed against a reference, manufacturer-suggested-retail-price comparisons, pre-sale price references, bundle "total value" comparisons, and anchor prices shown on product detail pages and in advertising. It applies to owned storefronts, marketplace listings, paid media, email, and print where the organization controls the price presentation.

It does not cover competitor price comparisons, which are governed by a separate control, nor the general question of whether the current price is fair. Its focus is the veracity and substantiation of the reference figure itself.

## Workflow or implementation guidance

1. **Classify each reference before creative is produced.** Every strike-through or "was" figure is classified by its basis: an actual prior offering price on the same channel, an actual prior offering price on a different channel, a list price genuinely charged by other retailers in the market, a suggested retail price, or a bundle arithmetic total. Different bases carry different evidence obligations and different disclosure requirements.
2. **Apply the former-price test to the primary case.** Where the reference is the marketer's own former price, the ordinary standard is that the product was offered to the public, in the usual volume, at or above the reference price for a reasonably substantial period immediately before the comparison. The offering must have been genuine: an inflated price set for a token period to manufacture a future discount does not qualify.
3. **Fix the substantiation window.** For each reference, record the period during which the former price was charged, the channel, the transaction evidence available, and the date through which the comparison remains supportable. When sales at the discounted price extend for so long that the discounted price becomes the ordinary price, the comparison is retired rather than left on autopilot.
4. **Document the arithmetic.** Percentage-off claims are computed from the reference actually displayed, under a documented rounding rule, and the displayed numbers must reconcile: a claim of "50% off" beside figures implying 40% off is a defect even when each number is individually real.
5. **Disclose the basis where it is not obvious.** When the reference is not the marketer's own recent price on the same surface, the basis is disclosed in clear language proximate to the comparison, using the disclosure placement discipline governed elsewhere.
6. **Bind references to a system of record.** Reference prices are stored as data with effective dates in the pricing system, not typed into creative by hand; rendered comparisons are generated from that data so that a price change propagates instead of stranding a stale figure in a cached ad.
7. **Schedule retirement.** Each comparison carries an expiry driven by the shortest-lived element: the evidence window, the promotion end, or the staleness rule. Automated checks flag comparisons past expiry.

## Controls

- A pricing evidence register links every active reference price to its basis, evidence documents, effective dates, and owner.
- Publication of a strike-through without a register entry is blocked at the content review gate.
- The pricing system of record is the only permitted source of rendered reference prices; hand-entered figures in templates fail the release check.
- Comparisons that have run continuously for a defined period trigger forced review, because an indefinitely extended discount stops being a discount.
- Channel-specific differences in reference basis are flagged so that a marketplace listing does not inherit a store-only former price without disclosure.
- Bundle value claims are recomputed whenever any component price changes; stale bundle arithmetic fails the daily price-integrity check.

## Validation evidence

- Register extracts for sampled comparisons, showing basis, evidence attachments, and validity windows.
- Transaction or listing records supporting the former-price period: dated price lists, catalog captures, or order data demonstrating actual offering at the reference level.
- Rendered captures pairing the displayed comparison with the register entry current at capture time, produced by an external monitor across the flight period.
- Arithmetic verification output for each percentage claim, including the rounding rule applied.
- Retirement records showing comparisons removed or re-based at expiry, with the triggering rule identified.

## Failure modes and correction

Common failures include a strike-through that outlives its evidence by months, a reference price used on one channel that was only ever charged on another without disclosure, an MSRP anchor that no retailer actually charges, bundle arithmetic that sums imaginary component prices, a "sale" that runs continuously until the sale price is the only price ever seen, and reference figures surviving in cached ad units after the storefront updated. The most damaging variant is the manufactured former price: a nominal price increase for a token interval, followed by a dramatic discount against it.

Correction begins with withdrawal of the unsupported comparison, not merely an intention to fix it. The affected population and window are quantified from monitoring data and the register. Where consumers paid based on a fictitious reference, remediation decisions, including price adjustments or refunds, are escalated with counsel rather than decided within the campaign team. The register entry is corrected, the generation path is fixed so the defect cannot recur through hand entry, and the staleness rules are tightened if the failure was age-related. Deliberate manufacture of a reference price is treated as an integrity violation, not a workflow error.

## Limitations

Former-price adequacy is judged against consumer perception and market context, and no fixed percentage or duration is universally safe; the tests described here are conservative operational defaults. Pricing evidence obligations vary by jurisdiction, and some markets impose prescriptive rules on discount advertising that exceed this control. This control does not certify that the current price is competitive, does not govern dynamic pricing algorithms beyond their reference outputs, and cannot prevent third-party resellers from presenting their own comparisons. Register completeness depends on disciplined intake, which is itself a governance assumption.

## Canonical sources

- **Primary authority 1 — Federal Trade Commission, Guides Against Deceptive Pricing, 16 CFR Part 233 (former price comparisons):** [https://www.ftc.gov/legal-library/browse/rules/guides-against-deceptive-pricing](https://www.ftc.gov/legal-library/browse/rules/guides-against-deceptive-pricing)
- **Primary authority 2 — Federal Trade Commission, Advertising FAQs: A Guide for Small Business (former price and savings claims):** [https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business](https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business)
- **Reference — eCFR, 16 CFR Part 233:** [https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-233](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-233)
