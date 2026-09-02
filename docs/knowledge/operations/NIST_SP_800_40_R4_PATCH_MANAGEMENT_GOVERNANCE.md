# NIST SP 800-40 r4 Guide to Enterprise Patch Management Governance

## Purpose

NIST SP 800-40 r4, "Guide to Enterprise Patch Management," provides guidance on establishing a comprehensive enterprise patch management program: identifying vulnerabilities, prioritizing patches, deploying patches, verifying deployment, and handling exceptions. The publication updates earlier versions with a risk-based approach to patching, exception handling, and the use of compensating controls. This article governs the application of SP 800-40 r4 so the patch management program operates with the discipline the publication requires.

## Scope

The publication applies to any organization that maintains IT systems and must address vulnerabilities. Within this knowledge base, the article covers the patch management process, the risk-based prioritization, the patch deployment methods, the exception handling, and the documentation of the program. It does not cover the specifics of vulnerability detection (which is addressed by SP 800-40 elsewhere and by other NIST publications).

## Workflow

1. Establish the patch management policy and scope: which systems, which stakeholders, which governance.
2. Identify vulnerabilities continuously through vulnerability scanning, vendor advisories, threat intelligence, and internal testing.
3. Prioritize patches based on risk: the severity of the vulnerability, the exposure of the system, the criticality of the affected system, the exploit availability, and the compensating controls.
4. Test patches before deployment: confirm the patch does not break the system. Use a test environment or a small-scope pilot.
5. Deploy patches using a defined deployment method: manual, scripted, or managed (e.g., WSUS, SCCM, Intune, MDM for mobile). Deployment should be scheduled and tracked.
6. Verify deployment: confirm the patch is installed on the targeted systems.
7. Handle exceptions: when a patch cannot be deployed promptly, document the exception with the rationale, the compensating controls, and the planned remediation.

## Controls and evidence

Patch management evidence includes the policy, the vulnerability inventory, the patch decisions (apply, defer, exception), the test records, the deployment records, the verification records, and the exception register. Each exception should have a documented review and a planned remediation.

## Validation

Validation should confirm the policy is current, vulnerabilities are identified continuously, prioritization is consistent with the policy, patches are tested before deployment, deployments are verified, and exceptions are tracked and reviewed. Periodic audits of the patch status confirm compliance with the policy.

## Failure correction

Common failure modes: patches are deployed without testing (correct: test patches before deployment, especially for critical systems); exception handling is informal (correct: require documented exceptions with rationale and compensating controls); verification is skipped (correct: verify deployment and follow up on missed systems); patching is limited to operating systems (correct: include third-party software, firmware, and dependencies); prioritization is uniform rather than risk-based (correct: apply the risk-based criteria the publication describes).

## Limitations

NIST SP 800-40 r4 provides guidance; it does not prescribe specific patch management tools or schedules. The publication does not address every vulnerability type or every system type (specialized systems may require additional guidance). Sector regulations may impose specific patching timelines (e.g., 30 days for high-severity vulnerabilities).

## Scope note

This article summarizes project-neutral operations use of NIST SP 800-40 r4. It does not assert any specific organization's patch management conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-40 r4 — Guide to Enterprise Patch Management: https://csrc.nist.gov/publications/detail/sp/800-40/rev-4/final