---
title: "CloudTrail Investigation Playbook"
owner: "Security Operations"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "CloudTrail anomaly alert, suspicious API call pattern, suspected account compromise, or scheduled investigation."
scope: "All AWS accounts under ORCHORDS management with CloudTrail enabled."
inputs:
  - "CloudTrail event stream and lookup tooling"
  - "Account inventory and organizational unit structure"
  - "Identity and access management inventory"
  - "Recent security advisories and threat intelligence"
plan:
  - "Step 1: Receive the trigger and capture account, time window, actor, event name, and resource scope."
  - "Step 2: Validate CloudTrail integrity: log file validation enabled and passing; multi-region trail enabled."
  - "Step 3: Identify the actor: IAM user, role, federated identity, or root account; cross-reference with the identity inventory."
  - "Step 4: Identify the resource scope and the sensitivity classification of any affected resource."
  - "Step 5: Reconstruct the action sequence: every API call by the actor in the window, with request parameters and response codes."
  - "Step 6: Correlate with identity activity logs, network flow logs, and security alert feeds."
  - "Step 7: Determine whether the action is benign, anomalous, or malicious; classify severity and open incident if applicable."
  - "Step 8: Capture evidence, document timeline, and feed findings into the security incident response pipeline if escalation is required."
evidence:
  - "CloudTrail event extracts with timestamps and request parameters"
  - "Identity and resource scope cross-reference"
  - "Action sequence timeline"
  - "Correlation with adjacent log sources"
  - "Classification and severity determination"
escalation:
  - "Any root account activity — escalate to Security on-call within 15 minutes."
  - "Confirmed unauthorized access — escalate to Security on-call and follow INCIDENT_COMMUNICATIONS_REVIEW.md."
completion:
  - "Action classified as benign, anomalous, or malicious."
  - "Timeline and evidence captured."
  - "Incident opened if escalation triggered."
exceptions:
  - "Documented break-glass activity with two-person attestation."
related:
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "ACCESS_REVIEW.md"
  - "CLOUD_IAM_PERIODIC_ACCESS_REVIEW.md"
