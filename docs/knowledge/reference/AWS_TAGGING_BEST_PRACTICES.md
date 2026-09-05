---
title: "AWS Tagging Best Practices Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "AWS Well-Architected Framework — Cost Optimization and Operations Excellence pillars; AWS Tagging documentation"
---

# AWS Tagging Best Practices Reference Card

## Scope

Reference card for AWS resource tagging as the mechanism for cost allocation, ownership, lifecycle, security classification, and compliance scoping. Profiles that govern AWS environments should adopt a mandatory tag set with automation for tagging enforcement, untagged-resource detection, and tag-based policy enforcement (IAM `aws:ResourceTag` conditions, AWS Organizations SCPs). Bind to the FINOPS cost allocation framework and the cloud asset inventory review.

## Identifier table

| Field | Value |
| --- | --- |
| Primary sources | AWS Well-Architected Framework, AWS Tagging documentation, AWS Organizations SCPs |
| Companion artifacts | FINOPS Cost Allocation Framework, Cloud Asset Inventory Review, AWS/Azure/GCP naming conventions |
| Source URL | https://docs.aws.amazon.com/tag-editor/latest/userguide/tagging.html |

## Plan

1. Adopt a mandatory tag set: `Name`, `Owner`, `Environment`, `CostCenter`, `Project`, `DataClassification`, `ComplianceScope`, `MFA` (or equivalent), `Created`, `Expires`.
2. Apply tags at resource creation; never leave a resource untagged.
3. Use AWS Organizations tag policies to enumerate allowed values per tag key.
4. Use IAM `aws:ResourceTag` conditions to enforce tag-based access control on sensitive tags (for example, `DataClassification=Confidential`).
5. Use AWS Config rules to detect untagged resources and trigger remediation.
6. Use AWS Cost Explorer and AWS Budgets to allocate cost by `CostCenter` and `Project` tags.
7. Bind to FINOPS Cost Allocation Framework for cost-allocation practice.
8. Bind to Cloud Asset Inventory Review for the asset-inventory binding.
9. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- AWS Organizations tag policy.
- AWS Config rules for untagged-resource detection.
- IAM policies with `aws:ResourceTag` conditions.
- Cost Explorer and Budgets configuration.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats AWS tagging as a foundational control for cost allocation, ownership, and compliance scoping. Profiles that govern AWS environments should adopt the mandatory tag set, enforce tags at creation, automate untagged-resource detection, use tag-based IAM conditions for sensitive tags, and bind to the FINOPS Cost Allocation Framework.

A profile that governs AWS without an enforced tagging strategy is non-conformant.

## Implementation Notes

- Tag inheritance via AWS Resource Groups can be used to apply tags to a group of resources consistently.
- Use SCPs to deny creation of resources that lack mandatory tags.
- Tag values should be normalized to a controlled vocabulary (for example, `Environment` ∈ {`dev`, `staging`, `prod`}).
- Treat untagged-resource detection as a control with a defined SLA (for example, untagged resources are remediated within 24 hours).
- Cost allocation by `CostCenter` and `Project` should be auditable; tag changes should be logged in CloudTrail.

## Companion Documents

- [Azure Resource Naming Conventions](AZURE_RESOURCE_NAMING_CONVENTIONS.md)
- [GCP Resource Naming Conventions](GCP_RESOURCE_NAMING_CONVENTIONS.md)
- [Cloud Asset Inventory Review](CLOUD_ASSET_INVENTORY_REVIEW.md)
- [FINOPS Cost Allocation Framework](FINOPS_COST_ALLOCATION_FRAMEWORK.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
