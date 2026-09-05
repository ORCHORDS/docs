# Anti-Automation Business Logic Abuse Review

## Purpose

Verify that high-impact application functions resist excessive automated use that could create abusive transactions, exhaust quotas or costly resources, generate unwanted data, scrape protected information, or cause denial of service.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-2.4.1 requires anti-automation controls against excessive calls that can lead to data exfiltration, garbage-data creation, quota exhaustion, rate-limit breaches, denial of service, or overuse of costly resources. Requirement v5.0.0-2.4.2 additionally calls for realistic human timing in applicable business flows.

## Inputs

- inventory of sensitive or costly application functions;
- documented business limits and expected user behavior;
- rate-limit, quota, fraud, and abuse-detection configuration;
- representative user roles, sessions, IP/network contexts, and API clients;
- safe load or automation test tooling.

## Procedure

1. **Identify abuse-sensitive functions.** Prioritize registration, login/recovery, invitations, search/export, messaging, purchases, reservations, voting, promo redemption, account changes, expensive compute, and other limited operations.
2. **Define expected limits.** Record per-user, per-account, per-resource, and global limits from product or security requirements before testing.
3. **Test burst behavior.** Send rapid repeated requests and confirm the application throttles, rejects, queues, or otherwise controls excessive activity before material harm occurs.
4. **Test distributed attempts.** Where appropriate and authorized, vary sessions or source contexts to determine whether controls can be trivially bypassed by spreading requests.
5. **Test resource exhaustion.** Confirm automation cannot cheaply consume finite inventory, quotas, expensive third-party calls, storage, or compute beyond intended business limits.
6. **Test duplicate effect.** Repeated calls should not generate duplicate irreversible actions where the business operation is intended to be one-time or idempotent.
7. **Test timing assumptions.** For workflows expected to require human interaction, check whether unrealistically fast submissions are detected or constrained when the threat model requires it.
8. **Review error behavior.** Rate-limit and abuse responses should not disclose sensitive implementation details or create a new amplification path.
9. **Review recovery and fairness.** Confirm legitimate users can recover from throttling and that shared network environments are not unnecessarily blocked by a control designed around one identifier.
10. **Review monitoring.** Confirm material abuse events are observable enough to support investigation, tuning, and escalation without collecting unnecessary sensitive data.

## Evidence

Record the tested function, identities and dimensions used for limiting, request rates, observed thresholds, response behavior, downstream resource impact, logs/alerts, exceptions, and remediation owners.

## Completion criteria

The review is complete when abuse-sensitive functions enforce documented limits under realistic automated testing, obvious evasion paths are addressed, costly or irreversible actions cannot be amplified beyond intended limits, and residual risks have accountable owners.

## Sources

- OWASP ASVS 5.0.0, V2.4 Anti-automation: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x11-V2-Validation-and-Business-Logic.md
- OWASP Automated Threats to Web Applications: https://owasp.org/www-project-automated-threats-to-web-applications/

## Scope note

Anti-automation controls should be risk-based. Rate limiting alone may be insufficient, while indiscriminate CAPTCHAs or aggressive blocking can create accessibility and availability problems for legitimate users.
