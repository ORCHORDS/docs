---
title: "Deploy Knowledge"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-02"
review-cycle: "90 days"
next-review: "2026-12-01"
---

# Deploy Knowledge

Reusable operational guidance for Helm, Argo CD and Rollouts, Flux, Sealed Secrets, Terraform and OpenTofu, Pulumi, Bicep, Kustomize, Syft SBOM generation, Cosign attestations, and adjacent supply-chain concerns.

## Selected guidance

### Helm

- [Helm Release Rollback Drills](helm-release-rollback-drills.md)
- [Helm OCI Chart Registry Provenance](helm-oci-registry-chart-provenance.md)
- [Helm Library Chart Composition](helm-library-chart-composition.md)
- [Helm Post-Renderers and Supply Chain](helm-post-renderers-supply-chain.md)

### GitOps

- [Argo CD App-of-Apps Progression](argo-cd-app-of-apps-progression.md)
- [Argo Rollouts Canary Metric Analysis](argo-rollouts-canary-metric-analysis.md)
- [Argo CD Sync Waves Orchestration](argo-cd-sync-wave-orchestration.md)
- [Flux Kustomization Health Checks](flux-kustomization-health-checks.md)
- [Sealed Secrets Rotation in GitOps](sealed-secrets-rotation-gitops.md)

### Infrastructure as code

- [Terraform State Remote Locking and Audit](terraform-state-remote-locking-audit.md)
- [Terraform Plan Drift Detection Cadence](terraform-plan-drift-detection.md)
- [OpenTofu Module Registry Pinning](opentofu-module-registry-pinning.md)
- [Pulumi Stack References Isolation](pulumi-stack-references-isolation.md)
- [Bicep What-If Deployment Gates](bicep-what-if-deployment-gates.md)
- [Kustomize Component Layering](kustomize-component-layering.md)

### Supply-chain

- [Syft SBOM Generation into Deployment Gates](syft-sbom-into-deployment-gates.md)
- [Cosign Keyless Attestation Gates](cosign-keyless-attestation-gates.md)
