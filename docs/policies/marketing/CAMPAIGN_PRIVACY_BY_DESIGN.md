---
title: "Campaign Privacy By Design"
owner: "Marketing Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Campaign Privacy By Design

## Purpose

Privacy-by-design requires that privacy considerations are integrated into every marketing campaign from conception through decommissioning rather than appended after launch. This article sets out the minimum requirements for data minimisation, lawful basis identification, retention, and approval that apply to any campaign that processes personal data. Adhering to these requirements reduces regulatory exposure, supports defensible responses to data-subject requests, and preserves trust with audiences, partners, and platforms.

## Scope

This article applies to every campaign, channel, and audience that processes personal data of natural persons, including identifiable pseudonymous identifiers, device identifiers, behavioural profiles, and inferred attributes. It applies whether the data is collected directly from the data subject, obtained from a third party, or derived by combining signals. It covers paid media, owned channels, joint campaigns with partners, and trials or pilots operated under a sandbox exception.

## Requirements

- Marketing MUST identify and document the lawful basis for each processing activity in a campaign before launch; the basis MUST be recorded in the Campaign Approval Governance record alongside the audience definition and the data sources used.
- Marketing MUST collect the minimum set of attributes necessary to deliver, measure, and optimise the campaign; convenience, future-proofing, or speculative analytics are not acceptable justifications for additional collection.
- Where a campaign relies on consent, Marketing MUST obtain affirmative, granular, informed, and freely-given opt-in and MUST record the consent artefact (timestamp, channel, scope, version of the notice shown). Pre-ticked boxes, bundled consent, and inferred consent are prohibited.
- Marketing MUST publish a privacy notice at every collection point that names the controller, the lawful basis, the recipients, the retention period, and the data-subject rights applicable in the audience's jurisdiction.
- Sensitive attributes (health, political opinion, religious belief, trade union membership, genetic or biometric data, sexual orientation) MUST NOT be used for campaign targeting, segmentation, or personalisation unless an explicit documented exception is approved by the Marketing Lead and the Privacy function, and only where lawful basis permits.
- Retention periods MUST be set per purpose and recorded in the Marketing Data Retention schedule; data MUST be deleted or irreversibly pseudonymised at the end of the retention period, and the deletion MUST be verifiable.
- Data Subject Rights requests (access, rectification, erasure, restriction, portability, objection) MUST be honoured within the time limits set by the applicable law; campaign infrastructure MUST be technically capable of locating and acting on a request against the data it holds.
- Vendor processors MUST be bound by a written contract that meets the requirements of the Marketing Vendor Governance policy; sub-processors MUST be disclosed and approved.
- Marketing MUST conduct a Data Protection Impact Assessment (DPIA) or equivalent risk assessment for any campaign that involves large-scale profiling, automated decisioning with legal effect, systematic monitoring of public areas, or processing of children's data; the DPIA MUST be approved before launch.
- Privacy review is a hard gate in the Campaign Approval workflow; no campaign that processes personal data MAY be launched without a recorded privacy sign-off.

## Workflow

1. The campaign owner drafts a Campaign Approval Governance record that includes audience, channels, data sources, lawful basis, retention, vendors, and measurement plan.
2. The Privacy function reviews the record against the lawful basis catalogue and the DPIA trigger list; where a DPIA is required, the assessment is attached to the record.
3. Where consent is the lawful basis, the consent collection flow is tested end-to-end before launch; the consent artefact schema is confirmed and the storage location is documented.
4. The campaign is launched only after privacy sign-off is recorded; the sign-off MUST include the reviewer identity and the version of the record approved.
5. During the campaign, the privacy control list (consent logs, opt-out logs, vendor processing logs) is monitored at the cadence set in the campaign record.
6. At campaign close, retention triggers are evaluated against the Marketing Data Retention schedule and the data is deleted or pseudonymised on schedule.

## Controls

- The privacy review checklist is versioned and published; changes require Privacy function approval.
- A weekly job reconciles active campaigns against the consent registry; campaigns without a current consent artefact are paused pending review.
- Privacy incidents affecting marketing data follow the Marketing Incident Response policy; the privacy review record is updated with the incident reference and the corrective actions taken.
- The privacy review process is audited annually; findings are reported to the Marketing Lead and the Privacy function.

## Canonical sources

- European Data Protection Board, "Guidelines 4/2019 on Article 25 — Data Protection by Design and by Default" — https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-42019-article-25-data-protection-design-and-default_en
- European Commission, "Regulation (EU) 2016/679 (General Data Protection Regulation)" — https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Information Commissioner's Office (UK), "Privacy by design" — https://ico.org.uk/about-the-ico/media-centre/blog-privacy-by-design-and-default-the-ico-s-25-year-journey/
- California Office of the Attorney General, "California Consumer Privacy Act (CCPA)" — https://oag.ca.gov/privacy/ccpa