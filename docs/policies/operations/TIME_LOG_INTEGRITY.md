---
title: "Time and Log Integrity"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Time and Log Integrity

## Purpose

Support trustworthy operational and security timelines without publishing logging topology.

## Requirements

Material systems SHOULD use consistent time sources and preserve enough timestamp context to correlate events.

Security-relevant logs should be protected against inappropriate alteration or deletion according to risk, and access to sensitive logs should be controlled.

## Quality

Logs must not be treated as perfect truth. Clock drift, retries, asynchronous processing, missing events, and collection delays should be considered during investigations.

## Sensitive content

Logging must minimize credentials, secrets, unnecessary personal data, and sensitive payloads.

Related expectations are in [Security Logging and Monitoring](SECURITY_LOGGING_MONITORING.md).
