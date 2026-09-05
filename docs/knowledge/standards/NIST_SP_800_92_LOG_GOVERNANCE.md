---
title: NIST SP 800-92 Guide to Computer Security Log Management Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-92 (September 2006) — Guide to Computer Security Log Management; https://csrc.nist.gov/publications/detail/sp/800-92/final
---

# NIST SP 800-92 Guide to Computer Security Log Management Governance

## Scope

This card governs how `orchords-docs` evaluates log management against NIST SP 800-92. It is the reference input for any KB card that describes logging, log retention, log analysis, or log archival.

## Why this card exists

NIST SP 800-92 is the de-facto log management guide. It organizes log management into planning, infrastructure, life cycle management, and analysis. A KB card that cites log management without binding to 800-92 produces a logging architecture that does not survive a NIST-aligned audit.

## Document set

- **NIST SP 800-92** (September 2006) — Guide to Computer Security Log Management.

References: `https://csrc.nist.gov/publications/detail/sp/800-92/final`.

## Four-part log management framework

### 1. Log management planning

- Define log management policy.
- Identify stakeholders (security, IT operations, compliance).
- Define log retention requirements.
- Document roles and responsibilities.

### 2. Log management infrastructure

- Log generation: log-producing hosts.
- Log collection and transfer: syslog, Windows Event Forwarding, journald.
- Log storage and disposal: SIEM, log archive.
- Log analysis: SOC analysts, automated rules.

### 3. Log management life cycle

- **Generate**: log-producing hosts and applications.
- **Transmit**: TLS-protected syslog, secure file transfer.
- **Store**: indexed and searchable for the retention period.
- **Analyze**: by SOC and automated rules.
- **Dispose**: at the end of the retention period, securely deleted.
- **Retention periods** depend on data class:

| Data class | Retention |
|---|---|
| Application logs | 30 — 90 days online, 1 year archive |
| Security logs | 90 days online, 1 year archive |
| Audit logs | 1 year online, 7 years archive |
| SIEM indexed | 90 days hot, 1 year warm, 7 years cold |
| Compliance (PCI, HIPAA, SOX) | per regulatory minimum |

### 4. Log management analysis

- Manual analysis: SOC analyst review.
- Automated analysis: SIEM rules, anomaly detection.
- Correlation: cross-source analysis.

## Log content

NIST recommends the following fields in every log entry:

- Timestamp (RFC 3339, with timezone).
- Source (host, IP, application).
- Event type / class.
- Severity.
- User (if applicable).
- Action / outcome.
- Description.

## Log source taxonomy

NIST categorizes log sources:

- **Operating system logs**: Windows Event Log, syslog, journald.
- **Application logs**: web server, database, custom applications.
- **Security tool logs**: IDS/IPS, EDR, firewall, VPN, NAC.
- **Network device logs**: router, switch, load balancer.
- **Cloud service logs**: CloudTrail, Azure Activity, GCP Audit Logs.

## Log integrity

- Hash log files daily; alert on hash drift.
- Use write-once storage (WORM) for compliance logs.
- Sign log files (HMAC or detached signature) for non-repudiation.

## Time synchronization

- NTP (RFC 5905) is required for all log-producing hosts.
- Use authenticated NTP (NTS per RFC 8915).
- Configure multiple time sources (≥ 3) for redundancy.
- Document the time source hierarchy.

## Mandatory pre-flight (before adopting a new log management component)

1. The log content policy is documented.
2. The retention period is documented.
3. The infrastructure components (collector, transport, storage, analysis) are documented.
4. Log integrity protection is configured.
5. Time synchronization is wired.
6. The log policy is reviewed annually.

## Cross-reference

| Domain | Card |
|---|---|
| SIEM | `SIEM_ARCHITECTURE_GOVERNANCE.md` |
| Time | `NTS_RFC_8915_VERSION_GOVERNANCE.md` |
| Threat intel | `RAVENSWORN_INDICATORS_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every log management card.
2. Confirm conformance to 800-92.
3. Confirm retention and integrity are current.
4. Update the next-review date.

## Sources

- NIST SP 800-92: `https://csrc.nist.gov/publications/detail/sp/800-92/final`
- RFC 5424 (syslog): `https://www.rfc-editor.org/rfc/rfc5424`
- RFC 5905 (NTP): `https://www.rfc-editor.org/rfc/rfc5905`
- RFC 8915 (NTS): `https://www.rfc-editor.org/rfc/rfc8915`
