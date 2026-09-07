# Mobile Device Management (MDM) and UEM Rollout Playbook

## Purpose

Deploy Unified Endpoint Management (UEM) coverage across iOS, Android, macOS, and Windows 10/11 endpoints with an enrolment programme, conditional access, and threat defence. The playbook standardises enrolment, policy enforcement, certificate distribution, and integration with the identity provider and security operations stack so that managed devices meet compliance baselines and untrusted devices are denied access to corporate resources.

## Audience

Endpoint engineering, IT operations, security engineers, IAM engineers, and MDM administrators who own enrolment design, policy authoring, certificate lifecycle, and operational handover of the UEM service.

## Pre-conditions

- UEM vendor selected (Intune, Jamf, Workspace ONE, MobileIron, Kandji, or equivalent) with a procurement contract in place.
- Apple Business Manager or Android Enterprise enrolment tokens issued to the tenant.
- Identity provider (IdP) configured with conditional access and a group model that maps to device compliance states.
- Certificate authority (SCEP/NDES or PKI) reachable from managed devices for device identity.
- Mobile Threat Defence (MTD) vendor selected and licensed for the target fleet size.
- Network connectivity for device enrolment, certificate enrolment, and app distribution from corporate and remote networks.
- Change window approved and stakeholder communication plan in place.

## Procedure

1. Stand up the UEM tenant with multi-region failover, RBAC roles, and admin break-glass accounts. Enable audit logging and forward events to the SIEM.
2. Configure enrolment profiles for BYOD, CYOD, and COPE on iOS, Android, macOS, and Windows 10/11. Bind Apple Business Manager or Android Enterprise tokens so device enrolment is zero-touch.
3. Integrate with the IdP for conditional access and device compliance signals. Map UEM compliance states to IdP claims so non-compliant devices are blocked at the edge.
4. Distribute SCEP/NDES certificates for device identity. Configure certificate templates per platform and align validity with the corporate PKI policy.
5. Configure compliance policies for OS version, passcode, encryption, jailbreak or root detection, and threat level. Set grace periods for remediation before marking non-compliant.
6. Configure app protection policies and MAM-wrapped app configurations. Apply per-app data loss prevention controls for mail, browser, and approved productivity apps.
7. Wire MTD signals into the SIEM and SOAR pipelines. Build playbooks for jailbreak detection, malicious app install, and high-risk network posture.
8. Roll out phased enrolment with a canary cohort. Start with IT pilot users, expand to a controlled business unit, then scale to the full fleet.
9. Validate remote wipe, lock, and locate controls on a representative device per platform. Confirm corporate data removal without affecting personal data on BYOD profiles.
10. Validate app-level encryption keys and per-app VPN policies for sensitive workloads. Verify certificate pinning and tunnel reachability from the managed browser and MAM apps.
11. Document recovery procedures for lost or stolen devices, including how to trigger selective wipe, full wipe, and certificate revocation.
12. Hand over to IT operations with runbooks, dashboards, alert routing, and a 30-day hypercare window before final acceptance.

## Rollback

Unenrol devices from the UEM tenant in cohorts, revoke issued SCEP/NDES certificates at the CA, isolate the UEM service by removing IdP trust and conditional access policies, restore group memberships and access rules to the pre-rollout baseline, and document the rollback with timestamps, affected cohorts, and outstanding risks for follow-up.

## References

- [Mobile Device Security Governance](../standards/NIST_SP_800_124_R2_MOBILE_GOVERNANCE.md)
- [Keycloak Version Governance](../reference/KEYCLOAK_VERSION_GOVERNANCE.md)
