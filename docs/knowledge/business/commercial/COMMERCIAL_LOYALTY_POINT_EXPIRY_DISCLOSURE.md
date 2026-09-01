# Loyalty Point Expiry Disclosure

## Scope

This article covers the disclosure and recordkeeping controls that apply to loyalty programs, rewards programs, and points-based incentive programs offered to consumers, with particular attention to expiration, dormancy, forfeiture, and devaluation events that materially affect the economic value the consumer was led to expect. The article is anchored in the FTC's Endorsement Guides, 16 CFR Part 255, and the underlying Section 5 unfair-or-deceptive-practices principle that governs how a merchant represents program economics to consumers — both at enrollment and as program terms change over time.

The scope covers traditional retail loyalty programs, paid loyalty or membership programs, coalition or cross-brand programs, credit-card-linked rewards, and digital or app-based reward wallets. It does not address state-specific sweepstakes, contests, or gambling laws; consumer-credit rewards governed by Regulation Z; or employee compensation programs.

## Workflow or implementation guidance

Begin by inventorying every loyalty program the merchant operates and identifying for each: the value proposition communicated to the consumer, the unit of value (points, miles, tier credits, dollars), the accrual rule, the redemption rule, the expiration rule, the dormancy rule, the forfeiture rule, and the devaluation rule. Each rule should be expressed as a parameter that is independently governable rather than as a single bundled "terms and conditions" artifact.

Disclose the program economics in close proximity to the enrollment decision. The disclosure should state, in plain language, the conditions under which points expire, the conditions under which the consumer's account is treated as dormant or inactive, the conditions under which points may be forfeited, the conditions under which the program may be changed, and the process (if any) by which the consumer is notified before a change takes effect. For paid loyalty programs, the disclosure should also state the renewal, cancellation, and refund treatment consistent with the FTC Negative Option Rule, 16 CFR Part 425, where the paid loyalty arrangement meets the rule's definition of a negative-option feature.

Where points have a stated expiration, the merchant should provide reasonable advance notice before the expiration event, through a channel the consumer has affirmatively agreed to (email, SMS, app notification). Notice timing should be consistent with the consumer's reasonable expectation based on the program's stated terms; a 30-day minimum advance notice is a common baseline for points that have been accrued through consumer activity.

Where the program changes in a way that materially reduces previously accrued value (a devaluation), the merchant should consider the Section 5 unfair-or-deceptive baseline in 16 CFR Part 255 and the broader consumer-protection principle that a representation about program economics at enrollment creates expectations the merchant must honor or properly disclose in advance. A unilateral, mid-cycle devaluation with insufficient notice can render the original enrollment representation misleading.

For loyalty-program communications that constitute endorsements (for example, an influencer's post about a loyalty perk, or a brand-creator program), 16 CFR Part 255's general guidance on material connections and clear-and-conspicuous disclosure applies to the program's own communications as well.

## Controls

Establish a loyalty-program disclosure matrix that maps each program to the enrollment surface, the ongoing-communication surfaces, the expiration rule, the dormancy rule, and the devaluation rule. Each rule should be enforced by the loyalty platform rather than relying on operational manual review.

Technical controls should enforce: (1) points do not expire before the disclosed expiration date; (2) dormancy treatment is applied only after the disclosed dormancy period and only with the disclosed notice; (3) devaluation is communicated in advance with sufficient notice and through the disclosed channel; (4) the loyalty platform can produce a per-customer history of points balance, expiration events, dormancy events, and devaluation events; and (5) the program's enrollment terms and the program's actual treatment match.

Monitor consumer complaints, dispute volume, and regulatory inquiries about loyalty programs. Investigate patterns that suggest points are expiring sooner than disclosed, are being forfeited without notice, or are being unilaterally devalued.

## Validation evidence

Retain the program's enrollment disclosures, the disclosure versions presented to each enrolling consumer, the per-consumer points history (accrual, redemption, expiration, dormancy, forfeiture), the notice records, and the devaluation communications. For regulatory purposes, the merchant should be able to demonstrate that each consumer received the disclosed treatment.

Sample testing should reconstruct a sample consumer's history, confirm that the disclosed rules match the platform's actions, confirm that expiration events were preceded by the disclosed notice, and confirm that any devaluation was communicated in advance.

## Failure modes and correction

Common failures include disclosing a generous expiration rule and then implementing a tighter rule in the platform; dormancy treatment that triggers without the disclosed notice; unilateral devaluation that is communicated only after the fact; expiration of accrued points without any notice; loyalty-program terms that allow unilateral change "at any time" without a meaningful consumer-protection floor; and inconsistency between the disclosure text and the loyalty-platform configuration.

When a defect is identified, identify the affected consumers by program, enrollment cohort, and date range. Restore lost value where the disclosed treatment was not honored, and consider goodwill remediation for consumers who relied on the original disclosure. Update the disclosure text and the loyalty platform configuration so that the corrected treatment is consistently applied. For systemic defects, escalate to qualified counsel and conduct a bounded lookback.

## Limitations

This article addresses the disclosure and platform-enforcement controls surrounding loyalty program economics and is not a substitute for state-specific consumer-protection, unclaimed-property, or paid-membership laws. The Endorsement Guides framework is used here as a structural baseline for clear-and-conspicuous representation; it does not create a private right of action. Where a paid loyalty program is a "negative option" within the meaning of 16 CFR Part 425, the rule's specific affirmative-consent and disclosure requirements apply.

## Canonical sources

- Electronic Code of Federal Regulations, **16 CFR Part 255 (FTC Guides Concerning the Use of Endorsements and Testimonials in Advertising)**: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-255
- Federal Trade Commission, **The FTC's Endorsement Guides: What People Are Asking**: https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking
- Electronic Code of Federal Regulations, **16 CFR Part 425 (Negative Option Rule)** for the adjacent framework that applies to paid loyalty with negative-option features: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-425
