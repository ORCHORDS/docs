# GCP Organization Policy Governance

## Purpose

Google Cloud Organization Policy constraints restrict allowed configurations across an organization, folder, or project. Governance ensures that constraints are applied at the correct scope, that exceptions are documented, and that constraints evolve with regulatory and threat-landscape changes.

## Current context and source status

Google Cloud Organization Policy is generally available. Constraints are defined in the `orgpolicy.googleapis.com` service. The list of available constraints evolves as Google introduces new services. Specific constraint identifiers (for example, `constraints/compute.disableInternetNetworkEndpoint`) change between releases. Validate the current constraint list before treating any identifier as a current requirement.

## Governance workflow and controls

### 1. Establish a constraint baseline

Adopt the constraints that reflect security, compliance, and cost-control requirements. Record in the constraint register:

- constraint identifier;
- constraint type (list, boolean);
- enforced scope (organization, folder, project);
- compliance framework mapping;
- exception owner and expiry.

### 2. Apply at the correct scope

Apply broad constraints at the organization or folder level. Apply narrow constraints at the project level. Use inheritance to reduce policy sprawl.

### 3. Use list constraints for allowlists

For sensitive workloads, use list constraints to restrict which services, regions, or external resources can be used. For example, restrict allowed external IP ranges, restrict VM images to a curated list, restrict API keys to specific apps.

### 4. Use boolean constraints for binary restrictions

Use boolean constraints to enable or disable a behavior. Examples include disabling service-account key creation, disabling external IPs on VM instances, and restricting which users can create new projects.

### 5. Manage policy inheritance

A project inherits the policy of its parent folder and the organization. Track effective policy, not just direct policy. Document the inheritance chain in the control register.

### 6. Manage exceptions

Use the policy dry-run mode to evaluate exceptions before enforcement. Record the exception owner, business justification, compensating control, and expiry. Expire exceptions automatically.

### 7. Audit

Audit constraint compliance as part of the regular security review. Track constraint changes in a change log. Investigate every constraint override.

## Validation and evidence

- Constraint inventory with scope and enforcement.
- Dry-run evaluation reports.
- Exception register with expiries.
- Change log with change rationale.
- Effective policy artifact per workload.

## Failure correction

Common defects include constraints applied at the wrong scope, exceptions that never expire, and untested constraint changes. Corrective actions include a quarterly scope review, automated exception expiry, and a dry-run evaluation workflow that requires sign-off before enforcement.

## Limitations

- GCP Organization Policy is specific to Google Cloud.
- Some constraints cannot be set at the organization level; validate scope.
- Dry-run mode is informational and does not enforce.
- Constraint changes may take time to propagate.

## Canonical sources

- Google Cloud Organization Policy documentation, current edition.
- Google Cloud Architecture Center, current edition.
- Google Cloud IAM documentation, current edition.

## Scope note

This article belongs to the platforms leaf and cross-references the security leaf for access controls, the operations leaf for resource lifecycle, and the engineering leaf for policy-as-code patterns.
