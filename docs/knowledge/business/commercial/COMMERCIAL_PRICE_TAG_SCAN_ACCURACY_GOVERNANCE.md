# Commercial Price Tag and Scan Accuracy Governance

## Scope

This article covers the controls that keep a price tag, shelf label, menu price, or scanned point-of-sale total consistent with the merchant's stated price. It is anchored in two frameworks: the FDA Food Code (the model code for retail and food service adopted in some form by most U.S. states, which requires accurate price representation on menus, menu boards, and tags for food sold by weight, measure, or count), and the NIST Office of Weights and Measures (OWM) scope, which publishes the specifications and tolerances used by state weights-and-measures officials for pricing accuracy on packaged goods and scale-based sales.

The scope covers price tags and shelf labels, menu boards and printed menus, scale-based sales, scanned point-of-sale totals, mobile and self-checkout totals, fuel-pump price displays, and online price displays tied to in-store pickup. It does not address advertising-claim substantiation under the FTC Act, lease or finance disclosures under Regulation Z, or fuel-quality disclosure under the FTC Fuel Rating Rule.

## Workflow or implementation guidance

Establish a single source of truth for every price that appears anywhere in the customer journey. The price master should record, for each SKU or menu item, the price type (regular, sale, member, loyalty, regional, time-of-day), the effective window, the stores or channels where it applies, and any required regulatory disclosure (for example, "sold by weight, price per pound" or a service-charge disclosure).

Where the FDA Food Code applies, the merchant must display the price on each menu or menu board in a manner that is conspicuous and not misleading, and for items sold by weight or measure, the price must be displayed per unit of measure consistent with the local weights-and-measures rule. Items subject to the Food Code's accuracy principles should be tied to the same price master used by the point-of-sale scanner so that the customer-facing total matches the published price.

For scan-accuracy programs, compare the scanned total to the displayed price for every item at the point of sale, flag mismatches, and resolve them before the customer authorizes payment. Many state scan-accuracy laws require a posted notice that the merchant will either honor the lower price or charge the lower price for a stated number of items, and require periodic audit records; the merchant's policy must be reflected in the point-of-sale workflow.

For weight- or measure-based sales, ensure the scale is certified, the unit price is consistent with the price master, the tare is correct, and the printed receipt shows the net weight, the unit price, and the total in the units customary in the jurisdiction.

## Controls

Maintain a price-master review board that includes store operations, merchandising, legal, and weights-and-measures compliance. Each price change should be approved by an authorized role and effective at a controlled timestamp. The point-of-sale system should reject a price that is not in the active price master.

Technical controls should enforce: (1) the price master is the sole source for prices displayed on tags, labels, menus, and the scanner; (2) the scanner reads the correct SKU and price; (3) the customer-facing total agrees with the price master at the moment of sale; (4) any exception for a customer-facing discrepancy is approved and recorded with the reason; and (5) the receipt and the price tag can be reconciled after the fact from a single retrieval path.

For scale-based sales, calibrate scales on a documented schedule and retain the calibration record. For weights-and-measures compliance, retain package-certification records and use NIST Handbook 44 (Specifications, Tolerances, and Other Technical Requirements for Weighing and Measuring Devices) where applicable.

## Validation evidence

Periodically sample transactions across stores, registers, departments, and price types. For each sampled transaction, recalculate the total independently from the price master and the line items, compare to the customer-facing receipt, and verify the price tag or menu price matches. For scale-based sales, reweigh the package, recalculate the total, and verify the receipt.

Retain the price master snapshot, the scanner audit log, the scale calibration record, and the period audit results for the longer of the state weights-and-measures retention window, the FTC Act's statute-of-limitations window, the state scan-accuracy statute's window, or the merchant's records-retention schedule.

## Failure modes and correction

Common failures include a price tag printed before a price-master update reaches the scanner, a menu price that diverges from the point-of-sale price because the menu is managed in a separate system, a scale that has drifted out of tolerance and is producing slightly low or high weights, a sign type that misstates the unit of measure, a loyalty or member price that does not apply at all registers, and a posted scan-accuracy notice that is not honored at the point of sale.

When a defect is identified, identify affected transactions by SKU, store, date range, and price type. Hold further use of the affected price or scale. Issue customer-facing corrections consistent with the merchant's scan-accuracy policy: honor the lower price, refund the difference, or otherwise comply with state law. Update the price master, the scanner, the menu, and the tag workflow so that the corrected price is consistently displayed.

For systemic defects, escalate to qualified counsel and weights-and-measures compliance. Conduct a bounded lookback and document root cause, correction, and control retest.

## Limitations

This article addresses pricing accuracy and is not a substitute for weights-and-measures device approval, the FDA Food Code's full sanitation and labeling requirements, or state-by-state menu-labeling rules for chain restaurants. It does not address advertising substantiation, lease or finance disclosures, or tax-breakout presentation. Where state scan-accuracy laws are stricter than the practices described here, those state rules control.

## Canonical sources

- U.S. Food and Drug Administration, **FDA Food Code** (retail and food service model code adopted in some form by most states): https://www.fda.gov/food/retail-food-protection/fda-food-code
- National Institute of Standards and Technology, **Office of Weights and Measures (OWM)** (publishes NIST Handbook 44 specifications and tolerances for pricing and weighing devices): https://www.nist.gov/pml/owm
- Federal Trade Commission, **Rules and policy** (general unfair-or-deceptive-practices baseline for pricing representations): https://www.ftc.gov/legal-library/browse/rules
