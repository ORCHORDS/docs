---
title: "Zero Trust Decision Audit"
owner: "Network Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Quarterly audit, post-incident review, new policy decision type, or material change in policy enforcement configuration."
scope: "All policy decision points across the Zero Trust Architecture, including policy engine, policy administrator, and enforcement points."
inputs:
  - "Policy decision logs from the policy engine and administrator"
  - "Policy definitions and version history"
  - "Identity, device, and data classification inventories"
  - "Threat intelligence and risk signal sources"
plan:
  - "Step 1: Confirm scope and pull decision logs for the audit window."
  - "Step 2: Validate decision log completeness: every decision has actor, action, resource, decision, and reason."
  - "Step 3: Sample decisions for policy compliance: verify that each decision aligns with the current policy definition."
  - "Step 4: Identify denied decisions and trace whether the denial aligns with policy intent and whether the requester has a documented workaround."
  - "Step 5: Identify allow decisions and trace whether the policy signals were sufficient for the access."
  - "Step 6: Identify stale policy signals: attributes that have not been refreshed within the documented window."
  - "Step 7: File remediation actions for any non-compliant or stale decisions."
evidence:
  - "Decision log sample with policy alignment assessment"
  - "Compliance report per decision class"
  - "Stale signal report"
  - "Remediation actions with owners and deadlines"
escalation:
  - "Decision log incompleteness — escalate to Network Security and the policy engine owner."
  - "Stale signal for a critical attribute — escalate to the attribute owner."
completion:
  - "Every sampled decision verified against policy."
  - "Stale signals remediated or risk-accepted with compensating control."
exceptions:
  - "Documented policy exceptions with expiry and compensating controls."
related:
  - "ACCESS_REVIEW.md"
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "CLOUD_IAM_PERIODIC_ACCESS_REVIEW.md"
