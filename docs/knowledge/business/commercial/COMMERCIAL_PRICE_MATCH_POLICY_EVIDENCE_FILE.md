# Price-Match Policy Evidence File

## Scope

This article covers the operational and evidence controls that support a merchant's price-match policy — a voluntary commitment to match a competitor's advertised price, an internal reference price, or a lower-priced channel of the merchant's own. The article uses the Consumer Financial Protection Bureau's Regulation Z (12 CFR Part 1026) Truth in Lending framing as a structural reference for conspicuous disclosure and evidence preservation, not because every price-match policy is a credit transaction. The principles of clear, conspicuous, and non-deceptive representation of the merchant's offer apply broadly, and Regulation Z provides an authoritative model for how a merchant should think about its representations when the customer's economic decision relies on those representations.

The scope covers the published policy text, the in-store or in-app eligibility check, the evidence file supporting each accepted price match, and the records needed to defend the policy's consistent application. It does not address predatory or exclusionary pricing claims under the antitrust laws; price-gouging statutes; or specific state-level "low-price guarantee" disclosure rules.

## Workflow or implementation guidance

Treat the price-match policy as a published representation that creates an expectation the merchant must honor consistently. The published policy should state, in plain language, the scope of competitors covered, the types of prices covered (advertised, online, clearance), the types of products excluded (for example, limited-quantity, door-busters, marketplace third-party sellers), the verification method, the timing of the match (at the point of sale, within a stated window after sale), and the form of the match (the competitor's price, a percentage off the merchant's price, the difference applied to the merchant's price).

Each price-match request should generate an evidence file that records the customer request, the merchant's verification (with timestamps), the competitor's price at the time of the request, the matched price, the matched form, and the resolution. Where the merchant uses a verification system (a website lookup, a phone call, a competitor-store survey), the system should retain a timestamped result.

The published policy should be conspicuous at the point where the price-match decision is made: at the point of sale for an in-store request, on the order detail page for an online request, or on the relevant help page for a customer-service request. A policy buried in a long terms-of-use document is not conspicuous.

For Regulation Z-adjacent contexts where a price match is offered in connection with a credit sale, the merchant should consider whether the price-match representation interacts with the credit disclosure. The clearest practice is to disclose the price-match policy in the same disclosure set as the credit terms and to ensure that the disclosed finance charge, annual percentage rate, and payment schedule are not affected by the price match in a way that would mislead the consumer.

Maintain a single policy-version record. Each accepted request should reference the policy version in effect at the time. When the policy is amended, the amendment should be applied prospectively, with a clear cutover date, and the merchant should be able to demonstrate that no request was honored under a superseded policy without proper disclosure.

## Controls

Establish a price-match control matrix that maps each published policy version to its scope, exclusions, evidence requirements, and resolution form. Each price-match request should be logged with the request timestamp, the verification timestamp, the matched amount, and the resolution.

Technical controls should enforce: (1) the published policy is the sole source of price-match terms; (2) the verification system retains a timestamped record; (3) the matched price is calculated using the policy-version logic in effect at the time of the request; (4) the request record is retained with the policy-version reference; (5) the merchant can demonstrate that the policy was applied consistently across requests; and (6) any exception or denial is approved and recorded with the reason.

Monitor customer complaints, denial patterns, and regulatory inquiries about price match. Investigate patterns of denials that suggest the published policy was not followed, denials that lack the required evidence, or matches granted at inconsistent amounts.

## Validation evidence

Retain the published policy versions, the price-match request records, the verification records, the resolution records, and the policy-version reference for each request. The merchant should be able to reconstruct any historical request and demonstrate the policy version applied, the verification performed, and the resolution granted.

Sample testing should retrieve a sample of accepted and denied requests, confirm that the published policy was followed, confirm that the verification evidence was retained, and confirm that the matched price was calculated using the correct policy-version logic.

## Failure modes and correction

Common failures include a published policy that does not match the operational verification process; a verification process that cannot produce a timestamped record of the competitor's price; a denial that is not supported by a documented exception; a price-match amount that is inconsistent with the policy's stated formula; a policy amendment that is applied retroactively; and a price-match representation made in connection with a credit sale that is not reflected in the credit disclosures.

When a defect is identified, identify the affected requests by date range and policy version. Refund the price-match amount where the published policy was not honored. Update the policy text and the verification process so that the corrected treatment is consistently applied. For systemic defects, escalate to qualified counsel and conduct a bounded lookback.

## Limitations

This article addresses the operational and evidence controls for a voluntary price-match policy and is not a substitute for Regulation Z's full credit-disclosure analysis, the FTC Act's unfair-or-deceptive-practices framework, or state-specific "low-price guarantee" rules. The Regulation Z framing here is structural and is not a determination that any specific price-match policy is a credit transaction.

## Canonical sources

- Electronic Code of Federal Regulations, **12 CFR Part 1026 (Regulation Z, Truth in Lending)** for the adjacent conspicuous-disclosure framing used in consumer representations: https://www.ecfr.gov/current/title-12/chapter-X/part-1026
- Consumer Financial Protection Bureau, **Rules and policy**: https://www.consumerfinance.gov/rules-policy/
- Federal Trade Commission, **Rules and policy** (general unfair-or-deceptive-practices baseline applied to price-match representations): https://www.ftc.gov/legal-library/browse/rules
