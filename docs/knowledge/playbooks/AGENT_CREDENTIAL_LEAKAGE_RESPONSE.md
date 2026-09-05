---
title: "Agent Credential Leakage Response Playbook"
standard: "NIST SP 800-61 Rev 3, OWASP Top 10 for LLM Applications (LLM02 Sensitive Information Disclosure)"
publisher: "NIST / OWASP"
category: "response-playbook"
subcategory: "agent-security"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/61/r3/final"
status: "approved"
classification: "public"
audience: "security operations, AI engineering, identity management"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Credential Leakage Response Playbook

## Trigger

Credentials, secrets, API keys, tokens, or other authentication material associated with an AI agent have been exposed — through prompt leakage, log exposure, error message, telemetry channel, screenshot capture, or a third-party data breach.

## Scope

The playbook applies to:

- Static secrets embedded in agent prompts, configuration, or tool arguments.
- Short-lived tokens the agent mints, holds, or relays.
- Credentials the agent accesses through connected identity providers.
- Customer or partner credentials the agent observes in conversation.

## Inputs

- Alert or ticket identifying the leaked credential, scope, and suspected exposure window.
- Audit trail of every place the credential has been used or referenced.
- Identity provider and secret manager configuration.
- Communication roster for affected parties.

## Steps

1. **Contain the leak.** Suspend the agent, disable the leaked credential, and revoke any tokens the credential could mint. Quarantine logs, screenshots, or messages that contain the credential.
2. **Assess blast radius.** Determine which systems, tenants, or customers were reachable with the leaked credential. Enumerate actions taken under the credential during the exposure window.
3. **Rotate credentials.** Replace static secrets, reissue API keys, force token revocation at the identity provider, and verify rotation in every dependent system.
4. **Investigate the leakage path.** Identify whether the leak came from prompt leakage, configuration exposure, logging, or a third party. Capture the chain of custody for evidence.
5. **Notify affected parties.** Inform internal teams, customers, partners, and regulators as required by the data breach response record. Coordinate public statements with legal and communications.
6. **Harden the agent.** Remove the credential from prompts and configuration, move to a secret broker with just-in-time issuance, and redact credential-shaped strings from logs and telemetry.
7. **Re-test.** Add a regression test that confirms the agent does not surface credential-shaped strings in any output, log line, or telemetry field.

## Escalation

Escalate when:

- The leaked credential enabled privileged actions.
- Multiple tenants, customers, or partners were impacted.
- Regulatory notification obligations are triggered.

Notify the CISO, legal, privacy, and the identity provider's trust and safety team.

## Evidence

- Quarantine log entries containing the credential.
- Rotation confirmation from the secret manager and identity provider.
- List of actions taken under the credential during the exposure window.
- Updated prompt, configuration, and logging policy with change ticket reference.

## Completion Criteria

The incident closes when:

- The credential is rotated and the old credential is confirmed disabled.
- Every dependent system has reverted any state that the credential touched during the exposure window.
- Affected parties are notified as required.
- The agent is hardened and a regression test is in place.

## Exceptions

- **Test environment only.** Where the credential was scoped to a non-production environment with no live data, follow a reduced response that documents the scope.
- **Customer-managed credential.** The customer owns rotation; the platform coordinates the boundary and documents it in the response.

## Related Documents

- NIST SP 800-61 Rev 3 (Computer Security Incident Handling Guide)
- OWASP Top 10 for LLM Applications (LLM02 Sensitive Information Disclosure)
- Secret Rotation Response
- Data Breach Response Record
- OAuth 2.1 Client Integration Response
