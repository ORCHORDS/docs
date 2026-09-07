# NIST SP 800-46 Rev. 2 (2016) Guide to Enterprise Telework, Remote Access, and Bring Your Own Device Governance

## 1. Scope
This card establishes governance requirements derived from NIST Special Publication 800-46 Revision 2, "Guide to Enterprise Telework, Remote Access, and Bring Your Own Device." It applies to all organizational units operating or consuming remote access services, including corporate-issued laptops, personally-owned devices used for work (BYOD), mobile endpoints, and the network services that terminate their connections. The card binds operators, security engineers, IT helpdesk, and remote employees to a single set of controls for connecting to internal resources from untrusted networks.

## 2. Normative references
The following documents are referenced and indispensable to the application of this card: NIST SP 800-46 Rev. 2, NIST SP 800-114 Rev. 1, NIST SP 800-63B, NIST SP 800-77 Rev. 1, NIST SP 800-53 Rev. 5, and ISO/IEC 27001:2022. For dated references, only the cited edition applies; for undated references, the latest edition of the referenced document applies.

## 3. Terms and definitions
- BYOD: Bring Your Own Device. A model in which an employee uses a personally owned endpoint to access organizational resources.
- MDM: Mobile Device Management. A centralized administrative framework that enforces device-level policy, configuration, and telemetry across enrolled endpoints.
- VDI: Virtual Desktop Infrastructure. A remote-display architecture that streams a desktop session from a centralized server or broker to a client device.
- ZTNA: Zero Trust Network Access. An access model that brokers per-session authorization using identity, device posture, and contextual signals rather than network location.

## 4. Background
Remote access was historically delivered by perimeter VPNs that granted broad network access once a user authenticated. Mobile devices, cloud workloads, and untrusted home networks have invalidated that model. SP 800-46 Rev. 2 codifies a layered set of controls covering device selection, hardening, authentication, transport security, and application publishing, and aligns them with modern zero-trust architectures.

## 5. Telework threat model and security considerations
Threats include untrusted Wi-Fi networks at cafés and hotels, lost or stolen devices, credential theft via phishing, malware exposure on personal devices, insider abuse of remote access, network capture of plaintext traffic, and unauthorized local accounts on shared family devices. Each threat shall be addressed by at least one preventive and one detective control recorded in the risk register.

## 6. Remote access architecture
Four architectural patterns dominate enterprise telework and each has distinct selection criteria.

- VPN: full tunnel to the corporate network; simple but exposes the entire network to the remote device.
- VDI: central desktop rendered on the endpoint; strong isolation but high bandwidth and licensing cost.
- Application publishing: brokered access to specific applications such as RDP, SSH, or web apps; minimal blast radius but requires per-app integrations.
- ZTNA (Zero Trust Network Access): per-session, identity- and posture-aware broker; preferred when the workforce is hybrid and the target estate spans multiple clouds.

Selection criteria include sensitivity of the target system, regulatory mandate (HIPAA, PCI DSS), user experience tolerance, and the maturity of the identity provider. ZTNA is the strategic default; legacy VPN is acceptable only where mandated by an existing peer-to-peer protocol that cannot traverse a broker.

## 7. BYOD and employer-owned device selection
Devices that touch organizational data shall meet a documented baseline. Employer-owned devices shall receive full-disk encryption, mobile device management enrolment, and an organization-issued identity. BYOD devices shall be partitioned: organization data and applications shall live in an MDM-managed container with separate keys, and personal applications shall be outside the container. Personally owned devices that cannot meet the baseline shall be denied access except to a limited public-facing subset of resources.

## 8. Client device hardening baselines
All managed endpoints shall run a supported operating system with security updates applied within the documented patch SLA. Local accounts shall use strong passphrases bound to the identity provider, biometric unlock shall not bypass authentication, and full-disk encryption shall be enabled. Host firewall and EDR agents shall be present and reporting. USB and removable media shall be restricted for endpoints handling regulated data.

## 9. Authentication, authorisation, and MFA
All remote access shall require phishing-resistant multi-factor authentication aligned with NIST SP 800-63B Authenticator Assurance Level 2 (AAL2) or higher. Acceptable authenticators include FIDO2/WebAuthn hardware keys, platform-bound passkeys, and PIV/CAC smart cards. SMS and voice one-time passcodes are prohibited for new deployments. Authorization shall be role-based, time-bound, and tied to a documented business purpose.

## 10. SOAR integration for remote access incidents
Security Orchestration Automation and Response (SOAR) platforms must consume remote access telemetry and execute documented playbooks. Integration points include VPN concentrator authentication events, ZTNA broker deny decisions, MDM compliance state changes, and EDR alerts raised on a remote endpoint. Playbooks shall perform session revocation, device quarantine, credential rotation, and ticket creation. Runbooks shall be tested quarterly and version-controlled under change management.

## 11. Compliance evidence
Evidence packages must satisfy multiple frameworks simultaneously. HIPAA: 45 CFR §164.312(a)(2)(iv) encryption, §164.312(d) authentication, and §164.308(a)(1)(ii)(D) device controls. PCI DSS v4.0: Requirements 8 (authentication), 12 (policy), and 1 (network segmentation between trusted and untrusted networks). FedRAMP: AC-2 account management, AC-17 remote access, IA-2 identification and authentication. Evidence includes remote access logs, MDM compliance reports, MFA enrollment records, and incident tickets.

## 12. Risk register
Identified risks include VPN concentrator compromise, ZTNA broker denial of service, MDM agent tampering, BYOD container bypass, lost device without remote wipe, and SOAR playbook staleness. Each entry includes likelihood, impact, inherent score, residual score post-control, and accountable owner.

## 13. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
