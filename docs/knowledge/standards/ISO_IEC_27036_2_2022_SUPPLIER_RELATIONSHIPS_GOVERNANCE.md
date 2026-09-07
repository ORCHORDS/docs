# ISO/IEC 27036-2:2022 Supplier Relationships Cybersecurity Governance

## Purpose

ISO/IEC 27036-2:2022 (second edition, published 2022-10) specifies the requirements and guidance for evaluating and treating cybersecurity risks in supplier relationships, with a focus on ICT supply chains. It is part of the ISO/IEC 27036 multi-part standard and supersedes the first edition (2014). Governance ensures that ORCHORDS sites that engage with suppliers of products, services, and infrastructure apply a documented supplier-cybersecurity lifecycle (acquisition, monitoring, change, incident handling, termination) that produces evidence consumable by NIST SP 800-161 Rev. 1 (C-SCRM) and by the EU CRA supply-chain conformity-assessment regime.

## Current context and source status

ISO/IEC 27036-2:2022 aligns with ISO/IEC 27002:2022 (controls applicable to supplier relationships) and is harmonised with ISO/IEC 27036-3 (ICT supplier relationship guidelines) and ISO/IEC 27036-4 (cloud services). The standard is widely cited in EU Member State procurement rules and is the canonical reference for supplier-cybersecurity evaluation outside US federal-procurement-bound contexts. Treat the standard text as the canonical reference.

## Governance workflow and controls

### 1. Supplier-cybersecurity scope and ownership

- Define the supplier-cybersecurity scope (supplier tiers, supplier categories, contract types) and publish the scope statement.
- Assign accountability for supplier cybersecurity to a named role; record the role description and reporting line.
- Integrate supplier cybersecurity with the ISMS (ISO/IEC 27001) and with NIST SP 800-161 Rev. 1 C-SCRM where US federal procurement applies.

### 2. Supplier risk assessment

- Conduct a supplier cybersecurity risk assessment before contract award; record the assessment in a supplier-risk register.
- Evaluate supplier maturity against ISO/IEC 27036-2 clauses 6–8 (acquisition, monitoring, change), against documented SSDF attestation evidence (NIST SP 800-218 v1.1), and against EU CRA conformity evidence where in scope.
- Re-baseline the risk assessment on every material change in the supplier relationship (new product, new service, new data flow, supplier acquisition, supplier security incident).

### 3. Acquisition controls

- Document cybersecurity requirements in the procurement specification; include SSDF attestation, SBOM, signed provenance, and EU CRA technical-documentation references where applicable.
- Define acceptance criteria that are testable; gate the acceptance decision on evidence rather than on attestation alone.
- Capture the supplier's evidence package in a supplier-catalog entry; require refresh on a documented cadence (default annually).

### 4. Monitoring controls

- Monitor supplier cybersecurity posture on a continuous basis; treat a drop in posture as a non-conformity.
- Subscribe to the supplier's coordinated vulnerability disclosure feed; document the integration.
- Monitor supplier-side SSDF attestation updates; treat an expired attestation as a release-blocking condition.

### 5. Change management

- Document change control with the supplier; gate production rollout on a signed change record.
- Re-evaluate cybersecurity requirements on every material change; document the re-evaluation outcome.
- Maintain a register of supplier change-control deviations and the remediation plan.

### 6. Incident handling

- Document the incident-handling process with the supplier; align it with ORCHORDS incident response (NIST SP 800-61 Rev. 3 / ISO/IEC 27035).
- Define notification timelines for supplier-side incidents that affect ORCHORDS products; align with EU CRA Article 11 reporting obligations when in scope.
- Conduct joint lessons-learned reviews after material incidents; capture findings in the supplier risk register.

### 7. Termination

- Define the supplier-termination playbook; cover return and destruction of ORCHORDS data, return of access credentials, and removal of supplier-side access.
- Conduct a post-termination review; capture residual risk in the supplier-risk register.
- Archive the supplier-catalog entry and the supplier-evidence package for the documented retention period (default 7 years).

### 8. Audit and continuous improvement

- Audit supplier cybersecurity at least annually; align the audit cadence with the ISMS internal audit cadence.
- Track supplier non-conformities in the issue tracker; treat unresolved non-conformities as a procurement-blocker.
- Report supplier-cybersecurity status to the executive risk committee at a documented cadence (default quarterly).

References: ISO/IEC 27036-2:2022; ISO/IEC 27036-3:2013; ISO/IEC 27036-4:2016; ISO/IEC 27001:2022; ISO/IEC 27002:2022; NIST SP 800-161 Rev. 1 (C-SCRM); NIST SP 800-218 v1.1 (SSDF); EU CRA Regulation 2024/2847.
