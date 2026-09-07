# NIST IR 8259A IoT Device Cybersecurity Capability Core Baseline Governance

## 1. Scope

This card governs how ORCHORDS evaluates IoT devices against the NIST IR 8259A core baseline of device cybersecurity capabilities. It applies to consumer-grade and small-business IoT products that ORCHORDS procures, integrates, or evaluates in reference architectures, and to internal edge and building-automation devices that connect to ORCHORDS-managed networks.

## 2. Normative references

- NIST IR 8259A (IoT Device Cybersecurity Capability Core Baseline).
- NIST IR 8259 (Foundational Cybersecurity Activities for IoT Device Manufacturers).
- NIST IR 8259B (IoT Non-Technical Supporting Capability Core Baseline).
- NIST SP 800-53 Rev. 5 (security and privacy controls).
- ETSI EN 303 645 (consumer IoT baseline).

## 3. Core device cybersecurity capabilities

| # | Capability | ORCHORDS acceptance criterion |
| --- | --- | --- |
| 1 | Device identification | Stable, unique identifier resolvable on the network. |
| 2 | Device configuration | Authenticated configuration interface with restrictive defaults. |
| 3 | Data protection | Confidentiality and integrity for data at rest and in transit. |
| 4 | Logical access to interfaces | Role-separated access for local and network interfaces. |
| 5 | Software update | Authenticated, integrity-verified, rollback-safe update path. |
| 6 | Cybersecurity state awareness | Device reports its security state to authorised actors. |

## 4. Procurement and acceptance workflow

1. Identify the device class and applicable regulatory profile before purchase.
2. Map the six IR 8259A capabilities to vendor documentation and independent test reports.
3. Require evidence for each capability: identifier format, configuration schema, cryptographic profile, update mechanism, and telemetry surface.
4. Reject devices that depend on universal default passwords, lack a published update policy, or expose undocumented network services.
5. Record the capability mapping in the device record with the publication date consulted and the test report reference.

## 5. Integration controls

- Place IoT devices on segmented networks with explicit egress filtering.
- Mediate identity with the platform identity provider where the device supports federation.
- Forward device telemetry to the SIEM and define alerting thresholds.
- Track end-of-life and end-of-support dates in the asset register.

## 6. Mapping to other frameworks

- ETSI EN 303 645: each IR 8259A capability is traceable to one or more EN 303 645 provisions.
- ISO/IEC 27400: data-protection capability aligns with the IoT privacy and security guidelines.
- NIST SP 800-53 Rev. 5: capability outcomes map to the AC, IA, SC, SI, and CM control families.
- ISO/IEC 30111: vulnerabilities discovered on integrated devices are routed through the ORCHORDS vulnerability handling process.

## 7. Limitations

IR 8259A is a baseline capability catalogue, not a control set. ORCHORDS does not infer conformance from vendor self-attestation alone; the capability mapping must be supported by documentation or test evidence. IR 8259A does not prescribe algorithms, key lengths, or authentication protocols; those choices follow the platform cryptographic profile.

The baseline is non-regulatory. Sector overlays (medical IoT, industrial IoT, automotive) typically add controls beyond IR 8259A; ORCHORDS applies the relevant overlay when the device class falls under sector-specific regulation. The baseline does not cover privacy properties, which are governed separately under ISO/IEC 27701 and applicable data-protection law.

## 8. Owner and recording

- Capability mapping is owned by the device security lead for the relevant business unit.
- Mapping results and supporting evidence are retained for the operational life of the device plus three years.
- Material changes to firmware, supplier, or deployment context trigger re-evaluation of the capability mapping.

## 9. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
