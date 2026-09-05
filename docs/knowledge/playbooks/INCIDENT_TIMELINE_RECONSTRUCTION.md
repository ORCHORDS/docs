---
title: "Incident Timeline Reconstruction"
owner: "Security Operations"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
trigger: "Security incident of medium severity or higher, regulatory investigation, or scheduled reconstruction exercise."
scope: "All confirmed security incidents in ORCHORDS environments."
inputs:
  - "Incident ticket and severity classification"
  - "Log sources: identity, network, application, cloud audit, endpoint detection"
  - "Affected systems inventory and configuration"
  - "Witness and responder statements"
plan:
  - "Step 1: Open a reconstruction workspace and assign a reconstruction lead from Security Operations."
  - "Step 2: Identify all in-scope log sources for the affected systems and time window."
  - "Step 3: Validate log integrity: ensure logs are immutable, signed, and within retention."
  - "Step 4: Anchor the timeline using external indicators: first alert, first responder action, containment timestamp, eradication timestamp."
  - "Step 5: Walk each log source in time order; record actor, action, target, source, and result."
  - "Step 6: Cross-reference between log sources to validate sequence and detect gaps."
  - "Step 7: Identify root cause and contributing factors; record evidence for each factor."
  - "Step 8: Publish the reconstruction report with timeline, root cause, contributing factors, and improvement actions."
evidence:
  - "Reconstruction report with annotated timeline"
  - "Log extracts anchored to the timeline"
  - "Cross-reference matrix between log sources"
  - "Root cause and contributing factor analysis"
  - "Improvement actions with owners and deadlines"
escalation:
  - "Gap in log integrity — escalate to Security leadership and Compliance."
  - "Discrepancy between log sources that cannot be reconciled — escalate to incident commander."
completion:
  - "Reconstruction report signed off by Security Operations and incident commander."
  - "Improvement actions logged with owners and deadlines."
exceptions:
  - "Low-severity incidents reconstructed within the standard post-incident review process."
related:
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "CYBERSECURITY_INCIDENT_RESPONSE.md"
  - "CLOUDTRAIL_INVESTIGATION_PLAYBOOK.md"
