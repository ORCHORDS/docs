# CNCF Crossplane Infrastructure as Code Governance

## Purpose

Crossplane is a CNCF Incubating project that extends Kubernetes with custom resources for managing external infrastructure (cloud, on-premises). It enables a GitOps-based, declarative approach to infrastructure management. Governance ensures that compositions are designed for reuse, that credentials are managed securely, and that changes are auditable.

## Current context and source status

Crossplane is a CNCF Incubating project. Versions and providers evolve; verify the current Crossplane documentation and the list of supported providers before treating any specific configuration as a current requirement.

## Governance workflow and controls

### 1. Adopt Crossplane for infrastructure

Adopt Crossplane for new infrastructure projects. Define Provider configurations for each cloud or platform.

### 2. Manage provider credentials

Manage provider credentials:

- use Kubernetes Secrets for credentials;
- integrate with external secret stores (HashiCorp Vault, AWS Secrets Manager);
- apply least privilege;
- rotate credentials.

### 3. Define Managed Resources

Apply Provider-managed resources (MRs) for direct infrastructure primitives (e.g., RDS instance, S3 bucket, GKE cluster).

### 4. Define Compositions

Define Compositions to assemble multiple MRs into higher-level abstractions (e.g., a "Database" composition that combines RDS instance, security group, parameter group, secrets). Apply Composition Revisions for versioning.

### 5. Define Composite Resource Definitions

Define XRDs (Composite Resource Definitions) to expose abstractions. Document the API.

### 6. Apply GitOps

Apply GitOps principles for infrastructure:

- Git as the source of truth;
- automated reconciliation;
- drift detection.

### 7. Apply policy controls

Apply policy controls through provider configurations and ValidatingAdmissionPolicies or Kyverno. Apply cost controls.

### 8. Audit and observe

Audit Crossplane activity. Send logs to a central destination. Apply monitoring and alerting.

## Validation and evidence

- Provider configurations.
- Composition library.
- Composite Resource Definitions.
- Audit logs.

## Failure correction

Common defects include unrotated credentials, untested compositions, and missing policy controls. Corrective actions include a credential rotation cadence, a composition test environment, and a policy review.

## Limitations

- Crossplane is specific to Kubernetes.
- Provider coverage varies; verify per provider.
- Compositions require maintenance; avoid sprawl.
- Some infrastructure operations require custom logic.

## Canonical sources

- CNCF, Crossplane documentation, current edition.
- CNCF, Crossplane provider list, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for cloud platforms, the operations leaf for infrastructure operations, and the security leaf for credential management.
