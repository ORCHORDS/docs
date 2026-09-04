---
title: "DNS Resilience and Mitigation Playbook"
owner: "Network Security Owner"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# DNS Resilience and Mitigation Playbook

## Trigger

Use this playbook when a DNS-related security or reliability event is detected (DNS hijacking, cache poisoning, denial-of-service, registration tampering, dangling delegation, lookup misconfiguration, resolver compromise) or when DNS-related security controls must be established or audited.

## Scope

Apply the process to authoritative DNS service, recursive resolvers, DNSSEC signing and validation, registrar accounts, DNS-based authentication (SPF, DKIM, DMARC, MTA-STS, TLS-RPT, DANE), and DNS-aware load-balancing or service-mesh configuration.

## Inputs

- DNS zone inventory and registrar records;
- resolver configuration and DNSSEC validation policy;
- DNS traffic logs and anomaly indicators;
- registration lock and contact-record state;
- authentication alignment records (SPF, DKIM, DMARC).

## Steps

1. **Detect and classify the event.** Determine whether the event is a hijack, poisoning, denial-of-service, registration tampering, dangling delegation, or misconfiguration; identify affected zones and resolvers.
2. **Preserve evidence.** Capture authoritative and resolver logs, traffic captures, registrar records with timestamps, and DNSSEC chain state before any change.
3. **Contain the threat.** For hijack, transfer control back to authorized accounts, restore valid records, and apply registry lock (e.g., clientTransferProhibited, clientUpdateProhibited); for DoS, activate upstream filtering or move authoritative resolution behind a DDoS-protected service.
4. **Remediate records.** Replace poisoned records, restore correct serial numbers, and verify zone signing if DNSSEC-enabled.
5. **Harden DNSSEC.** Sign affected zones with a validated chain (NSEC3 preferred over NSEC for non-enumeration); verify DS records at the parent and publish the signed zone via signed zone transfers (e.g., IXFR with TSIG).
6. **Lock registrar accounts.** Apply registry lock, two-factor authentication, hardware-backed credentials for registrar access; confirm contact records point to monitored mailboxes.
7. **Verify alignment.** Check SPF, DKIM, DMARC, MTA-STS, TLS-RPT records to ensure DNS state aligns with email and certificate policies.
8. **Communicate.** Notify affected internal teams and external relying parties; if the hijack or poisoning disrupted customer-visible services, follow the incident communications playbook.
9. **Recover.** Restore authoritative resolution, monitor for recurrence, and validate DNSSEC validation across recursive resolvers.
10. **Close and learn.** Document root cause, decisions, timeline, and corrective actions; track lessons to closure.

## Escalation

Escalate to the Network Security Owner, Public Communications, and Legal when:
- a registered domain has been transferred or modified without authorization;
- DNSSEC keys have been rotated by an unauthorized party;
- DNS state disruption has caused customer-visible outage;
- alignment records (SPF/DKIM/DMARC) have been tampered with.

## Evidence

- DNS transaction logs and resolver query logs;
- zone file snapshots and DNSSEC chain state;
- registrar account audit trail and registry lock records;
- detection and mitigation timeline;
- post-event validation results.

## Completion Criteria

The response is considered complete when:
- authoritative resolution returns to expected results across validation points;
- DNSSEC chain is valid where applicable;
- registrar controls are hardened and monitored;
- alignment records and authentication state are validated;
- corrective actions are tracked to closure.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Maintain an exception register for unsigned internal zones with documented mitigation.

## Related Documents

- [RFC 4033 DNSSEC Introduction](RFC_4033_DNSSEC_INTRODUCTION.md)
- [RFC 8461 MTA-STS](RFC_8461_MTA_STS.md)
- [RFC 8460 SMTP TLS Reporting](RFC_8460_SMTP_TLS_REPORTING.md)
- [NIST SP 800-81 Secure DNS Deployment](NIST_SP_800_81_SECURE_DNS.md)
