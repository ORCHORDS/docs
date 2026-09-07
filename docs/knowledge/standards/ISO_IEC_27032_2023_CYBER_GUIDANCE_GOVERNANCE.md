# ISO/IEC 27032:2023 Cybersecurity — Internet Security Guidelines Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27032:2023 ("Information technology — Security techniques — Cybersecurity guidelines for Internet security") for the protection of internet-facing systems, services, and data. It applies to public web properties, public APIs, customer-facing mobile apps, and any service exposed to the public internet.

## 2. Normative references

- ISO/IEC 27032:2023 (third edition).
- ISO/IEC 27001:2022, ISO/IEC 27002:2022.
- NIST SP 800-44 Rev. 2 (public web server security).
- NIST SP 800-95 (web services security).
- OWASP ASVS v4.0.

## 3. Stakeholder roles

1. **Asset owner**: business unit accountable for the service.
2. **Application owner**: engineering team developing the service.
3. **Cyber defender**: security engineering / SOC monitoring.
4. **Service provider**: cloud provider / ISP.
5. **Customer**: end user of the service.

## 4. Internet security controls

| Layer | Control | ORCHORDS implementation |
| --- | --- | --- |
| Network | DDoS scrubbing, BGP RPKI, BGP route monitoring | Always-on DDoS; RPKI enforced on own ASN |
| TLS | TLS 1.3 only; HSTS preload; ALPN h2 | Strict TLS profile; HSTS in the platform default |
| Application | OWASP ASVS L2 minimum; secure cookies; CSP | ASVS gate in CI; CSP via middleware |
| Identity | OIDC federation; short-lived tokens | ORCHORDS IDP federation; ≤ 1 hour token TTL |
| API | OAuth 2.1 + DPoP for sensitive endpoints | API gateway enforces scopes |
| Logging | Per-request structured logs to SIEM | SIEM with 400-day retention |
| Incident | Customer notification within 72 hours if breach | Incident playbook |

## 5. Threat sharing

- Participate in trusted ISACs (Information Sharing and Analysis Centres) for the relevant industry sectors.
- Internally, share threat intel via the platform security channel; mandatory triage SLA: ≤ 24 hours.

## 6. Code of practice

- No internet-facing service may be deployed without a documented threat model and a security review sign-off.
- Public APIs require OpenAPI 3.x documents with security schemes defined.
- External dependencies on third-party JavaScript are subject to CSP allow-listing and Subresource Integrity (SRI).

## 7. Audit cadence

- Monthly: CSP / SRI / TLS configuration scan; fail the deployment on regression.
- Quarterly: independent penetration test of the most-trafficked properties.
- Annually: third-party attestation against ISO/IEC 27032 + ASVS.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. ISO/IEC 27032 revisions and material changes in the threat landscape trigger out-of-cycle updates.
