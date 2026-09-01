# Email Sender Identity Alignment (DMARC)

## Scope

This control governs the alignment, identification, and policy of brand-domain email used for marketing. It applies to outbound customer-facing email from brand-owned domains, including newsletter, promotional, transactional, lifecycle, winback, re-engagement, and confirmation messages, regardless of whether they are technically classified as marketing or transactional. It applies to email produced by internal systems, by an email service provider, by a marketing automation platform, by an SMS-to-email bridge, or by any other sender. It also applies to delegated subdomains used by affiliates, partners, agencies, and event organizers when those subdomains carry the parent brand's customer relationship.

The governing reference is RFC 7489, the DMARC specification, which defines a mechanism by which email senders can publish a policy in DNS that receivers use to authenticate messages claiming alignment with the sender's domain. DMARC depends on SPF (RFC 7208) and DKIM (RFC 6376) as underlying authentication mechanisms and on the concept of identifier alignment, by which the authenticated identity (the SPF-checked domain or the DKIM-signed domain) must match the domain in the visible From: header according to either strict or relaxed alignment.

## Workflow or implementation guidance

DMARC governance proceeds in six phases.

1. Inventory all sending systems. The inventory records each sending service or platform, its parent domain and subdomain, the purpose of the email it sends, the SPF record in use, the DKIM selector(s) in use, and the operational owner. Forensic data sources and aggregate report destinations are also recorded.
2. Configure DKIM on every sending system. Each sender signs with a DKIM key whose `d=` value aligns with the From: domain according to the chosen alignment mode. Rotation of keys is documented; compromised keys are revoked.
3. Configure SPF on every sending IP. Each sender publishes an SPF record at the right scope, identifying the IP space from which the sender sends. Subdomain delegation is recorded.
4. Publish a DMARC record. A DMARC record is published at the `_dmarc` host of each sending domain. The record starts in a monitoring posture with a reporting URI, gathers aggregate reports, and is tightened to a quarantine or reject policy as alignment and authentication become reliable.
5. Operate aggregate and forensic reports. Aggregate reports (RUA) are collected from every domain, reconciled to the sending inventory, and reviewed. Forensic reports (RUF) when collected are reviewed for legitimate complaints and unusual sources.
6. Maintain and tune. New senders are onboarded through the same controls. Old senders are offboarded by removing DNS records, decommissioning DKIM keys, and updating DNS history so that decommissioned infrastructure cannot authenticate messages.

## Controls

The controls in this workflow are designed to keep authentication working and to keep the DMARC policy in step with the actual sending reality.

- Every sending domain has a DMARC record with a clearly stated policy. Records in monitoring posture have explicit review dates.
- Identifier alignment is enforced as relaxed for organizational domains and as strict for the visible From: domain where stricter is operationally possible.
- DKIM keys are rotated on a documented cadence. Old keys are not removed in a way that breaks verification of older in-flight messages during rotation windows.
- SPF lookup limits (the maximum of ten DNS lookups per RFC 7208 §4.6.4) are respected in published records; warnings trigger.
- The reporting URI is a stable destination. Aggregate reports are parsed and stored; reports to be saved forever are saved in a way that can be replayed, not merely displayed.
- Forensic reports are protected; their content includes message-level data and must be treated with confidentiality and limited retention.
- Offboarding a sender removes its DKIM selectors and its SPF inclusion; this is recorded in the change log.
- New senders cannot go live without a DKIM key, an SPF inclusion, and a documented alignment decision.

## Validation evidence

Evidence is collected at every change to the DMARC record or the underlying SPF/DKIM configuration.

- A copy of the live DMARC, SPF, and DKIM records and the date they were queried.
- A sample aggregate report (or a summary statistic from aggregate reports) for each sending domain, listing authenticated messages, misaligned messages, and messages that failed authentication.
- A forensics log where applicable.
- The change record for each onboarding, offboarding, key rotation, SPF edit, or DMARC policy change.
- A periodic end-to-end test: a message sent from a registered sender should pass DMARC with the published policy, and an unsigned or misaligned message should be rejected or quarantined under the published policy.

## Failure modes and correction

Frequent failures include publishing a `p=none` record and never tightening it, allowing a sender to send email without DKIM or without an SPF inclusion, configuring DKIM with a `d=` value that does not align with the From: domain, including a sender in SPF under one subdomain while publishing DMARC for the whole organizational domain without realizing it expects a different alignment mode, ignoring DMARC aggregate reports that show misalignment from a forgotten sender, and letting DKIM keys sit until expiration without rotation. Another failure is treating DMARC as a sender problem and not as a brand problem: a single sender can damage the parent domain's reputation if it sends phishing that fails DMARC and becomes a forensic signal.

Correction begins with the affected domain. If misalignment is reported for messages from a forgotten sender, the sender is removed (SPF and DKIM) or brought into compliance (signed with alignment). If messages from a legitimate sender are being rejected under a `p=quarantine` or `p=reject` policy, the authentication configuration is corrected on the sending platform and a monitoring-period message is sent to confirm pass-through. If the policy itself is too strict (rejecting legitimate mail), the policy is loosened to quarantine while the configuration is fixed, and tightened again afterward. The change log records the policy step and the affected configuration. Reported failures that cannot be matched to a sender are treated as a sign that something or someone is sending in the brand's name and are escalated.

## Limitations

DMARC is necessary but not sufficient. It does not stop all brand impersonation: visually similar domains, display-name spoofing, "look-alike" campaigns, and compromised legitimate accounts are outside DMARC's scope. It does not adjudicate whether a message is "marketing" or "transactional," whether a sender is authorized to use a brand mark in the visible From:, whether a recipient consented to receive the message, or whether the message's content complies with CAN-SPAM, GDPR, CASL, or other consent-based regimes. It does not cover every realm (SMS, RCS, push, voice, in-app messaging); it is an email authentication mechanism.

## Canonical sources

- **Primary authority 1 — RFC 7489, Domain-based Message Authentication, Reporting, and Conformance (DMARC):** [https://datatracker.ietf.org/doc/html/rfc7489](https://datatracker.ietf.org/doc/html/rfc7489)
- **Primary authority 2 — RFC 6376, DomainKeys Identified Mail (DKIM) Signatures:** [https://www.rfc-editor.org/rfc/rfc6376](https://www.rfc-editor.org/rfc/rfc6376)
