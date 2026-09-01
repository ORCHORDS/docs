---
title: "Data-Driven Personalization Limits"
owner: "Marketing Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Data-Driven Personalization Limits

## Purpose

Data-driven personalisation uses observed or inferred attributes to tailor marketing content, offers, or experiences to an individual. Personalisation can improve relevance, but it can also entrench bias, expose sensitive attributes, and erode the trust that audiences place in marketing. This article sets out the lawful basis, transparency, opt-out, and sensitive-attribute boundaries that apply to data-driven personalisation. The objective is to permit beneficial personalisation while preventing the use of personalisation as a vehicle for discrimination, undisclosed inference, or privacy-invasive inference.

## Scope

This article applies to any marketing activity that uses personal data to select, prioritise, generate, or present content, offers, recommendations, or experiences for an identified or identifiable individual. It covers email personalisation, web personalisation, in-product messaging, push notifications, paid-media audience selection, dynamic creative, AI-generated copy variations, and lookalike modelling. It applies regardless of the source of the data (first party, second party, third party, or inferred).

## Requirements

- Marketing MUST identify and document the lawful basis for every personalisation activity. The basis MUST be one of the recognised bases in the applicable jurisdiction and MUST be recorded in the Campaign Approval Governance record.
- Where personalisation relies on consent, Marketing MUST obtain affirmative, granular consent that names the categories of data used and the purpose of personalisation. Bundled or inferred consent is not acceptable.
- Marketing MUST provide a clear, accessible notice at every personalisation point that explains what is personalised, on what basis, and how the audience can opt out.
- An opt-out mechanism MUST be offered and MUST be honoured at the level of the personalisation signal, not merely at the level of the channel. Opting out of personalisation MUST stop the use of all personalisation signals for that individual.
- Sensitive attributes (health, political opinion, religious belief, trade union membership, genetic or biometric data, sexual orientation, philosophical belief) MUST NOT be used as personalisation signals except where lawful basis explicitly permits and a documented exception is approved by the Marketing Lead and the Privacy function.
- Inferred sensitive attributes MUST be treated as sensitive regardless of whether the underlying data is sensitive. Marketing MUST NOT use proxies that substantially correlate with sensitive attributes.
- Personalisation that produces automated decisions with legal or similarly significant effects (for example, differential pricing, eligibility for credit, employment screening) MUST be subject to a Data Protection Impact Assessment and a documented review before launch.
- Marketing MUST exclude audiences known to be vulnerable (minors, individuals experiencing financial difficulty, individuals in crisis) from personalisation patterns that could exploit that vulnerability.
- Personalisation models MUST be tested for disparate impact across protected characteristics; material disparities MUST be remediated before launch and monitored during flight.
- Personalisation data MUST be retained only for the period necessary for the stated purpose; the period is documented in the Marketing Data Retention schedule.
- The model inputs, version, training data class, and recertification date MUST be recorded in a model card that is auditable.
- Where personalisation is performed by a third party, the vendor MUST be bound by the Marketing Vendor Governance policy and a contractual prohibition on use of the data for any purpose other than the documented personalisation.

## Workflow

1. The personalisation owner drafts the campaign record with the audience, signals, lawful basis, vendor, model card, and exclusion list.
2. The Privacy function reviews the lawful basis, sensitive-attribute list, and DPIA trigger; the Legal function reviews any differential treatment, automated-decision impact, or jurisdictional concerns.
3. The Bias and Disparate Impact reviewer evaluates the model and audience design for disparate impact and recommends adjustments where required.
4. The campaign is launched only after all reviews have cleared and the campaign record is signed by the Marketing Lead.
5. During flight, the personalisation is monitored for disparate impact, opt-out volume, complaint rate, and accuracy; signals are reviewed at the cadence set in the record.
6. At recertification, the model card is updated and the personalisation is reviewed against current law and policy.

## Controls

- The model card is versioned and stored with the campaign record; changes require re-review.
- A weekly audit reconciles personalisation signals against the consent registry; missing or expired consent triggers a pause.
- The Bias and Disparate Impact reviewer operates independently of the campaign team and reports to the Privacy function.
- Cross-border personalisation is reviewed for jurisdiction-specific restrictions; some jurisdictions restrict certain personalisation patterns, including price personalisation.

## Canonical sources

- European Data Protection Board, "Guidelines on Automated individual decision-making and Profiling (wp251rev.01)" — https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-automated-individual-decision-making-and-profiling_en
- European Commission, "Regulation (EU) 2016/679 (GDPR)" — https://eur-lex.europa.eu/eli/reg/2016/679/oj
- California Office of the Attorney General, "California Privacy Protection Agency — Automated Decisionmaking Regulations" — https://oag.ca.gov/privacy/ccpa
- U.S. Federal Trade Commission, "Using Artificial Intelligence and Algorithms — Fairness and Avoiding Bias" — https://www.ftc.gov/business-guidance/small-businesses/using-artificial-intelligence