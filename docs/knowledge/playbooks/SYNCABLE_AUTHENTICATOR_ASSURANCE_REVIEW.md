# Syncable Authenticator Assurance Review

## Trigger
Run before adopting syncable passkeys or other syncable cryptographic authenticators, when changing sync-fabric policy, and whenever the target NIST assurance level changes.

## Inputs
- Authenticator architecture and key-storage documentation.
- Sync-fabric behavior and access controls.
- Recovery and account-transfer process.
- Target NIST AAL.

## Procedure
1. Determine whether the authentication private key can be exported, cloned, backed up, or synchronized.
2. Identify the sync fabric and document how cloned authentication keys are protected at rest and in transit.
3. Review how access to the sync fabric is authenticated and how recovery or device-transfer events are controlled.
4. Confirm the intended NIST assurance level for the relying service.
5. If the target is AAL3, reject use of a syncable authenticator for the AAL3 cryptographic authenticator because NIST requires a non-exportable private key at AAL3.
6. For use up to AAL2, verify the syncable-authenticator protections and recovery model against the current NIST Appendix B requirements.
7. Evaluate phishing resistance separately from syncability; do not treat “passkey,” “phishing-resistant,” and “AAL3-capable” as interchangeable labels.
8. Record assurance classification, exceptions, owners, and retest evidence.

## Escalation
Escalate any design that classifies an exportable/syncable authentication key as NIST AAL3, or that cannot explain how its sync fabric protects cloned authentication secrets.

## Evidence
- Key export/sync test results.
- Key-storage architecture evidence.
- Sync-fabric protection evidence.
- Recovery-path test.
- Final AAL classification.

## Completion criteria
Syncability and key exportability are known, the authenticator is assigned only to compatible assurance levels, and sync-fabric protections are evidenced for the chosen deployment.

## Source basis
- NIST SP 800-63B-4, final July 2025, including normative Appendix B on Syncable Authenticators: https://pages.nist.gov/800-63-4/sp800-63b.html
