---
title: "Workload Identity Attestation Verification"
owner: "Identity and Access Management"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Quarterly review, new workload identity provider onboarding, attestation-related incident, or change in trust chain."
scope: "All workload identities across ORCHORDS environments, including Kubernetes service accounts, CI/CD service accounts, and machine identities in cloud providers."
inputs:
  - "Workload identity inventory by provider and trust chain"
  - "Attestation policies and signing keys"
  - "Trust chain configuration and certificate authorities"
  - "Recent identity-related incidents or anomalies"
plan:
  - "Step 1: Confirm scope and pull workload identity inventory across all providers."
  - "Step 2: Validate that every workload identity has a documented attestation policy and a current signing key."
  - "Step 3: Validate the trust chain: certificate authorities are current, not revoked, and within the documented rotation window."
  - "Step 4: Sample attestation events and verify the attestation is signed by a current key and within policy."
  - "Step 5: Identify orphan or stale workload identities: no attestation in the audit window."
  - "Step 6: Notify workload owners with the remediation packet and require a 14-day response."
  - "Step 7: Auto-revoke identities with no attestation and no owner response after the window."
  - "Step 8: Capture metrics and report to governance."
evidence:
  - "Workload identity inventory and attestation policy table"
  - "Trust chain configuration and CA inventory"
  - "Attestation sample and verification report"
  - "Orphan and stale identity list"
  - "Revocation log and metrics dashboard"
escalation:
  - "Trust chain compromise or revocation — escalate to Security on-call."
  - "Identity with no attestation policy — escalate to workload owner and IAM leadership."
completion:
  - "Every workload identity has a current attestation policy."
  - "Trust chain verified across all providers."
  - "Orphan identities revoked or risk-accepted with compensating control."
exceptions:
  - "Documented break-glass workload identities with controlled activation."
related:
  - "ACCESS_REVIEW.md"
  - "CLOUD_IAM_PERIODIC_ACCESS_REVIEW.md"
  - "PUBLIC_KEY_INFRASTRUCTURE_REVIEW.md"
