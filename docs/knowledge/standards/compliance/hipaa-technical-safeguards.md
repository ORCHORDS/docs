# hipaa-technical-safeguards

**Issue:** Engineering teams building systems that touch electronic protected health information (ePHI) routinely treat HIPAA Security Rule technical safeguards as a checkbox ("we encrypt everything") and miss the actual structure of 45 CFR 164.312. The regulation defines five standards — Access Control, Audit Controls, Integrity, Person or Entity Authentication, and Transmission Security — each with "required" and "addressable" specifications, and "addressable" does not mean optional: it means implement the specification or document, via risk analysis, an equivalent alternative. The sibling safeguard families (administrative, physical, audit controls) have dedicated runbooks here, but the technical safeguards — the ones engineers actually build — did not, and January 2025's proposed HIPAA Security Rule overhaul (which would make encryption and MFA strictly mandatory and remove the addressable tier) makes under-implementing them now a growing liability.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The five standards of 45 CFR 164.312

1. **Access Control — 164.312(a)(1).** Controls that limit ePHI access to properly authorized persons. Two specifications are outright required: Unique User Identification (no shared or generic accounts) and Emergency Access Procedure (a documented break-glass path). Automatic Logoff and Encryption/Decryption are addressable — you either implement them or write a documented, risk-based justification for an equivalent measure.
2. **Audit Controls — 164.312(b).** Hardware, software, and procedural mechanisms that record and examine activity in information systems containing or transmitting ePHI. Logging alone is insufficient; the standard covers examination, meaning you need a review cadence, not just log storage.
3. **Integrity — 164.312(c)(1).** Policies and procedures protecting ePHI from improper alteration or destruction. The addressable sub-specification (164.312(c)(2)) adds mechanisms to authenticate ePHI — checksums, hashes, or electronic signatures that prove records have not been tampered with.
4. **Person or Entity Authentication — 164.312(d).** Technical verification that the person or entity accessing ePHI is who they claim to be. This is the legal hook for MFA: single-factor password authentication for remote ePHI access is very hard to defend in a modern risk analysis.
5. **Transmission Security — 164.312(e)(1).** Technical security measures guarding against unauthorized access to ePHI transmitted over an electronic communications network. Addressable sub-specifications cover Integrity Controls (assurance transmitted data arrives unaltered) and Encryption (in transit).

## Engineering implementation per standard

1. **Unique user IDs via a single IdP.** Federate every system that touches ePHI to one identity provider (Okta, Entra ID, WorkOS); prohibit local accounts and service-team shared logins. Service accounts get individual identities with rotated credentials, and each maps to a human owner in your asset inventory.
2. **Break-glass emergency access.** Implement a documented procedure — a segregated credential or a timed privilege grant — that fires an alert on use and triggers a post-use review within a defined window (for example, 24 hours). Untested break-glass paths are a common OCR finding.
3. **Automatic logoff and session timeouts.** Default to short idle timeouts (15 minutes is the common benchmark) on ePHI-facing consoles; for native mobile apps where 15-minute logoff destroys usability, document a compensating control set (device-level auth, biometric gate on app resume, remote wipe via MDM) in the risk analysis.
4. **Encryption at rest and in transit.** AES-256 at rest with managed KMS keys and TLS 1.2+ (prefer 1.3) in transit, with HSTS and modern cipher suites enforced. HHS guidance treats NIST-validated encryption plus properly managed key material as a safe harbor that can render breached data "unsecured ePHI"-exempt from breach notification.
5. **Audit logging pipeline.** Emit structured events (actor, action, patient record ID, source IP, timestamp) from every ePHI-touching component to append-only storage with 6-year documentation retention per 164.316(b)(2); protect logs from modification (object lock/WORM or equivalent) and run scheduled reviews with documented sign-off.
6. **MFA everywhere ePHI is reachable.** Phishing-resistant factors (WebAuthn/FIDO2) for workforce; step-up or re-authentication for high-risk actions like bulk record export.

## Gotchas and 2025-2026 outlook

1. **"Addressable" is a documentation trap.** If you skip an addressable specification, the artifact OCR expects is a written rationale tied to your risk analysis showing the alternative is reasonable and equivalent — not a silent omission. Most failed technical-safeguard audits are missing this paperwork, not the control.
2. **Unencrypted channels persist in the seams.** Email to patients, SFTP drops with vendors, fax gateways, and third-party JavaScript on patient portals are the usual places transmission security breaks while the main app is fully TLS'd.
3. **Audit logs without review fail 164.312(b).** Storing logs is table stakes; the examination half requires a documented review process (who, how often, what triggers escalation) and evidence the reviews happened.
4. **The January 2025 Security Rule NPRM tightens all of this.** OCR's proposed rule would eliminate the addressable/required distinction (making encryption and MFA mandatory), require asset inventory and network segmentation, and mandate 72-hour restoration capabilities for critical systems. Build to that bar now rather than re-architecting when the final rule lands.
5. **CSP inheritance has limits.** Cloud providers cover hypervisor-level controls, but unique user IDs, session timeouts, logging, and application-layer encryption remain your responsibility — inherited controls only cover what the BAA and shared-responsibility matrix actually say they cover.

## Related

1. **`hipaa-audit-controls.md`.** Deeper treatment of logging standards and examination cadence.
2. **`hipaa-administrative-safeguards.md` / `hipaa-physical-safeguards.md`.** The other two safeguard families that round out the Security Rule.
3. **`hipaa-phi-handling.md`.** Data-level patterns (de-identification, minimum necessary) that reduce how much of 164.312 applies in the first place.
