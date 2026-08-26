---
title: "Security Logging and Monitoring"
owner: "Security and Operations Leads"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Logging and Monitoring

## Purpose

Define company-wide expectations for security-relevant logging, monitoring, and
alert handling without disclosing internal telemetry architecture.

## Principles

- Record events needed to investigate material security and operational
  activity.
- Protect logs from unauthorized access and inappropriate modification.
- Synchronize time sufficiently for reliable event correlation.
- Avoid unnecessary secrets or personal data in logs.
- Define retention according to investigation, legal, privacy, operational, and
  cost requirements.
- Alerts should be actionable, owned, severity-aware, and tested.
- Monitoring gaps affecting material risk are tracked like other control gaps.

## Event categories

Depending on risk, useful categories include authentication, authorization,
privileged changes, security-control failures, key/secret events, sensitive
data access, administrative actions, deployment/change events, and incident
signals.

## Review

Monitoring effectiveness is assessed through incident learning, alert quality,
coverage gaps, test exercises, and recurring false-positive/false-negative
patterns.
