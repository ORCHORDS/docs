---
title: "ISO/IEC 27400:2022 IoT Security & Privacy Guidelines — Version Transition Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 27400:2022 (Cybersecurity — IoT security and privacy — Guidelines); https://www.iso.org/standard/44373.html"
---

# ISO/IEC 27400:2022 IoT Security & Privacy Guidelines — Version Transition Governance

## Purpose

This card governs how ORCHORDS references ISO/IEC 27400:2022 — the IoT security and privacy guidelines standard from ISO/IEC JTC1/SC27. It complements ISO/IEC 27402 (baseline controls) and ISO/IEC 30141 (IoT reference architecture), and provides a layered, device-to-cloud privacy and security model.

## Canonical Reference

- ISO/IEC 27400:2022, *Cybersecurity — IoT security and privacy — Guidelines*, first edition, February 2022.
- Companion: ISO/IEC 27402:2024 (baseline controls, formerly ISO/IEC 27402 PDTS, ISO/IEC TS 27402), ISO/IEC 30141:2018 (IoT reference architecture), ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27018:2019, ISO/IEC 29184 (privacy notices), ISO/IEC 27570 (PII de-identification techniques).
- Regional: NIST IR 8259A (US IoT baseline), ETSI EN 303 645 (Europe), GB/T 36951 (China).

## Core Clauses

- **Clause 5: IoT ecosystem overview** — Devices, gateways, cloud backends, mobile applications, third-party services, lifecycle actors.
- **Clause 6: Threat catalogue** — Device tampering, firmware extraction, network sniffing, MQTT/CoAP misconfiguration, default credentials, unencrypted firmware updates, side-channel leakage, PII aggregation.
- **Clause 7: Privacy risks and controls** — Data minimisation at sensor layer, on-device anonymisation, transparency, consent capture in constrained UIs, retention windows tied to purpose limitation.
- **Clause 8: Security controls** — Device identity, secure boot, hardware root-of-trust, network segmentation, mutual TLS for north-south traffic, OTA update integrity, vulnerability handling.
- **Clause 9: Lifecycle controls** — Design, development, manufacturing, deployment, operational, decommission. Includes out-of-band wipe at decommission.
- **Annex A (informative)**: Privacy-by-design attributes mapped to ISO/IEC 29100 privacy principles.
- **Annex B (informative)**: Mappings to NIST IR 8259A and ETSI EN 303 645.

## Migration and Version Drift

ISO/IEC 27400:2022 is the first edition; the 2024 amendment and ISO/IEC 27402:2024 are the most material follow-ups to track.

| Topic | 27400:2022 | 27402:2024 (controls) | Notes |
| --- | --- | --- | --- |
| Device identity | Guideline level | Specific controls (per-device X.509, secure element, hardware unique key) | 27402 promotes guideline → normative. |
| Default credentials | "Should change before deployment" | "MUST be changed before deployment" | 27402 mandates; 27400 recommended. |
| Vulnerability handling | ISO/IEC 30111 referenced | ISO/IEC 30111 + ISO/IEC 29147 mandatory | 27402 makes disclosure process mandatory. |
| PII at the edge | Privacy risk | Specific on-device anonymisation controls | 27402 adds control-level clarity. |
| Cryptographic agility | Mentioned | Required | 27402 mandates firmware can swap ciphers via configuration. |
| Secure update | Mentioned | Required; rollback protection + signed manifests | 27402 adds anti-rollback and pinned manifest verification. |

## Usage in ORCHORDS

- Treat ISO/IEC 27400:2022 as the *governance layer* and ISO/IEC 27402:2024 as the *implementation layer* for IoT deployments.
- For consumer IoT and B2C devices, pair with ETSI EN 303 645 conformance.
- For industrial IoT (IIoT) and OT environments, pair with IEC 62443 series and ISO/IEC 27019.
- For fleet management of ORCHORDS-supplied IoT, ensure OTA infrastructure implements signed manifests with rollback protection per 27402.
- Privacy impact assessments for IoT deployments MUST consult ISO/IEC 27400 §7 in addition to ORCHORDS' standard PIA template.

## Open Items

- Monitor ISO/IEC JTC1/SC42 AI work for IoT+AI overlap (model inference at the edge).
- Re-evaluate ISO/IEC 27402:2024 alignment with ORCHORDS device-onboarding platform after each device firmware release.
- Track the EU Cyber Resilience Act (CRA) regulatory alignment, which references several 27402 controls.
