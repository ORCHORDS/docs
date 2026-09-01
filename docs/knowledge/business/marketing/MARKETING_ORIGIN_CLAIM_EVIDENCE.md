# Marketing Origin Claim Evidence

Origin claims compress a supply chain into a phrase. "Made in USA," "Assembled in Germany," "Italian leather," "Product of Japan": each tells the consumer where value was created, and each demands proof proportionate to its breadth. The broadest form, an unqualified origin claim, asserts that the product is all or virtually all of the stated origin, and almost nothing short of that standard will support it. This article governs the evidence architecture behind origin representations: what an unqualified claim demands, when qualification is mandatory, and how supply-chain change is detected before it invalidates a live claim.

## Scope

This control covers origin representations in marketing and packaging owned by the organization: unqualified national-origin claims, qualified origin statements, origin references in brand names and taglines, flags, maps, landmarks, and imagery that communicate origin, component-level origin statements such as material provenance, and origin claims in marketplace listings and advertising. It applies to product labels, packaging, product detail pages, advertising creative, and naming.

It addresses claim substantiation and qualification only. Customs marking rules, country-of-origin determinations for tariff purposes, procurement preference programs, and the labeling rules of specific foreign markets interact with this control but are governed elsewhere; tariff origin and marketing origin are not interchangeable determinations.

## Workflow or implementation guidance

1. **Determine claim width first.** For every origin signal, decide whether it reads as unqualified or qualified. An unqualified claim asserts that all, or virtually all, of the product is of the stated origin. Everything narrower requires an accurate qualifier. The complete presentation decides width: a flag beside a modest "assembled in" line can render the qualified claim effectively unqualified.
2. **Apply the all-or-virtually-all standard to unqualified claims.** The evidence question is whether the product contains no, or negligible, foreign content, such that the final assembly, processing, and parts are substantially of the stated origin. Factors examined include the proportion of manufacturing costs attributable to foreign parts and processing, the distance of the foreign content from the finished product, and the importance of the foreign content to the overall product. A small but essential imported component can defeat the claim.
3. **Qualify to the truthful scope.** Where the standard is not met, the claim states the real fact: the specific origin of assembly, the specific share and origin of domestic content, or the origin of a named component. The qualifier must be prominent enough that the net impression matches the narrower fact.
4. **Build the origin dossier from the bill of materials.** For each product carrying an origin claim, maintain a dossier mapping significant parts and operations to locations and suppliers: where each significant input was made, where transformation occurred, and the cost share of foreign content. The dossier is dated and versioned with the product.
5. **Write qualification into naming and imagery review.** Brand names, taglines, flags, maps, and national imagery are reviewed for the origin message they deliver without text, since an unqualified impression from imagery is treated the same as one from words.
6. **Refresh on supply-chain events.** Supplier changes, relocation of manufacturing, sourcing substitutions, and formulation changes trigger dossier re-verification. The claim expiry is tied to the shortest-lived sourcing input.
7. **Reconcile claims across channels.** The dossier is the single source; packaging, listings, and advertising render from it, and a periodic check confirms that no surface carries a claim the dossier no longer supports.

## Controls

- An origin dossier is required before any origin claim publishes; the review gate blocks claims without a dossier identifier.
- Unqualified claims require a documented all-or-virtually-all analysis with cost-share data, not a supplier's verbal assurance.
- Supplier origin attestations are collected with liability clauses and verification sampling; a supplier-origin change notification clause obligates prompt notice.
- Imagery and naming review is mandatory for products with any origin association, closing the wordless-impression path.
- A sourcing-change watchlist ties dossier inputs to procurement events, so a supplier switch surfaces as a claim-review ticket, not as a discovered error.
- Marketplace listing templates inherit claims from the dossier and are re-verified on dossier version change.

## Validation evidence

- Dossier extracts for sampled products: parts map, transformation locations, foreign-content cost share, and version history.
- Supplier attestations and supporting documentation for significant inputs, with verification sampling results.
- The all-or-virtually-all analysis for each unqualified claim, showing the reasoning against the cost-share and significance factors.
- Rendered captures of packaging, listings, and advertising showing the claim and any qualifier as actually presented.
- Reconciliation reports between dossier versions and live claims across channels.
- Change tickets linking procurement events to claim reviews and their dispositions.

## Failure modes and correction

Common failures include a Made-in-USA claim retained after manufacturing moved, an imported component deemed insignificant without analysis, a qualified claim visually overwhelmed by flags and maps into an unqualified impression, origin claims on marketplace listings diverging from current packaging, and supplier attestations accepted for years without re-verification while sourcing quietly changed. The systemic failure is treating origin as a fixed product attribute rather than as a live claim dependent on a moving supply chain.

Correction starts with claim withdrawal on all surfaces, including printed packaging where a running change and inventory plan is documented. The exposure window is quantified from dossier versions and distribution records. Because origin claims can affect purchase decisions materially, remediation decisions including corrective communication are escalated with counsel. The dossier is rebuilt to current sourcing and the claim is re-approved at the correct width. Recurrence triggers procurement-to-marketing integration: no sourcing change closes without a claim-review disposition.

## Limitations

The all-or-virtually-all standard is a demanding evidentiary test applied to facts, and reasonable judgments about negligible foreign content can differ at the margin. Specific markets impose prescriptive origin-labeling regimes stricter than this control, and sectoral programs such as textile and food labeling carry their own rules. Customs and tariff origin determinations may diverge from advertising origin and are not validated here. The control depends on supplier truthfulness backed by sampling; deep-chain verification has practical limits.

## Canonical sources

- **Primary authority 1 — Federal Trade Commission, Complying with the Made in USA Standard (business guidance):** [https://www.ftc.gov/business-guidance/advertising-marketing/made-in-usa](https://www.ftc.gov/business-guidance/advertising-marketing/made-in-usa)
- **Primary authority 2 — Federal Trade Commission, Made in USA Labeling Rule (rule page):** [https://www.ftc.gov/made-in-usa-rule](https://www.ftc.gov/made-in-usa-rule)
- **Reference — eCFR, 16 CFR Part 323 (Made in USA Labeling Rule):** [https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-323](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-323)
