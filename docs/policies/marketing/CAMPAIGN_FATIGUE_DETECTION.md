---
title: "Campaign Fatigue Detection"
owner: "Marketing Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Campaign Fatigue Detection

## Purpose

Campaign fatigue is the measurable decline in audience responsiveness that occurs when an exposure surface, creative, or message is repeated beyond its useful attention window. Detecting fatigue protects deliverability, lowers cost per incremental outcome, and prevents complaint volume that can erode sender reputation and trigger platform or regulatory scrutiny. This article sets out the signal set, statistical thresholds, suppression behaviour, and recertification conditions that govern when a fatigued campaign is paused, refreshed, or reactivated.

## Scope

This article applies to paid digital media, organic social, email, in-product messaging, push notifications, and display placements operated by or on behalf of the Marketing organisation. It applies to direct response and brand campaigns that are tracked against response, engagement, or conversion signals. It does not govern brand awareness campaigns whose primary measurement is reach and where frequency is set by media-mix modelling; those follow the Brand Governance policy.

## Requirements

- Marketing MUST instrument every live campaign with frequency, exposure, and outcome signals sufficient to compute a fatigue score; the score MUST be reviewed at least weekly during active flight and at the close of every flight.
- Fatigue detection MUST combine at least one reach signal (impressions, sessions, or opens) and at least one response signal (click-through, conversion, assisted conversion, or reply rate). Single-signal fatigue detection is not acceptable because platforms vary in how they attribute repeat exposures.
- Marketing MUST define fatigue thresholds per channel and per audience segment before launch; default thresholds MUST be documented and SHOULD be tightened for narrow audiences, sensitive verticals, and regulated jurisdictions.
- A campaign MUST be flagged as fatigued when response rate per increment declines by at least 20 percent relative to the trailing two-week baseline AND complaint, unsubscribe, or negative-engagement rate increases by at least 10 percent relative to the same baseline.
- Marketing SHOULD use sequential testing or Bayesian shrinkage to avoid declaring fatigue on small samples; an audience with fewer than 1,000 exposures per week SHOULD NOT trigger automatic suppression on the basis of fatigue alone.
- When fatigue is detected, Marketing MUST either pause the affected audience-creative pair, rotate to a refresh pool, or apply a documented suppression window. Silent continuation without intervention is prohibited.
- Reactivation of a previously fatigued campaign requires a recertification record that names the creative, the audience, the prior fatigue window, the corrective action taken, and the new evidence supporting reactivation; this record MUST be retained per the Marketing Data Retention policy.
- Fatigue thresholds and suppression windows MUST be reviewed at least every 90 days; thresholds that have produced false positives or false negatives in the last cycle MUST be recalibrated before the next flight.
- Marketing MUST distinguish fatigue (declining marginal response) from saturation (all reachable audience members have been exposed); the two conditions require different responses and SHOULD be tracked with separate dashboards.
- Where fatigue affects regulated communications (financial promotions, health-related messaging, communications to minors), the recertification record MUST include legal review acknowledgement.

## Workflow

1. The campaign owner declares the fatigue thresholds and sample-size floors in the Campaign Approval Governance record before launch.
2. Daily and weekly analytics jobs compute fatigue indicators per audience-creative pair and publish them to the marketing measurement dashboard.
3. When a pair crosses a threshold, the campaign owner receives an automated alert and MUST choose one of: pause, refresh, or suppress. The chosen action and the timestamp are written back to the campaign record.
4. The owner documents the corrective action and, if the campaign is paused, the planned reactivation conditions.
5. After the suppression window ends, the owner submits a recertification request that cites the new evidence supporting reactivation; the request is reviewed against the original fatigue record.
6. The Marketing Lead confirms reactivation or extends the suppression window; the decision is logged with the same audit trail as the original approval.

## Controls

- Fatigue detection thresholds, alert configurations, and suppression windows are versioned in the marketing measurement system and changes are subject to peer review.
- The marketing analytics team performs a quarterly review of every threshold that fired in the prior quarter and reports false-positive and false-negative rates to the Marketing Lead.
- The recertification record is treated as a controlled artefact and is subject to the retention and audit obligations of the Marketing Data Retention policy.
- Where fatigue affects communications that intersect with privacy obligations (consent withdrawal, sensitive-attribute audiences), the privacy review attached to the original campaign MUST be consulted before reactivation.

## Canonical sources

- FTC, "FTC Issues Notice to Businesses: Don't Log on Empty Advertising Claims; Must Have Evidence Before Making Them" — https://www.ftc.gov/news-events/news/press-releases/2023/02/floor-claims-advertising-substantiation
- Interactive Advertising Bureau (IAB), "Viewability, Ad Fraud, and Brand Safety Measurement Guidelines" — https://www.iab.com/guidelines/viewability-ad-fraud-brand-safety-measurement-guidelines/
- W3C, "Web Content Accessibility Guidelines (WCAG) 2.2" — https://www.w3.org/TR/WCAG22/
- Information Commissioner's Office (UK), "Direct marketing code of practice" — https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/