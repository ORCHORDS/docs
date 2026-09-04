# NIST AAL3 Authenticator and Session Validation

## Trigger
Run before claiming NIST SP 800-63B-4 AAL3, after authenticator or session-management changes, and during periodic high-assurance authentication review.

## Inputs
- Authenticator key-storage and cryptographic architecture.
- Authentication protocol documentation.
- Session and reauthentication configuration.
- Test account and representative authenticator.

## Procedure
1. Verify that the AAL3 cryptographic authenticator uses a non-exportable private key.
2. Confirm that key protection uses the hardware-protected isolated environment required by the current NIST AAL3 model.
3. Exercise the authentication protocol and confirm phishing resistance.
4. Attempt replay of a captured authentication exchange and confirm the protocol rejects stale authentication messages.
5. Verify that initial authentication demonstrates authentication intent from at least one authenticator.
6. Measure the configured overall reauthentication timeout and confirm it does not exceed 12 hours.
7. Measure the inactivity timeout and compare it with NIST's recommended maximum of 15 minutes; document any deviation explicitly.
8. Trigger reauthentication and verify it retains the same AAL3 requirements as initial authentication, including phishing resistance, replay resistance, non-exportable-key use, and authentication intent.
9. Confirm that a session secret alone cannot extend the session beyond the applicable reauthentication boundary.
10. Record findings, owners, and retest evidence.

## Escalation
Escalate any AAL3 claim where the private key is exportable, phishing/replay resistance is absent, authentication intent is not demonstrated, or session reauthentication permits a weaker path while preserving the AAL3 label.

## Evidence
- Key exportability and protection evidence.
- Phishing-resistance test.
- Replay-resistance test.
- Authentication-intent test.
- Overall and inactivity timeout tests.
- End-to-end reauthentication evidence.

## Completion criteria
The authenticator and session-management path satisfy the documented NIST AAL3 requirements for the assessed deployment, including strong reauthentication behavior.

## Source basis
- NIST SP 800-63B-4, final July 2025: https://pages.nist.gov/800-63-4/sp800-63b.html
