# FDA cyber-device section 524B evidence package

**Issue:** A medical-device premarket submission treats cybersecurity as a penetration-test attachment instead of a traceable product-lifecycle evidence package addressing the statutory cyber-device requirements and FDA's current guidance.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Scope

FDA's February 2026 final guidance covers quality-system considerations and recommended premarket-submission content for devices with cybersecurity risk and addresses section 524B of the FD&C Act for cyber devices. Regulatory, quality, clinical, safety, privacy, and security owners must determine applicability for the specific device and submission.

## Evidence package

- intended use, architecture, trust boundaries, assets, interfaces, deployment environment, and data flows;
- threat model tied to hazardous situations, security risks, risk controls, residual risk, and benefit-risk decisions;
- security requirements and traceability through design, implementation, verification, and validation;
- authentication, authorization, cryptography, update, logging, recovery, hardening, and secure-default evidence;
- software bill of materials covering commercial, open-source, and off-the-shelf components;
- vulnerability, penetration, fuzz, abuse-case, interoperability, and update/rollback test results;
- plan and procedures to monitor, identify, and address postmarket vulnerabilities and exploits;
- coordinated vulnerability disclosure process and intake ownership;
- procedures for reasonably justified regular-cycle and out-of-cycle patches and updates;
- labeling, customer responsibilities, support period, end-of-support, and secure decommissioning information.

## Controls

1. Freeze the device, software, threat-model, SBOM, and test versions represented by the submission.
2. Map each section 524B element and guidance recommendation to owned evidence or an approved applicability rationale.
3. Link every unresolved vulnerability to exploitability, patient-safety impact, compensating controls, disclosure, and remediation timing.
4. Exercise the update path on production-equivalent hardware, including signature failure, power loss, rollback, and recovery.
5. Establish postmarket telemetry, vulnerability intelligence, supplier notification, coordinated disclosure, and field-action decision paths.
6. Reassess the package after material design, component, manufacturing, hosting, or threat changes.

## Verification

An independent reviewer traces sampled threats to controls, code, tests, residual-risk approval, labeling, and postmarket monitoring. Reproduce the SBOM from the release artifact, scan it with current intelligence, and demonstrate a signed security update and failed-update recovery on representative devices.

## Gotchas

A clean point-in-time scan does not demonstrate a secure product lifecycle. An SBOM is an inventory, not a vulnerability disposition. The 2026 final guidance supersedes the June 27, 2025 version; pin the guidance revision used and have regulatory counsel confirm submission obligations.

## Official sources

- [FDA: Cybersecurity in Medical Devices—February 2026 Final Guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cybersecurity-medical-devices-quality-management-system-considerations-and-content-premarket)
- [FDA: Cybersecurity in Medical Devices FAQs](https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity)
- [21 U.S.C. § 360n-2 (FD&C Act section 524B)](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title21-section360n-2)
