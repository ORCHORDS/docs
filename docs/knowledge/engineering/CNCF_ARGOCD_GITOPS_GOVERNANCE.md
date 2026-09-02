# CNCF Argo CD GitOps Governance

## Purpose

Argo CD is a CNCF Graduated project for GitOps-based continuous delivery on Kubernetes. It synchronizes Kubernetes manifests from Git repositories to clusters, with drift detection, automated or manual sync, and rollback. Governance ensures that application definitions are version-controlled, that sync policies reflect the workload's risk profile, and that drift is detected and remediated.

## Current context and source status

Argo CD is a CNCF Graduated project. Versions and CRDs (Application, AppProject, ApplicationSet) evolve; verify the current Argo CD documentation before treating any specific configuration as a current requirement.

## Governance workflow and controls

### 1. Adopt Argo CD for GitOps

Adopt Argo CD for GitOps-based continuous delivery. Define the Argo CD architecture (single cluster, hub-and-spoke, multi-cluster).

### 2. Configure repositories

Configure Git repositories as sources. Use HTTPS or SSH. Apply authentication and authorization (read-only tokens).

### 3. Configure destination clusters

Configure destination Kubernetes clusters. Apply cluster authentication. Apply cluster labels.

### 4. Define AppProjects

Define AppProjects per team or business unit. Apply namespace allowlists, repository allowlists, destination cluster allowlists.

### 5. Define Applications

Define Applications per workload. Apply:

- source (repository, path, revision);
- destination (cluster, namespace);
- sync policy (automated or manual);
- sync options (PrunePropagationPolicy, PruneLast, ApplyOutOfSyncOnly, ServerSideApply);
- ignore differences.

### 6. Apply sync windows

Apply sync windows (e.g., no syncs during change freezes). Apply automated sync with self-heal where appropriate.

### 7. Detect and remediate drift

Detect drift via Argo CD's health and sync status. Remediate drift by syncing or by updating the source.

### 8. Audit Argo CD activity

Audit Argo CD activity: sync events, application events, login events. Send logs to a central destination.

### 9. Apply RBAC

Apply RBAC for Argo CD users. Apply scoped policies (read, sync, admin).

## Validation and evidence

- Argo CD configuration.
- AppProject inventory.
- Application inventory.
- Audit logs.

## Failure correction

Common defects include missing sync policies, drift that is not remediated, and missing RBAC. Corrective actions include a sync policy enforcement review, a drift alerting setup, and an RBAC review.

## Limitations

- Argo CD is specific to Kubernetes.
- Sync policies that are too aggressive can cause unintended changes.
- Multi-cluster requires careful authentication management.
- Application sprawl requires governance.

## Canonical sources

- CNCF, Argo CD documentation, current edition.
- CNCF, Argo CD reference architecture, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for Kubernetes platforms, the operations leaf for deployment operations, and the security leaf for RBAC.
