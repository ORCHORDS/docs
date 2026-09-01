---
title: "Customer Sentiment Trend"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Customer Sentiment Trend

## Purpose

Define how customer-sentiment signals from surveys, chat, messaging, voice, social posts, app store reviews, and similar channels are aggregated, weighted, validated, and acted on, so that trends are visible to the right teams without being misread as ground truth, and so that downstream actions remain proportionate.

## Scope

This article covers the collection, classification, weighting, and reporting of sentiment signals drawn from customer interactions and from public customer-to-company or customer-to-customer communications about the company's products and services. It covers both automated (model-based) and human-rated sentiment. It does not govern individual complaint handling (which has its own policy), nor does it dictate which teams receive which signals; it sets the rules for the data and the alerts.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Source reliability

Each signal source MUST be classified by reliability before it enters a trend report. Reliability ratings SHOULD consider sample size, response rate, sampling bias, channel constraints, language coverage, and whether the rater is the customer, an agent, or an automated model. A model-based sentiment score MUST be treated as a derived signal, not as a primary measurement, and the model version, prompt template, and language coverage MUST be logged with the score. Free-text complaints on public forums MUST be treated as evidence of feeling, not as a representative cross-section of all customers. Survey responses MUST be reported with the response rate and the sampling frame.

## Weighting

Aggregation SHOULD weight signals by their reliability rating, by the customer's prior interaction history only where documented and lawful, and by recency. Weighting MUST NOT be calibrated to amplify or suppress protected characteristics, demographic attributes, or individual customers. Weighting schemes MUST be documented, version-controlled, and reproducible; a reviewer MUST be able to re-run an aggregation and obtain the same trend. Weighting MUST NOT be adjusted in response to a single inconvenient trend without a documented reason and a review.

## Validation

Before a trend is reported outside the support function, it SHOULD be validated against at least one independent signal — for example, ticket volume, complaint volume, deflection rate, first-contact resolution, or product telemetry — when such a signal exists. A model-derived trend that no other channel corroborates SHOULD be flagged as unconfirmed. A trend that is consistent across multiple channels SHOULD be considered elevated and acted on accordingly. Validation SHOULD look for survivorship bias (only the loudest customers are heard), response bias (only the most satisfied or most dissatisfied respond), and channel bias (a trend in app-store reviews may not generalize to all customers).

## Alert thresholds

Alerts SHOULD be calibrated against a baseline rather than against absolute counts, so that a normal seasonal variation does not produce alerts and an unusual variation does. Thresholds MUST be reviewed at the documented review cadence, after any material change in traffic mix, after any change in the survey instrument, and after any change in the weighting scheme. Alert receivers SHOULD include enough context to act — the time window, the affected queue or product, the comparison baseline, and the contributing sources — and SHOULD NOT require the receiver to consult another tool to understand the alert.

## Privacy

Sentiment processing MUST respect the same privacy rules as the source data. Survey responses MUST be processed according to the consent the customer gave. Public posts MUST be processed for the legitimate purpose of understanding customer experience, MUST be limited to the content needed, and MUST NOT be republished in a way that identifies the customer without a lawful basis. Aggregation MUST NOT produce identifiably small groups (for example, a sentiment score for a single identifiable employee or a single identifiable demographic cluster) without applying additional safeguards.

## Action and follow-up

A confirmed trend SHOULD trigger a documented action — for example, a quality review, a product feedback loop, a policy update, a knowledge-base update, an accessibility investigation, or an escalation to a specialist function. The action SHOULD be proportionate to the magnitude and direction of the trend and SHOULD be recorded with an owner and a target completion date. The absence of action on a confirmed trend MUST itself be documented with a reason.

## Reporting

Trend reports SHOULD be produced at the cadence set by the support-lead function and SHOULD be available to quality, product, accessibility, and privacy functions as appropriate. Reports MUST distinguish automated-derived signals from human-rated signals, MUST show sample sizes and response rates for surveys, and MUST include a plain-language summary that an executive reviewer can act on without consulting the underlying data.

## Canonical sources

- ISO 20252:2019, Market, opinion and social research, including insights and data analytics — Vocabulary and service requirements, https://www.iso.org/standard/73600.html
- ESOMAR/ICC International Code on Market, Opinion and Social Research and Data Analytics, https://esomar.org/code
- W3C Recommendation, *Web Content Accessibility Guidelines (WCAG) 2.2*, https://www.w3.org/TR/WCAG22/
- European Data Protection Board, *Guidelines on Automated individual decision-making and Profiling*, https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-automated-individual-decision-making-and-profiling_en
