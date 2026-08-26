# iso-27017-cloud-security

**Issue:** Implementing ISO 27017:2015 cloud-specific information security controls
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27017 provides cloud-specific guidance on top of ISO 27002. It adds controls for both cloud service providers (CSPs) and cloud service customers (CSCs) to address the shared responsibility model.

## Pattern / Solution
Controls unique to ISO 27017 (not in ISO 27002):

For cloud service customers (CSCs — organizations using AWS/GCP/Azure etc.):
- CLD.6.3.1: Shared roles and responsibilities — document the shared responsibility matrix; include in vendor agreements
- CLD.8.1.5: Removal/return of assets — ensure data is returned or securely deleted when leaving a CSP
- CLD.9.5.1: Segregation in virtual environments — use VPCs, network segmentation; document isolation controls
- CLD.9.5.2: Virtual machine hardening — use hardened base images (CIS Benchmarks); image scanning in CI

For cloud service providers (CSPs):
- CLD.12.1.5: Administrator operational security — CSP admin access auditing; privileged access management

Shared responsibility mapping template:
```
Control Area          | CSP Responsibility      | CSC Responsibility
Physical security     | Full                    | None
Network perimeter     | Shared                  | VPC config, SGs
OS patching           | Managed services: CSP   | IaaS: CSC
Data encryption       | Encryption at rest key mgmt available | Enable, manage keys
IAM                   | IAM service provided    | Configure policies, roles
```

Implementation checklist:
- Enable all CSP-native security services (AWS Security Hub, GuardDuty, CloudTrail)
- Review CSP's ISO 27017 certificate to confirm their responsibilities
- Include shared responsibility clauses in cloud SLAs

## Gotchas
- Assuming the CSP covers all security is the most common cloud compliance mistake
- CSP ISO certifications do not transfer to the customer — customer must achieve own certification
- Multi-cloud environments need a unified responsibility matrix
- Data sovereignty requirements interact with cloud region selection

## Related
- `iso-27002-2022-new-controls.md`
- `iso-27018-pii-cloud.md`
- `vendor-security-assessment.md`
