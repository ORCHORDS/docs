# iso-27001-compliance

**Issue:** ISO 27001 — information security management
**Date:** 2026-08-09
**Status:** documented

## Symptom
A European enterprise asks "are you ISO 27001?" You
say "no." They say "we'll evaluate you when you are."
You wish you'd started sooner.

## Root cause
**ISO 27001 is the global standard.** Implement it.

**Source:** ISO 27001:
https://www.iso.org/standard/27001

## The "ISO 27001" concept

ISO 27001 is an ISMS (Information Security Management
System):
- **Annex A:** 93 controls
- **Clauses 4-10:** ISMS structure
- **Risk-based:** Identify + treat
- **Audit:** Annual surveillance + 3-year re-cert

The ISMS is the management system.

## The "5 stages" pattern

For 5 stages:
1. **Build ISMS foundation:** Scope, policy, roles
2. **Select controls:** Annex A + SoA
3. **Implement:** Access, crypto, ops
4. **Audit yourself:** Internal audit + mgmt review
5. **Pass certification:** Stage 1 + Stage 2

The stages are sequential.

## The "Annex A controls" pattern

For Annex A:
- **93 controls** in 4 themes
- **A.5 Organizational:** 37
- **A.6 People:** 8
- **A.7 Physical:** 14
- **A.8 Technological:** 34

The controls are 93.

## The "SoA" pattern

For Statement of Applicability:
- **All 93 controls:** Marked
- **Applicable or excluded:** For each
- **Justification:** For exclusions
- **Owner:** For each applicable

The SoA is the document.

## The "risk assessment" pattern

For risk:
- **Identify:** Assets, threats, vulnerabilities
- **Analyze:** Likelihood × impact
- **Evaluate:** Risk acceptance
- **Treat:** Mitigate, transfer, accept, avoid

The risk is managed.

## The "ISMS scope" pattern

For scope:
- **Products:** What's in scope
- **Locations:** Where
- **Teams:** Who
- **Excluded:** What's not

The scope is defined.

## The "policy" pattern

For policy:
- **Top-level:** Information security policy
- **Specific:** Crypto, access, incident
- **Approved:** By management
- **Communicated:** To all staff

The policy is approved.

## The "access control" pattern

For A.5.15-A.5.18:
- **A.5.15:** Access control policy
- **A.5.16:** Identity management
- **A.5.17:** Authentication info
- **A.5.18:** Access rights

The access is controlled.

## The "cryptography" pattern

For A.8.24:
- **Policy:** Crypto use
- **Key management:** Generation, storage, rotation
- **Algorithms:** Approved (AES, RSA, etc.)

The crypto is managed.

## The "incident management" pattern

For A.5.24-A.5.28:
- **A.5.24:** Incident planning
- **A.5.25:** Assessment
- **A.5.26:** Response
- **A.5.27:** Learning
- **A.5.28:** Collection of evidence

The incidents are managed.

## The "supplier" pattern

For A.5.19-A.5.23:
- **A.5.19:** Info security in supplier relationships
- **A.5.20:** Security in supplier agreements
- **A.5.21:** Managing security in ICT supply chain
- **A.5.22:** Monitoring supplier services
- **A.5.23:** ICT supply chain changes

The suppliers are managed.

## The "internal audit" pattern

For internal audit:
- **Cover all clauses + applicable controls**
- **Nonconformities:** Documented
- **Corrective actions:** With owners + dates
- **Before Stage 1:** Close all findings

The audit is internal.

## The "management review" pattern

For mgmt review:
- **Inputs:** Audit results, incidents, changes
- **Outputs:** Decisions, actions
- **Documented:** In minutes

The review is documented.

## The "Stage 1 + Stage 2" pattern

For certification:
- **Stage 1:** Documentation review
- **Stage 2:** Implementation audit
- **Surveillance:** Year 2 + 3
- **Re-certification:** Every 3 years

The certification is multi-stage.

## The "ISO 27001 cost" pattern

For cost:
- **Tooling:** ~$10k - $50k
- **Consultant:** ~$30k - $200k
- **Audit body:** ~$10k - $50k
- **Annual:** ~$5k - $30k

The cost is significant.

## The "ISO 27001 + SOC 2" pattern

For both:
- **ISO 27001:** ISMS, process-based
- **SOC 2:** Trust service criteria
- **Overlap:** Significant (~60%)

For most apps, **both** is the right answer.

## The "ISO 27001 anti-pattern" anti-patterns

### 1. Paperwork only
- **Issue:** No real security
- **Fix:** Real controls

### 2. Too broad scope
- **Issue:** Hard to audit
- **Fix:** Narrow scope

### 3. Skipping internal audit
- **Issue:** Open findings
- **Fix:** Audit first

### 4. No management buy-in
- **Issue:** Not sustainable
- **Fix:** Executive sponsor

## Verification
- **Test:** SoA is complete
- **Test:** Internal audit is done
- **Test:** Mgmt review is documented
- **Live:** Ongoing monitoring
- **Audit:** Annual surveillance

## Gotchas
- **The "paperwork only" anti-pattern.** Real controls.
- **The "no internal audit" anti-pattern.** Audit first.
- **The "no mgmt buy-in" anti-pattern.** Executive
  sponsor.

## Related
- `compliance/fedramp-compliance.md`
- `compliance/hipaa-compliance.md`
- `compliance/gdpr-article-17-erasure.md`
- `compliance/soc2-compliance.md` (planned)
- ISO 27001: https://www.iso.org/standard/27001
- Konfirmity checklist: https://konfirmity.ai/checklists/iso-27001-checklist
- Hyperproof: https://hyperproof.io/resource/iso27001-implementation-checklist/
