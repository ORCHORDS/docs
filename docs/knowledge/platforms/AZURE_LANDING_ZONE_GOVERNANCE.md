# Azure Landing Zone Governance

## Purpose

An Azure Landing Zone is a pre-provisioned environment that supports workload migration and deployment at scale. It includes identity, management groups, subscription organization, networking, policy assignments, and logging. Governance ensures the landing zone reflects current architecture decisions, that subscription placement aligns with workload criticality and compliance scope, and that policy-as-code is reviewed before assignment.

## Current context and source status

Microsoft publishes the Azure Landing Zone architecture and the Azure Architecture Center reference implementations. The current reference implementations use the Azure Verified Modules (AVM) and Terraform or Bicep. Specific module identifiers, policy definitions, and management group names evolve. Validate the current AVM module version and policy definition references before treating any identifier as a current requirement.

## Governance workflow and controls

### 1. Define management group hierarchy

Establish a management group hierarchy that reflects organizational structure and platform responsibilities. Common patterns include a root, platform, landing zones, sandboxes, and decommissioned groups. Inheritance flows downward; more sensitive workloads are placed deeper.

### 2. Govern subscriptions

Allocate one subscription per workload, environment, or business unit. Treat a subscription as the unit of policy assignment, identity boundary, and billing. Avoid placing workloads from different compliance scopes in the same subscription.

### 3. Adopt Azure Policy

Assign Azure Policy definitions at the management-group level. Use initiative definitions (policy sets) for related controls. Track policy compliance as a board-level metric.

### 4. Configure identity

Adopt Microsoft Entra ID as the identity provider. Configure Conditional Access for privileged roles. Use Privileged Identity Management (PIM) for just-in-time elevation. Apply access reviews on a defined cadence.

### 5. Centralize logging

Configure diagnostic settings to send platform logs to a central Log Analytics workspace or to Sentinel. Retain logs per the documented retention policy. Restrict access to the log destination.

### 6. Network topology

Adopt a hub-and-spoke or Virtual WAN topology. Centralize egress, shared services, and DNS. Validate connectivity patterns before workload deployment.

### 7. Update the reference implementation

Track upstream changes to AVM modules and the Azure Landing Zone accelerator. Apply security and reliability updates within a defined window.

## Validation and evidence

- Management group hierarchy diagram.
- Subscription inventory with workload, environment, and owner.
- Policy assignment and compliance summary.
- Conditional Access and PIM configuration.
- Log destination configuration and retention policy.
- Network topology diagram.

## Failure correction

Common defects include orphaned subscriptions, unmanaged policy assignments, and unreviewed PIM activations. Corrective actions include a quarterly subscription inventory review, automated policy compliance reporting, and PIM activation alerts to a security team.

## Limitations

- Azure Landing Zone is specific to Azure.
- Policy compliance does not imply security; some policy violations are intentional.
- Cross-subscription networking introduces routing complexity.
- Some Azure services are region-specific; validate per deployment region.

## Canonical sources

- Azure Architecture Center Landing Zone documentation, current edition.
- Microsoft Cloud Adoption Framework, current edition.
- Azure Verified Modules documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for identity controls, the operations leaf for subscription provisioning, and the engineering leaf for policy-as-code patterns.
