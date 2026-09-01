---
title: "Email Platform Knowledge"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-02"
review-cycle: "90 days"
next-review: "2026-12-01"
---

# Email Platform Knowledge

Reusable operational guidance for SMTP, DNS-based mail authentication (DANE, MTA-STS, SPF, DKIM, DMARC), TLS reporting (TLSRPT), brand indicators (BIMI), authenticated received chain (ARC), RFC 8058 one-click unsubscribe, mailing-list feedback loops, delivery status notifications, and adjacent operational concerns.

## Selected guidance

### Authentication and reporting

- [RFC 8058 One-Click List-Unsubscribe Mechanics](rfc8058-one-click-list-unsubscribe.md)
- [RFC 9057 ARC and the Abstract MDA](rfc9057-arc-abstract-mda.md)
- [BIMI Verified Mark Certificate Lifecycle](bimi-vmc-certificate-lifecycle.md)
- [BIMI Logo Hash Delegation Records](bimi-logo-hash-delegation.md)
- [TLSRPT SMTP TLS Reporting](tlsrpt-smtp-tls-reporting.md)
- [TLSRPT Aggregate Report Cadence](tlsrpt-aggregate-report-cadence.md)
- [SMTP MTA-STS Policy Cache Poisoning Defense](smtp-sts-policy-cache-poisoning.md)
- [DANE SMTP TLSA Record Validation](dane-smtp-tlsa-validation.md)

### Operations and deliverability

- [Inbound Gateway Multi-Tenant Enforcement](inbound-gateway-multi-tenant-enforcement.md)
- [Postfix TLS Policy Map Overrides](postfix-tls-policy-map-override.md)
- [Sender Rewriting Scheme SRS Deployment](sender-rewriting-scheme-srs.md)
- [Mailing List Alignment and Feedback Loops](mailing-list-alignment-fbl.md)
- [Delivery Status Notification Actionable Fields](dsn-rfc3464-actionable-fields.md)
- [List-Unsubscribe-Post Header Precedence](list-unsubscribe-post-precedence.md)
- [Header Folding Injection Defense](header-folding-injection-defense.md)
- [Email IPv6 Sending Readiness](email-ipv6-sending-readiness.md)
