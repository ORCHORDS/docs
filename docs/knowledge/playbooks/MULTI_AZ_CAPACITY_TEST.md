---
title: "Multi-AZ Capacity Test"
owner: "Reliability Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
trigger: "New service onboarding, capacity change > 25 percent, post-incident capacity finding, or scheduled six-monthly test."
scope: "All production services deployed across multiple availability zones with autoscaling or explicit capacity planning."
inputs:
  - "Service capacity model and scaling thresholds"
  - "Recent peak traffic and projected next six-month peak"
  - "Autoscaling configuration and cooldown values"
  - "Load balancer and DNS configuration"
  - "Cost ceilings for the test"
plan:
  - "Step 1: Confirm scope and document the test plan including target load profile, success criteria, abort criteria, and rollback steps."
  - "Step 2: Synchronize time and synthetic clocks; capture baseline metrics for at least 30 minutes before the test."
  - "Step 3: Inject load using the agreed traffic generator and ramp in stages to the projected peak plus 25 percent headroom."
  - "Step 4: Validate scaling actions occur at thresholds; record scale-out latency and instance warm-up time."
  - "Step 5: Validate error budget consumption, latency distribution, and queue depth at peak."
  - "Step 6: Validate graceful degradation paths — circuit breakers, feature flags, and read-only fallbacks."
  - "Step 7: Validate dashboard, alerting, and paging thresholds behave under load."
  - "Step 8: Ramp down, capture metrics, debrief, and capture residual action items."
evidence:
  - "Test plan with timestamps, targets, and abort criteria"
  - "Capacity and autoscaling configuration exports"
  - "Baseline, peak, and recovery metrics"
  - "Record of scaling events and latencies"
  - "Residual action items with owners and dates"
escalation:
  - "Latency or error budget breach during the test that exceeds the documented abort criterion — halt immediately and escalate to on-call and Service Owner."
  - "Scaling system fails to add capacity within the documented maximum time — escalate to Reliability Engineering leadership."
completion:
  - "Test executed against the planned peak plus headroom."
  - "All success criteria met, or residual actions recorded with owners and dates."
exceptions:
  - "Services without autoscaling must provide a static capacity statement and an alternative load shedding strategy."
related:
  - "CONTINGENCY_EXERCISE.md"
  - "BACKUP_RESTORE_VALIDATION.md"
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
