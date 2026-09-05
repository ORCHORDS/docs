---
title: "Azure Resource Naming Conventions Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Microsoft Azure documentation — naming rules and conventions; Cloud Adoption Framework"
---

# Azure Resource Naming Conventions Reference Card

## Scope

Reference card for Microsoft Azure resource naming conventions, which define the abbreviated resource-type prefix, the environment, the region, the instance identifier, and optional scope or compliance tags. Profiles that govern Azure environments should adopt the Microsoft-recommended abbreviations, use Azure Policy to enforce the convention, and bind to the cloud asset inventory review, FINOPS framework, and AWS/GCP equivalents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Microsoft Azure naming rules and conventions, Cloud Adoption Framework |
| Companion artifacts | AWS Tagging Best Practices, GCP Resource Naming Conventions, Cloud Asset Inventory Review |
| Source URL | https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-naming |

## Plan

1. Adopt a resource-naming pattern: `{type}-{workload}-{environment}-{region}-{instance}` (for example, `vm-app1-prod-eus2-001`).
2. Use the Microsoft-recommended abbreviations for each resource type (for example, `vm` for Virtual Machine, `kv` for Key Vault, `sql` for SQL Database).
3. Use Azure Policy to enforce the naming pattern and detect violations.
4. Treat resource names as inputs to the asset inventory and cost allocation.
5. Use resource tags for cross-cutting metadata (Owner, CostCenter, DataClassification) that does not fit in the name.
6. Bind to Cloud Asset Inventory Review for the asset-inventory binding.
7. Bind to FINOPS Cost Allocation Framework for cost-allocation practice.
8. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Microsoft Azure naming-rules documentation.
- Azure Policy definitions for naming-convention enforcement.
- Azure Resource Graph queries for asset inventory.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats Azure resource naming as a foundational control for inventory, ownership, and cost allocation. Profiles that govern Azure should adopt the `{type}-{workload}-{environment}-{region}-{instance}` pattern, enforce the convention via Azure Policy, integrate names into the asset inventory, and bind to the FINOPS framework.

A profile that governs Azure without an enforced naming convention is non-conformant.

## Implementation Notes

- Azure resource names have length limits per resource type; the convention must respect these limits.
- Some resource types require globally unique names (for example, storage accounts); the naming pattern must include a uniqueness suffix.
- Azure Policy `deny` and `modify` effects can be used to enforce naming at creation.
- Resource-group naming should follow the same pattern and serve as the primary scope for IAM assignments.
- Naming changes after creation are not supported for many Azure resource types; the convention must be applied at creation.

## Companion Documents

- [AWS Tagging Best Practices](AWS_TAGGING_BEST_PRACTICES.md)
- [GCP Resource Naming Conventions](GCP_RESOURCE_NAMING_CONVENTIONS.md)
- [Cloud Asset Inventory Review](CLOUD_ASSET_INVENTORY_REVIEW.md)
- [FINOPS Cost Allocation Framework](FINOPS_COST_ALLOCATION_FRAMEWORK.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
