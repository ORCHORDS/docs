# Credential Compromise Response Playbook

## Trigger

Use when a password, token, API key, signing key, session, privileged account, or other authenticator is suspected or confirmed compromised.

## Inputs

- affected credential or account class;
- authentication, authorization, and audit logs;
- identity-provider and application session data;
- systems and data reachable with the credential;
- credential rotation, revocation, and recovery procedures.

## Steps

1. **Classify the exposure.** Determine whether compromise is suspected or confirmed, the credential type, privilege level, and known exposure window.
2. **Preserve evidence.** Retain relevant authentication, authorization, session, administrative, and application logs before routine retention or remediation destroys useful evidence.
3. **Contain active access.** Disable or restrict affected accounts, revoke exposed tokens or sessions, and block confirmed malicious access paths where safe to do so.
4. **Rotate or replace authenticators.** Replace compromised passwords, keys, tokens, or other authenticators using the approved recovery path; do not reuse exposed values.
5. **Assess blast radius.** Review privilege changes, related accounts, lateral movement, affected systems, and data access or exfiltration indicators.
6. **Validate clean recovery.** Restore access only after replacement credentials are active, malicious sessions are revoked, and the access path has been validated.
7. **Increase monitoring.** Watch for reuse attempts, anomalous authentication, privilege changes, and other signs of persistence.
8. **Notify appropriate owners.** Inform account owners, service owners, incident responders, and other required stakeholders according to policy and legal obligations.
9. **Record follow-up actions.** Capture root cause or likely cause, residual risk, control gaps, and any post-incident review or corrective work.

## Completion criteria

The response is complete when compromised access is contained, exposed authenticators are revoked or replaced, the likely blast radius has been assessed, recovery is validated, and follow-up actions are recorded.

## Sources

- CISA, Federal Government Cybersecurity Incident and Vulnerability Response Playbooks: https://www.cisa.gov/news-events/news/federal-government-cybersecurity-incident-and-vulnerability-response-playbooks
- NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide: https://csrc.nist.gov/pubs/sp/800/61/r2/final

## Scope note

Notification, forensic, regulatory, and evidence-retention requirements vary by organization and jurisdiction; this playbook does not replace those requirements.
