# CNCF SPIFFE/SPIRE Workload Identity Governance

## Purpose

SPIFFE (Secure Production Identity Framework For Everyone) and SPIRE (SPIFFE Runtime Environment) provide cryptographic workload identities for workloads across platforms. Governance ensures that workload identities are scoped appropriately, that the SPIRE control plane is hardened, and that identity federation works as designed.

## Current context and source status

SPIFFE and SPIRE are CNCF Graduated projects. Versions and APIs (SPIFFE Workload API, SPIRE Server, SPIRE Agent) evolve; verify the current SPIFFE/SPIRE documentation before treating any specific configuration as a current requirement.

## Governance workflow and controls

### 1. Adopt SPIFFE for workload identity

Adopt SPIFFE as the standard workload identity format. Adopt SPIRE as the implementation.

### 2. Plan the SPIRE deployment

Plan the SPIRE deployment:

- SPIRE Server (control plane);
- SPIRE Agent (per-node, retrieves SVIDs);
- federated trust domains.

Document the topology.

### 3. Define trust domains

Define trust domains per environment or business unit. Document the trust domain boundaries.

### 4. Configure node attestation

Configure node attestation for SPIRE Agents (cloud-IaaS attestation, Kubernetes attestation, x509pop attestation). Apply the attestation method that matches the platform.

### 5. Configure workload attestation

Configure workload attestation selectors. Use Kubernetes service account selectors, Unix UID selectors, or Docker labels.

### 6. Manage federated trust

Manage federated trust with other SPIRE deployments or identity providers. Apply federation bundles. Document trust relationships.

### 7. Issue SVIDs

Issue SVIDs (SPIFFE Verifiable Identity Documents). Use the SPIFFE Workload API. Verify SVIDs at the workload level.

### 8. Rotate identities

Rotate identities per the documented cadence. Document the rotation procedure.

### 9. Audit SPIRE activity

Audit SPIRE Server and Agent activity. Send logs to a central destination. Alert on unexpected activity.

## Validation and evidence

- SPIRE deployment topology.
- Trust domain configuration.
- Attestation configuration.
- Federation configuration.
- Audit logs.

## Failure correction

Common defects include misconfigured attestation, missing federation, and stale identities. Corrective actions include an attestation review, a federation test, and an identity rotation cadence.

## Limitations

- SPIFFE is a specification; SPIRE is the reference implementation.
- Workload identity requires application changes.
- Federation requires careful key management.
- SPIRE Server is a critical component; apply high availability.

## Canonical sources

- CNCF, SPIFFE specification, current edition.
- CNCF, SPIRE documentation, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for workload identity, the security leaf for mTLS, and the operations leaf for SPIRE operations.
