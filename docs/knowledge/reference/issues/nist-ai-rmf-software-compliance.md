# nist-ai-rmf-software-compliance

**Issue:** NIST AI RMF — software compliance for AI features
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship an LLM feature. Procurement asks "are
you NIST AI RMF compliant?" You don't have an AI
governance policy. The EU AI Act deadline is in
weeks. You realize you're missing the framework.

## Root cause
**AI features need AI-specific controls.** AI RMF.

**Source:** NIST AI RMF 1.0 + 600-1 (GenAI Profile).

## The "AI RMF" concept

AI RMF (NIST.AI.100-1):
- **Version:** 1.0 (2023, current 2026)
- **Voluntary:** US, not regulatory
- **GenAI overlay:** NIST.AI.600-1
- **EU bridge:** AI Act crosswalk
- **Use:** All AI features

The RMF is the framework.

## The "4 functions" pattern

For RMF:
1. **GOVERN:** Policies + roles
2. **MAP:** Context + impact
3. **MEASURE:** Analyze + assess
4. **MANAGE:** Prioritize + respond

The 4 are the lifecycle.

## The "GOVERN" pattern

For govern:
- **Policies:** AI use policy
- **Roles:** Who decides
- **Escalation:** When to halt
- **Authority:** Cross-team
- **Why:** No controls without authority

The govern is foundational.

## The "MAP" pattern

For map:
- **Context:** Intended use
- **Out of scope:** What AI won't do
- **Affected:** Who impacted
- **Harms:** Foreseeable
- **When:** Per release

The map is per release.

## The "MEASURE" pattern

For measure:
- **Bias:** Test per group
- **Performance:** Per use case
- **Robustness:** Adversarial
- **Privacy:** Data handling
- **Why:** Evidence, not claims

The measure is evidence.

## The "MANAGE" pattern

For manage:
- **Prioritize:** Risk-tier
- **Respond:** Incident process
- **Monitor:** Continuous
- **Document:** Lifecycle
- **Why:** AI risks evolve

The manage is continuous.

## The "GenAI Profile" pattern

For LLM:
- **Standard:** NIST.AI.600-1
- **Taxonomy:** 13 GenAI risks
- **Actions:** 400+ developer actions
- **Risks:** Hallucination, jailbreak, IP
- **Use:** Any LLM feature

The GenAI is the overlay.

## The "13 GenAI risks" pattern

For risks:
- Confabulation (hallucination)
- Data privacy
- Harmful bias
- IP infringement
- Jailbreak
- Confabulation
- Dangerous info
- Toxicity
- Privacy
- Copyright
- CBRN
- Cyber

The 13 are the GenAI.

## The "EU AI Act crosswalk" pattern

For bridge:
- **High-risk:** Annex III systems
- **Conformity:** Required for EU
- **AI RMF → Annex IV:** Docs map
- **Art 9:** Risk management
- **Use:** Voluntary + EU mandated

The crosswalk is per system.

## The "trustworthy characteristics" pattern

For requirements:
- **Valid/reliable:** Testable
- **Safe:** Fail-safe defaults
- **Secure:** Adversarial tested
- **Accountable:** Audit log
- **Transparent:** Explainable
- **Privacy:** Data minimization
- **Fair:** Bias managed

The 7 are the NFRs.

## The "AI impact assessment" pattern

For per release:
- **Intended:** What it does
- **Out of scope:** What it doesn't
- **Affected:** Who
- **Harms:** Foreseeable
- **Mitigations:** Controls
- **Why:** Repeatable

The assessment is per release.

## The "high-risk classification" pattern

For EU:
- **Annex III:** High-risk list
- **Use cases:** Biometric, education, employment, critical infra
- **Requirements:** Stricter (Art 9-15)
- **Conformity:** Required
- **When:** EU deploys

The classification drives controls.

## The "continuous monitoring" pattern

For drift:
- **Drift:** Detect + alert
- **Hallucination:** Rate tracked
- **Jailbreak:** Success rate
- **Bias:** Per demographic
- **Why:** One-time fails

The monitoring is ongoing.

## The "third-party model" pattern

For vendor:
- **Provenance:** Where from
- **Fine-tune:** Who responsible
- **Audit:** Provider
- **Risk:** Chain
- **Why:** Liability

The third-party is assessed.

## The "one-time audit" anti-pattern

For audit-only:
- **Issue:** Misses MANAGE
- **Fix:** Continuous process

The RMF is lifecycle.

## The "skip GOVERN" anti-pattern

For no govern:
- **Issue:** No authority
- **Fix:** Policy + roles

The govern is set.

## The "no GenAI overlay" anti-pattern

For no overlay:
- **Issue:** LLM-specific missed
- **Fix:** Apply 600-1

The overlay is applied.

## The "800-53 only" anti-pattern

For only 800-53:
- **Issue:** AI gaps
- **Fix:** Add AI RMF

The 800-53 is insufficient.

## The "self-attest" anti-pattern

For self:
- **Issue:** Weak evidence
- **Fix:** External review

The review is external.

## The "AI RMF = EU AI Act" anti-pattern

For conflate:
- **Issue:** Voluntary vs required
- **Fix:** AI RMF supports, not satisfies

The conflate is avoided.

## The "vendor-only" anti-pattern

For only vendor:
- **Issue:** Your responsibility
- **Fix:** Assess chain

The chain is per actor.

## The "AI RMF checklist" pattern

For checklist:
- [ ] GOVERN: policies + roles
- [ ] MAP: context per release
- [ ] MEASURE: bias + perf
- [ ] MANAGE: monitoring on
- [ ] GenAI overlay (if LLM)
- [ ] Trustworthy NFRs
- [ ] Impact assessment
- [ ] EU high-risk if applies
- [ ] Crosswalk documented
- [ ] Third-party assessed
- [ ] External review

The checklist is 11.

## Verification
- **Test:** AI policy exists
- **Test:** Impact per release
- **Test:** Bias measured
- **Test:** Drift detected
- **Audit:** Quarterly

## Gotchas
- **The "one-time" anti-pattern.** Lifecycle.
- **The "skip GOVERN" anti-pattern.** Required.
- **The "no overlay" anti-pattern.** LLM needs.

## Related
- `compliance/eu-ai-act.md`
- `compliance/soc2-compliance.md`
- `compliance/iso-27001-compliance.md`
- `security/owasp-top-10-2025.md`
- `patterns/llm-evaluation.md`
- NIST: https://www.nist.gov/itl/ai-risk-management-framework
- NIST 600-1: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- AIRC: https://airc.nist.gov/technical-reports
