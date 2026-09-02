# Azure Key Vault Access Governance

## Purpose

Azure Key Vault stores secrets, keys, and certificates. Governance ensures that access follows least privilege, that key rotation is enforced, that audit logging captures every access, and that secret lifecycle (issuance, rotation, revocation, deletion) is documented and tested.

## Current context and source status

Azure Key Vault is generally available. The current feature set includes Standard and Premium tiers (Premium supports HSM-backed keys), managed HSM, Azure RBAC and legacy access policies, soft delete with purge protection, and private endpoints. SKU capabilities and supported key types evolve; verify current SKU capabilities before designing a workload.

## Governance workflow and controls

### 1. Choose access model

Prefer Azure RBAC over legacy access policies because RBAC supports custom roles and integrates with Privileged Identity Management. Use access policies only for compatibility with older deployments.

### 2. Configure access

Grant least privilege. Secrets, keys, and certificates have separate permissions. Use PIM-eligible roles for administrative operations. Require approval for permanent role assignments.

### 3. Configure network access

Use private endpoints for vault access from a virtual network. Disable public network access where the workload supports it. Use service endpoints where private endpoints are unavailable.

### 4. Configure soft delete and purge protection

Enable soft delete and purge protection on every production vault. Without purge protection, a vault can be irreversibly deleted, including the keys and secrets it contains.

### 5. Configure logging

Send Key Vault diagnostic logs to a central Log Analytics workspace. Track every secret access, key operation, and certificate event. Alert on unusual patterns.

### 6. Define secret lifecycle

For every secret type, define:

- issuance procedure;
- rotation cadence;
- revocation procedure;
- deletion procedure;
- owner;
- storage location.

Store the lifecycle document in the control register. Test the rotation procedure annually.

### 7. Manage keys

Enable automatic rotation for keys where supported. Track key versions in the key registry. Maintain a documented procedure for replacing keys.

### 8. Manage certificates

Define certificate authority (CA) source, validation procedure, renewal cadence, and revocation procedure. Use private CA where the certificate is internal-only.

## Validation and evidence

- Vault configuration with RBAC or access-policy details.
- Soft delete and purge protection status.
- Private endpoint configuration.
- Diagnostic log destination and retention.
- Secret, key, and certificate inventory.
- Rotation evidence.

## Failure correction

Common defects include public network access enabled by default, missing purge protection, and secrets stored outside the documented rotation cadence. Corrective actions include a configuration drift check, a quarterly vault review, and a rotation test for at least one secret per vault annually.

## Limitations

- Azure Key Vault is specific to Azure.
- Premium tier has higher cost; use only where HSM is required.
- Some operations have rate limits; design around them.
- RBAC and access policies are mutually exclusive within a vault; standardize on one model.

## Canonical sources

- Azure Key Vault documentation, current edition.
- Azure Managed HSM documentation, current edition.
- Microsoft Entra Privileged Identity Management documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for cryptographic controls, the engineering leaf for workload credential retrieval, and the operations leaf for rotation cadence.
