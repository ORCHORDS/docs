# dsa-online-platform-obligations-2026

**Issue:** The EU Digital Services Act (Regulation (EU) 2022/2065) applies to far more platforms than the DMA: every intermediary service with EU users — not just designated gatekeepers — carries duties that phased in fully on 17 February 2024, and the compliance machinery keeps expanding (harmonised transparency-report templates from the November 2024 implementing regulation, statements of reasons flowing to the Commission's public database, a July 2025 delegated act on researcher data access). Teams that treated the DSA as a VLOP-only concern discover mid-enforcement that notice-and-action, statements of reasons, trader tracing, and recommender transparency apply to ordinary hosting services and platforms, with fines up to 6% of global annual turnover. This article maps the obligations that bite a non-VLOP online platform and the systems they require. It complements `dma-platform-designation.md` (gatekeepers) and `age-gating.md` (minor protection).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Who is caught and at which tier

1. **Tiered scope by service type.** Duties stack from "intermediary services" (transmission/caching — light information duties), through "hosting services" (notice-and-action and statements of reasons), to "online platforms" (disseminating content to the public adds complaints, ads, recommender, and trader duties); each layer includes all lower layers.
2. **Extraterritorial reach via EU users.** The DSA applies to any provider offering services to recipients in the EU, regardless of establishment; non-EU providers must designate an EU legal representative or face enforcement through their national Digital Services Coordinator.
3. **VLOP is a separate, higher tier.** The Commission designates very large online platforms/search engines at 45 million average monthly active EU recipients, adding risk assessments, independent audits, and ad repositories; ordinary platforms must still count and report MAU figures so tier changes are detected, not discovered.
4. **The 2022/2024 phasing has fully landed.** All-intermediary duties applied from 16 November 2022; hosting and platform duties from 17 February 2024 — including marketplace trader-tracing under Art. 30, which took effect 17 February 2024 ([Pinsent Masons](https://www.pinsentmasons.com/out-law/analysis/kyc-the-eu-digital-services-act-adds-platforms-dac7-duties)).
5. **Penalties scale globally.** Non-compliance risks fines up to 6% of worldwide annual turnover plus periodic penalties, enforced by the Digital Services Coordinator of the member state of establishment (or main establishment for non-EU providers).

## Content-moderation machinery

1. **Notice-and-action mechanism (Art. 16).** Individual users must have an easy, publicly accessible way to flag specific items of illegal content, and the platform must process such notices diligently and without delay — a real queue with SLAs, not an inbox.
2. **Statements of reasons (Art. 17).** Every restriction of specific content or account (removal, demotion, disabling of access, suspension, monetisation cuts) must be communicated to the affected user with a statement of reasons, the ground for restriction, and information on redress options.
3. **SoR feed to the Commission database (Art. 24(5)).** Online platforms must submit all statements of reasons in a machine-readable format to the public [DSA Transparency Database](https://transparency.dsa.ec.europa.eu/) — an engineering obligation with an [API and schema](https://transparency.dsa.ec.europa.eu/page/api-documentation) that must be integrated into the moderation pipeline.
4. **Internal complaint-handling (Art. 20).** Users affected by moderation decisions get a right to complain internally, with the platform required to reply and inform them of out-of-court dispute-settlement options (Arts. 20–21); complaint volumes and outcomes feed the transparency report.
5. **Measures against misuse (Art. 23) and trusted flaggers (Art. 22).** Platforms must act against notices submitted abusively and suspend recidivist users who persistently manifestly infringe the law, while notices from Commission-appointed trusted flaggers must be processed with priority.

## Marketplace and trader-tracing duties

1. **Know Your Business Customer (Art. 30).** Platforms allowing consumers to conclude distance contracts with traders must collect and reliably verify trader identity, contact, payment, and establishment information **before** enabling selling, and re-verify annually for sellers presenting as businesses (full text at [DSA Art. 30](https://www.eu-digital-services-act.com/Digital_Services_Act_Article_30.html)).
2. **Compliance by design (Art. 31).** The marketplace interface must be designed so traders cannot circumvent the Art. 30 collection — "sell" buttons, listing flows, and checkout all have to enforce the KYBC gate rather than trusting profile fields.
3. **Consumer information on illegal products (Art. 32).** When a platform becomes aware that a purchased product or service was illegal, it must inform affected consumers (including recalls and, where relevant, trader identity); that requires purchase-to-notification plumbing, not a policy document.
4. **Random checks.** Online marketplaces must perform random checks on products and services offered via their services against available information, and prioritise suspicious traders — the checks and their rationale need to be logged as evidence.
5. **Overlap with DAC7 KYC.** The same seller onboarding data largely satisfies DAC7 tax due diligence (see `dac7-platform-seller-tax-reporting.md`); build one verified-seller profile serving both regimes instead of two parallel KYC silos — vendor analyses ([Moody's](https://www.moodys.com/web/en/us/kyc/resources/insights/know-your-business-5-obligations-relating-digital-services-act.html)) treat them as a combined programme.

## Transparency, advertising, and recommenders

1. **Harmonised transparency reports (Art. 15).** Platforms publish periodic transparency reports on content moderation, orders received, complaints, and automated-detection accuracy; the November 2024 implementing regulation fixed a common template, format, and timing, with first harmonised reports already due through 2025–2026 ([Global Policy Watch](https://www.globalpolicywatch.com/2024/11/european-commission-adopts-implementing-regulation-on-dsa-transparency-reporting-obligations/)) — the report is a data-engineering export from the moderation and order queues, so instrument those queues for it from day one.
2. **No dark patterns (Art. 25).** Online interfaces must not deceive, manipulate, or materially distort users' decisions — cancel flows, consent flows, and "are you sure" friction are all in scope, which ties into the banner patterns covered by `gdpr-cookie-consent-implementation.md`.
3. **Advertising transparency (Art. 26).** Ads must be clearly identifiable as such, presented on request with the parameters used for targeting, and ads based on GDPR special-category data (health, politics, sexual orientation) are banned outright.
4. **Recommender transparency (Art. 27).** Platforms must disclose the main parameters used by recommender systems and the options for users to modify them; keep a public, versioned disclosure page so the described parameters never drift from the deployed ranking model.
5. **Minors and researcher access.** Profiling-based advertising to known minors is prohibited (Art. 28, with age-assurance hooks covered in `age-gating.md`), and vetted researchers gain data-access rights under Art. 39, with the Commission's 2 July 2025 delegated act specifying templates and procedures ([Commission](https://digital-strategy.ec.europa.eu/en/news/commission-adopts-delegated-act-data-access-under-digital-services-act)) — plan for structured data extracts now.
