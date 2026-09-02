# FIRST.org CVSS 4.0 Vulnerability Scoring Governance

## Purpose

The Forum of Incident Response and Security Teams (FIRST.org) Common Vulnerability Scoring System (CVSS) provides an open framework for communicating the characteristics and severity of software vulnerabilities. CVSS 4.0 is the current generation. Governance ensures that an organization applies CVSS 4.0 consistently, that scoring reflects current threats, and that scores are used appropriately in vulnerability management.

## Current context and source status

FIRST.org published CVSS 4.0 as a specification in November 2023, replacing CVSS 3.1. CVSS 4.0 introduces new metrics (including supplemental metrics for environmental, threat, and impact characteristics) and revised metric values. Verify the current FIRST.org CVSS 4.0 specification before treating any specific metric value as a current requirement.

## Governance workflow and controls

### 1. Use CVSS 4.0 for new scoring

Use CVSS 4.0 for new vulnerability scoring. Maintain CVSS 3.1 scores for historical vulnerabilities as needed.

### 2. Apply Base, Threat, Environmental, Supplemental metrics

Apply CVSS 4.0 metrics:

- Base metrics (intrinsic characteristics);
- Threat metrics (current threat state);
- Environmental metrics (organization-specific impact);
- Supplemental metrics (additional context).

Document the metric selection per scoring.

### 3. Train scorers

Train vulnerability analysts on CVSS 4.0. Apply a calibration exercise before production scoring.

### 4. Apply consistent scoring

Apply consistent scoring across analysts. Use a documented rubric. Review disputed scores.

### 5. Use official calculator

Use the official CVSS 4.0 calculator from FIRST.org. Document the calculator version.

### 6. Integrate with vulnerability management

Integrate CVSS scores with the vulnerability management process. Use scores for prioritization, not as the sole input.

### 7. Disclose scores

Disclose CVSS scores in vulnerability disclosures. Provide the vector string and the source.

## Validation and evidence

- Scoring procedure documentation.
- Calibration exercise results.
- Vulnerability records with CVSS scores.

## Failure correction

Common defects include inconsistent scoring across analysts, missing environmental metrics, and scores used as the sole prioritization input. Corrective actions include a calibration refresh, a metric completeness check, and a multi-factor prioritization requirement.

## Limitations

- CVSS is one input to vulnerability prioritization; it does not capture business context.
- Scoring is subject to analyst judgment; calibration is essential.
- CVSS 4.0 includes some metric changes; analysts trained on 3.1 may need re-training.
- The specification evolves; track FIRST.org updates.

## Canonical sources

- FIRST.org, Common Vulnerability Scoring System v4.0 Specification, 2023.
- FIRST.org, CVSS v4.0 User Guide, current edition.
- FIRST.org, CVSS v4.0 Calculator, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for vulnerability management, the operations leaf for patch management, and the engineering leaf for application security.
