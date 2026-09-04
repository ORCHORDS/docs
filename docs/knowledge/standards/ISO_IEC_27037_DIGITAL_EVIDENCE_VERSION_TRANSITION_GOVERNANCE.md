---
title: "ISO/IEC 27037:2012 Guidelines for Identification, Collection, Acquisition and Preservation of Digital Evidence Version Transition Governance"
standard: "ISO/IEC 27037:2012"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "standards"
subcategory: "digital-evidence"
canonical_url: "https://www.iso.org/standard/44381.html"
status: "approved"
classification: "public"
audience: "Incident response investigators, digital forensics teams, legal liaison"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 27037:2012 Digital Evidence Version Transition Governance

## Profile

ISO/IEC 27037:2012 provides guidelines for the identification, collection, acquisition, and preservation of digital evidence. It defines concepts and identifies the processes and requirements for handling digital evidence to maintain its integrity and admissibility. The standard introduces key concepts of digital evidence first responders (DEFRs), the chain of custody, and the principles of preserving digital evidence in a forensically sound manner.

ISO/IEC 27037 is often treated as the forerunner of the ISO/IEC 27037 series (27040 for storage security, 27041 for assurance, 27042 for investigation). It is widely used by digital forensic practitioners; the requirements are baseline, not exhaustive.

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 27037:2012 |
| Title | Information technology — Security techniques — Guidelines for identification, collection, acquisition and preservation of digital evidence |
| Family | ISO/IEC 27037 series |
| Cross-reference | ISO/IEC 27042 (interpretation of digital evidence); ISO/IEC 27043 (incident investigation principles); NIST SP 800-86 (forensic process guide) |

## Process Components

| Component | Intent |
| --- | --- |
| Identify | Identify potential digital evidence sources within the incident boundary. |
| Collect | Acquire evidence from identified sources using forensically sound methods. |
| Acquire | Create bit-for-bit copies or logical acquisitions; document methods and tools. |
| Preserve | Maintain evidence integrity, chain of custody, and continuity through retention. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Cite as the methodology basis for digital evidence handling during incident response. |
| DEFRs | Identify and train digital evidence first responders; record their roster. |
| Tool selection | Use vetted acquisition and analysis tools; record tool versions and hashes. |
| Chain of custody | Maintain documented chain of custody for every artifact from collection to disposition. |
| Integrity | Compute and verify hash digests for every artifact at acquisition and at transfer. |
| Storage | Store evidence in a controlled, access-tracked location with retention rules. |
| Legal | Coordinate with Legal on jurisdiction-specific evidence-handling requirements. |

## Implementation Notes

- The standard provides framework guidance, not a comprehensive procedure; develop detailed internal procedures.
- Pair with ISO/IEC 27041 (method validation), ISO/IEC 27042 (interpretation), ISO/IEC 27043 (principles) for full forensic methodology.
- NIST SP 800-86 is the complementary U.S. guide for integrating forensics into incident response.
- Cloud and SaaS evidence requires attention to data-residency and service-provider records; clarify authority, scope, and chain-of-custody before collection.

## Companion Documents

- [ISO/IEC 27042:2015 Digital Evidence Interpretation](ISO_IEC_27042_DIGITAL_EVIDENCE_INTERPRETATION_GOVERNANCE.md)
- [ISO/IEC 27043:2015 Incident Investigation Principles](ISO_IEC_27043_INCIDENT_INVESTIGATION_GOVERNANCE.md)
- [NIST SP 800-86 Guide to Integrating Forensic Techniques](NIST_SP_800_86_FORENSIC_TECHNIQUES_GOVERNANCE.md)
- [Cybersecurity Incident Response Playbook](CYBERSECURITY_INCIDENT_RESPONSE.md)
