---
title: "Kernel Live Patch Review"
owner: "Platform Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "30 days"
next-review: "2026-10-05"
trigger: "Critical kernel CVE advisory, monthly review of live-patch coverage, or post-incident review following a kernel vulnerability."
scope: "All production Linux hosts running long-lived workloads, including Kubernetes nodes, database hosts, and batch workers, where live patching is feasible."
inputs:
  - "Kernel version inventory by host class"
  - "Live patch vendor feed (for example, Ubuntu Livepatch, kpatch, ksplice) and subscription state"
  - "Critical CVE feed filtered for kernel class"
  - "Maintenance window and reboot policy"
plan:
  - "Step 1: Pull kernel inventory and cross-reference with live-patch eligibility."
  - "Step 2: Identify hosts with no live-patch subscription or with subscription lapsed."
  - "Step 3: For each new critical CVE, determine whether the live patch is available, applicable, or pending; record SLA per CVE severity."
  - "Step 4: Validate the live-patch client health — last contact, last successful patch, error state."
  - "Step 5: Apply live patches during the maintenance window in line with change control; coordinate with workload owners if patch requires quiescent state."
  - "Step 6: Verify patch application via uname and the live-patch status command; record patch ID."
  - "Step 7: Reboot hosts where the live patch is unavailable or where the vendor requires it; coordinate with workload owner."
  - "Step 8: Capture residual action items for hosts requiring later remediation."
evidence:
  - "Kernel inventory and live-patch coverage report"
  - "CVE-to-patch mapping table"
  - "Live-patch application log with patch IDs"
  - "Reboot schedule and confirmation log"
  - "Residual action register"
escalation:
  - "Critical CVE with no live patch available for an in-scope host class — escalate to Platform Engineering and Security; treat as emergency patch."
  - "Live-patch client errors exceeding threshold across a host class — escalate to Platform vendor support."
completion:
  - "Every critical CVE has a documented remediation path within SLA."
  - "Every in-scope host has either a current live patch or a scheduled reboot."
exceptions:
  - "Hosts with documented business constraints against live patching; require compensating monitoring and accelerated reboot SLAs."
related:
  - "PATCH_MANAGEMENT_EFFECTIVENESS_REVIEW.md"
  - "CONFIGURATION_BASELINE_REVIEW.md"
  - "CHANGE_CONTROL.md"
