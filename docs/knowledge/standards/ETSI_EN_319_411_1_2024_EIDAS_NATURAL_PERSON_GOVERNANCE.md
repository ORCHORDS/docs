# ETSI EN 319 411-1:2024 eIDAS Natural Person Certificate Governance

## Purpose

ETSI EN 319 411-1:2024, "Electronic Signatures and Infrastructures (ESI); Policy and security requirements for Trust Service Providers issuing certificates; Part 1: General requirements," defines policy and security requirements for TSPs issuing certificates for natural persons, primarily in support of electronic signatures. The standard addresses certificate policy, certificate practice statement, identification and authentication, certificate lifecycle, facility and operational controls, and the audit framework. This article governs the application of EN 319 411-1 so a TSP issuing certificates for natural persons meets the policy and security requirements.

## Scope

The standard applies to TSPs issuing certificates for natural persons. Within this knowledge base, the article covers the certificate policy (CP), the certification practice statement (CPS), the identification and authentication of the subject, the certificate lifecycle (registration, issuance, suspension, revocation), the facility and operational controls, and the audit framework. It does not cover legal-person certificates (readers should consult EN 319 411-2).

## Workflow

1. Establish the certificate policy: the certificate types, the applicability, the obligations of the TSP and the subscriber, and the relationship to the general policy of EN 319 401.
2. Develop the certification practice statement (CPS): the operational practices the TSP follows.
3. Identify and authenticate the subject per the certificate policy:
   - For natural person certificates, identity proofing may be in person, remote (with approved methods), or based on existing electronic identity means.
   - Document the identity proofing and retain the evidence.
4. Manage the certificate lifecycle:
   - Registration: collect the subject's information and identity proofing.
   - Issuance: generate the key pair (or receive the subject's public key for non-QC), issue the certificate, and deliver the certificate to the subject.
   - Suspension: suspend the certificate where required (e.g., subject request, suspected compromise).
   - Revocation: revoke the certificate where required (compromise, termination, request).
   - Renewal: renew the certificate per the policy.
5. Operate the facility and operational controls per the standard: physical security, personnel security, network security, and incident management.
6. Audit the TSP per the audit framework: internal audit, self-assessment, conformity assessment by a conformity assessment body.
7. Cooperate with the supervisory body.

## Controls and evidence

Controls include the CP, the CPS, the identity proofing records, the certificate lifecycle records, the facility and operational controls, the audit records, and the supervisory communications. Each certificate should be traceable through the lifecycle.

## Validation

Validation should confirm the CP and CPS are current, identity proofing meets the policy, the lifecycle operates per the policy, the controls operate, the audit framework operates, and the supervisory body is informed. Conformity assessment confirms the TSP's eIDAS compliance.

## Failure correction

Common failure modes: identity proofing does not meet the policy (correct: re-perform the identity proofing); the CPS is not updated (correct: update the CPS per the policy); revocation is delayed (correct: process revocations within the standard's timeframes); facility controls are not operating (correct: maintain the facility controls per the standard).

## Limitations

ETSI EN 319 411-1 is a standard for TSPs issuing certificates for natural persons; it does not certify the TSP outside the conformity assessment. The standard does not cover legal-person certificates; readers should consult EN 319 411-2 for those. The standard does not replace national law.

## Scope note

This article summarizes project-neutral standards use of ETSI EN 319 411-1:2024. It does not assert any specific TSP's conformance or claim any certification outcome.

## Canonical sources

- ETSI EN 319 411-1:2024 — Policy and security requirements for Trust Service Providers issuing certificates; Part 1: General requirements: https://www.etsi.org/deliver/etsi_en/319400_319499/31941101/
- ETSI EN 319 411-2 — Requirements for trust service providers issuing certificates for legal persons: https://www.etsi.org/deliver/etsi_en/319400_319499/31941102/