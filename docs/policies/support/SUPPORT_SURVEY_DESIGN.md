---
title: "Support Survey Design"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Support Survey Design

## Purpose

Define how customer-satisfaction and experience surveys are designed so that they produce defensible, comparable, useful results, do not bias customers toward favorable or unfavorable responses, do not collect personal data beyond what is needed, and remain accessible to customers using assistive technology or alternative languages.

## Scope

This article covers surveys sent after a support interaction — including transactional surveys (sent at the close of a case), relational surveys (sent periodically to measure overall relationship), and event-driven surveys (sent after an incident, a complaint, or another significant event). It covers surveys delivered by email, in-product, messaging, voice IVR, and chat. It does not cover ad-hoc user research, which has its own consent and ethics rules, although it draws on the same bias and accessibility principles.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Question design

Survey questions MUST be written in plain language, MUST avoid leading or loaded wording, MUST avoid double-barrelled questions, and MUST avoid jargon the customer is unlikely to know. Questions MUST NOT presuppose that the customer had a particular experience. For example, a survey about a phone interaction MUST NOT ask the customer to rate the agent's tone if the customer never reached an agent. Questions SHOULD be specific (about the interaction just completed) rather than general (about the company overall), unless the survey is explicitly relational.

Rating scales MUST be balanced, MUST have a defined midpoint, and MUST have labels at every point so that the customer is not forced to interpret numeric anchors. Free-text fields MUST be optional and MUST NOT be required for submission. The survey SHOULD be short enough that a customer with limited time or limited data plan can complete it; length SHOULD be justified against the value of each question.

## Bias controls

The survey SHOULD be designed to minimize common biases:

- recency bias: ask about the overall interaction, not only the most recent message;
- primacy bias: vary the order of answer options where the option order could plausibly affect results;
- acquiescence bias: balance positively and negatively worded items;
- non-response bias: track and report response rates and sampling frame so that the results can be interpreted;
- social-desirability bias: do not imply that a particular answer is preferred;
- channel bias: do not assume the customer used the same channel as the survey delivery channel.

The survey MUST NOT be designed to elicit a particular favorable rating. For example, it MUST NOT include "trap" questions whose purpose is to flatter the agent or to confirm a predetermined conclusion. The survey design SHOULD be reviewed for bias at the documented cadence and SHOULD be revised when evidence of bias emerges.

## Sampling and targeting

Survey sampling SHOULD be defined in advance, including the population sampled (all customers after interaction, a stratified sample, a randomly selected control group), the timing (immediately after interaction, after a delay), the frequency cap per customer, and the exclusion criteria (for example, customers who have asked not to be surveyed, customers in jurisdictions where the survey would require additional consent). Sampling changes SHOULD be documented and SHOULD NOT be made to inflate a particular metric in the short term.

Customers MUST NOT be surveyed more often than the documented cap. Customers who have opted out of marketing or research communications MUST NOT be sent surveys that the company's policy treats as research unless a documented, lawful basis applies. Customers who have asked not to be contacted MUST NOT be contacted for a survey even if the cap allows it.

## Opt-in and opt-out

Customers MUST be told, at the point of the survey, what the survey is for, who will see the results, how long the data is retained, and how to opt out of future surveys. Opt-out MUST be honored promptly and MUST persist across the customer's relationship with the company unless the customer opts back in. Opt-in (where used) MUST be specific, informed, and freely revocable. The company MUST NOT condition service on the customer completing a survey.

## Privacy and data minimization

Surveys MUST collect only the data needed. Personal identifiers SHOULD be separated from survey responses where the survey analysis does not require the linkage, and the linkage SHOULD be removed or destroyed as soon as the analysis is complete. Survey responses MUST be retained only as long as needed for the stated purpose and MUST be deleted or anonymized when the purpose ends. The survey MUST NOT ask for sensitive categories of personal data unless there is a documented, lawful basis and the customer is told why. Survey data MUST be handled according to the privacy notices the customer has seen, and any change in the purpose MUST trigger a renewed consent or a stop in collection.

## Accessibility and language

Surveys MUST be designed to meet the accessibility standard the company has committed to (for example, WCAG 2.2 Level AA). They MUST be screen-reader friendly, MUST have adequate color contrast, MUST not rely on color alone, MUST support keyboard navigation, and MUST provide text alternatives for any non-text content. Surveys SHOULD be available in the languages the company has committed to support, with translation reviewed by a qualified translator.

## Validation

Before a survey is deployed at scale, it SHOULD be cognitively tested on a small sample of customers representative of the population, SHOULD be reviewed for bias, SHOULD be reviewed for accessibility and language, and SHOULD be reviewed by privacy and legal functions. After deployment, the survey SHOULD be monitored for response patterns, completion time, drop-off, free-text sentiment, and consistency with other signals. Material changes in the survey instrument SHOULD be documented with a version, an effective date, and a brief description of the change, and SHOULD NOT be applied retroactively to historical data.

## Reporting

Survey results SHOULD be reported with the response rate, the sampling frame, the survey version, and the comparison baseline. Results SHOULD NOT be reported in a way that implies a higher or lower satisfaction than the underlying data supports. Aggregate results MUST be checked against re-identification risk before publication, and any subgroup with a small population SHOULD be suppressed or flagged.

## Canonical sources

- ISO 20252:2019, Market, opinion and social research, including insights and data analytics — Vocabulary and service requirements, https://www.iso.org/standard/73600.html
- ESOMAR/ICC International Code on Market, Opinion and Social Research and Data Analytics, https://esomar.org/code
- W3C Recommendation, *Web Content Accessibility Guidelines (WCAG) 2.2*, https://www.w3.org/TR/WCAG22/
- Plain Language Action and Information Network (PLAIN), https://www.plainlanguage.gov/
