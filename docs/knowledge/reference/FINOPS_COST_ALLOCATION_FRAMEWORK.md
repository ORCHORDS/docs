---
title: "FINOPS Cost Allocation Framework Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "FINOPS Foundation; https://www.finops.org/framework/"
---

# FINOPS Cost Allocation Framework Reference Card

## Scope

Reference card for the FINOPS Framework, specifically the *Allocation* phase, which assigns cloud costs to the teams, products, or business units that consume them. Cost allocation requires accurate tagging or labeling, allocation rules for untagged or shared resources, and visibility into unit economics. Profiles that govern cloud spend should adopt the FINOPS Allocation phase practices, enforce tagging per cloud-provider conventions, and bind to the cloud asset inventory review.

## Identifier table

| Field | Value |
| --- | --- |
| Primary source | FINOPS Foundation — Framework, Allocation phase |
| Companion artifacts | AWS Tagging Best Practices, Azure/GCP Naming Conventions, Cloud Asset Inventory Review |
| Source URL | https://www.finops.org/framework/ |

## Plan

1. Cite the FINOPS Allocation phase in cost-allocation policies and FinOps practice documentation.
2. Adopt mandatory tag set (or equivalent labeling) for cost allocation: `CostCenter`, `Project`, `Environment`, `Owner`.
3. Define allocation rules for shared or untagged resources (for example, pro-rata by usage or by tagging enforcement).
4. Establish showback or chargeback reporting on a defined cadence.
5. Use unit-economics metrics (cost per customer, cost per transaction) to drive optimization.
6. Bind to AWS Tagging Best Practices for AWS environments.
7. Bind to Azure/GCP Naming Conventions for Azure and GCP environments.
8. Bind to Cloud Asset Inventory Review for the authoritative inventory source.
9. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- FINOPS Framework documentation (Allocation phase).
- Cloud-provider tagging and naming enforcement.
- Cost Explorer, Cost Management, or equivalent per cloud provider.
- Unit-economics data sources (for example, customer count, transaction count).
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the FINOPS Allocation phase as the canonical reference for cloud cost allocation. Profiles that govern cloud spend should cite the FINOPS Allocation phase, enforce tagging or labeling, define allocation rules for shared resources, establish showback or chargeback reporting, and bind to the cloud-provider conventions.

A profile that governs cloud spend without binding to the FINOPS Allocation phase is non-conformant.

## Implementation Notes

- Untagged or shared resources must have an explicit allocation rule; do not let them fall into a default bucket.
- Showback (visibility without chargeback) is the typical first phase; chargeback (internal billing) requires finance integration.
- Unit-economics metrics require collaboration between engineering, finance, and product; they are not solely an engineering concern.
- Allocation should be visible to engineering teams in near real time; daily or weekly reporting is typical.
- Cost anomalies should trigger alerts that are routed to the engineering team and the FinOps practice owner.

## Companion Documents

- [AWS Tagging Best Practices](AWS_TAGGING_BEST_PRACTICES.md)
- [Azure Resource Naming Conventions](AZURE_RESOURCE_NAMING_CONVENTIONS.md)
- [GCP Resource Naming Conventions](GCP_RESOURCE_NAMING_CONVENTIONS.md)
- [Cloud Asset Inventory Review](CLOUD_ASSET_INVENTORY_REVIEW.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
