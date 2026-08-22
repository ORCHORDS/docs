---
title: "Alternate Dependency Strategy"
owner: "Operations Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-23"
review-cycle: "90 days"
next-review: "2026-11-21"
---

# Alternate Dependency Strategy

## Purpose

Reduce resilience risk where a critical dependency has no practical substitute.

## Requirements

For material dependencies, owners SHOULD assess substitution options, switching cost, data portability, contractual constraints, recovery time, manual fallback, and concentration risk.

An alternate does not need to be permanently active, but assumptions about its readiness must be testable.

Where no viable alternate exists, residual risk and compensating measures should be explicit.
