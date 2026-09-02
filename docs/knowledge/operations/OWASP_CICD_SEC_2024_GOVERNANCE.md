# OWASP CICD-SEC-2024 Pipeline Security Governance

## Purpose

The OWASP CICD-SEC-2024 (top 10 CI/CD Security Risks) project identifies the most critical security risks in CI/CD pipelines. Risks include insecure system configuration, inadequate identity and access management, dependency chain abuse, poisoned pipeline execution, insufficient PBAC (pipeline-based access controls), insufficient credential hygiene, insecure system communication, inadequate monitoring and logging, and insecure artifact validation. This article governs the application of OWASP CICD-SEC-2024 so the organization's CI/CD pipeline security covers the risks the publication identifies.

## Scope

The publication applies to any organization that uses CI/CD pipelines to build, test, and deploy software. Within this knowledge base, the article covers the pipeline security risks, the application of defensive controls against each risk, the pipeline security review process, and the documentation of the pipeline security posture. It does not cover the substantive engineering of each application; the publication focuses on the pipeline itself.

## Workflow

1. Identify the CI/CD pipeline components: source control, the build system, the artifact repository, the deployment system, the runner/agent hosts, and the secrets management.
2. Assess each component against the OWASP CICD-SEC-2024 risks. For each risk, evaluate the current controls and identify gaps.
3. Apply defensive controls for each risk:
   - Insecure system configuration: harden the pipeline components; use least privilege; restrict network exposure.
   - Inadequate identity and access management: enforce strong authentication; minimize pipeline access; review permissions regularly.
   - Dependency chain abuse: pin dependencies; verify integrity; use dependency provenance.
   - Poisoned pipeline execution: isolate build environments; limit access to the execution context; verify the build inputs.
   - Insufficient PBAC: model pipeline permissions explicitly; use just-in-time credentials; separate build and deploy identities.
   - Insufficient credential hygiene: rotate credentials; store secrets in a secrets manager; never store secrets in repository.
   - Insecure system communication: use TLS; verify certificates; restrict egress.
   - Inadequate monitoring and logging: log pipeline activity; alert on anomalous actions; retain logs for incident response.
   - Insecure artifact validation: sign artifacts; verify signatures on deployment; track artifact provenance.
4. Review the pipeline security posture periodically and after each material change.

## Controls and evidence

Pipeline security evidence includes the assessment results, the controls applied, the configuration baselines, the access records, the dependency and supply chain records, the signed-artifact records, and the monitoring logs. Each risk should have a documented control and a verifiable implementation.

## Validation

Validation should confirm each pipeline component has been assessed against the risks, the controls are operational, the configuration baselines are current, the secrets are managed correctly, the artifacts are signed and verified, and the monitoring operates. Periodic audits confirm the posture remains effective.

## Failure correction

Common failure modes: pipeline credentials are long-lived and stored in the repository (correct: move to a secrets manager and rotate); build environments are shared and persistent (correct: use ephemeral build environments); pipeline access is not reviewed (correct: review pipeline access quarterly and on personnel change); artifacts are not signed (correct: sign build artifacts and verify on deployment); pipeline logs are not retained (correct: integrate pipeline logs into the security monitoring and retain per the incident response plan).

## Limitations

OWASP CICD-SEC-2024 is a guidance publication, not a certification scheme. The publication does not prescribe specific pipeline tools or vendors. The publication does not address every risk (e.g., AI-specific pipeline risks may be added in future updates).

## Scope note

This article summarizes project-neutral operations use of OWASP CICD-SEC-2024. It does not assert any specific pipeline's conformance or claim any certification outcome.

## Canonical sources

- OWASP — Top 10 CI/CD Security Risks (CICD-SEC-2024): https://owasp.org/www-project-top-10-ci-cd-security-risks/