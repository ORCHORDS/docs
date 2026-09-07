# NIST SP 800-188 (2019) Trustworthy Email Governance

## 1. Scope
This card establishes governance requirements derived from NIST Special Publication 800-188 (2019), Trustworthy Email. It applies to all organisational domains, mail transfer agents, submission services, mail user agents, and abuse-reporting pipelines operated by or on behalf of the organisation. The scope covers inbound, outbound, and intra-organisational email flows, including automation-generated messages, and is binding on operators, administrators, and developers responsible for mail infrastructure.

## 2. Normative references
The following documents are referenced and are indispensable for the application of this card:
- NIST SP 800-188 (2019), Trustworthy Email
- RFC 5321, Simple Mail Transfer Protocol
- RFC 5322, Internet Message Format
- RFC 6376, DomainKeys Identified Mail (DKIM) Signatures
- RFC 7208, Sender Policy Framework (SPF)
- RFC 7489, Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- RFC 8460, SMTP MTA Strict Transport Security (MTA-STS)
- RFC 8461, SMTP DANE
- RFC 8462, SMTP TLS Reporting (TLS-RPT)
- RFC 8551, Secure/Multipurpose Internet Mail Extensions (S/MIME) 4.0

## 3. Terms and definitions
For the purposes of this card, the following terms apply:
- DKIM: DomainKeys Identified Mail, a cryptographic message-signing mechanism defined in RFC 6376.
- DMARC: Domain-based Message Authentication, Reporting, and Conformance, defined in RFC 7489.
- DANE: DNS-based Authentication of Named Entities, used here in the SMTP context per RFC 8461.
- MTA-STS: SMTP MTA Strict Transport Security, defined in RFC 8460.
- SOAR: Security Orchestration, Automation, and Response platform used to triage, automate, and remediate security incidents.
- SPF: Sender Policy Framework, defined in RFC 7208.
- TLS-RPT: SMTP TLS Reporting, defined in RFC 8462.

## 4. Background
NIST SP 800-188 codifies the controls required to deliver trustworthy email in the face of spoofing, interception, and tampering. Email remains a primary vector for phishing, business email compromise, and data exfiltration. The publication provides organisations with a structured framework for authenticating senders, protecting message confidentiality and integrity, hardening transport, and operationalising abuse handling. This card operationalises those recommendations into binding policy statements aligned to the organisation's risk register and review cadence.

## 5. Email confidentiality and integrity controls
DMARC MUST be enforced at p=reject with a percent value of 100 for organisational domains; subdomains MUST be covered explicitly. SPF MUST be published as a single record per RFC 7208. DKIM signing MUST be applied to all outbound messages from authorised submission services, with keys rotated on a documented schedule aligned to RFC 6376 key-length recommendations. Messages lacking valid authentication MUST be rejected at the gateway; quarantine disposition is permitted only during documented migration windows. Failure to authenticate MUST generate a forensic report forwarded to the abuse handling pipeline.

## 6. Anti-spoofing controls (SPF, DKIM, DMARC)
SPF records MUST list every authorised sending source and MUST NOT rely on unsafe resolution terms. DKIM keys MUST be scoped to the signing domain and MUST NOT be reused across organisational boundaries. DMARC policy MUST be published at the organisational apex and at each subdomain, with rua and ruf reporting URIs routed to monitored addresses. Aggregate and forensic reports MUST be ingested by the analytics pipeline and reconciled against the authoritative inventory of sending sources; drift MUST be remediated within seven calendar days.

## 7. S/MIME and PGP message protection
S/MIME 4.0 per RFC 8551 is the preferred organisational standard for message-level confidentiality and integrity. Certificates MUST be issued from the approved internal or third-party authority, with revocation information consulted at signature verification. PGP is permitted for interoperability with named external counterparties only and MUST NOT be used as a substitute for S/MIME within the organisation. Plaintext transmission of restricted content is prohibited.

## 8. Submission and transport security (DANE SMTP, MTA-STS, TLS-RPT)
Submission services MUST enforce TLS 1.2 or higher with forward secrecy. MX hosts MUST advertise DANE SMTP per RFC 8461 using DNSSEC-validated TLSA records, and MUST publish MTA-STS policies per RFC 8460 in mode enforce. TLS-RPT reports MUST be ingested by the analytics pipeline and reconciled weekly; downgrade events MUST generate an incident within the SOAR platform.

## 9. Anti-phishing and abuse reporting workflows
User-reported phishing MUST be ingested via the report button and forwarded to the triage queue. Triage analysts MUST classify, prioritise, and remediate reports within defined SLAs, escalating confirmed compromises into the Security Orchestration, Automation, and Response (SOAR) platform for automated containment, host isolation, and credential reset. Indicators extracted from reports MUST be pushed to mail filtering, endpoint detection, and threat intelligence platforms. Post-incident reviews MUST capture lessons learned and feed the risk register.

## 10. Compliance evidence
Evidence retained for audit MUST include: published DNS records (SPF, DKIM, DMARC, MTA-STS, TLSA), TLS-RPT and DMARC aggregate reports, certificate inventories, configuration baselines for submission and MX hosts, signed policy attestations, and SOAR case logs. Evidence MUST be retained for the period required by the records retention schedule and MUST be reproducible from primary sources on demand.

## 11. Risk register
Material risks tracked under this card include: subdomains lacking DMARC enforcement, stale DKIM keys, missing DNSSEC validation at recursive resolvers, misconfigured MTA-STS modes, and gaps between reported and authorised sending sources. Each risk is assigned an owner, likelihood, impact, and remediation target. Residual risk above appetite MUST be escalated to the Information Security Steering Committee.

## 12. Review cadence
This card is reviewed every 180 days. The next scheduled review is 2027-03-07.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.