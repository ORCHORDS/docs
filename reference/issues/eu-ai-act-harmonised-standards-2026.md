# eu-ai-act-harmonised-standards-2026

**Issue:** A team ships a high-risk AI system in the EU. The team reads the EU AI Act. The team needs to comply with Articles 9-15 (risk management, data, logging, transparency, oversight, accuracy, cybersecurity). The team finds the CEN-CENELEC JTC 21 standards are still drafts. The team is confused about presumption of conformity.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Act (Regulation (EU) 2024/1689) requires harmonised standards for high-risk AI to grant "presumption of conformity" with the legal requirements. As of mid-2026, the standards are still drafts; none is published in the Official Journal. The 2026 default: align with draft standards while preparing for final publication.

## Root cause

CEN-CENELEC JTC 21 was tasked with developing 10 harmonised standards for the AI Act. The original April 2025 deadline was missed; the new target is Q4 2026 for prioritised deliverables, with the amended Commission request expiring 28 February 2027. None of the standards grants presumption yet.

## The 10 requested areas

The Commission's standardisation request M/593 (now M/613 amendment) lists 10 areas.

1. Risk management
2. Governance and quality of datasets
3. Record keeping (logging)
4. Transparency
5. Human oversight
6. Accuracy
7. Robustness
8. Cybersecurity
9. Quality management
10. Conformity assessment

The 10 areas map to AI Act Articles 9-15 (the high-risk system requirements).

## The 8 JTC 21 deliverables (status as of June 2026)

| Deliverable | Title | AI Act article | Stage (June 2026) | Target |
|---|---|---|---|---|
| EN 18286 | Quality management system | Article 17 | Approval (Formal Vote) | Q4 2026 |
| prEN 18228 | AI risk management | Article 9 | Enquiry | Q4 2026 |
| prEN 18229-1 | Logging | Article 12 | Enquiry | Q4 2026 |
| prEN 18282 | Cybersecurity | Article 15 | Enquiry | Q4 2026 |
| prEN 18229-3 | Transparency, human oversight | Articles 13, 14 | Drafting | evolving |
| prEN 18283 | Bias in AI systems | Article 10 | Drafting | evolving |
| prEN 18284 | Datasets | Article 10 | Drafting | evolving |
| prEN 18229-2 | Accuracy, robustness | Article 15 | Drafting | evolving |

The 8 deliverables are the JTC 21 work programme; EN 18286 is closest to publication.

## The 4 stage lifecycle

| Stage | What | When to engage |
|---|---|---|
| Drafting | internal working drafts | comment via national body |
| Enquiry | public consultation (3 months) | submit comments |
| Approval (Formal Vote) | national bodies vote | monitor for vote |
| Publication (cited in OJEU) | final harmonised standard | presumption of conformity |

The 4 stages take 18-30 months total; EN 18286 is the first to reach Approval.

## The 5 areas mapped to AI Act requirements

| AI Act article | Requirement | Primary JTC 21 deliverable |
|---|---|---|
| 9 | Risk management | prEN 18228 |
| 10 | Data governance, bias | prEN 18284 (datasets) + prEN 18283 (bias) |
| 12 | Logging, record-keeping | prEN 18229-1 |
| 13, 14 | Transparency, human oversight | prEN 18229-3 |
| 15 | Accuracy, robustness, cybersecurity | prEN 18229-2 + prEN 18282 |
| 17 | Quality management | EN 18286 |

The 5 AI Act articles map to 5 JTC 21 deliverables (1:1 with some articles merged).

## The 5-step compliance pattern

For a high-risk AI system deployed in the EU:

1. **Map your system** to the AI Act's high-risk categories (Annex III)
2. **Align with the draft standards** — the JTC 21 drafts are the de facto baseline
3. **Document conformity** — even without presumption, the standards are best practice
4. **Track JTC 21 progress** — once EN 18286 and others are OJEU-cited, presumption attaches
5. **Re-evaluate** — once presumption is available, align formally; reduce documentation burden

The 5 steps are the 2026 production pattern.

## The 5 anti-patterns

1. **Wait for publication before starting.** The drafts are the baseline; aligning now is cheaper.
2. **Ignore the standards because they're drafts.** The Commission FAQ states the first harmonised standards are expected in 2026; the content is mostly stable.
3. **Try to comply without aligning to drafts.** The drafts are the best guidance until publication.
4. **Confuse presumption with compliance.** Presumption is a legal mechanism; compliance is the actual standard. They're related but not identical.
5. **Skip conformity assessment.** Article 43 requires it for high-risk systems; presumption doesn't replace it.

## The 3-step presumption of conformity

1. **Standard is harmonised** — adopted by CEN-CENELEC
2. **Standard is cited in the Official Journal of the EU** — by the Commission
3. **Your system conforms to the standard** — implementing the standard's requirements

The 3 steps are the legal mechanism. None has fully completed for AI Act standards as of June 2026.

## The 4 Article 40 conditions

Under Article 40, presumption of conformity attaches when:

1. The standard is published in the Official Journal of the EU
2. The standard covers the relevant AI Act requirement
3. The provider has applied the standard correctly
4. The provider's documentation demonstrates compliance

The 4 conditions are cumulative; missing any breaks the presumption.

## The 5 Article 9 risk management requirements

Article 9 requires an AI risk management system with 5 elements.

1. **Risk identification and analysis** — known and reasonably foreseeable risks
2. **Risk evaluation** — against the system's intended use
3. **Risk mitigation** — measures to address identified risks
4. **Testing** — to ensure the system performs consistently
5. **Documentation** — of the entire process

prEN 18228 (when finalized) operationalizes these 5 elements. Until then, the text of Article 9 is the requirement.

## The 4 Article 10 data governance requirements

Article 10 requires data governance with 4 elements.

1. **Data quality** — relevant, representative, free of errors
2. **Data preparation** — annotation, cleaning, enrichment
3. **Bias examination** — possible biases in the data
4. **Documentation** — data sources, collection methodology, labeling

prEN 18284 (datasets) and prEN 18283 (bias) operationalize these elements.

## The 5 Article 15 requirements

Article 15 covers accuracy, robustness, and cybersecurity with 5 elements.

1. **Accuracy** — declared and verified
2. **Robustness** — performance under errors, faults, inconsistencies
3. **Cybersecurity** — protection against unauthorized access
4. **Resilience to attacks** — adversarial testing
5. **Fallback plans** — graceful degradation

prEN 18229-2 (accuracy, robustness) and prEN 18282 (cybersecurity) operationalize these.

## The 5 best practices for 2026

1. **Monitor the JTC 21 work programme.** The kla.digital JTC 21 Standards Tracker is the 2026 reference.
2. **Align with the drafts now.** Even without presumption, the drafts are the best practice.
3. **Build a conformity assessment plan.** Article 43 is required for high-risk; not optional.
4. **Document compliance continuously.** Article 11 technical documentation is generated, not assembled.
5. **Engage with national standardisation bodies.** Comment on drafts; influence the standards.

## The 5-step conformity assessment

For high-risk AI:

1. **Internal control** — provider self-assessment (most high-risk systems)
2. **Notified body assessment** — third-party for some Annex III categories
3. **CE marking** — applied to the system
4. **EU declaration of conformity** — Article 47
5. **Registration** — EU database (Article 49)

The 5 steps are required for high-risk AI market access in the EU.

## Verification

The tell that AI Act harmonised standards compliance is real:

- The team is tracking the JTC 21 work programme
- Documentation aligns with the draft standards (even before publication)
- Article 9 risk management is implemented per draft prEN 18228
- Article 10 data governance is implemented per drafts prEN 18283 + prEN 18284
- Article 15 is implemented per drafts prEN 18229-2 + prEN 18282

The tell it isn't:

- "We'll wait until the standards are final"
- No documentation aligned with the drafts
- Article 9 risk management is "we do some testing"
- Article 10 data governance is "we have a CSV of data sources"
- Article 15 is "we don't get hacked"

## Gotchas

- **Presumption only attaches after OJEU citation.** Not before. As of June 2026, zero JTC 21 standards are OJEU-cited.
- **Drafts are the de facto baseline.** Aligning to drafts now is cheaper than aligning after publication.
- **The amended Commission request expires 28 February 2027.** Standards may not be fully published by then.
- **The Article 40 presumption is the legal mechanism, not the standard itself.** The standard is the technical content; presumption is the legal effect.
- **Conformance assessment (Article 43) is required for high-risk systems.** Not optional, not replaced by standards.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — high-risk categories
- `issues/eu-ai-act-article-5-prohibited-2026.md` — prohibited practices
- `issues/eu-ai-act-gpai-2026.md` — GPAI obligations
- `issues/ai-system-cards-2026.md` — model card template

## Source URLs (verified 2026-08-10)

- https://www.cencenelec.eu/news-events/news/2026/newsletter/ots-73-etuc/ — CEN-CENELEC update
- https://digital-strategy.ec.europa.eu/en/policies/ai-act-standardisation — Commission AI Act standardisation
- https://kla.digital/blog/jtc-21-standards-tracker — JTC 21 standards tracker (June 2026)
- https://www.cencenelec.eu/news-events/news/2025/brief-news/2025-10-23-ai-standardization/ — accelerated delivery October 2025
- https://data.consilium.europa.eu/doc/document/WK-12134-2025-INIT/en/pdf — Council document on standards
- https://publications.jrc.ec.europa.eu/repository/bitstream/JRC139430/JRC139430_01.pdf — JRC brief on standards
- https://artificialintelligenceact.eu/the-act/ — full AI Act text
- https://artificialintelligenceact.eu/article/9/ — Article 9 risk management
- https://artificialintelligenceact.eu/article/15/ — Article 15 accuracy, robustness
- https://artificialintelligenceact.eu/article/40/ — Article 40 harmonised standards
- https://artificialintelligenceact.eu/article/43/ — Article 43 conformity assessment
