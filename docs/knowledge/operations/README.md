---
title: "Operations Documentation"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Operations Documentation

This family contains reusable operational guidance for infrastructure, deployment, monitoring, observability, incident response, resilience, release management, continuous integration and delivery, runners, and troubleshooting.

## Selected current guidance

- [Network Ingress Filtering with BCP 38](infra/network-ingress-filtering-bcp38-governance.md)
- [NTP Operational Baseline from RFC 8633](infra/ntp-bcp-operational-baseline-rfc-8633.md)
- [GitHub Artifact Attestation Verification](GITHUB_ARTIFACT_ATTESTATION_VERIFICATION.md)
- [GitHub Actions Immutable OIDC Subject Governance](GITHUB_ACTIONS_IMMUTABLE_OIDC_SUBJECTS.md)
- [GitHub Reusable Workflow OIDC Trust](GITHUB_REUSABLE_WORKFLOW_OIDC_TRUST.md)
- [GitHub Reusable Workflow Secret Boundaries](GITHUB_REUSABLE_WORKFLOW_SECRET_BOUNDARIES.md)
- [GitHub Dependency Review and Submission Ordering](GITHUB_DEPENDENCY_REVIEW_SUBMISSION_ORDERING.md)
- [GitHub Actions Cache Trust Boundaries](GITHUB_ACTIONS_CACHE_TRUST_BOUNDARIES.md)
- [BGP Roles and RFC 9234 Route-Leak Prevention](infra/bgp-roles-rfc-9234-route-leak-prevention.md)

## 2026-09-01 standards and implementation guidance

- [Admission Controller Chain Design](infra/kubernetes-admission-controller-chain-design.md)
- [API Data Encryption and Key Rotation](infra/kubernetes-api-data-encryption-key-rotation.md)
- [API Priority and Fairness Tuning](infra/kubernetes-api-priority-and-fairness-tuning.md)
- [Audit Policy and Evidence Pipeline](infra/kubernetes-audit-policy-evidence-pipeline.md)
- [PodDisruptionBudget Availability Governance](infra/kubernetes-pod-disruption-budget-availability.md)
- [Pod Security Admission Rollout](infra/kubernetes-pod-security-admission-rollout.md)
- [Pod Security Standards Profile Governance](infra/kubernetes-pod-security-standards-profile-governance.md)
- [RBAC Least-Privilege Review](infra/kubernetes-rbac-least-privilege-review.md)
- [ResourceQuota and LimitRange Governance](infra/kubernetes-resourcequota-limitrange-governance.md)
- [ValidatingAdmissionPolicy Governance](infra/kubernetes-validating-admission-policy-governance.md)

## 2026-09-01 cross-family standards and governance guidance

- [Ietf-Bgp-4-Operational-Stability-Rfc4271](ietf-bgp-4-operational-stability-rfc4271.md)
- [Ietf-Snmpv3-Usm-Key-Rotation-Rfc3414](ietf-snmpv3-usm-key-rotation-rfc3414.md)
- [Iso-20000-1-Service-Management-Requirements](iso-20000-1-service-management-requirements.md)
- [Iso-27001-2022-Annex-A-Control-Themes](iso-27001-2022-annex-a-control-themes.md)
- [Itil-4-Change-Enablement-Practice](itil-4-change-enablement-practice.md)
- [Itil-4-Incident-And-Problem-Management-Practice](itil-4-incident-and-problem-management-practice.md)
- [Itil-4-Service-Management-Practices-Summary](itil-4-service-management-practices-summary.md)
- [Nist-Sp-800-34-Contingency-Plan-Types-And-Exercise](nist-sp-800-34-contingency-plan-types-and-exercise.md)
- [Nist-Sp-800-53-Control-Baseline-Selection](nist-sp-800-53-control-baseline-selection.md)
- [Nist-Sp-800-61-Incident-Response-Roles-And-Artifacts](nist-sp-800-61-incident-response-roles-and-artifacts.md)
- [Owasp-Asvs-Secure-Development-Control-Derivation](owasp-asvs-secure-development-control-derivation.md)
- [Owasp-Devsecops-Maturity-Model-Application](owasp-devsecops-maturity-model-application.md)
- [Sre-Service-Level-Objectives-Error-Budget-Policy](sre-service-level-objectives-error-budget-policy.md)

## Operations leaf indexes

- [Deploy](deploy/README.md) — Helm, Argo CD/Rollouts, Flux, Sealed Secrets, Terraform/OpenTofu, Pulumi, Bicep, Kustomize, Syft SBOM, and Cosign attestations.
- [Monitoring](monitoring/README.md) — OpenTelemetry, Prometheus, Mimir, Loki, Tempo, Pyroscope, Alertmanager, OTLP, Grafana, synthetic probes, and SLO burn-rate alerting.

## 2026-09-02 cross-family standards and governance guidance (Batch 11)

- [CNCF CERTIFIED KUBERNETES OPERATOR GOVERNANCE](CNCF_CERTIFIED_KUBERNETES_OPERATOR_GOVERNANCE.md)
- [IEEE 1044 2009 ANOMALY CLASSIFICATION GOVERNANCE](IEEE_1044_2009_ANOMALY_CLASSIFICATION_GOVERNANCE.md)
- [IEEE 1063 2016 SOFTWARE USER DOCUMENTATION GOVERNANCE](IEEE_1063_2016_SOFTWARE_USER_DOCUMENTATION_GOVERNANCE.md)
- [IEEE 828 2012 CONFIGURATION MANAGEMENT GOVERNANCE](IEEE_828_2012_CONFIGURATION_MANAGEMENT_GOVERNANCE.md)
- [ISO 20000 1 2018 SERVICE MANAGEMENT AUDIT GOVERNANCE](ISO_20000_1_2018_SERVICE_MANAGEMENT_AUDIT_GOVERNANCE.md)
- [ISO 27035 1 2023 INCIDENT DETECTION GOVERNANCE](ISO_27035_1_2023_INCIDENT_DETECTION_GOVERNANCE.md)
- [ISO 27035 2 2023 INCIDENT RESPONSE GUIDELINES GOVERNANCE](ISO_27035_2_2023_INCIDENT_RESPONSE_GUIDELINES_GOVERNANCE.md)
- [ITIL 4 SERVICE DESIGN PRACTICE GOVERNANCE](ITIL_4_SERVICE_DESIGN_PRACTICE_GOVERNANCE.md)
- [ITIL 4 SERVICE VALIDATION TESTING PRACTICE GOVERNANCE](ITIL_4_SERVICE_VALIDATION_TESTING_PRACTICE_GOVERNANCE.md)
- [NIST SP 800 184 GUIDANCE FOR CYBER EVENT RECOVERY GOVERNANCE](NIST_SP_800_184_GUIDANCE_FOR_CYBER_EVENT_RECOVERY_GOVERNANCE.md)
- [NIST SP 800 40 R4 PATCH MANAGEMENT GOVERNANCE](NIST_SP_800_40_R4_PATCH_MANAGEMENT_GOVERNANCE.md)
- [NIST SP 800 61 R3 INCIDENT RESPONSE TIMELINE GOVERNANCE](NIST_SP_800_61_R3_INCIDENT_RESPONSE_TIMELINE_GOVERNANCE.md)
- [OWASP CICD SEC 2024 GOVERNANCE](OWASP_CICD_SEC_2024_GOVERNANCE.md)
- [SRE RELEASE COORDINATION ERROR BUDGET GOVERNANCE](SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md)
