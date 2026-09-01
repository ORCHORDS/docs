# OWASP ASVS Secure Development Control Derivation

## Purpose

The OWASP Application Security Verification Standard (ASVS) is a list of security requirements and verification criteria that organizations can apply during design, development, and deployment of web applications and APIs. ASVS uses three assurance levels (rather than three maturity levels) that organizations select based on the impact of the application, the data it handles, and the threat model it faces. This article summarizes ASVS as a reference for engineering teams that need to derive and track secure-development controls. It is not a verifier's guide.

## Assurance levels

ASVS levels are not maturity levels; they are risk-based floors:

- **Level 1** — opportunistic coverage, automated where possible; for low-impact applications.
- **Level 2** — application-level security controls and review; for moderate-impact applications.
- **Level 3** — detailed verification and threat-model-aligned coverage; for high-impact applications, particularly those processing regulated data or facing sophisticated adversaries.

A common pattern is to select Level 2 by default, escalate to Level 3 for high-risk applications, and use Level 1 for internal tools where the threat model justifies lighter coverage. Selecting a level requires a deliberate decision and a record; it does not default to Level 2 simply because a previous project selected it.

## Control families

ASVS organizes its verification requirements by security domain, including (but not limited to):

- **Architecture, Design, and Threat Modeling** — design-time considerations, threat-model coverage, and architecture decisions.
- **Authentication** — credential lifecycle, second-factor controls, recovery controls.
- **Session Management** — session identifier generation, expiration, idle and absolute timeouts, and concurrency.
- **Access Control** — authorization decisions, role and policy design, segregation of duties.
- **Validation, Sanitization, and Encoding** — input handling, output encoding for injection defenses, and structural defenses for deserialization.
- **Cryptography** — algorithm and library choices, key handling, storage and transit protection.
- **Error Handling and Logging** — logs that are useful, logs that are safe to retain, and error responses that do not leak.
- **Data Protection** — sensitive data lifecycle, retention, and disposal.
- **Communications** — TLS configuration and certificate handling, and protection of management channels.
- **Malicious Code** — third-party dependency handling and inspection of build outputs.
- **Business Logic** — workflow controls such as rate limiting, transaction reordering defenses, and approval.
- **Files and Resources** — file-handling controls for upload, storage, and retrieval.
- **API and Web Service** — service-to-service authentication, traffic protections, and request integrity.
- **Configuration** — deployment-time configuration for the application and its dependencies.

Each section contains a list of verifiable controls with an identifier and acceptance criteria.

## Derivation workflow

1. Select the assurance level appropriate to the application's impact, regulatory regime, and threat model.
2. For each control category, identify the requirements that apply at the chosen level.
3. Map each requirement to one or more controls implemented in code, configuration, or platform service.
4. Identify the verification mechanism (test, code review, configuration review, manual assessment) for each control.
5. For each mechanism, decide how often it runs and how the result is reviewed.
6. Track deviations and waivers explicitly; do not silently skip requirements.
7. Re-select the level when application impact, data sensitivity, or threat model changes.

## Operations perspective

ASVS is most useful when its requirements drive platform defaults, not just application checklists. If the platform enforces TLS, key handling, and dependency hygiene as defaults, ASVS becomes a maintenance activity instead of a remediation cycle. Operations should review each ASVS section to determine whether the control belongs in the application, the platform, or both. Controls in both places should not be duplicated; the contract should clarify ownership and the residual responsibility.

## Validation evidence

Validation evidence includes the selected assurance level with rationale, the mapping between requirements and implementation, the verification mechanism per requirement, the verification results across releases, the deviation register with expiration, and the periodic re-evaluation when application impact or threat model changes. The most useful evidence is the persistent record of verification results per release.

## Failure modes

Failure modes include selecting the level by precedent rather than by analysis, mapping requirements to platform defaults without confirming the platform actually enforces them, running static analysis on a section that requires manual review, treating ASVS as a release gate and slowing release without remediating the underlying gap, and conflating compliance with verification results.

## Verification mechanism selection

Different verification mechanisms are appropriate for different requirements. Source-code review and unit testing suit controls in code. Configuration review suits controls that govern settings, certificates, or files. Threat modeling and architecture review suit design-time controls. Penetration testing suits runtime controls that resist behavior-driven testing, including business-logic controls and certain anti-abuse behaviors. ASVS sections explicitly recommend verification approaches for each requirement; following that recommendation is the path of least surprise at audit time. Operations teams benefit from mapping each requirement to its verification mechanism because the resulting table doubles as a test plan.

## Bringing ASVS into day-to-day engineering

A practical ASVS adoption pattern is to embed the requirements into tooling. Static analysis can be configured to fail when a Category is missing or broken. Pre-commit or pre-merge checks can enforce small categories of requirements, such as cryptographic algorithm choices, dependency provenance, or hard-coded credential checks. Platform defaults can absorb larger categories, such as session timeout and TLS configuration, so that engineers are not asked to satisfy them individually. Embedding eliminates the recurring cost of remembering the checklist, and shifts the conversation from "did you comply" to "is the right pipeline configured".

## Canonical sources

- OWASP Application Security Verification Standard (ASVS): https://owasp.org/www-project-application-security-verification-standard/
- OWASP Cheat Sheet Series (operational guidance for specific requirements): https://cheatsheetseries.owasp.org/
- OWASP DevSecOps Guideline (companion model for culture and process): https://owasp.org/www-project-devsecops-guideline/

## Scope note

This article summarizes ASVS as an operations reference; specific verification mechanisms, level-selection thresholds, and deviation policies must be set by each organization based on its portfolio and risk profile.
