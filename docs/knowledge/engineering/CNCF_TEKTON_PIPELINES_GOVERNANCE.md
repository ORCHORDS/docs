# CNCF Tekton Pipelines CI/CD Governance

## Purpose

Tekton Pipelines is a CNCF project that provides a Kubernetes-native framework for creating CI/CD pipelines. Pipelines are defined declaratively as Kubernetes resources. Governance ensures that pipelines are version-controlled, that secrets are managed securely, and that pipeline execution is auditable.

## Current context and source status

Tekton is a CNCF Incubating project. Versions and API resources (Task, Pipeline, PipelineRun, TaskRun, Workspace) evolve; verify the current Tekton documentation before treating any specific resource or feature as a current requirement.

## Governance workflow and controls

### 1. Adopt Tekton for CI/CD

Adopt Tekton Pipelines for new CI/CD workflows on Kubernetes. Migrate existing CI/CD workflows where practical.

### 2. Define Tasks as reusable units

Define Tasks as reusable units (build, test, scan, publish). Apply versioning. Maintain a shared library of Tasks.

### 3. Define Pipelines as compositions

Define Pipelines as compositions of Tasks. Apply parameterization. Maintain a catalog of Pipelines.

### 4. Manage secrets

Manage secrets using Kubernetes Secrets, external secrets (External Secrets Operator), or dedicated secret stores (HashiCorp Vault). Apply encryption at rest. Restrict access.

### 5. Apply Workspaces

Apply Workspaces to share data between Tasks. Use persistent volume claims for large data. Use ConfigMaps and Secrets for small data.

### 6. Apply resource limits

Apply resource limits to TaskRuns and PipelineRuns. Apply per-Pipeline or per-Task. Document the limits.

### 7. Audit pipeline execution

Audit PipelineRun and TaskRun executions. Send audit logs to a central destination. Apply log retention.

### 8. Apply security controls

Apply security controls:

- image scanning for Task images;
- signature verification (cosign);
- restricted network egress;
- read-only file systems.

## Validation and evidence

- Pipeline repository.
- Task library.
- Secret management configuration.
- Audit log destination.

## Failure correction

Common defects include missing secret encryption, missing image scanning, and pipeline runs without resource limits. Corrective actions include a secret encryption audit, a scanning integration, and a resource limits enforcement.

## Limitations

- Tekton is specific to Kubernetes.
- Some build patterns (e.g., matrix builds) require custom logic.
- Secrets management requires Kubernetes-native or external tooling.
- Pipeline complexity can grow; maintain documentation.

## Canonical sources

- CNCF, Tekton Pipelines documentation, current edition.
- CNCF, Tekton Catalog, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for Kubernetes platforms, the operations leaf for CI/CD operations, and the security leaf for supply chain security.
