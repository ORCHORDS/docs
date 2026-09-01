# Search Keyword Brand Bidding Governance

## Scope

This control governs paid-search bidding strategies that involve competitors' brand names, the brand names of partners, the names of protected marks, trademarked terms, personal names, common-law trademarks, generic terms subject to keyword bidding disputes, and the firm's own brand names. It applies to search advertising on general search engines, in-app search, retail search, marketplace search, social-platform search, video-platform search, and AI-assistant discovery surfaces; and to bidding on those keywords as a query term, as a negative keyword set, or as a target keyword in audience or product-feed targeting.

The governing reference is the FTC's framework on patent assertion entities, as articulated in the FTC's policy work on entities whose principal activity is the assertion of patent claims, used here by analogy for the operational discipline that the FTC expects of firms that take action against others. Although the FTC's PAE framing addresses patent assertion rather than trademark bidding, the principles are analogous: a firm that monetizes another's name as a search keyword must evaluate the legal posture of the practice, document the basis on which it proceeds, and be prepared to defend or cease the practice. Trademarks are also addressed by Lanham Act false-advertising and trademark-infringement law; the FTC's advertising-substantiation framework reinforces the principle that the public-relations and legal posture of a competitor's name as a search term must be defensible.

## Workflow or implementation guidance

The search-keyword bidding workflow proceeds in six steps.

1. Identify the keyword universe. The keyword universe is the recorded list of brand terms the bidding practice covers, with the mark owner, the class of mark (registered, common-law, personal name, descriptive term, generic), the jurisdiction in which the mark is asserted, and the campaign or owner that uses the term.
2. Decide on the posture for each term. For each term, the posture is one of: bid, do not bid, bid defensively only (to claim brand terms the firm owns), bid negatively to block broad match from triggering, monitor without bidding, or escalate for legal review. The decision is recorded with the basis.
3. Configure the platform. Keyword lists are configured in the bidding platform with the chosen posture. Negative keyword lists are configured. Brand-defense campaigns are configured separately from non-brand campaigns, with separate budgets, separate ad copy, and separate landing pages.
4. Review ad copy and landing pages. Ad copy that uses a competitor's name is reviewed for the jurisdiction's tolerance for comparative or "vs." ads, for required disclosures (sponsored labeling, source identification), and for accuracy claims that the campaign can substantiate.
5. Set alerts. Alerts are configured for changes to the brand universe (a new mark, a new jurisdiction, a new enforcement action against the firm or against an industry peer), and for platform policy changes (such as a search engine updating its trademark policy).
6. Audit. Periodically (and after any incident), the keyword universe, the platform configuration, the ad copy, and the landing pages are reviewed against the current posture, the current policy, and the current law.

## Controls

The controls in this workflow are designed to ensure that bidding on competitor brand terms is a defensible, documented business practice rather than an ad hoc decision that accumulates.

- A keyword universe record names the term, the mark owner (or "self" for own marks), the class of mark, the jurisdiction, the campaign, and the posture.
- A posture change requires a documented basis, an approver, and an effective date. Posture changes are recorded for the audit trail.
- Negative keyword lists are reviewed when the brand universe changes, when a new broad-match trigger is observed, when the platform reports an unexpected match, and after any platform policy change.
- Ad copy using a competitor's name is flagged for legal review before publication, and each subsequent revision is reviewed. The review covers required disclosures (sponsored label, source, comparison language), accuracy substantiation, and appropriateness to the platform.
- Defensive bidding on the firm's own brand is treated distinctly: a budget, a separate campaign structure, and ad copy subject to the firm's brand guidelines.
- An escalation path exists for notifications of trademark complaints, platform removals, or regulator inquiries. Each notification is recorded with the response and the disposition.
- The campaign record preserves the chosen posture, the version of the brand universe, the legal-reviewer's name, and the date.

## Validation evidence

Evidence is collected at each phase.

- The brand universe record: terms, owners, classes, jurisdictions, current posture, and last review date.
- The platform configuration: keyword list, negative keyword list, brand-defense campaign, and ad copy version. Snapshots are taken at each change.
- The legal review record: each ad copy and each landing page reviewed, the reviewer, the date, and the basis for approval or change.
- The incident log: trademark complaints received, platform removals, regulator inquiries, and the disposition.
- The periodic audit summary: a sample of brand-universe terms reviewed, the current posture, the change history since the previous audit.

## Failure modes and correction

Frequent failures include bidding on a competitor's brand term without a recorded basis, configuring the keyword list once and treating it as static, allowing broad match to trigger against a brand term that was not meant to be targeted, drafting ad copy that uses a competitor's name and makes claims that cannot be substantiated, bidding on the firm's own brand without a brand-defense budget, and ignoring platform changes to trademark policy. Other failures include conflating competitive targeting with harassment of a specific competitor and continuing to bid after a cease request that the team should have honored.

Correction begins by pausing the affected bidding. The keyword universe is reviewed for affected terms and posture decisions are re-evaluated. Where the defect is a configuration error, the campaign structure is corrected (separate campaign for brand-defense, broader negative keyword list, restricted match types). Where the defect is an ad-copy error, the copy is updated or removed and the affected landing page is reviewed. Where the defect is a legal posture issue, the bidding is paused and referred to counsel. Each correction is logged; the campaign record is updated; and the corrective action is reviewed in the next periodic audit.

## Limitations

This control does not adjudicate trademark infringement or dilution under the Lanham Act, it does not determine whether a particular use of a competitor's name in ad copy is permissible in a particular jurisdiction, and it does not preempt platform trademark-policy enforcement. Where a search engine's policy treats bidding on a competitor's brand as impermissible, the platform policy takes precedence. This control does not cover every advertising surface (for example, out-of-home, connected-TV, or audio); it focuses on search and on the analogous query-input surfaces.

## Canonical sources

- **Primary authority 1 — Federal Trade Commission, Patent Assertion Entities (PAE) Activity (policy portal):** [https://www.ftc.gov/enforcement-policy/patent-assertion-entities](https://www.ftc.gov/enforcement-policy/patent-assertion-entities)
- **Primary authority 2 — Federal Trade Commission, Online Advertising and Marketing (business guidance):** [https://www.ftc.gov/business-guidance/advertising-marketing/online-advertising-marketing](https://www.ftc.gov/business-guidance/advertising-marketing/online-advertising-marketing)
