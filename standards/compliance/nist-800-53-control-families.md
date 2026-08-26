# nist-800-53-control-families

**Issue:** Navigating NIST SP 800-53 Rev 5 control families for federal and commercial security programs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
NIST 800-53 Rev 5 provides a comprehensive catalog of security and privacy controls used in FedRAMP, FISMA, and increasingly commercial frameworks. Understanding the 20 control families is essential for gap analysis.

## Pattern / Solution
20 Control Families (Rev 5):

| ID  | Family                        | Key Controls |
|-----|-------------------------------|--------------|
| AC  | Access Control                | Least privilege, MFA, remote access |
| AT  | Awareness and Training        | Security training, role-based training |
| AU  | Audit and Accountability      | Audit logging, log protection, review |
| CA  | Assessment, Auth, and Monitoring | Risk assessments, continuous monitoring |
| CM  | Configuration Management      | Baselines, change control, SBOM |
| CP  | Contingency Planning          | BCP, DR, backup |
| IA  | Identification and Authentication | Identity management, authenticator mgmt |
| IR  | Incident Response             | IRP, incident handling, training |
| MA  | Maintenance                   | Controlled maintenance, remote maintenance |
| MP  | Media Protection              | Media sanitization, transport |
| PE  | Physical and Environmental    | Physical access, visitor control |
| PL  | Planning                      | Security plans, concept of operations |
| PM  | Program Management            | Risk management program, POAM |
| PS  | Personnel Security            | Screening, termination, transfers |
| PT  | PII Processing and Transparency | Privacy notices, consent, individual participation |
| RA  | Risk Assessment               | Risk assessment process, vulnerability monitoring |
| SA  | System and Services Acquisition | Developer security requirements, SDLC |
| SC  | System and Communications Protection | Network segmentation, encryption in transit |
| SI  | System and Information Integrity | Malware protection, security alerts, patching |
| SR  | Supply Chain Risk Management  | Supplier assessments, SBOM, provenance |

Baseline selection: Low, Moderate, High — each baseline specifies which controls apply.
Overlays: specific sectors (healthcare, privacy) add additional controls.

## Gotchas
- Rev 5 merged security and privacy controls — privacy team must be involved in assessment
- "Inherited" controls (from CSP/FedRAMP package) must be documented in SSP even if not implemented by customer
- Control enhancements (e.g., AC-2(1)) are separate from base controls and have independent requirements
- Not all controls are applicable to all system types — use tailoring guidance

## Related
- `fedramp-authorization-basics.md`
- `nist-csf-2-mapping.md`
