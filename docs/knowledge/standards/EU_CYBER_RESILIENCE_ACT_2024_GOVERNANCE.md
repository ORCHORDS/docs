# EU Cyber Resilience Act (Regulation 2024/2847) Governance

## Purpose

Regulation (EU) 2024/2847, the Cyber Resilience Act (CRA), entered into force on 10 December 2024 and applies in full from 11 December 2027, with reporting obligations effective 11 September 2026. The CRA imposes mandatory cybersecurity, vulnerability handling, and conformity-assessment obligations on manufacturers and developers of products with digital elements (PDEs) and on their distributors and integrators. Governance ensures that ORCHORDS sites that place PDEs on the EU market, including open-source software stewards that fall within scope, apply a documented CRA compliance programme that produces a conformity assessment, technical documentation, and a statement of conformity before any in-scope product is made available in the Union.

## Current context and source status

Regulation (EU) 2024/2847 was adopted on 23 October 2024 and published in the Official Journal on 20 November 2024. It supplements Regulation (EU) 2019/881 (Cybersecurity Act) and is supported by the implementing acts that the European Commission is publishing between 2025 and 2027. Treat the Regulation text and the published implementing acts as the canonical reference; this card is a governance overlay and is not a substitute for legal review.

## Governance workflow and controls

### 1. Scope and product classification

- Maintain a register of every PDE that ORCHORDS makes available on the EU market, including open-source software stewardships that meet the CRA "monetisation" test.
- Classify each in-scope PDE as Class I (default) or Class II (Annex IV) based on the Annex III functionality and the Annex IV impact assessment.
- Identify the corresponding conformity assessment route (self-assessment, harmonised-standard self-assessment, third-party assessment by a notified body for Class II / Annex IV critical products).
- Re-baseline the scope register on every release that introduces a new PDE, an Annex III functionality, or a remote data-processing dependency.

### 2. Essential cybersecurity requirements (Annex I)

- Design and develop PDEs to ensure an appropriate level of cybersecurity based on the intended use, the reasonably foreseeable conditions of use, and the attack surface.
- Ensure that PDEs are delivered without known exploitable vulnerabilities; verify the SBOM and the SCA report at release.
- Implement secure-by-default configuration; document the secure configuration baseline in the user information.
- Implement an attack-surface reduction plan that addresses attack paths documented in the threat model.
- Provide an exploitability analysis for vulnerabilities that the manufacturer becomes aware of, including those reported through coordinated disclosure.

### 3. Vulnerability handling (Article 11)

- Document and publish a coordinated vulnerability disclosure policy; designate a single point of contact for vulnerability reports.
- Disseminate vulnerability information to users free of charge and without undue delay; align disclosure cadence with ENISA's reporting timeline.
- Apply security updates free of charge for the support period declared in the statement of conformity (minimum 5 years for Class II; default 5 years for Class I unless shorter is documented and justified).
- Operate an effective early-warning, notification, and remediation process; align notification with ENISA's reporting templates.

### 4. Technical documentation (Annex VII)

- Maintain technical documentation that demonstrates conformity with the essential cybersecurity requirements; include the SBOM, the threat model, the secure-coding evidence, and the test results.
- Keep the technical documentation up to date; reflect every security update and every change to the product's attack surface.
- Retain the technical documentation for 10 years after the PDE has been placed on the market.

### 5. Conformity assessment and CE marking

- Run the documented conformity-assessment procedure for the product class; record the assessment outcome in a signed attestation.
- Apply the CE marking and the CRA-specific support-period marking in accordance with Article 13.
- Draw up an EU declaration of conformity in accordance with Article 15; retain it as part of the technical documentation.
- For Class II / Annex IV products, obtain an EU-type examination certificate from a notified body; re-examine on every change that affects conformity.

### 6. Reporting obligations

- Notify ENISA of any actively exploited vulnerability within 24 hours of becoming aware of it (Article 11(4)).
- Notify ENISA of any severe incident affecting the product within 24 hours; provide a final report within 14 days.
- Maintain an internal register of all CRA notifications; tie each notification to a tracked incident.

### 7. Open-source software stewardship

- For open-source software stewardships that fall within scope, treat the stewardship as a manufacturer; apply the full CRA programme.
- For pure community-driven open-source projects that do not fall within scope, document the out-of-scope rationale and re-evaluate on any monetisation event.

### 8. Audit and continuous improvement

- Audit CRA compliance at least annually; align the audit cadence with the SSDF audit cadence (NIST SP 800-218) to avoid double work.
- Treat non-conformity findings as release-blocking defects; track remediation in the issue tracker.
- Update the conformity assessment and the statement of conformity on every release that affects conformity.

References: Regulation (EU) 2024/2847; ENISA CRA implementation guidance; Regulation (EU) 2019/881 (Cybersecurity Act); Annex III (critical product classes), Annex IV (conformity-assessment modules), Annex VII (technical documentation).
