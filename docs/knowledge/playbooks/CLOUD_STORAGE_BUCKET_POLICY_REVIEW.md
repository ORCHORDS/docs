---
title: "Cloud Storage Bucket Policy Review"
owner: "Storage Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Quarterly review, new bucket creation, policy change, public exposure finding, or data egress incident."
scope: "All object storage buckets in production and pre-production accounts, including shared services and analytics sandboxes."
inputs:
  - "Bucket inventory and ACL configuration"
  - "Bucket policy and IAM policy attached to the bucket"
  - "Encryption configuration and key reference"
  - "Lifecycle policy and current object count"
  - "Data classification for objects in the bucket"
plan:
  - "Step 1: Pull bucket inventory and policy state across every account and provider."
  - "Step 2: Identify public or anonymous-readable buckets; verify each against the data classification register."
  - "Step 3: Identify cross-account access grants and validate that each is documented and current."
  - "Step 4: Identify encryption gaps — unencrypted at rest, customer-managed keys not rotated, default provider keys without justification."
  - "Step 5: Identify lifecycle gaps — buckets with no lifecycle policy and high object counts, indicating cost or retention risk."
  - "Step 6: Identify access logging gaps — buckets without access logs enabled or with logs not reviewed."
  - "Step 7: Notify each bucket owner with a remediation packet and a 14-day response window."
  - "Step 8: Auto-remediate public access on buckets with no compensating justification; record evidence."
evidence:
  - "Inventory and policy snapshots before and after"
  - "Public exposure findings and remediation log"
  - "Encryption and key rotation status"
  - "Lifecycle and access log coverage report"
  - "Reviewer attestations"
escalation:
  - "Public bucket containing sensitive or regulated data — escalate to Security on-call within 30 minutes."
  - "Encryption gap on a regulated-data bucket — escalate to Compliance and Information Security Officer."
completion:
  - "100 percent of buckets have a current policy review attestation."
  - "No buckets with unintended public access remain."
  - "Encryption and lifecycle gaps resolved or risk-accepted with expiry."
exceptions:
  - "Buckets explicitly approved for public hosting; reviewed annually and tagged in the inventory."
related:
  - "ACCESS_REVIEW.md"
  - "DATA_FLOW_INVENTORY_REVIEW.md"
  - "SECURITY_CATEGORIZATION_REVIEW.md"
