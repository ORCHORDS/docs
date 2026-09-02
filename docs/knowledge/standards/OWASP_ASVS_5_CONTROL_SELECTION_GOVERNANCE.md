# OWASP ASVS 5.0 Control Selection Governance

## Purpose

OWASP Application Security Verification Standard (ASVS) 5.0 (2024) defines security verification requirements for web applications. The standard is organized into verification requirements across security areas: architecture, authentication, session management, access control, validation/sanitization/encoding, stored cryptography, error handling and logging, data protection, communications, malicious code, business logic, files and resources, API and web service, and configuration. Each requirement is assigned a verification level (L1, L2, L3) based on the application's risk profile. This article governs the application of ASVS 5.0 so an application is verified against an appropriate level and the controls are selected accordingly.

## Scope

ASVS 5.0 applies to web applications, APIs, and web services. Within this knowledge base, the article covers the verification level selection (L1, L2, L3), the security areas and verification requirements, the verification process (self-assessment, third-party assessment, penetration testing), and the documentation of the verification. It does not cover the specific security controls for each requirement; readers should consult ASVS 5.0 directly.

## Workflow

1. Determine the application's verification level per the standard's guidance:
   - L1: low assurance; basic security controls; suitable for applications with low risk (e.g., internal applications with no sensitive data).
   - L2: standard assurance; most applications; suitable for applications with sensitive data but not life-critical.
   - L3: high assurance; applications with significant risk (e.g., financial, healthcare, critical infrastructure).
2. Identify the verification requirements applicable to the application at the selected level.
3. Apply the requirements during design, development, and testing:
   - Architecture: secure design, threat modeling.
   - Authentication: credential storage, multi-factor authentication, session management.
   - Access control: authorization enforcement, privilege management.
   - Validation: input validation, output encoding.
   - Cryptography: secure algorithms, key management.
   - Error handling and logging: secure error messages, security logging.
   - Data protection: data classification, encryption at rest and in transit.
   - Communications: TLS, secure cookies, CSP.
   - Business logic: workflow integrity, rate limiting.
   - Files and resources: secure upload/download, file validation.
   - API and web service: API security, JWT, OAuth.
   - Configuration: secure defaults, hardening.
4. Verify the application:
   - Self-assessment against ASVS 5.0.
   - Third-party assessment by a qualified verifier.
   - Penetration testing as required.
5. Document the verification: the level selected, the requirements verified, the evidence collected, and any gaps.

## Controls and evidence

ASVS controls include the documented verification level, the requirements list, the test cases, the test results, the remediation records, and the verifier's report. Each application should be traceable to the verification level and the requirements applicable to that level.

## Validation

Validation should confirm the verification level matches the application's risk profile, the requirements are applied, the test cases cover the requirements, the verification operates, and the gaps are tracked to closure. Independent review by a qualified verifier confirms the verification.

## Failure correction

Common failure modes: the verification level is too low for the application's risk (correct: increase the level to match the risk); only L1 requirements are verified when L2 is required (correct: verify all requirements at the selected level); verification is one-time (correct: re-verify on changes); gaps are not tracked (correct: track gaps to closure with deadlines); the verifier is not qualified (correct: engage a qualified verifier per the standard).

## Limitations

OWASP ASVS 5.0 is a verification standard; it does not certify any application outside the verification process. The standard does not replace a penetration test; it provides a structured baseline. The standard does not address every application type (mobile, IoT); readers should consult the appropriate OWASP or industry standards.

## Scope note

This article summarizes project-neutral standards use of OWASP ASVS 5.0. It does not assert any specific application's conformance or claim any certification outcome.

## Canonical sources

- OWASP Application Security Verification Standard 5.0 (2024): https://owasp.org/www-project-application-security-verification-standard/
- OWASP Testing Guide: https://owasp.org/www-project-web-security-testing-guide/