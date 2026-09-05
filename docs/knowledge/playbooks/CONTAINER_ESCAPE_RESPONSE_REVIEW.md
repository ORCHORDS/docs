---
title: "Container Escape Response Review"
owner: "Container Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Detection of a container escape, advisory affecting the container runtime, or scheduled quarterly review."
scope: "All containerized workloads in production and pre-production clusters."
inputs:
  - "Container runtime configuration and version matrix"
  - "Workload manifests with security context, capabilities, and seccomp profiles"
  - "Detection alerts from runtime security tooling"
  - "Recent advisories affecting the runtime"
plan:
  - "Step 1: Receive the trigger and capture workload identifier, runtime, host, and detection timestamp."
  - "Step 2: Quarantine the affected workload: cordon the node, stop the pod, and preserve the workload manifest and runtime logs."
  - "Step 3: Validate that the runtime version is current and patched against known escape vulnerabilities."
  - "Step 4: Validate workload security context: drop capabilities, read-only root filesystem, no privileged escalation, seccomp profile enforced."
  - "Step 5: Validate network segmentation: workload cannot reach the Kubernetes control plane, secrets API, or other sensitive services."
  - "Step 6: Validate image provenance and integrity: signed image, registry allow-list, and runtime policy enforced."
  - "Step 7: File a post-incident review if an actual escape occurred; capture remediation actions and timeline."
evidence:
  - "Workload manifest and runtime configuration exports"
  - "Runtime version matrix and patch status"
  - "Detection alert with timestamp and scope"
  - "Quarantine action log"
  - "Post-incident review record if applicable"
escalation:
  - "Confirmed escape with lateral movement evidence — escalate to Security on-call within 15 minutes."
  - "Runtime with unpatched known escape vulnerability — escalate to Container Platform and Security."
completion:
  - "Affected workload quarantined and investigated."
  - "Runtime and workload configuration verified against policy."
  - "Post-incident review filed if applicable."
exceptions:
  - "Privileged workloads explicitly documented with business justification and compensating controls."
related:
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "KUBERNETES_RBAC_AUDIT.md"
  - "CONTAINER_IMAGE_VULNERABILITY_RESPONSE.md"
