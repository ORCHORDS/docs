# OWASP API Security Top 10 2023 Governance

## Purpose
Establish the governance pattern for selecting, applying, and validating controls against the OWASP API Security Top 10 — 2023 edition across every API surface produced or operated by the studio.

## Scope
Applies to every REST, GraphQL, gRPC, and event-driven API produced by the studio, including internal APIs used for service-to-service communication and external APIs exposed to customers.

## Workflow
1. Maintain an API inventory keyed to the studio's API gateway; tag each API with its classification (Public, Partner, Internal, Management).
3. For each API, perform threat modelling against the OWASP API Security Top 10 (2023) items: API1 Broken Object Level Authorization, API2 Broken Authentication, API3 Broken Object Property Level Authorization, API4 Unrestricted Resource Consumption, API5 Broken Function Level Authorization, API6 Unrestricted Access to Sensitive Business Flows, API7 Server Side Request Forgery, API8 Security Misconfiguration, API9 Improper Inventory Management, API10 Unsafe Consumption of APIs.
5. For each finding, capture the evidence (request/response samples, configuration exports, scan output) and the remediation plan.
7. Re-run the threat modelling exercise annually or whenever the API surface changes by more than 10 percent.
9. Track closure rates per API and per Top 10 item; report to the security steering group quarterly.

## Controls and evidence
- API inventory with classification, owner, and last review date.
- Threat model document per API keyed to the 2023 Top 10 items.
- Findings register with severity, owner, remediation status, and due date.
- Quarterly closure-rate report with year-over-year trend.

## Validation
- Sample-audit three APIs by re-executing the threat model and confirming the captured evidence matches the current API behaviour.
- Verify that the API inventory matches the live API gateway configuration (no shadow APIs).
- Confirm the threat model has been reviewed within the last 12 months.

## Failure correction
- **High-severity finding open beyond 30 days** → halt API changes until remediation is in place or accept the risk in writing with CISO approval.
- **Threat model out of date by more than 12 months** → refresh the model within 30 days and document the staleness window.
- **Shadow API discovered** → register the API in the inventory within 7 days and run an emergency threat model.

## Limitations
- The OWASP API Security Top 10 (2023) is a prioritisation guide, not a comprehensive list of API risks.
- Some controls (e.g., business flow protection) require domain expertise beyond the Top 10 itself.
- Threat models can miss authorisation issues that require runtime monitoring to detect.

## Scope note
This article is part of the security leaf. Cross-reference: MITRE_D3FEND_DETECTION_COUNTERMEASURE_GOVERNANCE.md, OWASP_API_SECURITY_TOP_10_2023_GOVERNANCE.md, ISO_IEC_27402_2023_IOT_SECURITY.md.

## Canonical sources
- OWASP API Security Top 10 — 2023: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
- OWASP API Security Project: https://owasp.org/API-Security/
- OWASP API Security Verification Standard (ASVS) API chapter: https://owasp.org/www-project-application-security-verification-standard/
- OWASP Cheat Sheet Series — API Security: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- NIST SP 800-204 (Security Strategies for Microservices-based Application Systems): https://csrc.nist.gov/pubs/sp/800/204/final