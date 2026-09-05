---
title: "Kubernetes RBAC Audit"
owner: "Container Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Quarterly review, new cluster onboarding, new high-privilege role definition, or RBAC-related incident."
scope: "All Kubernetes clusters in production and pre-production, including hosted and self-managed distributions."
inputs:
  - "Cluster inventory and version matrix"
  - "RBAC inventory: roles, cluster roles, role bindings, cluster role bindings"
  - "Service account inventory and workload mapping"
  - "Previous review attestation and outstanding remediation"
plan:
  - "Step 1: Pull the RBAC inventory across every cluster and normalize into a single report."
  - "Step 2: Identify high-privilege subjects — cluster-admin, wildcard verbs, wildcard resources, secrets access, exec into pods, persistent volume manipulation."
  - "Step 3: Identify inactive subjects — users and service accounts with no API access in the review window."
  - "Step 4: Identify excessive subjects — service accounts with privileges exceeding the documented least-privilege baseline for the workload."
  - "Step 5: Identify break-glass subjects and confirm two-person activation and audit-log review."
  - "Step 6: Notify each cluster owner and workload owner with the reviewer packet; require response within 14 days."
  - "Step 7: Auto-revoke subjects with no consumer and no response after the window; record evidence."
  - "Step 8: Publish metrics — bindings reviewed, revoked, modified, and outstanding exceptions."
evidence:
  - "Signed reviewer attestations"
  - "Inventory snapshots before and after"
  - "Revocation log with timestamps"
  - "Exception register with compensating controls and expiry"
  - "Metrics dashboard export"
escalation:
  - "Any cluster-admin binding outside an explicitly approved set — escalate to Security on-call."
  - "Any owner who fails to respond within 7 days — escalate to their manager and Container Platform leadership."
completion:
  - "100 percent of in-scope bindings have a current attestation."
  - "All stale or excessive subjects revoked or risk-accepted with compensating control and expiry."
exceptions:
  - "Vendor-managed control plane bindings explicitly documented as managed by the provider."
related:
  - "ACCESS_REVIEW.md"
  - "CLOUD_IAM_PERIODIC_ACCESS_REVIEW.md"
  - "PRIVILEGED_MFA_DEFAULT_VALIDATION.md"
