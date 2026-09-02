# CNCF Tekton Pipeline Supply Chain Governance

## Purpose

Govern the use of Tekton as the pipeline execution layer for build, test, and deploy workflows so that pipeline definitions are declarative, version-controlled, least-privileged, and produce attested artifacts that downstream stages can verify.

## Scope

Applies to every Tekton pipeline, task, and trigger used by the studio for artifact production. It covers pipeline definition lifecycle, RBAC, parameter handling, and results chaining. It does not cover the deployment strategies that pipelines trigger (covered by progressive delivery guidance) or artifact signing itself (covered by provenance guidance).

## Workflow

1. Define pipelines declaratively in version control; pipeline definitions living only in a cluster are prohibited. Apply them through GitOps the same as any other workload.
2. Compose pipelines from reusable Tasks where possible; customize by parameter, not by fork, and pin remote Task references by digest.
3. Grant each pipeline's service account only the permissions its steps require; cluster-admin service accounts for pipelines are prohibited.
4. Chain stages through Tekton `results` rather than positional artifacts, so each stage consumes explicitly named outputs from its predecessors.
5. Require every producing pipeline run to emit provenance and SBOM as task results attached to the image before any deploy task can reference the image.
6. Record pipeline run logs and termination status for each run; treat log unavailability as a run failure for audit purposes.
7. Upgrade Tekton and task bundles on a deliberate cadence, testing against a staging pipeline before promotion.

## Controls and evidence

- Version-controlled pipeline repository with review records for each change.
- RBAC matrix per pipeline service account, reviewed when pipelines change.
- Pinned task references (by digest) for all remote task usage.
- Provenance and SBOM emission check in every producing pipeline run.
- Run log retention configuration meeting the audit window.

## Validation

- Confirm every pipeline in production has a corresponding definition in the pipeline repository at a matching revision.
- Sample one production run and trace its image reference to a provenance attestation and SBOM emitted by the run.
- Confirm no pipeline service account holds permissions beyond those its steps use.

## Failure correction

- **Pipeline drift (cluster state ≠ repository)** → reconcile from the repository, and investigate why GitOps promotion was bypassed.
- **Missing provenance on a produced image** → quarantine the image, block promotion, and fix the pipeline before rebuilding.
- **Over-privileged service account** → reduce permissions to least privilege, document what was actually needed, and audit recent activity under the old grant.

## Limitations

- Tekton executes what pipelines define; it does not make pipelines correct. Review and testing remain the quality control.
- Result chaining and workspaces semantics evolve across Tekton versions; consult the version-specific documentation when upgrading.
- Governance here covers the execution layer; full supply-chain assurance needs signing and verification controls covered elsewhere.

## Scope note

This article is part of the operations leaf and pairs with GitOps deployment and supply-chain provenance guidance. Cross-reference: `deploy/argo-cd-gitops-getting-started.md`, `CNCF_CERTIFIED_KUBERNETES_OPERATOR_GOVERNANCE.md`, and `infra/container-image-scanning-trivy-grype.md`.

## Canonical sources

- Tekton Documentation — Pipelines: https://tekton.dev/docs/pipelines/
- Tekton Chains — Provenance and attestation: https://tekton.dev/docs/chains/
- CNCF Graduated & Incubating Projects — Tekton: https://www.cncf.io/projects/
- SLSA v1.0 — Supply-chain Levels for Software Artifacts: https://slsa.dev/
- Kubernetes Documentation — RBAC: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
