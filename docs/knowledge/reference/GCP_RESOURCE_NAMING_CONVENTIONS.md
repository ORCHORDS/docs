---
title: "GCP Resource Naming Conventions Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Google Cloud documentation — naming conventions; Cloud Architecture Center"
---

# GCP Resource Naming Conventions Reference Card

## Scope

Reference card for Google Cloud resource naming conventions, which define the resource-type prefix, the environment, the region, the instance identifier, and optional labels. Profiles that govern GCP environments should adopt the recommended abbreviations, use Organization Policy to enforce the convention, and bind to the cloud asset inventory review, FINOPS framework, and AWS/Azure equivalents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | Google Cloud naming-convention documentation, Cloud Architecture Center |
| Companion artifacts | AWS Tagging Best Practices, Azure Resource Naming Conventions, Cloud Asset Inventory Review |
| Source URL | https://cloud.google.com/resource-manager/docs/cloud-resource-manager |

## Plan

1. Adopt a resource-naming pattern: `{type}-{workload}-{environment}-{region}-{instance}` (for example, `gce-app1-prod-usce1-001`).
2. Use the recommended abbreviations for each resource type (for example, `gce` for Compute Engine, `gcs` for Cloud Storage, `bq` for BigQuery).
3. Use Organization Policy constraints to enforce naming-convention adherence.
4. Apply labels for cross-cutting metadata (Owner, CostCenter, DataClassification) that does not fit in the name.
5. Treat names and labels as inputs to the asset inventory and cost allocation.
6. Bind to Cloud Asset Inventory Review for the asset-inventory binding.
7. Bind to FINOPS Cost Allocation Framework for cost-allocation practice.
8. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- Google Cloud naming-convention documentation.
- Organization Policy constraints for naming enforcement.
- Cloud Asset Inventory feeds.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats GCP resource naming as a foundational control for inventory, ownership, and cost allocation. Profiles that govern GCP should adopt the `{type}-{workload}-{environment}-{region}-{instance}` pattern, enforce the convention via Organization Policy, integrate names and labels into the asset inventory, and bind to the FINOPS framework.

A profile that governs GCP without an enforced naming convention is non-conformant.

## Implementation Notes

- GCP resource names have length limits per resource type; the convention must respect these limits.
- Some GCP resource types require globally unique names (for example, Cloud Storage buckets); the naming pattern must include a uniqueness suffix.
- Organization Policy constraints can be applied at the folder or project level.
- Resource-name changes after creation are not supported for many GCP resource types; the convention must be applied at creation.
- Labels are mutable after creation and can be used for tagging-style metadata.

## Companion Documents

- [AWS Tagging Best Practices](AWS_TAGGING_BEST_PRACTICES.md)
- [Azure Resource Naming Conventions](AZURE_RESOURCE_NAMING_CONVENTIONS.md)
- [Cloud Asset Inventory Review](CLOUD_ASSET_INVENTORY_REVIEW.md)
- [FINOPS Cost Allocation Framework](FINOPS_COST_ALLOCATION_FRAMEWORK.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
