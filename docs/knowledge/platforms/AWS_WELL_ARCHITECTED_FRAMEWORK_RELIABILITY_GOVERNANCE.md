# AWS Well-Architected Framework Reliability Pillar Governance

## Purpose

The AWS Well-Architected Framework's Reliability Pillar (current edition, 2024 update) defines best practices for building resilient workloads on AWS: recover from failures, meet recovery objectives, and mitigate disruptions. The reliability governance pattern captures the recovery objective tracking (RTO, RPO), the failure-mode analysis process, the change-management discipline, and the documented workload testing cadence. Without explicit governance, recovery objectives are aspirational rather than measured, and outages exceed expected duration.

## Current context and source status

AWS Well-Architected Framework Reliability Pillar whitepaper, updated 2024. AWS maintains six pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability. The AWS Well-Architected Tool records answers and produces improvement items.

## Governance pattern

1. Inventory every workload with documented RTO, RPO, and recovery strategy.
2. Track workload-criticality tier (Tier 1: customer-facing, Tier 2: business-critical, Tier 3: internal) and assign RTO/RPO accordingly.
3. Use AWS Well-Architected Tool to record answers per pillar; mark unanswered questions as risks.
4. Conduct failure-mode analysis using the AWS Component Failures Lens.
5. Test recovery procedures using AWS Fault Injection Service (FIS) or equivalent chaos engineering.
6. Define change-management discipline: CloudFormation/HashiCorp Terraform plan review, separate change window.
7. Implement auto-scaling, multi-AZ deployment, and backups per the RTO/RPO.
8. Monitor recovery metrics: time-to-detect, time-to-recover, error budget burn rate.
9. Review the Well-Architected review quarterly with the workload owner.
10. Maintain a backlog of high-risk-question (HRQ) items with owner and target date.

## Validation and evidence

- Workload inventory with RTO, RPO, and tier recorded.
- AWS Well-Architected Tool review artifact recorded.
- Failure-mode analysis recorded per workload.
- Recovery test artifacts recorded (FIS experiment log, runbook test result).
- HRQ backlog with owner and target date.

## Failure correction

Common defects include aspirational RTO/RPO without testing, missing multi-AZ deployment, and stale Well-Architected reviews. Corrective actions include requiring annual recovery testing, enforcing multi-AZ via Service Control Policy (SCP), and triggering review reminders on a quarterly cadence.

## Limitations

- The AWS Well-Architected Framework is specific to AWS workloads.
- The Framework does not provide quantitative risk scoring (use Cloud Custodian or AWS Config).
- FIS requires target resources that support fault injection; validate per service.
- The Framework does not address workload portability to other clouds.

## Scope note

This knowledge article is part of the **platforms** leaf. Sibling leaves cover: **operations** (incident response and chaos engineering), **security** (AWS IAM and SCP), **engineering** (architecture patterns), and **templates** (reliability review template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- AWS Well-Architected Framework — Reliability Pillar (AWS, 2024 update): https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html
- AWS Well-Architected Framework (AWS whitepaper index): https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html
- AWS Well-Architected Tool (AWS console documentation): https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html

Sources were verified on September 1, 2026.