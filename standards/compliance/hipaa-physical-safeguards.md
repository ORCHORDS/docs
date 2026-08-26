# hipaa-physical-safeguards

**Issue:** Implementing HIPAA Security Rule physical safeguards (45 CFR 164.310)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HIPAA physical safeguards cover physical access to systems that store or process ePHI, including facilities, workstations, and device security. Cloud-hosted systems still require physical safeguard consideration.

## Pattern / Solution
Four required physical safeguard standards:

1. Facility Access Controls (164.310(a)(1)):
   - Contingency operations plan for physical access during disasters
   - Facility security plan: documented physical access controls (keycards, locks, guards)
   - Access control and validation: procedures for access to areas with ePHI
   - Maintenance records for physical security controls

2. Workstation Use (164.310(b)):
   - Specify proper functions of each workstation class
   - Restrict access to workstations with ePHI access (screensavers, positioning away from public view)
   - Remote/work-from-home: policy for secure workstation use

3. Workstation Security (164.310(c)):
   - Physical safeguards for workstations accessing ePHI
   - Cable locks, office door locks, clear desk policy
   - Device encryption (FileVault, BitLocker) required

4. Device and Media Controls (164.310(d)(1)):
   - Disposal: NIST 800-88 compliant media sanitization; certificate of destruction
   - Media reuse: sanitize before reuse with ePHI for non-ePHI purposes
   - Accountability: track hardware containing ePHI (serial numbers, locations)
   - Data backup before movement of equipment

Cloud environments:
- For AWS/Azure/GCP: physical controls are inherited from CSP; obtain CSP's HIPAA-compliant BAA
- Document shared responsibility for physical security in risk analysis
- Still required: workstation controls for all endpoints accessing cloud-hosted ePHI

## Gotchas
- BYOD devices accessing ePHI require physical safeguards — MDM enrollment mandatory
- Printers in shared areas that print ePHI documents are in scope
- Thumb drives/external media with ePHI: prohibit or require encryption + tracking
- Physical safeguard audit: OCR looks for written procedures, not just practices

## Related
- `hipaa-administrative-safeguards.md`
- `hipaa-audit-controls.md`
- `hipaa-compliance.md`
