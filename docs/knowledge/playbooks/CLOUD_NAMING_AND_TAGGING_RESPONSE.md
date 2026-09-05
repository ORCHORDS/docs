---
title: "Cloud Resource Naming and Tagging Playbook"
owner: "Cloud Platform Owner"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Cloud Resource Naming and Tagging Playbook

## Trigger

Use this playbook when cloud resources are provisioned, modified, audited, or decommissioned, and the resource name, tag set, or taxonomy must be applied, validated, or corrected to support cost allocation, security policy, operations, and lifecycle management.

## Scope

Apply the process to all resources in the organization's cloud accounts, subscriptions, projects, and management groups across the environments, providers, and resource types in scope of the cloud governance baseline.

## Inputs

- cloud provider account, subscription, project, and region context;
- resource type, purpose, owner, environment, and criticality;
- cost center, charge code, project, and customer identifiers;
- applicable compliance and data classification labels;
- the organization's naming and tagging taxonomy and policy.

## Steps

1. **Confirm the taxonomy.** Apply the current version of the naming and tagging standard; document any custom tag values in the central tag registry.
2. **Generate the resource name.** Construct the name from documented segments: environment, region, business unit, application, resource type, instance or identifier, and optional environment suffix; enforce length, character set, and uniqueness constraints per provider.
3. **Apply mandatory tags.** Set the required tags at provision time using infrastructure-as-code (Terraform, CloudFormation, Bicep, Pulumi, deployment manifests); do not rely on post-provision tagging.
4. **Apply optional and conditional tags.** Add business, chargeback, regulatory, and operational tags as defined in the taxonomy; record owner and on-call contact for incident routing.
5. **Validate tag policy.** Run the cloud provider's tag policy or a third-party evaluator to confirm presence, format, and allowed values; reject non-conformant provisioning in CI/CD.
6. **Propagate and inherit.** Use tag inheritance (e.g., tag-on-resource-group, tag-on-subscription, AWS Organizations tag policies, GCP folder policies) to minimize per-resource tagging error.
7. **Detect drift.** Schedule daily or continuous scans for untagged or non-conformant resources; produce a remediation report per owner and per environment.
8. **Remediate.** Apply missing or invalid tags through automated remediation where the value is derivable; route non-derivable cases to the resource owner for confirmation.
9. **Audit usage.** Reconcile tags against cost allocation, security policy (SCOPE, environment-based access), and operational dashboards; retire unused tags on a defined cadence.
10. **Decommission and release.** On resource deletion, retain the tag history in the central registry for audit; release the name only after the resource has been fully terminated.

## Escalation

Escalate to the Cloud Platform Owner, FinOps Lead, and Security when:
- a resource type is outside the taxonomy or requires a new segment;
- compliance or regulatory tags are missing or invalid on production data-bearing systems;
- tag drift exceeds the documented threshold;
- cost allocation cannot be completed because of missing tags.

## Evidence

- IaC diff or pull request showing tag application;
- tag policy evaluation report and compliance score;
- remediation tickets and closure evidence;
- cost allocation reconciliation per tag dimension;
- decommissioning record with tag retention evidence.

## Completion Criteria

The naming and tagging process is considered complete for a given resource when:
- the name conforms to the documented pattern;
- all mandatory tags are present and validated;
- the resource is discoverable in inventory, cost, and security reports;
- non-conformant resources are tracked to remediation or exception.

## Exceptions

Document deviations with the approver, scope, expiration, compensating control, and review schedule. Maintain the exception register alongside the taxonomy.

## Related Documents

- AWS Tagging Best Practices
- Azure Resource Naming Conventions
- GCP Resource Naming Conventions
- FinOps Cost Allocation Framework
- Cloud Asset Inventory Review
