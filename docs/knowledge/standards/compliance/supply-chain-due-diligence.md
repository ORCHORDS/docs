# supply-chain-due-diligence

**Issue:** Implementing supply chain due diligence for EU CSDD Directive and ICT supply chain security
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
EU Corporate Sustainability Due Diligence Directive (CSDDD) requires large companies to identify and address human rights and environmental risks in their supply chains. Separately, NIS2 and DORA require ICT supply chain security assessments.

## Pattern / Solution
CSDDD due diligence steps (phased rollout 2024-2027):
1. Integrate due diligence into policies (code of conduct, supplier requirements)
2. Identify and assess actual and potential adverse impacts in own operations and supply chain
3. Prevent, mitigate, and remediate identified impacts
4. Establish complaints mechanism for affected parties
5. Monitor effectiveness annually
6. Public communication (annual due diligence report)

ICT supply chain security (NIS2 Art. 21(2)(d), DORA Art. 28-30):
- Classify ICT suppliers by criticality (critical, important, standard)
- Annual security assessment for critical suppliers:
  - Security questionnaire (based on ISO 27001 / NIST CSF)
  - Review of audit reports (SOC 2, ISO cert)
  - Contract review for security SLAs
- Concentration risk: avoid single-supplier dependency for critical functions
- Exit strategy: documented for each critical supplier
- Incident notification clauses: supplier must notify you within defined timeframe

Software supply chain (SBOM):
- Maintain Software Bill of Materials for all production software
- Scan SBOM against CVE databases weekly (Syft + Grype)
- SBOM required for US federal contracts (EO 14028)

Supplier contract clauses:
```
- Right to audit supplier's security controls
- Incident notification within 24-72 hours
- Data breach notification per applicable law
- Sub-processor restrictions and notification requirements
- Certification maintenance (SOC 2 Type II / ISO 27001)
- Business continuity and exit plan
```

## Gotchas
- CSDDD scope: EU companies >1,000 employees and >EUR 450M turnover; and non-EU companies with >EUR 450M EU net turnover
- Supply chain due diligence cannot be outsourced to suppliers via questionnaire alone — some verification required
- SBOM formats: SPDX and CycloneDX are most widely accepted
- Open source dependencies count as supply chain — track with dependency management tools

## Related
- `vendor-security-assessment.md`
- `nis2-directive-implementation.md`
- `modern-slavery-act-compliance.md`
