# uk-online-safety-act-platform-duties-2026

**Issue:** The UK Online Safety Act 2023 moved from statute to live regulation in under two years: illegal-content duties became enforceable on 17 March 2025, Ofcom's Protection of Children codes and "highly effective age assurance" expectations landed on 25 July 2025, and 2026 is the first full enforcement year, with Ofcom estimating that well over 100,000 user-to-user and search services are in scope — including small forums, comment sections, and search front-ends that never considered themselves platforms. The duties are systems duties: proportionate risk assessment, moderation and reporting tooling, appeals, record-keeping, and transparency disclosures, all evidenced to Ofcom on demand, with fines up to GBP 18 million or 10 percent of worldwide revenue for failure.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Duty Timeline And In-Scope Services

1. **Scope is functional, not corporate.** Any user-to-user service (chat, comments, profiles, uploads) with a significant number of UK users, or that is capable of being used in the UK by individuals, is in scope; search services are separately in scope, so a product with just a support forum still owes duties.
2. **Illegal-content risk assessment first.** Services had to complete their illegal-content risk assessment by 16 March 2025 before duties took effect on 17 March 2025; the assessment is a living document that must be updated when risks materially change, not a one-time artifact.
3. **Children's access assessment.** Services likely to be accessed by children completed child-risk assessments on the January-July 2025 schedule, with children's safety duties enforceable from 25 July 2025; concluding children cannot access your service requires evidence of highly effective age assurance, not a self-declared date-of-birth field.
4. **Exempt categories are narrow.** Internal business communication tools, one-to-one email/SMS/MMS, and limited editorial content are the main carve-outs; a community feature bolted onto a SaaS product is not exempt just because the core product is B2B.

## Illegal Content Duties

1. **Priority offences drive systems.** The offences specified by Secretary of State regulations (terrorism, CSAM, trafficking, fraud including phishing and scam ads, threats and incitement) set the moderation floor: proportionate measures to minimize their presence and dissemination and swift takedown once notified.
2. **Terms of service as a compliance surface.** Terms must clearly set out how the service handles illegal content and complaints, and Ofcom can enforce against services that do not operate their own stated policies — so publish only enforcement logic you actually ship.
3. **Reporting and redress routes.** Users and affected persons need accessible reporting and appeal mechanisms, with human review of content and of account-level actions (suspension, bans), and decisions communicated with reasons; these are product features with SLAs, not mailbox promises.
4. **Proactive technology expectations.** For public channels, Ofcom's illegal-content codes expect use of automated detection (hash matching, URL blocking against trusted lists like the IWF and Project Sunflower feeds, keyword classifiers) calibrated to risk; for private channels, technology can only be mandated by direction on a case-by-case basis.
5. **Fraud duties hit ads and profiles.** Paid-for fraudulent adverts and impersonation via verified-lookalike profiles are in scope, requiring advertiser identity checks and profile-verification signals — duties that fall on the payments and identity layers, not just moderation.

## Children's Safety And Age Assurance

1. **Highly effective age assurance.** Where children are likely to access the service, the operator must use age assurance that is highly effective in correctly identifying whether a user is a child — face-based age estimation, ID-document verification with on-device deletion, mobile-network age checks, or credit-card age checks; Ofcom's 2026 age-assurance report scrutinizes deployment quality, and self-declaration alone is treated as ineffective for higher-risk services.
2. **Highly effective versus privacy-protective.** Ofcom's guidance requires age assurance to be privacy-protective and proportionate — prefer vendors that do data minimization and deletion proofs, and write a data-protection assessment of the age-check pipeline itself.
3. **Child-safe defaults.** If children are allowed, default settings must be safe: filtering harmful content categories, disabling direct messaging from strangers, geolocation off by default, and recommender systems tuned to reduce risks identified in the child-risk assessment.
4. **Adult-content age gates.** Services publishing pornography faced the Part 5 age-verification duty from July 2025, enforceable by Ofcom with the same penalty ceiling — a stricter standard than the general children's duties and a common trigger for smaller communities.

## Categorization Thresholds

1. **Category 1 user-to-user.** Services exceeding 7 million monthly UK users carry extra duties: user-empowerment tools (filtering, blocking of content from unverified users), transparency about enforcement against their own terms, and complaints about how the service treats lawful-but-harmful content.
2. **Category 2A search.** Search services above the 7 million threshold face additional risk-assessment duties including about health and civic content in search results.
3. **Category 1A/2A best endeavours.** The largest services (over 45 million UK users) must use best endeavours to assess and mitigate risks around civic discourse and journalistic content — the first time the Act reaches content ranking politics.
4. **Threshold monitoring.** User-count metrics are computed by Ofcom's categorization rules, not marketing numbers; instrument UK-user measurement with the same rigor as billing so a category jump (and its new duties) does not arrive unannounced.

## Enforcement Evidence And Transparency

1. **Penalty ceiling.** Fines reach the greater of GBP 18 million and 10 percent of qualifying worldwide revenue, plus business-disruption measures including service blocking for persistent non-compliance — board-level exposure that justifies an evidence program.
2. **Information notices bind.** Ofcom can demand documents, data, and answers under statutory notice; maintaining a compliance register (risk assessments, moderation stats, appeal outcomes, training records, tech-deployment configs) means responses take days, not panic archaeology.
3. **Transparency reporting duties.** Services must produce transparency information of Ofcom-prescribed form (notice-and-action volumes, automated-detection usage, appeal reversal rates) on request; the metrics pipeline must reconcile with internal moderation dashboards.
4. **Senior-manager criminal exposure.** Providing information that is false or misleading in response to an Ofcom information notice is an offence attributable to senior managers, so route regulator-facing data through a validated reporting path, not ad-hoc spreadsheets.
5. **Regulator tracker.** Ofcom's codes continue to roll out (fraud codes, further categorization reviews, periodic technology notices); assign an owner to track new codes, because duties attach on fixed dates after publication.
