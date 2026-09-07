# ISO/IEC 27034-1:2024 Application Security Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27034-1:2024 ("Information technology — Application security — Part 1: Overview and concepts") as the framework for application-level security governance across the lifecycle of custom-built and integrated software. It applies to all in-house engineering teams and to integration patterns that touch third-party SaaS.

## 2. Normative references

- ISO/IEC 27034-1:2024 (third edition).
- ISO/IEC 27034-2:2015 (normative framework).
- ISO/IEC 27034-3:2018 (application security management process).
- ISO/IEC 27034-4:2024 (XML schemas for ASMP).
- ISO/IEC 27034-5:2017 (protocols and services).
- ISO/IEC 27034-7:2018 (assurance prediction framework).

## 3. Application Security Management Process (ASMP)

1. **Establish**: define application security requirements, roles, and the application security policy (ASP).
2. **Assess**: identify risks via threat modelling and code review.
3. **Implement**: codify controls into the application and the surrounding tooling.
4. **Operate**: monitor, detect, respond, recover.
5. **Review**: continuous improvement via metrics, audits, and lessons learned.

## 4. Application Security Controls (ASCs)

- **ASC 1 — Input validation**: every input field validated against a strict schema; reject all unknown fields by default.
- **ASC 2 — Output encoding**: context-aware output encoding at the rendering boundary.
- **ASC 3 — Authentication and session management**: see NIST SP 800-210 card.
- **ASC 4 — Authorisation**: deny-by-default; explicit allow-list.
- **ASC 5 — Cryptography**: use platform-provided primitives; never roll your own.
- **ASC 6 — Error handling**: log full context server-side; show opaque error codes to the client.
- **ASC 7 — Data protection**: classify data; apply encryption at rest and in transit.
- **ASC 8 — Communication security**: mTLS for service-to-service paths.

## 5. Roles

- **Application Owner**: accountable for ASP and risk register.
- **Security Champion**: technical lead per engineering team; advocate for secure coding practices.
- **Application Security Engineer**: reviewer and tooling owner; consulted on design.
- **Auditor**: validates ASMP and ASC implementation.

## 6. Application risk register

Every application maintains a risk register in the platform repo (path: `security/risk/<app>/`); each risk entry includes classification, owner, mitigation, residual risk, and review date.

## 7. Application Security Levels

- **Level 1**: low-risk internal apps; baseline ASMP and ASCs.
- **Level 2**: business apps; + automated testing in CI and dependency scanning.
- **Level 3**: customer-facing apps; + annual pentest, SBOM, and Sigstore signature.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. ISO/IEC 27034 revisions and platform tooling changes trigger out-of-cycle updates.
