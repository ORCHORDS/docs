# ISO/IEC 27040:2015 Storage Security Governance

## 1. Scope

This card defines the storage security governance baseline derived from ISO/IEC 27040:2015. It applies to all persistent and ephemeral storage assets holding regulated, confidential, or personally identifiable information. The card covers encryption, key management, sanitisation, and incident response controls. It is normative for infrastructure teams, storage administrators, and security operations personnel. Exclusions are limited to network-layer cryptography, which is governed separately under the network security baseline.

## 2. Normative references

The following documents are referenced and indispensable to the application of this card: ISO/IEC 27040:2015, ISO/IEC 27001:2022, ISO/IEC 27002:2022, NIST SP 800-88 Rev. 1, NIST SP 800-57 Part 1 Rev. 5, and the OASIS Key Management Interoperability Protocol (KMIP) specification. For dated references, only the cited edition applies. For undated references, the latest edition of the referenced document applies.

## 3. Terms and definitions

- WORM: Write Once Read Many. A storage paradigm preventing mutation or deletion of committed data within a defined retention window.
- SED: Self-Encrypting Drive. A storage device that performs cryptographic operations in dedicated hardware internal to the drive controller.
- KMIP: Key Management Interoperability Protocol. An OASIS standard specifying the lifecycle management of cryptographic keys across heterogeneous vendor systems.

## 4. Background

ISO/IEC 27040:2015 consolidates storage-specific guidance that was previously dispersed across ISO/IEC 27001 and ISO/IEC 27002 control families. It introduces a dedicated taxonomy covering device types, threat models, and cryptographic techniques, and aligns sanitisation expectations with NIST SP 800-88 Rev. 1.

## 5. Storage security domains

Three distinct domains must be controlled separately.

- Data at rest: byte sequences resident on persistent media, including block, file, and object systems. Controls include encryption, access segmentation, and integrity attestation.
- Data in transit: byte sequences crossing trust boundaries, including replication links, backup transport, and storage management APIs. Controls include TLS 1.3, IPsec, and MACsec.
- Data in use: byte sequences resident in volatile memory or processor registers during active computation. Controls include memory encryption, remote attestation, and confidential computing primitives.

## 6. Storage device types and threat models

Device classes include Hard Disk Drives (HDD), Solid State Drives (SSD), Self-Encrypting Drives (SED), Non-Volatile Memory Express (NVMe) devices, tape media, and optical media. Threat vectors include theft, insider exfiltration, firmware compromise, side-channel leakage, and physical destruction. Each device class requires a documented threat model with associated compensating controls recorded in the risk register.

## 7. Storage encryption: SED, FDE, application-level

Three principal mechanisms are recognised.

- SED: Self-Encrypting Drives execute cryptographic operations in controller hardware. Selection criterion: high throughput with minimal host CPU impact, vendor key escrow integration, and TCG Opal or Enterprise compatibility.
- FDE: Full Disk Encryption applies encryption at the logical volume layer via software. Selection criterion: portability across heterogeneous hardware, absence of vendor lock-in, and compatibility with non-self-encrypting media.
- Application-level encryption: cryptographic operations executed within the application before persistence. Selection criterion: highest assurance against storage-layer compromise, fine-grained per-record key derivation, and regulatory mandates requiring cryptographic separation between tenants.

## 8. Key management and KMIP

All cryptographic keys must be generated, distributed, rotated, and retired through a dedicated Key Management Service. KMIP is the preferred interoperability protocol, supporting symmetric keys, asymmetric keys, certificates, and lifecycle states. Vendor options include Thales, Entrust, Utimaco, and HashiCorp Vault with KMIP listeners. Separation of duties between storage administrators and key custodians is mandatory.

## 9. Data sanitisation (NIST SP 800-88 alignment)

Sanitisation decisions follow NIST SP 800-88 Rev. 1 and select one of three categories.

- Clear: logical overwrite of all addressable storage locations, suitable for reuse within the same security domain.
- Purge: physical or logical technique rendering data recovery infeasible through state-of-the-art laboratory techniques, including cryptographic erase for SED devices.
- Destroy: physical disintegration, incineration, or pulverisation, reserved for media leaving the security domain or containing classified data.

## 10. Compliance evidence

Evidence packages must satisfy multiple frameworks simultaneously.

- HIPAA: 45 CFR §164.312(a)(2)(iv) and §164.312(e)(2)(ii) for encryption and transmission security.
- GDPR: Article 32 obligations for pseudonymisation and encryption.
- PCI DSS v4.0: Requirements 3 and 4 for stored and transmitted cardholder data.
- ISO 27001:2022: Annex A 8.10 for information deletion and 8.24 for use of cryptography.

## 11. SOAR integration for storage incident response

Security Orchestration Automation and Response (SOAR) platforms must consume storage telemetry and execute documented playbooks. Integration points include anomalous access alerts, ransomware detection on file systems, SED authentication failures, and KMIP key revocation events. Playbooks must perform credential rotation, snapshot isolation, network quarantine, and forensic preservation. Runbooks shall be tested annually and version-controlled under change management.

## 12. Risk register

Identified risks include insider exfiltration via removable media, firmware compromise of SED controllers, KMIP endpoint compromise, sanitisation procedural deviation, and SOAR playbook staleness. Each entry includes likelihood, impact, inherent score, residual score post-control, and accountable owner.

## 13. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
