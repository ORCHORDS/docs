# NIST SP 800-45 Version 2 (2007) Email Security Governance

## 1. Scope

This standard establishes the minimum requirements for securing Simple Mail Transfer Protocol (SMTP) services operated in support of administrative, clinical, financial, and engineering functions. It applies to all Mail Transfer Agents (MTAs), Mail User Agents (MUAs), submission services, anti-spam relays, and abuse-reporting pipelines within the trust boundary. Conformance is required for every outbound mail domain and every inbound mail listener exposed to the public Internet. This document governs the policy, technical, and procedural controls referenced by related standards at `docs/knowledge/standards/NIST_SP_800_53_REV_5_CONTROLS.md:1`.

## 2. Normative references

The following documents are indispensable to the application of this standard. For dated references, only the cited edition applies. For undated references, the latest edition applies. RFC 5321 (SMTP), RFC 6376 (DKIM), RFC 7208 (SPF), RFC 7489 (DMARC), RFC 8461 (MTA-STS), RFC 7672 (SMTP TLS), and RFC 6698 (DANE/TLSA) are normative. NIST SP 800-45 Version 2, NIST SP 800-177, and NIST SP 800-53 Revision 5 are normative. HIPAA Security Rule (45 CFR §164), GDPR Articles 32 and 33, PCI DSS v4.0, and SOX Section 404 are referenced for compliance mapping.

## 3. Terms and definitions

MTA: Mail Transfer Agent. A network service that relays, accepts, and stores mail per SMTP. MUA: Mail User Agent. A client application used by an end user to compose, submit, read, and manage mail. MTA-STS: MTA Strict Transport Security. A policy mechanism that publishes a domain's strict TLS requirement and pins a trust-anchored certificate set for inbound SMTP. DANE: DNS-based Authentication of Named Entities. A DNSSEC-anchored mechanism that publishes TLSA records binding certificates to domains. SASL: Simple Authentication and Security Layer. A framework for authenticating mail submission. STARTTLS: An SMTP command that upgrades an existing plaintext connection to TLS. SOAR: Security Orchestration Automation and Response.

## 4. Background

Email remains the dominant initial-access vector for targeted intrusion, business email compromise, and credential harvesting. NIST SP 800-45 Version 2 provides the baseline guidance for mail server security. Since 2007, the threat landscape has shifted toward domain spoofing, brand impersonation, and supplier compromise. Modern governance must layer authentication (SPF, DKIM, DMARC), transport encryption (STARTTLS, MTA-STS, DANE), submission controls (SASL), content filtering, and SOAR-driven abuse handling onto the SP 800-45 baseline.

## 5. Mail server architecture and trust zones

Three trust zones are defined. The Public zone contains inbound SMTP listeners exposed to the Internet. The Submission zone hosts authenticated submission on port 587 with mandatory SASL. The Internal zone hosts the message store and groupware, accessible only to authenticated and authorized clients. Firewalls must enforce default-deny between zones. The Public zone is the only zone permitted to accept unauthenticated connections from external MTAs. The Submission zone must require SASL on every transaction. The Internal zone must not be reachable from the Public zone except through explicit application proxies.

## 6. Sender authentication: SPF, DKIM, DMARC enforcement

Every outbound domain must publish a Sender Policy Framework (SPF) record as a DNS TXT entry that authoritatively lists every authorized sending host. Every outbound message must carry a DomainKeys Identified Mail (DKIM) signature generated with at least a 2048-bit RSA key and aligned with the visible From: domain. Every outbound domain must publish a Domain-based Message Authentication, Reporting, and Conformance (DMARC) record. Enforcement must be configured at p=reject with pct=100, meaning one hundred percent of failing messages are rejected rather than quarantined. Aggregate (rua) and forensic (ruf) reports must be ingested by the security analytics platform described at `docs/knowledge/standards/SECURITY_ANALYTICS_PIPELINE.md:1`. Subdomains are governed by sp=reject unless an explicit exception is approved in writing.

## 7. Transport encryption: opportunistic TLS, MTA-STS, and DANE

Transport encryption is mandatory in all zones. Opportunistic TLS is enabled by advertising the STARTTLS capability on every listener and by configuring a minimum TLS 1.2 protocol with modern cipher suites. Opportunistic TLS provides confidentiality against passive eavesdroppers but does not defend against active downgrade attacks. MTA-STS is therefore required for every inbound-receiving domain. The MTA-STS policy at the `_mta-sts` subdomain must declare mode=enforce, pin the CA trust anchor, and refresh at intervals not exceeding sixty days. Reporting is delivered to the address published in the MTA-STS TXT record and is monitored continuously. DANE is required for outbound submission and is recommended for high-assurance peers. DANE binds the TLS certificate to the destination MX host via TLSA records anchored under DNSSEC-validated chains. DNSSEC must be valid on every authoritative name server that publishes mail-relevant records.

## 8. Content filtering and anti-phishing controls

Content filtering is layered at the MTA, the submission proxy, and the MUA. At the MTA, connection reputation, reverse DNS verification, and HELO/EHLO consistency checks are enforced. At the submission proxy, outbound DLP scanning is enforced for sensitive patterns including payment data, identifiers protected by `docs/knowledge/standards/HIPAA_SECURITY_RULE_GOVERNANCE.md:1`, and intellectual property markers. At the MUA, banner injection distinguishes external mail, first-time senders, and authenticated bulk senders. URL rewriting and sandbox detonation are required for links extracted from inbound mail.

## 9. Submission and SASL authentication

Authenticated submission must occur on port 587 over TLS and must complete a SASL exchange prior to any MAIL FROM command. Plaintext passwords are prohibited; SCRAM-SHA-256, OAUTHBEARER, or GSSAPI are the permitted mechanisms. Submission credentials must be bound to a single user identifier and must rotate on a documented schedule. Submission listeners must reject authentication attempts exceeding five per minute per source IP and must log every successful and failed authentication event.

## 10. SOAR (Security Orchestration Automation and Response) integration for abuse reporting and user-reported phishing

User-reported phishing and abuse@ inbox intake must be automated through a SOAR platform. Inbound abuse messages are parsed for report headers, ARF format indicators, DMARC failure report attachments, and MTA-STS report attachments. SOAR playbooks must enrich each report with passive DNS, certificate transparency, and reputation data, must correlate against historical reports, and must escalate to incident response when the affected brand, registrar, or hosting provider has been observed within the prior thirty days. SOAR playbooks must auto-generate remediation tickets for confirmed malicious senders, including blocklist submissions, registrar abuse filings, and takedown requests.

## 11. Compliance evidence (HIPAA, GDPR, PCI DSS, SOX)

Controls described herein generate evidence suitable for HIPAA Security Rule (45 CFR §164.308, §164.312), GDPR Articles 32 and 33, PCI DSS v4.0 (Requirements 1, 4, 7, 8, 10, 11), and SOX Section 404 IT general controls. Evidence artifacts include DMARC aggregate reports, DKIM signing logs, MTA-STS policy fetch logs, DANE TLSA validation logs, SASL authentication logs, SOAR playbook execution logs, DLP incident tickets, and abuse-report case files.

## 12. Risk register

| Identifier | Risk | Likelihood | Impact | Treatment |
|------------|------|------------|--------|-----------|
| EM-01 | Domain spoofing absent DMARC p=reject | High | High | Mandated in §6 |
| EM-02 | TLS downgrade absent MTA-STS | Medium | High | Mandated in §7 |
| EM-03 | Unauthenticated submission relay | Medium | Critical | Mandated in §9 |
| EM-04 | Delayed phishing response | Medium | High | SOAR playbooks in §10 |
| EM-05 | Sensitive data exfiltration via outbound mail | Medium | Critical | DLP scanning in §8 |

## 13. Review cadence

This standard is reviewed semi-annually, or upon material change to NIST guidance, IETF RFCs, or applicable law.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
