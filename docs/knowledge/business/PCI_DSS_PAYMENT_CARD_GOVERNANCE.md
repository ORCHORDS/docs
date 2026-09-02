# PCI DSS Payment Card Industry Data Security Standard Governance

## Purpose

The Payment Card Industry Data Security Standard (PCI DSS) is the global standard for protecting cardholder data. Governance ensures that merchants, service providers, and other entities that store, process, or transmit cardholder data implement the applicable controls, validate compliance through the required assessment method, and maintain compliance between assessments.

## Current context and source status

The PCI Security Standards Council (PCI SSC) maintains the PCI DSS. The current version is PCI DSS v4.0, published in March 2022, with v4.0.1 as a published errata. Future-dated requirements in v4.0 became mandatory on March 31, 2025. The PCI SSC also maintains related standards (PCI PTS for PIN Transaction Security, PA-DSS for payment applications, P2PE for point-to-point encryption). Verify the current PCI SSC publication before treating any specific requirement identifier as a current requirement.

## Governance workflow and controls

### 1. Determine applicability and scope

Determine applicability based on the entity's role (merchant, service provider) and the card brands' volume thresholds. Define the scope of the cardholder data environment (CDE) and connected systems.

### 2. Apply the 12 requirements

Apply the 12 PCI DSS requirements:

1. Install and maintain network security controls.
2. Apply secure configurations to all system components.
3. Protect stored account data.
4. Use strong cryptography during transmission over open, public networks.
5. Protect all systems and networks from malicious software.
6. Develop and maintain secure systems and software.
7. Restrict access to system components and cardholder data by business need to know.
8. Identify users and authenticate access to system components.
9. Restrict physical access to cardholder data.
10. Log and monitor all access to system components and cardholder data.
11. Test security of systems and networks regularly.
12. Support information security with organizational policies and programs.

### 3. Select the assessment method

Select the appropriate assessment method (Self-Assessment Questionnaire for lower volumes; Report on Compliance for higher volumes). Engage a Qualified Security Assessor (QSA) for ROC assessments.

### 4. Apply segmentation

Apply network segmentation to isolate the CDE from other systems. Validate segmentation annually.

### 5. Maintain compliance between assessments

Maintain compliance between formal assessments. Track control changes. Re-validate after significant changes.

### 6. Submit compliance reports

Submit the required compliance reports to the acquiring bank and the card brands per the brand-specific reporting requirements.

## Validation and evidence

- Scope documentation.
- Implementation evidence for each requirement.
- Network segmentation validation.
- Assessment report (SAQ or ROC).
- Attestation of Compliance (AOC).

## Failure correction

Common defects include scope expansion without assessment, missing segmentation validation, and outdated AOCs. Corrective actions include a scope review, a segmentation validation cadence, and an AOC expiry calendar.

## Limitations

- PCI DSS applies to cardholder data; other payment data may be covered by other standards.
- The standard evolves; v4.0 future-dated requirements are mandatory since March 31, 2025.
- Compliance is a snapshot; ongoing security requires continued investment.
- Compliance does not guarantee security; PCI DSS is a baseline.

## Canonical sources

- PCI Security Standards Council, Payment Card Industry Data Security Standard, v4.0.1 (or current version).
- PCI Security Standards Council, Self-Assessment Questionnaire, current version.
- PCI Security Standards Council, Report on Compliance template, current version.

## Scope note

This article belongs to the business leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for secure development, and the operations leaf for network segmentation.
