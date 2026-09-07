# OWASP Top 10 CI/CD Security Risks (2024) Governance

## Purpose

The OWASP Top 10 CI/CD Security Risks project (CICD-SEC, 2024 list published September 2024) catalogues the highest-impact weaknesses in build, test, deploy, and release pipelines. Governance ensures the ORCHORDS platform treats CI/CD as a first-class attack surface with controls for code-source integrity, build isolation, artifact trust, deployment permissions, and pipeline configuration review — distinct from, and complementary to, application-level OWASP Top 10 / OWASP ASVS controls.

## Current context and source status

The 2024 list supersedes the 2022 draft and aligns with the SLSA v1.0 build levels, NIST SP 800-204D microservices guidance, and the Sigstore / Notary v2 attestation ecosystems. The list is the canonical reference for "what counts as a CI/CD risk" in vendor selection, pipeline review, and supply-chain due diligence. Treat the OWASP document as authoritative for risk naming; cross-reference SLSA, NIST, and Sigstore for control implementation.

## Governance workflow and controls

### 1. CICD-SEC-1: Insufficient flow control mechanisms

- Maintain an explicit pipeline diagram with each source, artifact, and trust boundary labelled.
- Require every pipeline to declare an owner, a change-advisory contact, and a template reference (or an exception ticket) for non-template steps.
- Treat the absence of a flow diagram as a control failure during vendor risk review.

### 2. CICD-SEC-2: Inadequate identity and access management

- Pipelines MUST run with the minimum-privilege identity required for the step; ephemeral federated identities are preferred over long-lived secrets.
- Secrets referenced from pipelines MUST be stored in a managed secret store and MUST be rotated on the rotation schedule declared by `NIST_SP_800_53_R5_SECURITY_GOVERNANCE.md` (or the equivalent internal standard).
- Treat self-hosted runners with persistent cloud credentials as a high-risk finding; migrate to short-lived OIDC federated credentials.

### 3. CICD-SEC-3: Dependency chain abuse

- Pin transitive dependencies to a SHA digest (lock file) and review lock-file changes as code.
- Use a trusted internal mirror that mirrors upstream registries; deny pipelines direct egress to public registries.
- Cross-reference `NIST_SP_800_218_SSDF_GOVERNANCE.md` and `NIST_SP_800_161_R2_CYBER_SCRM_GOVERNANCE.md` for the upstream-governance inputs.

### 4. CICD-SEC-4: Poisoned pipeline execution

- Treat CI scripts, reusable workflow definitions, and pipeline DSL as production code: review, test, and sign.
- Disable untrusted workflow reuse; if reuse is required, pin the upstream ref to a digest and verify the upstream signature.
- Run untrusted code (PRs from forks) in ephemeral, network-restricted, and storage-restricted runners.

### 5. CICD-SEC-5: Insufficient PBAC (pipeline-based access controls)

- Production-deploy steps MUST require a second-person review OR a release-automation approval recorded in an audit log.
- Pipeline-level permissions (e.g., GitHub Actions `permissions:`, GitLab `rules:`) MUST be the tightest that the step requires.
- Avoid `*` or `write-all` permission grants at the pipeline or job level.

### 6. CICD-SEC-6: Insufficient credential hygiene

- No long-lived secrets in pipeline YAML, scripts, or repository history.
- Scan historical commits for leaked secrets and rotate any credential that is detected.
- Use OIDC federation to cloud providers; remove service-account key files from pipeline workspaces.

### 7. CICD-SEC-7: Insecure system configuration

- Pin runner and agent base images; rebuild on a published schedule.
- Disable unnecessary network egress from runners; allowlist only the registries and endpoints the pipeline requires.
- Review managed-CI configuration (org settings, repository settings, runner pools) at the same cadence as production system configuration.

### 8. CICD-SEC-8: Ungoverned usage of third-party services

- Maintain a register of every third-party service invoked from a pipeline (cloud, code-quality, security, deployment).
- Each third-party service MUST have a vendor-review record that covers data handling, incident disclosure, and breach-notification terms.
- Treat the absence of a vendor record as a control failure.

### 9. CICD-SEC-9: Improper artifact integrity validation

- Production admission MUST verify image signatures (see `COSIGN_VERSION_GOVERNANCE.md` and `NOTARY_V2_VERSION_GOVERNANCE.md`).
- SLSA provenance and SBOMs MUST be verified on deploy; unverified artifacts are quarantined, not deployed.
- SBOMs MUST be retained for the artifact's deployment lifetime and at least one major-version cycle after retirement.

### 10. CICD-SEC-10: Insufficient logging and visibility

- Pipeline events (start, end, source ref, artifact digest, runner identity, deploy target) MUST be logged to a tamper-evident sink.
- Logs MUST be retained for the duration declared by the SIEM retention schedule and MUST be queryable by the SOC.
- Deploy events MUST be cross-correlated with runtime detection events (see `FALCO_VERSION_GOVERNANCE.md` and `TETRAGON_VERSION_GOVERNANCE.md`).

## Mapping to NIST and SLSA

- Map every CICD-SEC control to a NIST SP 800-53 Rev 5 control family (SI, SR, CM, AC, AU, SC, SA, RA) and to a SLSA v1.0 build/source level where applicable.
- Treat un-mapped controls as gaps during internal audit; assign to the next review cycle.

## Review cadence

- Re-baseline the CICD-SEC control set at every OWASP list update.
- Quarterly: confirm the third-party services register is current.
- Annually: re-test the credential-hygiene and PBAC controls with a tabletop exercise.

References: `https://owasp.org/www-project-top-10-ci-cd-security-risks/`, `https://slsa.dev/`, `https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final`, `https://docs.sigstore.dev/`, `https://github.com/notaryproject/specification`.
