# OWASP SAMM v2 Maturity Assessment Template Governance

## Purpose

OWASP Software Assurance Maturity Model (SAMM) v2.0 (OWASP, 2024) organizes software-security practice into five Business Functions (Governance, Design, Implementation, Verification, Operations) across 15 Security Practices. A reusable SAMM v2 maturity assessment template records, for each Security Practice, the current maturity score (0-3), the target maturity score, the score rationale, the supporting evidence, and the gap remediation plan. The template converts a software-assurance posture from an ad-hoc team assertion into an auditable artifact suitable for executive security steering, customer assurance reviews, and benchmark comparison.

The template must remain generic: it MUST NOT embed real scoring that identifies a specific organization's maturity, customer names, or specific evidence references that disclose internal posture.

## Scope

This template applies to OWASP SAMM v2.0 organizational assessments (sometimes called "Current" and "Target" assessments). It does not address SAMM v1.x assessments (which use a different maturity scoring scale and stream-based structure); a separate template is required for legacy evaluations. The template does not address SAMM Toolbox (the assessment spreadsheet); the toolbox output is captured in this template but the spreadsheet mechanics are documented in a separate runbook.

## Workflow

1. Open the template and complete the header with the assessment identifier, the SAMM version (v2.0), the assessment date, the assessor, the assessment scope (business units, product lines, geographies), and the target maturity score.
2. For each Business Function (Governance, Design, Implementation, Verification, Operations), record the Function-level current and target maturity score.
3. For each Security Practice within a Function (for example GOV.1 Security Governance, DES.1 Threat Assessment, IMP.1 Implementation Pipeline, VER.1 Architecture Assessment, OPS.1 Operational Management), record:
   - Practice identifier and title.
   - Current maturity score (0, 1, 2, or 3) per the SAMM v2 rubric.
   - Target maturity score.
   - Activities completed (per the SAMM v2 streams) that justify the score.
   - Evidence references for completed activities.
   - Quality criteria ratings (A: comprehensive, B: adequate, C: minimal, D: not present).
4. Document the gap between current and target scores, with a remediation plan, owner, and target date for each gap.
5. Identify the top-priority Security Practices for the assessment period (typically those with the highest delta between current and target).
6. Save the completed template alongside the software-security strategy, with access restricted to the security steering committee and the executive sponsor.

## Controls and evidence

- Header records assessment identifier, version, scope, target score, date, and assessor.
- Function-level scores recorded for both current and target.
- Practice-level scores recorded with activity completion and quality criteria.
- Evidence references precise (policy identifier, configuration baseline, tool report).
- Remediation plan records gap, owner, and target date.

## Validation

- Every Security Practice has a current and target score.
- Activity completion and quality criteria support the score.
- Function-level scores are consistent with the Practice-level scores (typically the average or weighted average).
- Priority practices are identified and routed to the security roadmap.
- The assessment is reviewed annually or after a significant change in scope.

## Failure correction

Common defects include selecting scores without supporting activity completion, recording Function-level scores without rolling up from Practice-level data, and treating SAMM as a compliance checklist rather than a maturity model. Corrective actions include requiring activity-based justification for every score, computing Function-level scores from Practice-level data, and framing the assessment as a maturity conversation that informs investment priorities.

## Limitations

- The template does not substitute for a SAMM v2 Toolbox walkthrough; it captures the assessment output.
- It does not address the SAMM v2 assessment questionnaire; a separate questionnaire template is required.
- It does not cover SAMM v2's mapping to other frameworks (BSIMM, NIST SSDF, ISO/IEC 27034); mapping tables are governed by a separate template.
- It does not address the SAMM v2 Business Function weighting; the weighting methodology is documented in a separate methodology document.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (software-security governance), **engineering** (secure SDLC integration), **standards** (SAMM relationships to BSIMM and NIST SSDF), and **business** (executive security reporting). The template should be used together with those sibling-leaf articles.

## Canonical sources

- OWASP SAMM v2.0 (OWASP, 2024): https://owasp.org/samm
- OWASP SAMM v2.0 Business Functions (OWASP): https://owasp.org/samm/model/business-functions/
- OWASP SAMM v2.0 Security Practices (OWASP): https://owasp.org/samm/model/security-practices/

Sources were verified on September 1, 2026.