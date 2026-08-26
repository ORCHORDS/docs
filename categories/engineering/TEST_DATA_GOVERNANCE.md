---
title: "Test Data Governance"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Test Data Governance

## Purpose

Prevent testing from becoming an uncontrolled copy of production-sensitive information.

## Requirements

Test data SHOULD be synthetic or minimized where practical, classified, access-controlled, retained only as needed, and protected from accidental publication or logging.

Production-derived data requires a justified need and safeguards appropriate to its sensitivity, including de-identification where suitable and validation that de-identification is meaningful for the use.

Tests must not embed reusable credentials, private keys, recovery secrets, or customer-specific sensitive records in public source content.
