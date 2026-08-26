# eu-ai-act

**Issue:** EU AI Act — high-risk system compliance
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy an AI system in the EU. It screens CVs.
The deadline is August 2026. You're not sure if
you're high-risk. The fine is €35M or 7% of revenue.

## Root cause
**The EU AI Act is now enforceable.** Plan for
August 2026.

**Source:** EU AI Act:
https://artificialintelligenceact.eu/

## The "EU AI Act timeline" pattern

For the timeline:
- **2 Feb 2025:** Prohibited AI enforceable
- **2 Aug 2025:** GPAI model obligations
- **2 Aug 2026:** High-risk Annex III enforceable
- **2 Aug 2027:** Pre-2026 high-risk must comply
- **2 Aug 2028:** Product-integrated AI
- **2 Dec 2027:** Some high-risk (per AI Omnibus)

The deadlines are per chapter.

## The "risk tiers" pattern

For the 4 risk tiers:
1. **Unacceptable (prohibited):** Social scoring,
   subliminal manipulation, real-time public
   biometric ID
2. **High-risk (Annex III):** CV screening, credit
   scoring, biometric ID, education assessment
3. **Limited-risk:** Chatbots, deepfakes, emotion
   recognition
4. **Minimal-risk:** Most AI

The tiers are per use case.

## The "Annex III high-risk" pattern

For the 8 high-risk sectors:
1. **Biometrics** — ID, categorization, emotion
2. **Critical infrastructure** — Energy, water,
   transport, digital
3. **Education** — Access, assessment, evaluation
4. **Employment** — Recruitment, performance,
   promotion, termination
5. **Essential services** — Credit scoring, insurance,
   emergency dispatch
6. **Law enforcement** — Risk assessment, lie
   detection, evidence
7. **Migration** — Applications, risk, documents
8. **Justice + democracy** — Legal proceedings,
   electoral systems

The sectors are the 8.

## The "high-risk provider obligations" pattern

For providers (Art. 9-15, 43, 49, 72):
- **Art. 9:** Risk management system (continuous)
- **Art. 10:** Data governance (relevant,
  representative, error-free)
- **Art. 11 + Annex IV:** Technical documentation
- **Art. 12:** Automatic event logging
- **Art. 13:** Instructions for use (transparency)
- **Art. 14:** Human oversight (override)
- **Art. 15:** Accuracy, robustness, cybersecurity
- **Art. 43:** Conformity assessment
- **Art. 49:** EU database registration
- **Art. 72:** Post-market monitoring

The provider obligations are 10.

## The "deployer obligations" pattern (Art. 26)

For deployers:
- **Use per instructions:** Per provider's manual
- **Human oversight:** Assigned, trained
- **Input data:** Relevant, representative
- **Monitor:** Operation + report incidents
- **Log retention:** 6 months minimum
- **Worker notification:** Before workplace use
- **FRIA:** Fundamental Rights Impact Assessment
- **Inform natural persons:** Subject to AI

The deployer obligations are 8.

## The "GPAI obligations" pattern

For General Purpose AI (Chapter V):
- **All providers:**
  - Technical documentation
  - Copyright compliance
  - Downstream transparency
- **Systemic risk (≥10²⁵ FLOP):**
  - Model evaluations (adversarial)
  - Systemic risk assessment
  - Cybersecurity
  - Incident reporting
  - Notification of AI Office

The GPAI is per FLOP threshold.

## The "Article 50 transparency" pattern

For limited-risk transparency:
- **Chatbots:** Inform AI nature
- **Emotion recognition:** Notify subjects
- **Biometric categorization:** Notify
- **Deepfakes:** Watermark + label
- **AI text (public interest):** Mark as AI

The transparency is per use.

## The "penalties" pattern

For fines (Art. 99):
- **Prohibited AI:** €35M or 7% turnover
- **High-risk non-compliance:** €15M or 3%
- **Incorrect info:** €7.5M or 1%
- **SMEs:** Lower of fixed or %

The fines are tiered.

## The "conformity assessment" pattern

For assessment:
- **Self-assessment:** Most Annex III
- **Third-party:** Biometric ID, critical
  infrastructure (Annex VII)
- **Procedure:** Per Art. 47
- **Post-market:** Continuous

The assessment is per type.

## The "EU database registration" pattern

For registration (Art. 49):
- **Provider:** Registers before deployment
- **Deployer (public):** Verifies registration
- **Public:** EU database
- **Update:** Material changes

The registration is required.

## The "technical documentation" pattern

For Annex IV:
- **System purpose:** Intended use
- **Design:** Architecture
- **Capabilities:** Performance metrics
- **Limitations:** Known boundaries
- **Data:** Sources, preparation
- **Training:** Methodology
- **Testing:** Validation results
- **Risk analysis:** Per Art. 9

The docs are comprehensive.

## The "human oversight" pattern (Art. 14)

For oversight:
- **Understand:** AI outputs
- **Monitor:** Operation
- **Override:** When needed
- **Intervene:** Don't proceed if unsafe
- **Bias awareness:** Detect discrimination

The oversight is meaningful.

## The "data governance" pattern (Art. 10)

For data:
- **Relevant:** To intended purpose
- **Representative:** Of population
- **Error-free:** As much as possible
- **Bias evaluation:** Documented
- **Privacy:** GDPR compliant

The data is governed.

## The "post-market monitoring" pattern (Art. 72)

For monitoring:
- **Continuous:** Performance tracking
- **Serious incidents:** Report to authority
- **Updates:** Plan documented
- **Reporting:** Per member state

The monitoring is continuous.

## The "vendor contract" pattern

For B2B contracts:
- **Conformity assessment:** Evidence from provider
- **Tech documentation:** Access provided
- **Update clause:** Material changes
- **Liability:** Indemnification
- **Compliance:** Act + GDPR

The contract is updated.

## The "compliance checklist" pattern

For August 2026:
- [ ] AI system inventory
- [ ] Risk classification (per system)
- [ ] Prohibited AI shut down
- [ ] High-risk: Art. 9-15, 43, 49, 72
- [ ] Deployer: Art. 26 obligations
- [ ] GPAI: Chapter V (if applicable)
- [ ] Article 50 transparency
- [ ] EU database registration
- [ ] Vendor contracts updated
- [ ] Staff training

The checklist is per system.

## The "AI inventory" pattern

For inventory:
- **System name:**
- **Vendor:** (provider or in-house)
- **Purpose:**
- **Data inputs/outputs:**
- **User population:**
- **Risk tier:**

The inventory is mapped.

## The "FRIA" pattern (Fundamental Rights Impact Assessment)

For FRIA:
- **Required for:** Public + essential services
- **Includes:** Risks, mitigations, oversight
- **Notify:** Market surveillance authority
- **Document:** Outcomes

The FRIA is documented.

## The "high-risk already in service" pattern

For pre-August-2026 systems:
- **Deadline:** 2 August 2027 to comply
- **Plan:** Phased compliance
- **Risk:** Continue current practices until then
  (if compliant with prior law)

The grace is until Aug 2027.

## The "non-EU provider" pattern

For non-EU:
- **Applies if:** Output used in EU
- **Representative:** Appoint in EU
- **Compliance:** Same as EU providers
- **Enforcement:** Border + EU

The non-EU is in scope.

## Verification
- **Test:** Inventory complete
- **Test:** Risk classification documented
- **Test:** Conformity assessment done
- **Test:** EU database registered
- **Audit:** Annual

## Gotchas
- **The "we're not high-risk" anti-pattern.** Document
  the decision.
- **The "no documentation" anti-pattern.** Annex IV.
- **The "no human oversight" anti-pattern.** Art. 14.
- **The "no post-market" anti-pattern.** Art. 72.

## Related
- `compliance/gdpr-article-17-erasure.md`
- `compliance/hipaa-compliance.md`
- `compliance/soc2-compliance.md`
- `compliance/iso-27001-compliance.md`
- `compliance/fedramp-compliance.md`
- `security/owasp-top-10-2025.md`
- EU AI Act: https://artificialintelligenceact.eu/
- EU Commission: https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-high-risk-systems
- OrbIQ: https://www.orbiqhq.com/eu-regulations/eu-ai-act-compliance
